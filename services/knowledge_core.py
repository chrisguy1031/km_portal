"""Knowledge Core V2 Bundle ingestion client."""
import json
import os
from typing import Any

import aiohttp

from core.config.settings import KnowledgeCoreConfig
from file_loader.file_params import AttachmentFailure, DownloadedAttachment


class KnowledgeCoreClientError(Exception):
    """A sanitized KC API error with a retry classification."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 code: str | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.retryable = retryable


class KnowledgeCoreClient:
    """Posts one complete KM Asset bundle to the KC V2 intake endpoint."""

    def __init__(self, config: KnowledgeCoreConfig):
        self.config = config

    @property
    def intake_url(self) -> str:
        base_url = self.config.base_url.rstrip("/")
        return (
            f"{base_url}/api/v2/knowledge/domains/{self.config.domain_id}"
            f"/collections/{self.config.collection_key}/ingestions/km-assets"
        )

    async def accept_km_asset(
        self,
        *,
        bundle: dict[str, Any],
        attachments: list[DownloadedAttachment],
        failures: list[AttachmentFailure],
        idempotency_key: str,
    ) -> dict[str, Any]:
        form = aiohttp.FormData()
        form.add_field("bundle", json.dumps(bundle), content_type="application/json")
        documents = [
            {
                "part_name": attachment.part_name,
                "external_document_id": attachment.external_document_id,
                "role": "ATTACHMENT",
                "source_url": attachment.source_url,
                "declared_name": attachment.declared_name,
                "declared_mime_type": attachment.declared_mime_type,
                "ordinal": attachment.ordinal,
                "required_flag": attachment.required_flag,
                "byte_size": attachment.byte_size,
                "content_sha256": attachment.content_sha256,
            }
            for attachment in attachments
        ]
        form.add_field("documents", json.dumps(documents), content_type="application/json")
        form.add_field(
            "document_failures",
            json.dumps([failure.model_dump() for failure in failures]),
            content_type="application/json",
        )

        opened_files = []
        try:
            for attachment in attachments:
                file_handle = attachment.file_path.open("rb")
                opened_files.append(file_handle)
                form.add_field(
                    attachment.part_name,
                    file_handle,
                    filename=attachment.declared_name,
                    content_type=attachment.declared_mime_type,
                )

            internal_token = os.getenv("KBOT_INTERNAL_SERVICE_TOKEN")
            if not internal_token:
                raise KnowledgeCoreClientError(
                    "KBOT_INTERNAL_SERVICE_TOKEN is not configured", retryable=False
                )
            timeout = aiohttp.ClientTimeout(
                connect=self.config.connect_timeout_seconds,
                total=self.config.request_timeout_seconds,
            )
            headers = {
                "X-KBot-Internal-Token": internal_token,
                "X-KBot-Actor-Id": "svc:km-portal",
                "Idempotency-Key": idempotency_key,
            }
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.intake_url, data=form, headers=headers) as response:
                    body = await self._read_json(response)
                    if response.status == 202:
                        return body
                    code = body.get("code") if isinstance(body, dict) else None
                    retryable = response.status in {408, 429} or response.status >= 500
                    raise KnowledgeCoreClientError(
                        f"KC intake rejected request: status={response.status}, code={code or 'unknown'}",
                        status_code=response.status,
                        code=code,
                        retryable=retryable,
                    )
        except aiohttp.ClientError as exc:
            raise KnowledgeCoreClientError(
                f"KC intake request failed: {type(exc).__name__}", retryable=True
            ) from exc
        finally:
            for file_handle in opened_files:
                file_handle.close()

    @staticmethod
    async def _read_json(response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            body = await response.json(content_type=None)
        except (aiohttp.ContentTypeError, json.JSONDecodeError):
            return {}
        return body if isinstance(body, dict) else {}
