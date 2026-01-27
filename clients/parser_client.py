"""文档解析微服务调用类。

集成文档解析微服务的远程调用逻辑。
"""
import os
import aiohttp
from loguru import logger
from parsers.file_params import ParserParams

from core.config.settings import get_parser_config
from parsers.txt_to_md import TxtToMarkdownParser


class CallParser:
    """文档解析微服务调用类。"""

    def __init__(self):
        """初始化配置。"""
        self.parser_config = get_parser_config()
        # self.prompt_service = PromptService()

    async def call_doc_parser_service(
        self, 
        file_path: str,
        parser_params: ParserParams,
        file_content: str | bytes | None = None,
        output_format: str = "chunks"
    ) -> str | list[dict]:
        """调用文档解析微服务。

        Args:
            file_path: 待上传的本地文件路径。
            parser_params: 解析参数对象。
            file_content: 待解析的文件内容，如果有则表示直接解析内容，否则从文件路径读取。
            output_format: 输出格式 (markdown, html, json, chunks)。

        Returns:
            str | list[dict]: 解析结果。
        """
        service_host = self.parser_config.service_host
        service_port = self.parser_config.service_port
        
        # 超时设置
        total_timeout = self.parser_config.timeout
        timeout = aiohttp.ClientTimeout(total=total_timeout)
        
        url = f"http://{service_host}:{service_port}/v1/parse/file"

        # 1. 构造 Multipart 报文
        data = aiohttp.FormData()

        # 处理文件内容
        if file_path.endswith(".txt"):
            # 因为docling不支持直接解析txt文件，所以先转换为md
            file_content = TxtToMarkdownParser().process(file_path)
            file_path = file_path.replace(".txt", ".md")

        # 获取 VLM 提示词
        prompt_content = None

        if parser_params.use_vlm:
            prompt_path = os.path.join(os.path.dirname(__file__), "..", "configuration", "prompt.txt")
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt_content = f.read().strip()
            except Exception as e:
                logger.error(f"读取 prompt.txt 失败: {e}")
                prompt_content = None

        if not prompt_content:
            prompt_content = """你是一个高效的文档图片信息提取助手。请从用户提供的文档图片中，识别并分析其中的所有图片（包括嵌入的文字截图、图标、示意图、流程图、表格截图等）。这些图片来自美化过的PPT或PDF，常含有大量装饰性元素。 
请按以下要求执行：
 1. 【识别类型】判断每张图片的类型： 
    - 文字类：包含标题、要点、段落（如PPT文本框截图） 
    - 图标类：象征性图形（如箭头、勾号、人物、齿轮、云朵等）→ 忽略不提取 
    - 图表类：柱状图、饼图、折线图等数据可视化的图表 
    - 结构类：流程图、架构图等 - 表格类：带行列结构的数据表 
    - 装饰类：纯色块、渐变、线条、无意义背景图 → 忽略不提取 
    - 其他：照片、插图等 → 忽略不提取 
2. 【内容提取】仅提取有语义价值的内容： 
    - 文字类：提取出完整的文本内容 
    - 图标类：忽略不提取，只留下说明文字：忽略的图标 
    - 图表类：折线图，饼状图等，描述出图表内容和要表达的含义，如上升下降趋势，占比百分之几等内容 
    - 结构类：提取出完整的流程/架构，使大模型能根据描述文字轻易还原流程/架构
    - 表格类：提取完整表格，保持表格格式，内容不错位 
    - 装饰类：忽略不提取图片，只留下文字：忽略的装饰图 
    - 其他：忽略不提取，只留下文字：忽略的插图 
3. 【输出格式】（严格按此JSON数组格式）： [ { 
"类型": "文字|图标|图表|结构|表格|装饰|其他", 
"内容": "实际提取的图片内容" }, ... ] 
注意：只输出JSON数组，不要额外说明，输出语言为英文。若无有效图片，返回空数组 []。"""


        # 填充解析控制参数
        kwargs = parser_params.model_dump()
        kwargs["output_format"] = output_format
        kwargs["vlm_prompt"] = prompt_content

        # 在循环中添加类型检查和转换
        for k, v in kwargs.items():
            if v is not None:
                # 根据类型进行适当的转换
                if isinstance(v, (int, float)):
                    data.add_field(k, str(v))
                elif isinstance(v, bool):
                    data.add_field(k, str(v).lower())  # 布尔值转为小写字符串
                else:
                    data.add_field(k, v)  # 字符串和其他类型直接添加

        # 2. 读取并添加文件流
        try:
            filename = os.path.basename(file_path)
            # 采用这种方式 aiohttp 会自动管理文件关闭
            if not file_content:
                data.add_field('file', 
                               open(file_path, 'rb'), 
                               filename=filename, 
                               content_type='application/octet-stream')
            else:
                data.add_field('file', 
                               file_content, 
                               filename=filename, 
                               content_type='application/octet-stream')
        except Exception as e:
            logger.error(f"读取文件失败: {filename}, error: {e}")
            raise e

        # 3. 发起请求
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=data) as response:
                    if response.status != 200:
                        err = await response.text()
                        raise Exception(f"解析服务响应错误 {response.status}: {err}")
                    
                    res_json = await response.json()
                    if res_json.get("status") != "success":
                        raise Exception(f"解析服务异常: {res_json.get('detail')}")
                    
                    return res_json.get("result")
                    
        except Exception as e:
            logger.error("解析微服务调用异常")
            raise e
        