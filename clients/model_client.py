import aiohttp
from PIL import Image
from decimal import Decimal
from loguru import logger
from typing import Any
from .encoder import ImageEncoder
from core.config.settings import get_vlm_config, get_llm_config


class CallModel():
    """模型微服务客户端"""
    def __init__(self):
        self.vlm_config = get_vlm_config()  # 获取 VLM 模型配置
        self.llm_config = get_llm_config()  # 获取 LLM 模型配置


    async def call_vlm_model(
            self,
            model_name: str,
            image: str | Image.Image,
            prompt: str,
            **kwargs
        ) -> str:
            """调用视觉语言模型进行图片解析。

            Args:
                model_name: 模型技术名称。
                image: 输入图片（文件路径或 PIL.Image 对象）。
                prompt: 完整的提示词文本（必填）。
                **kwargs: 推理的额外参数（如 temperature, max_tokens 等）。

            Returns:
                str: 模型生成的输出文本。
            """
            service_host = self.vlm_config.service_host
            service_port = self.vlm_config.service_port
            
            # 1. 超时配置
            use_health_check_timeout = kwargs.pop("use_health_check_timeout", False)
            total = self.vlm_config.health_check_timeout if use_health_check_timeout else self.vlm_config.timeout
            timeout = aiohttp.ClientTimeout(total=total)
            
            url = f"http://{service_host}:{service_port}/v1/inference"
            headers = {"Content-Type": "application/json"}

            # 2. 图片编码（Base64）
            try:
                image_base64 = await ImageEncoder.encode(image)
            except Exception as e:
                msg = f"VLM 图片编码失败: {e}"
                logger.error(msg)
                raise e

            # 3. 构建 OpenAI 兼容格式的消息体
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ]

            # 4. 构建请求体
            payload = {
                "model_name": model_name,
                "messages": messages,
                "stream": False,
                **kwargs
            }

            # 5. 执行请求
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, headers=headers, json=payload) as response:
                        # 处理 HTTP 错误
                        if response.status != 200:
                            error_text = await response.text()
                            msg = f"VLM 服务 HTTP {response.status} 错误: {error_text}"
                            logger.error(msg)
                            raise Exception(msg)

                        response_data = await response.json()
                        
                        # 提取内容
                        try:
                            content = response_data["choices"][0]["message"]["content"]
                            logger.info(f"VLM 解析成功 | 模型: {model_name} | Prompt长度: {len(prompt)}")
                            return content
                        except (KeyError, IndexError) as e:
                            msg = f"VLM 响应格式非法: {str(e)}"
                            logger.error(msg)
                            raise e

            # 6. 异常分类捕获
            except aiohttp.ClientConnectorError as e:
                msg = f"无法连接到 VLM 服务 {service_host}:{service_port}"
                logger.error(msg)
                raise e
                
            except aiohttp.ServerTimeoutError as e:
                msg = f"VLM 服务响应超时 ({total}s)"
                logger.error(msg)
                raise e
                
            except Exception as e:
                msg = f"VLM 调用过程中发生异常: {str(e)}"
                logger.exception(msg)
                raise Exception(msg)
            

    async def call_llm_model(self, model_name: str, prompt: str, **kwargs):
        """
        调用LLM微服务并处理SSE格式的响应

        Args:
            model_name: 模型技术名称
            prompt: 输入的提示信息
            **kwargs: 其他可选参数，如stream、temperature等

        Returns:
            异步生成器，逐块产生LLM的响应
        """


        service_host = self.llm_config.service_host
        service_port = self.llm_config.service_port
        use_health_check_timeout = kwargs.pop("use_health_check_timeout", False)
        total = self.llm_config.health_check_timeout if use_health_check_timeout else self.llm_config.timeout
        timeout = aiohttp.ClientTimeout(total=total)
        url = f"http://{service_host}:{service_port}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}

        # 构建请求体
        payload = {
            "model_name": model_name,
            "messages": prompt,
            "stream": kwargs.get("stream", True)  # 默认为流式
        }

        # 处理额外参数（Decimal转float/int）
        if kwargs:
            processed_kwargs = {}
            for k, v in kwargs.items():
                if v is not None:
                    if isinstance(v, Decimal):
                        processed_kwargs[k] = float(v) if v % 1 else int(v)
                    else:
                        processed_kwargs[k] = v
            payload.update(processed_kwargs)

        logger.debug(f"调用LLM服务，请求负载: {payload}")

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        text = await response.text()
                        msg = f"LLM服务错误: HTTP {response.status}, {text}"
                        logger.error(msg)
                        raise Exception(msg)

                    async for raw_chunk in response.content:
                        yield raw_chunk.decode('utf-8')
        except aiohttp.ClientConnectorError as e:
            msg = f"无法连接到LLM服务 {service_host}:{service_port}，请检查服务是否启动"
            logger.error(msg)
            raise Exception(msg)
        except aiohttp.ServerTimeoutError:
            msg = f"LLM服务响应超时 ({total}s)，请检查服务状态"
            logger.error(msg)
            raise Exception(msg)
        except Exception as e:
            msg = f"LLM服务发生错误: {e}"
            logger.error(msg)
            raise Exception(msg)