from loguru import logger
import io
import json
from weasyprint import HTML

from .file_params import ParserParams, AssetMeta
from clients.parser_client import CallParser
from clients.model_client import CallModel
from services.sharepoint import get_sharepoint_client, SharePointClient
from core.config.settings import get_parser_config, get_llm_config



class FileProcessor:
    """文件处理类，负责文件解析和处理的业务逻辑"""
    def __init__(self):
        self.llm_model = get_llm_config().model_name


    async def process_asset(self, item: AssetMeta):
        """
        处理单个 asset 元数据
        
        参数:
            item: AssetMeta 实例
        """
        asset_id = item.asset_id
        asset_title = item.asset_title
        asset_details = item.asset_details
        solution_briefing = item.solution_briefing
        first_sp_url = item.first_sp_url
        second_sp_url = item.second_sp_url

        original_file_url = f"https://apex.oraclecorp.com/pls/apex/f?p=2018:130:::::P130_ASSET_ID:{asset_id}"
        if first_sp_url:
            file_name, html = await self._download_and_parse_file(first_sp_url)
            await self._upload_file(html, asset_title, asset_details, solution_briefing, original_file_url, file_name)
            logger.info(f"成功处理文件 {first_sp_url}，asset_id: {asset_id}")

        if second_sp_url:
            file_name, html = await self._download_and_parse_file(second_sp_url)
            await self._upload_file(html, asset_title, asset_details, solution_briefing, original_file_url, file_name)
            logger.info(f"成功处理文件 {second_sp_url}，asset_id: {asset_id}")

    def _get_filename_from_response(self, response) -> str:
        """
        从 HTTP 响应头解析文件名 (Content-Disposition)
        """
        content_disposition = response.headers.get('Content-Disposition', '')
        if 'filename=' in content_disposition:
            # 解析类似: attachment; filename="Report.pdf"
            import re
            fname = re.findall('filename="?([^";]+)"?', content_disposition)
            if fname:
                return fname[0]
        return "unknown_file"
    
    async def _download_and_parse_file(self, sp_url: str) -> tuple[str, str]:
        """异步下载并解析 Sharepoint 文件"""
        sp_client = get_sharepoint_client()
        
        # 1. 从 Sharepoint 下载文件到内存 (BytesIO 对象)
        content_io, file_name = sp_client.download_file_to_memory(sp_url)
        if not content_io:
            msg = f"从 Sharepoint 下载文件 {sp_url} 失败"
            logger.error(msg)
            raise Exception(msg)

        # 解析
        html = await CallParser().call_doc_parser_service(
            file_path=file_name,  # type: ignore
            parser_params=self._get_parser_params(),
            file_content=content_io.read(), # BytesIO 转 bytes
            output_format="html"
        )
        
        if not isinstance(html, str):
            msg = f"文件 {file_name} 解析为 HTML 失败，返回值类型为 {type(html)}"
            logger.error(msg)
            raise Exception(msg)
        
        return file_name, html  # type: ignore

    def _get_parser_params(self) -> ParserParams:
        """获取解析参数"""
        parser_config = get_parser_config()
        parser_params = ParserParams(
            chunk_size = parser_config.chunk_size,
            overlap = parser_config.overlap,
            min_chunk_len = parser_config.min_chunk_len,
            generate_picture_images = parser_config.generate_picture_images,
            do_ocr = parser_config.do_ocr,
            ocr_engine = parser_config.ocr_engine,
            images_scale = parser_config.images_scale,
            use_vlm = parser_config.use_vlm
        )
        return parser_params

    def _html_to_pdf(self, html: str) -> bytes:
        """
        将 HTML 内容转换为 PDF 字节流

        参数:
            html: HTML 字符串内容

        返回:
            bytes: PDF 字节流
        """
        try:
            # 使用 BytesIO 捕获 PDF 输出
            pdf_buffer = io.BytesIO()

            # 将 HTML 转换为 PDF
            HTML(string=html).write_pdf(pdf_buffer)

            # 获取 PDF 字节流
            pdf_bytes = pdf_buffer.getvalue()
            pdf_buffer.close()

            logger.info("✅ HTML 转换为 PDF 成功")
            return pdf_bytes

        except Exception as e:
            logger.error(f"❌ HTML 转 PDF 失败: {e}")
            raise Exception(f"HTML 转 PDF 失败: {e}")

    async def _upload_file(self, file_content: str, asset_title: str,
                          asset_details: str, solution_briefing: str,
                          original_file_url: str, file_name: str):
        """上传文件到 Sharepoint"""
        # 1.给 html 增加 asset 元数据
        html = f"""
        <div>
            <p>Asset Title: {asset_title}</p>
            <p>Asset Details: {asset_details}</p>
            <p>Solution Briefing: {solution_briefing}</p>
            <p>Original Asset URL: {original_file_url}</p>
        </div>
        {file_content}
        <div>
            <p>Original Asset URL: {original_file_url}</p>
        </div>
        """
        # 2. 调用 LLM 将内容翻译为英文
        response_str = ""
        async for chunk in CallModel().call_llm_model(
            prompt=f"Prompt: Translate the content of the following document into English. Only translate, do not add any explanations or comments. The output format should be standard HTML. Additionally, determine whether the content contains information such as customer names or company names; if so, desensitize them to 'XX Company'.\n\n{html}",
            model_name=self.llm_model or "gpt-4o-mini",
            temperature=0.0,
            stream=False):
            response_str += chunk

        if not response_str:
            msg = "LLM 翻译响应为空"
            logger.error(msg)
            raise Exception(msg)

        # 解析 OpenAI 标准格式的 JSON 响应并提取内容
        response_data = json.loads(response_str)
        html = response_data["choices"][0]["message"]["content"]
        
        # 3. 将 html 内容转换为 pdf 字节流
        pdf_bytes = self._html_to_pdf(html)

        # 4. 获取 SEHUB 的 SharePoint 客户端
        sp_client = await self._get_sehub_sp_client()
        
        file_ext = file_name.split(".")[-1]
        new_file_name = file_name.replace(f".{file_ext}", ".pdf")

        # 4. 上传 pdf 到 Sharepoint
        sp_client.upload_pdf_string(file_name=new_file_name, file_content=pdf_bytes)
        logger.info(f"成功上传文件 {file_name} 到 Sharepoint")

        # 5. 反写处理标记到数据库
        # await self._update_asset_processed_flag(asset_id, processed=True)

    async def _get_sehub_sp_client(self) -> SharePointClient:
        """获取 SEHUB 的 SharePoint 客户端"""
        sp_client = get_sharepoint_client()
        # 获取 SEHUB 站点 ID
        response = sp_client.get_sehub_site()
        logger.debug(f"获取 SEHUB 站点响应: {response}")
        if response and 'id' in response:
            site_id = response.get('id', None)
            logger.debug(f"SEHUB 站点 ID: {site_id}")
        else:
            logger.error("获取 SEHUB 站点失败")
            raise Exception("获取 SEHUB 站点失败")
        
        if not site_id:
            logger.error("获取 SEHUB 站点 ID 失败")
            raise Exception("获取 SEHUB 站点 ID 失败")
        else:
            sp_client.site_id = site_id
        
        # 获取默认驱动器 ID
        response = sp_client.get_drives_by_site_id()
        logger.debug(f"获取默认驱动器响应: {response}")
        if response and 'value' in response:
            drive = response.get("value")[0] # type: ignore
            drive_id = drive.get("id", None)
            logger.debug(f"默认驱动器 ID: {drive_id}")
        else:
            logger.error("获取默认驱动器失败")
            raise Exception("获取默认驱动器失败")
        
        if not drive_id:
            logger.error("获取默认驱动器 ID 失败")
            raise Exception("获取默认驱动器 ID 失败")
        else:
            sp_client.drive_id = drive_id

        return sp_client
