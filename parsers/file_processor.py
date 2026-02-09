from loguru import logger
import io
import os
import json
from weasyprint import HTML
from urllib.parse import unquote
from .file_params import ParserParams, AssetMeta
from clients.parser_client import CallParser
from clients.model_client import CallModel
from services.sharepoint import get_sharepoint_client, SharePointClient
from services.km_meta import KMFileMetaService
from core.config.settings import get_parser_config, get_llm_config



class FileProcessor:
    """文件处理类，负责文件解析和处理的业务逻辑"""
    def __init__(self):
        self.llm_model = get_llm_config().model_name
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

        original_file_url = f"https://apex.oraclecorp.com/pls/apex/f?p=2018:130:::::P130_ASSET_ID:{asset_id}"
        try:
            first_result = True
            second_result = True
            if first_sp_url:
                try:
                    file_name, html = await self._download_and_parse_file(first_sp_url)
                    await self._upload_file(html, asset_title, asset_product, sub_type, industry_id,
                                            asset_details, asset_solution, solution_briefing, original_file_url, file_name)
                    logger.info(f"成功处理文件 {first_sp_url}，asset_id: {asset_id}")

                except Exception as e:
                    logger.error(f"处理文件 {first_sp_url} 时发生错误: {e}")
                    first_result = False

            if second_sp_url:
                try:
                    file_name, html = await self._download_and_parse_file(second_sp_url)
                    await self._upload_file(html, asset_title,  asset_product, sub_type, industry_id,
                                            asset_details, asset_solution, solution_briefing, original_file_url, file_name)
                    logger.info(f"成功处理文件 {second_sp_url}，asset_id: {asset_id}")
                except Exception as e:
                    logger.error(f"处理文件 {second_sp_url} 时发生错误: {e}")
                    second_result = False

            if not first_sp_url and not second_sp_url:
                logger.warning(f"asset {asset_id} 没有有效文件 URL")
                # 更新 asset 元数据为处理失败
                await self._upload_file("", asset_title,  asset_product, sub_type, industry_id,
                                        asset_details, asset_solution, solution_briefing, original_file_url, f"asset_{asset_id[:6]}_no_file.html")
            
            # 更新 asset 元数据为已处理
            if first_result or second_result:
                await self.meta_service.update_asset_metadata(asset_id, processed_flag="Y")
            else:
                await self.meta_service.update_asset_metadata(asset_id, processed_flag="F")

            logger.info(f"asset {asset_id} 处理完成")
        except Exception as e:
            logger.error(f"处理 asset {asset_id} 时发生错误: {e}")
            # 更新 asset 元数据为处理失败
            await self.meta_service.update_asset_metadata(asset_id, processed_flag="F")

    
    async def _download_and_parse_file(self, sp_url: str) -> tuple[str, str]:
        """异步下载并解析 Sharepoint 文件"""
        sp_client = get_sharepoint_client()
        
        # 1. 从 Sharepoint 下载文件到内存 (BytesIO 对象)
        content_io, file_name = sp_client.download_file_to_memory(sp_url)
        if not content_io:
            msg = f"从 Sharepoint 下载文件 {sp_url} 失败"
            logger.error(msg)
            raise Exception(msg)

        # 2. 获取文件扩展名
        if not file_name:
            raise Exception(f"从 Sharepoint 下载文件 {sp_url} 失败，文件名为空")
        file_ext = os.path.splitext(file_name)[1]

        if file_ext not in [".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".html", ".xhtml", ".md", ".asciidoc", ".csv", ".png", ".jpeg", ".tiff", ".bmp", ".webp", ".wav", ".mp3", ".vtt"]:
            logger.error(f"文件 {file_name} 不是支持的文件类型 {file_ext}")
            return file_name, ""

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
        
        return file_name, html

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

    async def _upload_file(self, file_content: str, asset_title: str, asset_product: str, 
                           sub_type: str, industry_id: str, asset_details: str, asset_solution: str,
                           solution_briefing: str, original_file_url: str, file_name: str):
        """上传文件到 Sharepoint"""
        # 1.给 html 增加 asset 元数据
        html = f"""
        <div>
            <div>
                <span style="font-size: 1.2rem;">Original Asset URL: </span>
                <a href="{original_file_url}" style="color: #31c0ff;font-size: 1.2rem;text-decoration: underline;">{original_file_url}</a>
                <span style="color: red;"> (VPN Required)</span>
            </div>
            <h2>{asset_title}</h2>
            <p>Asset Product: {asset_product}</p>
            <p>Sub Type: {sub_type}</p>
            <p>Industry ID: {industry_id}</p>
            <p>Asset Solution:</p>
            <p>{asset_solution}</p>
            <p>Asset Details:</p>
            <p>{asset_details}</p>
            <p>Solution Briefing:</p>
            <p>{solution_briefing}</p>
        </div>
        {file_content}
        <div>
            <span style="font-size: 1.2rem;">Original Asset URL: </span>
            <a href="{original_file_url}" style="color: #31c0ff;font-size: 1.2rem;text-decoration: underline;">{original_file_url}</a>
            <span style="color: red;"> (VPN Required)</span>
        </div>
        """
        # 2. 调用 LLM 将内容翻译为英文
        response_str = ""
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "configuration", "translate.txt")
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_content = f.read().strip()
        except Exception as e:
            logger.error(f"读取 translate.txt 失败: {e}")
            prompt_content = f"""请将以下HTML内容进行英文翻译，并严格按照以下要求执行：

**核心任务：**
1. **完整翻译** - 将文档内容全部翻译成自然、专业的英文
2. **格式保持** - 保持原有HTML标签结构不变，输出标准格式的HTML文档
3. **仅翻译，不解释** - 只输出翻译后的HTML，不要添加任何解释、评论或额外说明

**脱敏规则：**
- **需要脱敏的信息**：
  - 客户姓名（如：张三 → XX Customer）
  - 公司名称（当作为客户时，如：ABC科技有限公司 → XX Company）
- **不需要脱敏的信息**：
  - 产品名称中的公司名（如：Oracle数据库 → Oracle Database）
  - 通用技术术语（如：微软Windows系统 → Microsoft Windows System）
  - 公开的知名品牌和产品
  
**具体执行：**
1. 翻译优先级高于脱敏
2. 保持HTML标签的完整性和属性不变
3. 脱敏时使用中性替代词：
   - 客户姓名 → "XX Customer"
   - 公司名称 → "XX Company"
4. 上下文判断：只有明确作为客户或敏感实体的名称才脱敏

**输出要求：**
- 只输出翻译完成且经过脱敏处理的完整HTML代码
- 不要包含任何元说明，如"以下是翻译结果："等
- 确保HTML格式规范，可直接在浏览器中渲染

需要处理的HTML内容: {html}

请开始翻译并脱敏。"""

        async for chunk in CallModel().call_llm_model(
            prompt=prompt_content,
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
        # pdf_bytes = self._html_to_pdf(html)

        # 4. 获取 SEHUB 的 SharePoint 客户端
        sp_client, drive_id = await self._get_sehub_sp_client()

        # URL 解码文件名
        decoded_file_name = unquote(file_name)

        file_ext = decoded_file_name.split(".")[-1]
        new_file_name = decoded_file_name.replace(f".{file_ext}", ".pdf")

        # 4. 上传 pdf 到 Sharepoint
        sp_client.upload_file_string(file_name=new_file_name, drive_id=drive_id, file_content=html) # 如果需要转换为pdf，则使用 pdf_bytes
        logger.info(f"成功上传文件 {file_name} 到 Sharepoint")

    async def _get_sehub_sp_client(self) -> tuple[SharePointClient, str]:
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

        # 获取 SEHUB 的 drive id
        drives = sp_client.get_drives_by_site_id()
        if drives and 'value' in drives:
            drive = drives.get('value')[0] # type: ignore
            drive_id = drive.get('id')
        else:
            logger.error("获取 SEHUB 的 drive id 失败")
            raise Exception("获取 SEHUB 的 drive id 失败")
        
        return sp_client, drive_id
