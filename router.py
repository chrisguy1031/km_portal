from fastapi import APIRouter, HTTPException
from urllib.parse import unquote

from services.km_meta import KMFileMetaService
from services.sharepoint import get_sharepoint_client


router = APIRouter(prefix="/km-portal")

@router.get("/assets")
async def get_assets(offset: int = 0, limit: int = 10):
    """获取 asset 元数据"""
    try:
        meta_service = KMFileMetaService()
        results = await meta_service.retrieve_asset_metadata(offset=offset, limit=limit, processed=False)


        return [{
            "asset_id": result.asset_id,
            "asset_title": result.asset_title,
            "asset_details": result.asset_details,
            "solution_briefing": result.solution_briefing,
            "first_sp_url": unquote(result.first_sp_url) if result.first_sp_url else 'N/A',
            "second_sp_url": unquote(result.second_sp_url) if result.second_sp_url else 'N/A',
        }for result in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=e)
    
@router.get("/uploaded-files")
async def get_uploaded_files():
    """获取已上传的文件"""
    try:
        sp_client = get_sharepoint_client()

        # 1. 获取站点信息
        response = sp_client.get_sehub_site()
        site_id = None
        if response and 'id' in response:
            site_id = response.get('id')
        else:
            raise HTTPException(status_code=500, detail="获取 SEHUB 站点失败")
        
        if not site_id:
            raise HTTPException(status_code=500, detail="站点 ID 为空，无法获取驱动器信息")
        else:
            sp_client.site_id = site_id
        
        # 2. 获取驱动器信息
        drive_id = None
        response = sp_client.get_drives_by_site_id()
        if response and 'value' in response:
            drive = response.get('value')[0] # type: ignore
            drive_id = drive.get('id')

        if not drive_id:
            raise HTTPException(status_code=500, detail="获取默认驱动器失败")
        else:
            sp_client.drive_id = drive_id

        if not drive_id:
            raise HTTPException(status_code=500, detail="驱动器 ID 为空，无法获取列表信息")
        else:
            sp_client.drive_id = drive_id

        # 3. 获取站点列表
        lists = sp_client.get_lists_with_details()
        id = None
        for list_info in lists:
            name = list_info.get('name')
            if name == "Shared Documents":
                id = list_info.get('id')
                break

        if not id:
            raise HTTPException(status_code=500, detail="列表 ID 为空，无法获取列表信息")

        # 4. 获取列表中的所有文件
        items = sp_client.get_list_items(list_id=id)
        if items:
            documents = sp_client.get_file_list(items)
            return documents
        else:
            raise HTTPException(status_code=500, detail="获取文件列表失败")
        
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=e)

@router.get("/download")
async def download_file(download_url: str):
    """下载文件到内存并返回给浏览器"""
    try:
        from fastapi.responses import Response

        sp_client = get_sharepoint_client()

        # 1. 获取站点信息
        response = sp_client.get_sehub_site()
        site_id = None
        if response and 'id' in response:
            site_id = response.get('id')
        else:
            raise HTTPException(status_code=500, detail="获取 SEHUB 站点失败")

        if not site_id:
            raise HTTPException(status_code=500, detail="站点 ID 为空，无法获取驱动器信息")
        else:
            sp_client.site_id = site_id

        # 2. 获取驱动器信息
        drive_id = None
        response = sp_client.get_drives_by_site_id()
        if response and 'value' in response:
            drive = response.get('value')[0] # type: ignore
            drive_id = drive.get('id')

        if not drive_id:
            raise HTTPException(status_code=500, detail="获取默认驱动器失败")
        else:
            sp_client.drive_id = drive_id

        if not drive_id:
            raise HTTPException(status_code=500, detail="驱动器 ID 为空，无法获取列表信息")
        else:
            sp_client.drive_id = drive_id

        # 下载文件到内存
        file_data, filename = sp_client.download_file_to_memory(sharepoint_url=download_url)

        if not file_data:
            raise HTTPException(status_code=500, detail="下载文件失败")

        # 返回文件内容
        return Response(
            content=file_data.getvalue(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))