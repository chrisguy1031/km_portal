import json
import os
import uuid
import aiohttp
from urllib.parse import unquote
from loguru import logger
from io import BytesIO
from fastapi import UploadFile
from .file_params import AssetMeta
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
        """
        # 1. 结构化元数据提取
        # 使用 item.__dict__ 或直接引用 item 属性，减少 10 行冗余赋值
        asset_id = item.asset_id
        asset_title = item.asset_title or "Untitled_Asset"
        
        # 2. 巧妙构建 Markdown 文档
        # 使用列表推导式过滤空值，不仅代码简洁，性能也更好
        fields = {
            "Solution": item.asset_solution,
            "Product": item.asset_product,
            "Industry": item.industry_id,
            "Type": item.sub_type,
            "Details": item.asset_details,
            "Solution Briefing": item.solution_briefing
        }
        header = f"## {asset_title}\n\n"
        body = "\n\n".join([f"**{k}:** {v}" for k, v in fields.items() if v])
        asset_doc = header + body

        # 3. 构建上传元数据字典
        upload_metadata = {
            **{k: v for k, v in item.__dict__.items() if not k.startswith('_')},
            "original_asset_url": f"https://apex.oraclecorp.com/pls/apex/f?p=2018:130:::::P130_ASSET_ID:{asset_id}"
        }

        try:
            # 4. 循环处理多个 SharePoint URL
            raw_urls = item.first_sp_url.split('^^^') if item.first_sp_url else []
            # 过滤掉空字符串并去除首尾空格
            valid_urls = [u.strip() for u in raw_urls if u and u.strip()]
            
            has_attachments = False
            
            # 循环处理解析出来的每一个 URL
            for index, url in enumerate(valid_urls, start=1):
                has_attachments = True
                try:
                    # 构造默认文件名，例如 asset_title_1.html, asset_title_2.html
                    default_name = f"{asset_title}_{index}.html"
                    
                    file_io, file_name = await self._download_file(url)
                    # 优先使用下载时获取的文件名，否则使用生成的默认名
                    await self._upload_file(file_io, file_name or default_name, upload_metadata)
                    
                    logger.info(f"成功处理文件 {index}: {url}，asset_id: {asset_id}")
                except Exception as e:
                    logger.error(f"处理第 {index} 个文件 {url} 失败: {e}")
                    raise e

            if not has_attachments:
                logger.warning(f"Asset {asset_id} 没有附件，跳过附件处理")

            # 5. 上传生成的 Markdown 文档
            await self._upload_file(BytesIO(asset_doc.encode()), f"{asset_title}.md", upload_metadata)

            # 6. 更新状态
            await self.meta_service.update_asset_metadata(asset_id, processed_flag="Y", sp_file_name="")
            logger.info(f"Asset {asset_id} 处理完成")

        except Exception as e:
            logger.error(f"处理 Asset {asset_id} 关键流程出错: {e}")
            await self.meta_service.update_asset_metadata(asset_id, processed_flag="F", sp_file_name="")

    
    async def _download_file(self, sp_url: str) -> tuple[BytesIO, str]:
        """异步下载 Sharepoint 文件"""
        sp_client = get_sharepoint_client()
        
        # 1. 从 Sharepoint 下载文件到内存 (BytesIO 对象)
        try:
            content_io, file_name = sp_client.download_file_to_memory(sp_url)

            if not content_io:
                raise ValueError(f"下载文件为空: {sp_url}")

            file_name = unquote(file_name)

        except Exception as e:
            logger.error(f"从 Sharepoint 下载文件 {sp_url} 失败: {e}")
            raise e
        
        return content_io, file_name

    async def _upload_file(self, file_io: BytesIO, file_name: str, metadata: dict):
        """上传文件到 Sharepoint"""
        config = get_kbot_config()
        upload_key = os.getenv("KBOT_API_KEY")
    
        # 1. 构造整体的 Metadata JSON 字符串
        full_metadata_dict = {
            "app_id": config.app_id,
            "domain_id": config.domain_id,
            "kb_id": config.kb_id,
            "batch_id": config.batch_id,
            "batch_name": "km_portal",
            "overwrite": False,
            "skip_approval": True,
            "biz_metadata": metadata  # 传入的业务元数据作为 biz_metadata 字段
        }

        data = aiohttp.FormData()
        data.add_field("metadata", json.dumps(full_metadata_dict))

        # 2. 关键：将 BytesIO 包装为文件上传
        # 确保指针在开头
        file_io.seek(0)
        data.add_field(
            'files',           # 对应 FastAPI 接口中的参数名
            file_io, 
            filename=file_name, 
            content_type='application/octet-stream'
        )

        headers = {
            "Authorization": f"Bearer {upload_key}"
        }

        # 3. 发送请求
        timeout = aiohttp.ClientTimeout(total=60)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(config.upload_api_url, data=data, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"状态码: {response.status}, 详情: {error_text}")
                    
                    logger.info(f"文件 {file_name} 上传成功")
        except Exception as e:
            logger.error(f"上传文件到 KBot 失败: {e}")
            raise e
