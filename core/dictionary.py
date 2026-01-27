from enum import Enum


class ModelCategory(Enum):
    """模型分类枚举"""
    LLM = 1
    VLM = 5

class LLMProvider(Enum):
    """LLM提供商枚举"""
    API_DEEPSEEK = "api_deepseek"
    API_QWEN = "api_qwen"
    CHATGPT = "chatgpt"
    OCI = "oci"

class VLMProvider(Enum):
    """VLM提供商枚举"""
    API_QWEN = "api_qwen"
    CHATGPT = "chatgpt"