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
    first_sp_url: str | None = Field(None, description="第一个文件下载URL")
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
