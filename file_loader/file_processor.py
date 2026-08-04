"""Build and submit one Knowledge Core bundle for each Metadb Asset."""
import asyncio
import hashlib
import json
import mimetypes
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from loguru import logger

from core.config.settings import get_knowledge_core_config
from file_loader.file_params import AssetMeta, AttachmentFailure, DownloadedAttachment
from file_loader.km_meta import KMFileMetaService
from services.knowledge_core import KnowledgeCoreClient, KnowledgeCoreClientError
from services.sharepoint import get_sharepoint_client


class AssetInputError(ValueError):
    """A permanent source/configuration error that requires operator action."""


class FileProcessor:
    """Coordinates SharePoint download, Bundle construction and KC acceptance."""

    def __init__(self):
        self.meta_service = KMFileMetaService()
        self.kc_config = get_knowledge_core_config()
        self.kc_client = KnowledgeCoreClient(self.kc_config)

    async def process_asset(self, item: AssetMeta):
        asset_id = item.asset_id
        try:
            if not item.last_update_time:
                raise AssetInputError("Metadb last_update_time is required as source_revision")

            with tempfile.TemporaryDirectory(prefix=f"km_asset_{self._safe_name(asset_id)}_") as temp_dir:
                attachments, failures = await self._download_attachments(item, Path(temp_dir))
                bundle = self._build_bundle(item)
                idempotency_key = self._idempotency_key(bundle, attachments, failures)
                acceptance = await self.kc_client.accept_km_asset(
                    bundle=bundle,
                    attachments=attachments,
                    failures=failures,
                    idempotency_key=idempotency_key,
                )

            await self.meta_service.update_asset_metadata(
                asset_id, processed_flag="Y", sp_file_name=""
            )
            logger.info(
                "Asset accepted by Knowledge Core: asset_id={}, bundle_id={}, revision_id={}",
                asset_id,
                acceptance.get("bundle_id"),
                acceptance.get("bundle_revision_id"),
            )
        except KnowledgeCoreClientError as exc:
            if exc.retryable:
                logger.warning(
                    "KC temporarily unavailable; keep asset pending: asset_id={}, status={}, code={}",
                    asset_id, exc.status_code, exc.code,
                )
                return
            logger.error(
                "KC permanently rejected asset: asset_id={}, status={}, code={}",
                asset_id, exc.status_code, exc.code,
            )
            await self.meta_service.update_asset_metadata(asset_id, processed_flag="F", sp_file_name="")
        except AssetInputError as exc:
            logger.error("Invalid Asset source data: asset_id={}, reason={}", asset_id, exc)
            await self.meta_service.update_asset_metadata(asset_id, processed_flag="F", sp_file_name="")
        except Exception as exc:
            logger.exception(
                "Unexpected Asset processing failure; keep pending for retry: asset_id={}, type={}",
                asset_id, type(exc).__name__,
            )

    async def _download_attachments(
        self, item: AssetMeta, temp_dir: Path
    ) -> tuple[list[DownloadedAttachment], list[AttachmentFailure]]:
        attachments: list[DownloadedAttachment] = []
        failures: list[AttachmentFailure] = []
        urls = [url.strip() for url in (item.first_sp_url or "").split("^^^") if url.strip()]
        sp_client = get_sharepoint_client()

        for ordinal, source_url in enumerate(urls):
            graph_item = await asyncio.to_thread(sp_client.get_drive_item_metadata, source_url)
            external_document_id, filename, declared_mime_type = self._attachment_identity(
                source_url, graph_item, ordinal
            )
            target_path = temp_dir / f"{ordinal:04d}_{self._safe_name(filename)}"
            try:
                downloaded = await asyncio.to_thread(
                    sp_client.download_file, source_url, str(target_path)
                )
                if not downloaded or not target_path.is_file():
                    raise RuntimeError("sharepoint_download_failed")
                content_sha256, byte_size = await asyncio.to_thread(self._file_digest, target_path)
                attachments.append(
                    DownloadedAttachment(
                        part_name=f"attachment_{ordinal}",
                        external_document_id=external_document_id,
                        source_url=source_url,
                        declared_name=filename,
                        declared_mime_type=declared_mime_type,
                        ordinal=ordinal,
                        file_path=target_path,
                        byte_size=byte_size,
                        content_sha256=content_sha256,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Attachment download failed; report it to KC: asset_id={}, ordinal={}, type={}",
                    item.asset_id, ordinal, type(exc).__name__,
                )
                failures.append(
                    AttachmentFailure(
                        external_document_id=external_document_id,
                        source_url=source_url,
                        declared_name=filename,
                        ordinal=ordinal,
                        failure_code="SOURCE_DOWNLOAD_FAILED",
                    )
                )
        return attachments, failures

    def _build_bundle(self, item: AssetMeta) -> dict[str, Any]:
        title = item.asset_title.strip() if item.asset_title else "Untitled Asset"
        facets = {
            key: value
            for key, value in {
                "product": item.asset_product,
                "sub_type": item.sub_type,
                "industry": item.industry_id,
                "solution": item.asset_solution,
                "language": item.asset_language,
                "asset_type": item.asset_type,
                "content_category": item.content_category,
                "pillar": item.pillar,
                "pillar_category": item.pillar_category,
            }.items()
            if value
        }
        metadata = item.model_dump(mode="json")
        return {
            "source_id": item.asset_id,
            "source_revision": item.last_update_time,
            "title": title,
            "canonical_url": (
                "https://apex.oraclecorp.com/pls/apex/f?p=2018:130:::::P130_ASSET_ID:"
                f"{item.asset_id}"
            ),
            "security_level": self.kc_config.default_security_level,
            "facet": facets,
            "metadata": metadata,
        }

    @staticmethod
    def _idempotency_key(
        bundle: dict[str, Any],
        attachments: list[DownloadedAttachment],
        failures: list[AttachmentFailure],
    ) -> str:
        request_shape = {
            "source_id": bundle["source_id"],
            "source_revision": bundle["source_revision"],
            "attachments": [
                {
                    "external_document_id": item.external_document_id,
                    "ordinal": item.ordinal,
                    "byte_size": item.byte_size,
                    "content_sha256": item.content_sha256,
                }
                for item in attachments
            ],
            "failures": [
                {
                    "external_document_id": item.external_document_id,
                    "ordinal": item.ordinal,
                    "failure_code": item.failure_code,
                }
                for item in failures
            ],
        }
        raw = json.dumps(request_shape, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"km-{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _file_digest(file_path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        byte_size = 0
        with file_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                byte_size += len(chunk)
        return digest.hexdigest(), byte_size

    @staticmethod
    def _external_document_id(source_url: str) -> str:
        parsed = urlsplit(source_url.strip())
        normalized = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), unquote(parsed.path), "", ""))
        return f"urlsha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"

    @classmethod
    def _attachment_identity(
        cls, source_url: str, graph_item: dict[str, Any] | None, ordinal: int
    ) -> tuple[str, str, str]:
        """Prefer Graph DriveItem identity; use a stable URL fallback otherwise."""
        if graph_item:
            item_id = graph_item.get("id")
            drive_id = (graph_item.get("parentReference") or {}).get("driveId")
            if item_id and drive_id:
                filename = graph_item.get("name") or cls._filename_from_url(source_url, ordinal)
                mime_type = (graph_item.get("file") or {}).get("mimeType")
                return (
                    f"driveitem:{drive_id}:{item_id}",
                    filename,
                    mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
                )
        filename = cls._filename_from_url(source_url, ordinal)
        return (
            cls._external_document_id(source_url),
            filename,
            mimetypes.guess_type(filename)[0] or "application/octet-stream",
        )

    @staticmethod
    def _filename_from_url(source_url: str, ordinal: int) -> str:
        parsed = urlsplit(source_url)
        candidate = Path(unquote(parsed.path)).name
        return candidate or f"attachment_{ordinal}"

    @staticmethod
    def _safe_name(value: str) -> str:
        return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)
