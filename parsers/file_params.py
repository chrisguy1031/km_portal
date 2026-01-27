from pydantic import BaseModel, Field


class ParserParams(BaseModel):
    """解析参数模型"""
    chunk_size: int = Field(..., description="分块大小")
    overlap: int = Field(..., description="分块重叠大小")
    min_chunk_len: int = Field(..., description="最小分块长度")
    generate_picture_images: bool = Field(description="是否生成图片描述")
    do_ocr: bool = Field(description="是否进行OCR识别")
    ocr_engine: str | None = Field(None, description="OCR引擎名称")
    images_scale: float = Field(..., description="图片缩放比例")
    use_vlm: bool = Field(default=False, description="是否使用VLM生成图片描述")

    def to_dict(self) -> dict:
        """转换为字典"""
        return self.model_dump()
    
class AssetMeta(BaseModel):
    asset_id: str = Field(..., description="Asset ID")
    asset_title: str = Field(..., description="Asset 标题")
    asset_details: str = Field(..., description="Asset 详情")
    solution_briefing: str = Field(..., description="解决方案简介")
    first_sp_url: str | None = Field(None, description="第一个文件下载URL")
    second_sp_url: str | None = Field(None, description="第二个文件下载URL")
