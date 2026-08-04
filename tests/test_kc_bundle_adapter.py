"""Focused unit checks for the KM Portal → Knowledge Core V2 adapter."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import web

from core.config.settings import KnowledgeCoreConfig
from file_loader.file_params import AssetMeta, AttachmentFailure, DownloadedAttachment
from file_loader.file_processor import FileProcessor
from services.knowledge_core import KnowledgeCoreClient, KnowledgeCoreClientError


class KnowledgeCoreBundleAdapterTest(unittest.TestCase):
    def setUp(self):
        self.asset = AssetMeta(
            asset_id="A-10086",
            asset_title="Asset title",
            asset_product="Database",
            sub_type="Reference",
            industry_id="Retail",
            asset_solution="AIOps",
            asset_details="Details",
            solution_briefing="Briefing",
            last_update_time="2026-07-22T10:15:00Z",
            first_sp_url="",
            asset_language="en",
        )
        self.processor = object.__new__(FileProcessor)
        self.processor.kc_config = SimpleNamespace(default_security_level=2)

    def test_bundle_keeps_asset_metadata_for_kc_manifest(self):
        bundle = self.processor._build_bundle(self.asset)

        self.assertEqual("A-10086", bundle["source_id"])
        self.assertEqual("2026-07-22T10:15:00Z", bundle["source_revision"])
        self.assertEqual("Briefing", bundle["metadata"]["solution_briefing"])
        self.assertEqual("AIOps", bundle["facet"]["solution"])
        self.assertEqual(2, bundle["security_level"])

    def test_idempotency_key_is_stable_for_same_bundle_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "attachment.pdf"
            file_path.write_bytes(b"content")
            attachment = DownloadedAttachment(
                part_name="attachment_0",
                external_document_id="urlsha256:abc",
                source_url="https://example.test/file.pdf?token=temporary",
                declared_name="file.pdf",
                declared_mime_type="application/pdf",
                ordinal=0,
                file_path=file_path,
                byte_size=7,
                content_sha256="hash",
            )
            failure = AttachmentFailure(
                external_document_id="urlsha256:def",
                source_url="https://example.test/missing.pdf",
                ordinal=1,
                failure_code="SOURCE_DOWNLOAD_FAILED",
            )
            bundle = self.processor._build_bundle(self.asset)

            first = FileProcessor._idempotency_key(bundle, [attachment], [failure])
            second = FileProcessor._idempotency_key(bundle, [attachment], [failure])

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("km-"))

    def test_external_document_id_ignores_temporary_query_string(self):
        first = FileProcessor._external_document_id("https://EXAMPLE.test/a%20file.pdf?token=one")
        second = FileProcessor._external_document_id("https://example.test/a%20file.pdf?token=two")

        self.assertEqual(first, second)

    def test_drive_item_identity_is_preferred_over_url_fallback(self):
        external_id, filename, mime_type = FileProcessor._attachment_identity(
            "https://example.test/Doc.aspx?token=temporary",
            {
                "id": "item-42",
                "name": "architecture.pdf",
                "file": {"mimeType": "application/pdf"},
                "parentReference": {"driveId": "drive-7"},
            },
            0,
        )

        self.assertEqual("driveitem:drive-7:item-42", external_id)
        self.assertEqual("architecture.pdf", filename)
        self.assertEqual("application/pdf", mime_type)


class KnowledgeCoreClientContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.received = {}
        self.app = web.Application()
        self.app.router.add_post(
            "/api/v2/knowledge/domains/1/collections/assets/ingestions/km-assets",
            self._accept,
        )
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        port = self.site._server.sockets[0].getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        self.previous_internal_token = os.environ.get("KBOT_INTERNAL_SERVICE_TOKEN")
        os.environ["KBOT_INTERNAL_SERVICE_TOKEN"] = "test-token"

    async def asyncTearDown(self):
        if self.previous_internal_token is None:
            os.environ.pop("KBOT_INTERNAL_SERVICE_TOKEN", None)
        else:
            os.environ["KBOT_INTERNAL_SERVICE_TOKEN"] = self.previous_internal_token
        await self.runner.cleanup()

    async def _accept(self, request):
        self.received["internal_token"] = request.headers.get("X-KBot-Internal-Token")
        self.received["idempotency_key"] = request.headers.get("Idempotency-Key")
        multipart = await request.multipart()
        while part := await multipart.next():
            self.received[part.name] = await part.read(decode=False)
        return web.json_response({"bundle_id": 101, "bundle_revision_id": 301}, status=202)

    async def test_client_posts_one_bundle_with_all_attachment_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "architecture.pdf"
            file_path.write_bytes(b"PDF")
            client = KnowledgeCoreClient(
                KnowledgeCoreConfig(base_url=self.base_url, domain_id=1, collection_key="assets")
            )
            result = await client.accept_km_asset(
                bundle={"source_id": "A-1", "source_revision": "v1", "title": "Asset"},
                attachments=[
                    DownloadedAttachment(
                        part_name="attachment_0",
                        external_document_id="driveitem:drive:item",
                        source_url="https://example.test/architecture.pdf",
                        declared_name="architecture.pdf",
                        declared_mime_type="application/pdf",
                        ordinal=0,
                        file_path=file_path,
                        byte_size=3,
                        content_sha256="hash",
                    )
                ],
                failures=[
                    AttachmentFailure(
                        external_document_id="urlsha256:missing",
                        source_url="https://example.test/missing.pdf",
                        ordinal=1,
                        failure_code="SOURCE_DOWNLOAD_FAILED",
                    )
                ],
                idempotency_key="km-test-key",
            )

        self.assertEqual(101, result["bundle_id"])
        self.assertEqual("test-token", self.received["internal_token"])
        self.assertEqual("km-test-key", self.received["idempotency_key"])
        self.assertEqual(b"PDF", self.received["attachment_0"])
        self.assertIn(b'"source_id": "A-1"', self.received["bundle"])
        self.assertIn(b'"part_name": "attachment_0"', self.received["documents"])
        self.assertIn(b"SOURCE_DOWNLOAD_FAILED", self.received["document_failures"])


class FileProcessorAcceptanceBehaviorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.asset = AssetMeta(
            asset_id="A-10086",
            asset_title="Asset title",
            asset_product="Database",
            sub_type="Reference",
            industry_id="Retail",
            asset_solution="AIOps",
            asset_details="Details",
            solution_briefing="Briefing",
            last_update_time="2026-07-22T10:15:00Z",
        )
        self.processor = object.__new__(FileProcessor)
        self.processor.kc_config = SimpleNamespace(default_security_level=1)
        self.processor.meta_service = SimpleNamespace(update_asset_metadata=AsyncMock())
        self.processor._download_attachments = AsyncMock(return_value=([], [
            AttachmentFailure(
                external_document_id="urlsha256:missing",
                source_url="https://example.test/missing.pdf",
                ordinal=0,
                failure_code="SOURCE_DOWNLOAD_FAILED",
            )
        ]))

    async def test_accepts_asset_with_download_failure_and_marks_processed(self):
        self.processor.kc_client = SimpleNamespace(
            accept_km_asset=AsyncMock(return_value={"bundle_id": 101, "bundle_revision_id": 301})
        )

        await self.processor.process_asset(self.asset)

        self.processor.kc_client.accept_km_asset.assert_awaited_once()
        self.processor.meta_service.update_asset_metadata.assert_awaited_once_with(
            "A-10086", processed_flag="Y", sp_file_name=""
        )
        failures = self.processor.kc_client.accept_km_asset.await_args.kwargs["failures"]
        self.assertEqual("SOURCE_DOWNLOAD_FAILED", failures[0].failure_code)

    async def test_retryable_kc_failure_keeps_asset_pending(self):
        self.processor.kc_client = SimpleNamespace(
            accept_km_asset=AsyncMock(side_effect=KnowledgeCoreClientError("timeout", retryable=True))
        )

        await self.processor.process_asset(self.asset)

        self.processor.meta_service.update_asset_metadata.assert_not_awaited()

    async def test_permanent_kc_failure_marks_asset_failed(self):
        self.processor.kc_client = SimpleNamespace(
            accept_km_asset=AsyncMock(
                side_effect=KnowledgeCoreClientError("invalid bundle", status_code=422, retryable=False)
            )
        )

        await self.processor.process_asset(self.asset)

        self.processor.meta_service.update_asset_metadata.assert_awaited_once_with(
            "A-10086", processed_flag="F", sp_file_name=""
        )


if __name__ == "__main__":
    unittest.main()
