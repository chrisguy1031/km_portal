import os
import aiohttp
from loguru import logger
from io import BytesIO
from .file_params import UploadMetadata, AssetMeta
from services.sharepoint import get_sharepoint_client
from file_loader.km_meta import KMFileMetaService
from core.config.settings import get_kbot_config


class FileProcessor:
    """文件处理类，负责文件解析和处理的业务逻辑"""
    def __init__(self):
        self.meta_service = KMFileMetaService()

    async def process_asset(self, item: AssetMeta):
        """
        处理单个 asset 元数据
        
        参数:
            item: AssetMeta 实例
        """
        asset_id = item.asset_id
        asset_title = item.asset_title
        asset_product = item.asset_product
        sub_type = item.sub_type
        industry_id = item.industry_id
        asset_solution = item.asset_solution
        asset_details = item.asset_details
        solution_briefing = item.solution_briefing
        first_sp_url = item.first_sp_url
        second_sp_url = item.second_sp_url

        asset_doc = f"## {asset_title}\n\n"
        if asset_solution:
            asset_doc += f"**Solution:** {asset_solution}\n\n"
        if asset_product:
            asset_doc += f"**Product:** {asset_product}\n\n"
        if industry_id:
            asset_doc += f"**Industry:** {industry_id}\n\n"
        if sub_type:
            asset_doc += f"**Type:** {sub_type}\n\n"
        if asset_details:
            asset_doc += f"**Details:** {asset_details}\n\n"
        if solution_briefing:
            asset_doc += f"**Solution Briefing:** {solution_briefing}\n\n"

        asset_doc_name = f"{asset_title}.md" # 上传的 Asset 文档文件名

        # 原始 Asset 链接
        original_asset_url = f"https://apex.oraclecorp.com/pls/apex/f?p=2018:130:::::P130_ASSET_ID:{asset_id}"
        
        # 构建上传元数据
        upload_metadata = UploadMetadata(
            asset_id=asset_id,
            original_asset_url=original_asset_url,
            asset_title=asset_title,
            asset_product=asset_product,
            sub_type=sub_type,
            industry_id=industry_id,
            first_sp_url=first_sp_url,
            second_sp_url=second_sp_url,
        ).to_dict()
        
        
        # 从 SharePoint 下载附件
        try:
            # 有第一个附件
            if first_sp_url:
                try:
                    file_io, file_name = await self._download_file(first_sp_url)
                    if not file_io:
                        raise Exception("下载的文件为空")
                    if not file_name:
                        file_name = f"{asset_title}_sp1.html"
                    await self._upload_file(file_io, file_name, upload_metadata)
                    logger.info(f"成功处理文件 {first_sp_url}，asset_id: {asset_id}")

                except Exception as e:
                    logger.error(f"处理文件 {first_sp_url} 时发生错误: {e}")
                    first_result = False

            # 有第二个附件
            if second_sp_url:
                try:
                    file_io, file_name = await self._download_file(second_sp_url)
                    if not file_io:
                        raise Exception("下载的文件为空")
                    if not file_name:
                        file_name = f"{asset_title}_sp2.html"
                    await self._upload_file(file_io, file_name, upload_metadata)
                    logger.info(f"成功处理文件 {second_sp_url}，asset_id: {asset_id}")

                except Exception as e:
                    logger.error(f"处理文件 {second_sp_url} 时发生错误: {e}")
                    second_result = False

            # 没有附件
            if not first_sp_url and not second_sp_url:
                logger.warning(f"Asset {asset_id} 没有附件，跳过附件处理")
            
            # 上传 asset 文档
            await self._upload_file(BytesIO(asset_doc.encode()), asset_doc_name, upload_metadata)
            
            # 更新 asset 元数据为已处理
            await self.meta_service.update_asset_metadata(asset_id, processed_flag="Y", sp_file_name="")

            logger.info(f"Asset {asset_id} 处理完成")
        except Exception as e:
            logger.error(f"处理 Asset {asset_id} 时发生错误: {e}")
            # 更新 Asset 元数据为处理失败
            await self.meta_service.update_asset_metadata(asset_id, processed_flag="F", sp_file_name="")

    
    async def _download_file(self, sp_url: str) -> tuple[BytesIO, str]:
        """异步下载 Sharepoint 文件"""
        sp_client = get_sharepoint_client()
        
        # 1. 从 Sharepoint 下载文件到内存 (BytesIO 对象)
        try:
            content_io, file_name = sp_client.download_file_to_memory(sp_url)
        except Exception as e:
            logger.error(f"从 Sharepoint 下载文件 {sp_url} 失败: {e}")
            return BytesIO(), ""
        
        if not content_io:
            logger.error(f"从 Sharepoint 下载文件 {sp_url} 失败")
            return BytesIO(), "" # 未下载到文件，返回空二进制流

        if not file_name:
            logger.error(f"从 Sharepoint 下载文件 {sp_url} 失败，文件名为空")
            return BytesIO(), ""
        
        return content_io, file_name

    async def _upload_file(self, file_io: BytesIO, file_name: str, metadata: dict) -> bool:
        """上传文件到 Sharepoint"""
        # 1. 构建上传请求数据
        app_id = get_kbot_config().app_id
        domain_id = get_kbot_config().domain_id
        kb_id = get_kbot_config().kb_id
        batch_id = get_kbot_config().batch_id
        payload = {
            "app_id": app_id,
            "domain_id": domain_id,
            "kb_id": kb_id,
            "batch_id": batch_id,
            "batch_name": "km_portal",
            "overwrite": False,
            "skip_approval": True,
            "biz_metadata": metadata
        }

        # 2. 调用 KBot 接口上传文件
        timeout = aiohttp.ClientTimeout(total=30)
        url = get_kbot_config().upload_api_url
        headers = {"Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        raise Exception(f"上传文件失败，状态码: {response.status}")
                    return True
        except Exception as e:
            logger.error(f"上传文件到 KBot 失败: {e}")
            return False
