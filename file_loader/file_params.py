from pathlib import Path

from pydantic import BaseModel, Field
    
class AssetMeta(BaseModel):
    asset_id: str = Field(..., description="Asset ID")
    asset_title: str = Field(..., description="Asset 标题")
    asset_product: str = Field(..., description="Asset 产品类型")
    sub_type: str = Field(..., description="Asset 子类型")
    industry_id: str = Field(..., description="行业ID")
    asset_solution: str = Field(..., description="Asset 解决方案")
    asset_details: str = Field(..., description="Asset 详情")
    solution_briefing: str = Field(..., description="解决方案简介")
    author_mail: str | None = Field(None, description="作者邮箱")
    create_time: str | None = Field(None, description="创建时间")
    last_update_time: str | None = Field(None, description="来源修订时间")
    first_sp_url: str | None = Field(None, description="第一个文件下载URL")
    asset_language: str | None = Field(None, description="资产语言")
    asset_type: str | None = Field(None, description="资产类型")
    content_category: str | None = Field(None, description="内容分类")
    pillar: str | None = Field(None, description="Pillar")
    pillar_category: str | None = Field(None, description="Pillar 分类")
    # second_sp_url: str | None = Field(None, description="第二个文件下载URL")

class UploadMetadata(BaseModel):
    asset_id: str = Field(..., description="Asset ID")
    original_asset_url: str = Field(..., description="原始 Asset 链接")
    asset_title: str = Field(..., description="Asset 标题")
    asset_product: str = Field(..., description="Asset 产品类型")
    sub_type: str = Field(..., description="Asset 子类型")
    industry_id: str = Field(..., description="行业ID")
    first_sp_url: str | None = Field(None, description="第一个文件下载URL")
    second_sp_url: str | None = Field(None, description="第二个文件下载URL")

    def to_dict(self):
        return self.model_dump()


class DownloadedAttachment(BaseModel):
    """已下载、可作为 KC multipart 文件 Part 上传的附件。"""

    part_name: str
    external_document_id: str
    source_url: str
    declared_name: str
    declared_mime_type: str
    ordinal: int
    required_flag: bool = False
    file_path: Path
    byte_size: int
    content_sha256: str


class AttachmentFailure(BaseModel):
    """来源已声明但 Portal 无法取得字节的附件。"""

    external_document_id: str
    source_url: str
    declared_name: str | None = None
    ordinal: int
    required_flag: bool = False
    failure_code: str
