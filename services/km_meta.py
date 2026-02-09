import os
import base64
import requests
from loguru import logger
from typing import Any
from parsers.file_params import AssetMeta

class KMFileMetaService:
    """文件元数据服务"""
    async def _get_asset_meta_from_db(self, offset: int, limit: int, processed_flag: str) -> list[dict[str, Any]]:
        """从数据库获取 asset 元数据"""
        user = os.getenv("KM_USER")
        password = os.getenv("KM_PASSWORD")
        url = os.getenv("KM_URL")
        if not url:
            raise ValueError("请设置 KM_URL 环境变量")
        if not user or not password:
            raise ValueError("请设置 KM_USER 和 KM_PASSWORD 环境变量")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {base64.b64encode(f'{user}:{password}'.encode('utf-8')).decode('utf-8')}"
        }
        processed_flag = processed_flag.upper()
        request_url = f"{url}?offset={offset}&limit={limit}&processed={processed_flag}"
        response = requests.get(request_url, headers=headers)
        metadata_response = response.json()
    
        result = []

        if not metadata_response or 'items' not in metadata_response:
            logger.warning("元数据响应格式错误或为空")
            return result

        items = metadata_response.get('items', [])
        if not items:
            logger.info("没有找到待处理的 asset 文档")
            return result

        for item in items:
            try:
                asset_dict = {
                    "asset_id": item.get("asset_id", ""),
                    "asset_title": item.get("asset_title", ""),
                    "author_mail": item.get("author_mail", ""),
                    "contact_info": item.get("contact_info", ""),
                    "biz_background": item.get("biz_background", ""),
                    "asset_details": item.get("asset_details", ""),
                    "engagement_id": item.get("engagement_id", ""),
                    "asset_status": item.get("asset_status", ""),
                    "create_time": item.get("create_time", ""),
                    "last_update_time": item.get("last_update_time", ""),
                    "asset_type": item.get("asset_type", ""),
                    "online_env_avail": item.get("online_env_avail", ""),
                    "solution_briefing": item.get("solution_briefing", ""),
                    "industry_id": item.get("industry_id", ""),
                    "country": item.get("country", ""),
                    "deal_size": item.get("deal_size", ""),
                    "competition": item.get("competition", ""),
                    "osn_link": item.get("osn_link", ""),
                    "customer": item.get("customer", ""),
                    "duration": item.get("duration", ""),
                    "duration_unit": item.get("duration_unit", ""),
                    "audience": item.get("audience", ""),
                    "asset_language": item.get("asset_language", ""),
                    "sub_type": item.get("sub_type", ""),
                    "ranking": item.get("ranking", ""),
                    "asset_plan_id": item.get("asset_plan_id", ""),
                    "pillar_category": item.get("pillar_category", ""),
                    "team": item.get("team", ""),
                    "pillar": item.get("pillar", ""),
                    "red_stack": item.get("red_stack", ""),
                    "eng_type": item.get("eng_type", ""),
                    "asset_source": item.get("asset_source", ""),
                    "content_category": item.get("content_category", ""),
                    "contact_names": item.get("contact_names", ""),
                    "publish_date": item.get("publish_date", ""),
                    "business_challenges": item.get("business_challenges", ""),
                    "scc_contribution": item.get("scc_contribution", ""),
                    "collaboration": item.get("collaboration", ""),
                    "results": item.get("results", ""),
                    "service_effort": item.get("service_effort", ""),
                    "asset_domain": item.get("asset_domain", ""),
                    "metadata_notify_times": item.get("metadata_notify_times", ""),
                    "asset_review_date": item.get("asset_review_date", ""),
                    "asset_hours": item.get("asset_hours", ""),
                    "processed": item.get("processed", "N"),
                    "second_sp_url": item.get("second_sp_url", ""),
                    "first_sp_url": item.get("first_sp_url", "")
                }
                result.append(asset_dict)
                logger.info(f"获取 asset 文档: {asset_dict['asset_id']} - {asset_dict['asset_title']}")
            except Exception as e:
                logger.error(f"获取 asset 文档元数据时发生错误: {str(e)}")
                continue

        logger.info(f"成功获取 {len(result)} 条 asset 文档元数据")
        return result


    async def retrieve_asset_metadata(self, offset: int = 0, limit: int = 5, processed_flag: str = "N") -> list[AssetMeta]:
        """获取 asset 元数据，返回 asset 信息和下载路径"""
        asset_meta = await self._get_asset_meta_from_db(offset=offset, limit=limit, processed_flag=processed_flag)
        if not asset_meta:
            logger.warning("没有找到待处理的 asset 元数据")
            return []

        results = []

        for item in asset_meta:
            try:
                asset_id = item.get("asset_id") or ""
                asset_title = item.get("asset_title") or ""
                asset_details = item.get("asset_details") or ""
                asset_product = item.get("asset_product") or ""
                sub_type = item.get("sub_type") or ""
                industry_id = item.get("industry_id") or ""
                asset_solution = item.get("asset_solution") or ""
                solution_briefing = item.get("solution_briefing") or ""
                first_sp_url = item.get("first_sp_url") or ""
                second_sp_url = item.get("second_sp_url") or ""

                result = AssetMeta(
                    asset_id=asset_id,
                    asset_title=asset_title,
                    asset_product=asset_product,
                    sub_type=sub_type,
                    industry_id=industry_id,
                    asset_solution=asset_solution,
                    asset_details=asset_details,
                    solution_briefing=solution_briefing,
                    first_sp_url=first_sp_url,
                    second_sp_url=second_sp_url,
                )

                results.append(result)
                logger.info(f"成功解析 asset {asset_id} 的元数据")

            except Exception as e:
                logger.error(f"解析 asset {item.get('asset_id')} 元数据时发生错误: {str(e)}")
                continue

        logger.info(f"解析 asset 元数据完成，共解析 {len(results)} 个 asset")
        return results

    async def reset_processed_flag(self, offset: int = 0, limit: int = 100) -> int:
        """
        将数据库中标记为 Y 的记录批量改回 N

        Args:
            offset: 偏移量
            limit: 批量处理的数量

        Returns:
            成功重置的记录数
        """
        # 1. 获取所有标记为 Y 的记录
        assets = await self.retrieve_asset_metadata(offset=offset, limit=limit, processed_flag="Y")
        if not assets:
            logger.info("没有找到标记为 Y 的 asset")
            return 0

        logger.info(f"找到 {len(assets)} 个标记为 Y 的 asset，准备重置为 N")

        # 2. 批量更新为 N
        success_count = 0
        for asset in assets:
            try:
                await self.update_asset_metadata(asset.asset_id, processed_flag="N")
                success_count += 1
            except Exception as e:
                logger.error(f"重置 asset {asset.asset_id} 状态失败: {e}")

        logger.info(f"成功重置 {success_count}/{len(assets)} 个 asset 的状态为 N")
        return success_count

    async def update_asset_metadata(self, asset_id: str, processed_flag: str):
        """更新 asset 元数据"""
        user = os.getenv("KM_USER")
        password = os.getenv("KM_PASSWORD")
        url = os.getenv("KM_URL")
        if not url:
            raise ValueError("请设置 KM_URL 环境变量")
        if not user or not password:
            raise ValueError("请设置 KM_USER 和 KM_PASSWORD 环境变量")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {base64.b64encode(f'{user}:{password}'.encode('utf-8')).decode('utf-8')}"
        }
        
        request_url = url
        json_body = {
            "asset_id": asset_id,
            "processed": processed_flag
        }
        try:
            response = requests.put(request_url, headers=headers, json=json_body)
            response.raise_for_status()
            logger.info(f"成功更新 asset {asset_id} 的 processed 标志为 {processed_flag}")
        except requests.RequestException as e:
            logger.error(f"更新 asset {asset_id} 元数据时发生错误: {e}")
            raise
