from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response
from urllib.parse import unquote
from loguru import logger
from services.km_meta import KMFileMetaService
from services.sharepoint import get_sharepoint_client
import os


router = APIRouter(prefix="/km-portal")

@router.get("/assets")
async def get_assets(offset: int = 0, limit: int = 10, processed_flag: str = "N"):
    """获取 asset 元数据"""
    try:
        meta_service = KMFileMetaService()
        results = await meta_service.retrieve_asset_metadata(offset=offset, limit=limit, processed_flag=processed_flag)


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
        
        # # 2. 获取驱动器信息
        # drive_id = None
        # response = sp_client.get_drives_by_site_id()
        # if response and 'value' in response:
        #     drive = response.get('value')[0] # type: ignore
        #     drive_id = drive.get('id')

        # if not drive_id:
        #     raise HTTPException(status_code=500, detail="获取默认驱动器失败")
        

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

    except Exception as e:
        raise HTTPException(status_code=500, detail=e)

@router.get("/download")
async def download_file(download_url: str):
    """下载文件到内存并返回给浏览器"""
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

        # # 2. 获取驱动器信息
        # drive_id = None
        # response = sp_client.get_drives_by_site_id()
        # if response and 'value' in response:
        #     drive = response.get('value')[0] # type: ignore
        #     drive_id = drive.get('id')

        # if not drive_id:
        #     raise HTTPException(status_code=500, detail="获取默认驱动器失败")
        

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
    
@router.put("/update-asset")
async def update_asset(asset_id: str):
    """更新 Asset 处理状态"""
    try:
        meta_service = KMFileMetaService()
        await meta_service.update_asset_metadata(asset_id, processed_flag="N", sp_file_name="")
        return {"message": "Asset 处理状态更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/reset-processed-flag")
async def reset_processed_flag(offset: int = 0, limit: int = 10):
    """批量重置已处理的 Asset 为未处理状态"""
    try:
        meta_service = KMFileMetaService()
        count = await meta_service.reset_processed_flag(offset=offset, limit=limit)
        return {"message": f"成功重置 {count} 个 Asset 的处理状态", "count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
def _download_all_files_background(local_path: str):
    """后台下载所有文件的任务"""
    try:
        sp_client = get_sharepoint_client()

        # 1. 获取站点信息
        response = sp_client.get_sehub_site()
        site_id = None
        if response and 'id' in response:
            site_id = response.get('id')
        else:
            logger.error("获取 SEHUB 站点失败")
            return

        if not site_id:
            logger.error("站点 ID 为空，无法获取驱动器信息")
            return
        else:
            sp_client.site_id = site_id

        # 获取文件列表
        sp_client.site_id = site_id
        lists = sp_client.get_lists_with_details()
        list_id = None
        for list_info in lists:
            name = list_info.get('name')
            if name == "Shared Documents":
                list_id = list_info.get('id')
                break

        if not list_id:
            logger.error("列表 ID 为空，无法获取列表信息")
            return

        # 获取列表中的所有文件
        items = sp_client.get_list_items(list_id=list_id)
        if not items:
            logger.error("获取文件列表失败")
            return

        documents = sp_client.get_file_list(items)
        success_count = 0
        fail_count = 0

        logger.info(f"开始下载 {len(documents)} 个文件到 {local_path}")

        if documents:
            for document in documents:
                download_url = document['download_url']
                filename = document['name']
                if download_url:
                    try:
                        local_file_path = os.path.join(local_path, filename)
                        result = sp_client.download_file(sharepoint_url=download_url, local_save_path=local_file_path)
                        if not result:
                            logger.error(f"下载文件 {filename} 失败")
                            fail_count += 1
                        else:
                            logger.info(f"下载文件 {filename} 成功")
                            success_count += 1
                    except Exception as e:
                        logger.error(f"下载文件 {filename} 时发生异常: {e}")
                        fail_count += 1

        logger.info(f"下载完成！成功: {success_count}, 失败: {fail_count}, 总计: {len(documents)}")

    except Exception as e:
        logger.error(f"后台下载任务异常: {e}")


@router.get("/download-all")
async def download_all_files(background_tasks: BackgroundTasks, local_path: str):
    """触发后台下载所有文件到指定路径，立即返回"""
    if not local_path:
        raise HTTPException(status_code=400, detail="必须指定保存路径")

    # 添加后台任务
    background_tasks.add_task(_download_all_files_background, local_path)

    return {
        "message": "下载任务已启动，文件将在后台下载完成",
        "local_path": local_path
    }