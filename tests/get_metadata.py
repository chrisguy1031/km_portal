import sys
import asyncio
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv
load_dotenv()

# Add both project root and backend directory to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Use absolute imports from project root
from file_loader.km_meta import KMFileMetaService
from services.sharepoint import get_sharepoint_client
from parsers.file_processor import FileProcessor


class TestFileProcessor:

    async def _get_file_meta(self):
        meta_service = KMFileMetaService()
        results = await meta_service.retrieve_asset_metadata(offset=0, limit=1)
        for result in results:
            # 打印每个 asset 的详细信息
            asset_id = result.asset_id
            print(f"Asset ID: {asset_id}")
            asset_title = result.asset_title
            print(f"Asset Title: {asset_title}")
            first_sp_url = result.first_sp_url
            second_sp_url = result.second_sp_url
            print("")
            print(f"First Sharepoint URL: {unquote(first_sp_url) if first_sp_url else 'N/A'}")
            print("")
            print(f"Second Sharepoint URL: {unquote(second_sp_url) if second_sp_url else 'N/A'}")
            print("")
            print("-"*50)
        
        return results[0]

    async def test_parse_file(self):
        file_processor = FileProcessor()
        file = await self._get_file_meta()
        await file_processor.process_asset(file)
        print("Successfully parsed file:", file.asset_id)

if __name__ == "__main__":
    asyncio.run(TestFileProcessor().test_parse_file())