import requests
import time
import os
import io
import re
import base64
from typing import Any
from urllib.parse import quote, unquote, urlparse
from loguru import logger

class SharePointClient:
    """
    Microsoft Graph API 客户端，专门用于 SharePoint 操作
    """
    
    def __init__(self, tenant_id: str, client_id: str, client_secret: str, site_id: str, drive_id: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.site_id = site_id
        self.drive_id = drive_id
        self._access_token = None
        self._token_expires_at = None
    
    def _get_token(self) -> str | None:
        """
        获取或刷新访问令牌
        """
        # 如果令牌存在且未过期，直接返回
        if (self._access_token and self._token_expires_at and 
            time.time() < self._token_expires_at - 60):  # 提前60秒刷新
            return self._access_token
        
        # 获取新令牌
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        data = {
            "client_id": self.client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        
        try:
            response = requests.post(token_url, data=data)
            response.raise_for_status()
            
            token_info = response.json()
            self._access_token = token_info['access_token']
            # 设置过期时间（提前一点刷新）
            self._token_expires_at = time.time() + token_info.get('expires_in', 3600) - 60
            
            logger.info("✅ 成功获取/刷新访问令牌")
            return self._access_token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 获取令牌失败: {e}")
            return None
    
    def make_request(self, method: str, url: str, **kwargs) -> dict[str, Any] | None:
        """
        发送 HTTP 请求到 Microsoft Graph API
        
        Args:
            method: HTTP 方法 ('get', 'post', 'put', 'delete')
            url: API 端点 URL
            **kwargs: 其他 requests 参数
        
        Returns:
            响应数据的字典形式
        """
        access_token = self._get_token()
        if not access_token:
            return None
        
        # 设置默认请求头
        headers = kwargs.pop('headers', {})
        headers.update({
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json'
        })
        
        try:
            # 发送请求
            response = requests.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            
            # 如果是二进制内容（如下载文件），返回响应对象本身
            content_type = response.headers.get('content-type', '')
            if 'application/json' not in content_type:
                return response # type: ignore
            
            # 返回 JSON 数据
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ API 请求失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"错误状态码: {e.response.status_code}")
                logger.error(f"错误响应: {e.response.text}")
            return None
    
    # SharePoint 原有方法
    def get_sites(self):
        """获取所有 SharePoint 站点"""
        return self.make_request('GET', 'https://graph.microsoft.com/v1.0/sites')
    
    def get_site_by_path(self, site_path: str):
        """通过路径获取特定站点"""
        return self.make_request('GET', f'https://graph.microsoft.com/v1.0/sites/{site_path}')
    
    def get_sehub_site(self):
        """获取 SEHUB 站点"""
        return self.get_site_by_path('oracle.sharepoint.com:/sites/sehub')
    
    def get_drives_by_site_id(self):
        """获取特定站点的所有驱动器"""
        return self.make_request('GET', f'https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives')
    
    def get_list_items(self, list_id: str):
        """获取列表中的所有项目"""
        return self.make_request('GET', f'https://graph.microsoft.com/v1.0/sites/{self.site_id}/lists/{list_id}/items')
    
    def get_lists(self, filter_system_lists: bool = True):
        """
        获取站点中的所有列表，可选择过滤系统列表
        
        Args:
            site_id (str): 站点 ID
            filter_system_lists (bool): 是否过滤系统列表，默认为 True
        
        Returns:
            dict: 列表数据
        """
        lists_data = self.make_request('GET', f'https://graph.microsoft.com/v1.0/sites/{self.site_id}/lists')
        
        if lists_data and filter_system_lists:
            # 过滤掉系统列表
            filtered_lists = self._filter_system_lists(lists_data)
            return filtered_lists
        
        return lists_data

    def _filter_system_lists(self, lists_data):
        """
        过滤系统列表，只保留用户创建的列表
        
        Args:
            lists_data (dict): 原始列表数据
        
        Returns:
            dict: 过滤后的列表数据
        """
        if not lists_data or 'value' not in lists_data:
            return lists_data
        
        # 系统列表的关键词
        system_keywords = [
            'web template extensions',
            'workflow',
            'workflow history',
            'workflow tasks',
            'user information',
            'master page',
            'theme',
            'composed look',
            'site columns',
            'content type',
            'event receiver',
            'recycle bin',
            'quick deploy',
            'long running operation status',
            'notification queue',
            'app package',
            'app request',
            'app credentials',
            'microfeed',
            'social comment',
            'social following',
            'social rating',
            'social tag',
            'user profile service application proxy',
            'user property',
            'wiki page',
            'translation package',
            'variation label',
            'variation labels',
            'variation root',
            'work management',
            'workflow associations',
            'workflow templates'
        ]
        
        # 过滤列表
        filtered_value = []
        for list_item in lists_data['value']:
            list_name = list_item.get('name', '').lower()
            list_title = list_item.get('displayName', '').lower()
            
            # 检查是否包含系统关键词
            is_system = any(keyword in list_name or keyword in list_title 
                        for keyword in system_keywords)
            
            if not is_system:
                filtered_value.append(list_item)
        
        # 返回过滤后的数据
        return {
            '@odata.context': lists_data.get('@odata.context'),
            'value': filtered_value
        }

    def get_lists_with_details(self):
        """
        获取列表详细信息，包括项数统计
        
        Returns:
            list[dict]: 过滤后的列表详情
        """
        lists_data = self.get_lists(filter_system_lists=True)
        
        if not lists_data or 'value' not in lists_data:
            return []
        
        detailed_lists = []
        for list_item in lists_data['value']:
            list_info = {
                'id': list_item.get('id'),
                'name': list_item.get('name'),
                'displayName': list_item.get('displayName'),
                'lastModified': list_item.get('lastModifiedDateTime', ''),
                'webUrl': list_item.get('webUrl', '')
            }
            detailed_lists.append(list_info)
        
        return detailed_lists

    def get_file_list(self, items_data):
        """
        从 get_list_items 的结果中提取文件列表
        """
        files = []
        
        if not items_data or 'value' not in items_data:
            return files
        
        items = items_data['value']
        
        for item in items:
            # 跳过文件夹
            if 'contentType' in item and isinstance(item['contentType'], dict):
                ct_name = item['contentType'].get('name', '').lower()
                if 'folder' in ct_name:
                    continue
            
            # 从 webUrl 获取信息
            web_url = item.get('webUrl', '')
            if web_url:
                # 解码 webUrl 得到正确的文件路径
                from urllib.parse import unquote
                decoded_web_url = unquote(web_url)
                
                # 从解码后的 URL 提取文件名
                decoded_file_name = decoded_web_url.split('/')[-1]
                
                # 从原始 URL 提取文件路径部分（用于下载）
                # 我们仍然使用原始的 web_url（编码的）来构建路径，因为 Graph API 需要编码的路径
                original_web_url = web_url
                
                # 过滤条件
                if (decoded_file_name and 
                    not decoded_file_name.startswith(('Shared Documents', '_catalogs', 'wte')) and
                    not self._is_system_file(decoded_file_name)):
                    
                    files.append({
                        'name': decoded_file_name,  # 解码后的文件名
                        'download_url': original_web_url,  # 保持原始编码的 URL，用于路径构建
                        'decoded_web_url': decoded_web_url  # 解码后的 URL，可选
                    })
        
        return files
    
    def _is_system_file(self, file_name):
        """
        判断是否是系统文件
        
        Args:
            file_name (str): 文件名
            
        Returns:
            bool: 是否是系统文件
        """
        import re
        # Web Template Extensions 的系统文件格式
        return bool(re.match(r'^\d+_\.\d+$', file_name) or  # 数字_点数字 格式
                   re.match(r'^[a-f0-9\-]{36}$', file_name))  # UUID格式

    
    def download_file(self, sharepoint_url: str, local_save_path: str) -> bool:
        """下载 SharePoint 文件"""
        # 1. 获取下载 URL
        download_url = self.get_download_url(sharepoint_url)
        
        logger.debug(f"正在请求最终下载链接: {download_url}")

        # 2. 直接执行请求
        response = self.make_request('GET', download_url, stream=True)
        
        if response and response.status_code == 200: # type: ignore
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(local_save_path)), exist_ok=True)
            
            with open(local_save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024*1024): # type: ignore
                    if chunk: f.write(chunk)
            return True
        return False


    def download_file_to_memory(self, sharepoint_url: str):
        """
        下载文件并返回 (BytesIO, filename)
        """
        # 1. 获取下载 URL
        download_url = self.get_download_url(sharepoint_url)
        
        # 这里的 make_request 应该返回原始的 requests.Response 对象
        # 或者确保你能拿到 headers
        response = self.make_request('GET', download_url, stream=True)
        
        if not response or response.status_code != 200: # type: ignore
            return None, None

        # 从 Header 提取文件名
        cd = response.headers.get('Content-Disposition', '') # type: ignore
        fname = ""
        if 'filename=' in cd:
            fname = re.findall('filename="?([^";]+)"?', cd)[0]
        
        # 如果 Header 没给，从 URL 里猜一个
        if not fname:
            fname = unquote(sharepoint_url.split('file=')[-1].split('&')[0])

        return io.BytesIO(response.content), fname # type: ignore
    
    def upload_file(self, folder_path: str, local_file_path: str) -> bool:
        """
        上传本地文件到 SharePoint，支持大文件 (分块上传) 和中文路径
        """
        try:
            if not os.path.isfile(local_file_path):
                logger.error(f"❌ 本地文件不存在: {local_file_path}")
                return False

            file_name = os.path.basename(local_file_path)
            file_size = os.path.getsize(local_file_path)
            
            # 规范化路径编码：保留斜杠，编码中文字符
            clean_folder = folder_path.strip('/')
            encoded_folder = quote(clean_folder, safe='/')
            encoded_file = quote(file_name)
            target_path = f"/root:/{encoded_folder}/{encoded_file}:/content"
            
            # 1. 小文件上传 (<= 4MB)
            if file_size <= 4 * 1024 * 1024:
                upload_url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}{target_path}"
                with open(local_file_path, 'rb') as f:
                    response = self.make_request('PUT', upload_url, data=f.read())
                return True if response else False

            # 2. 大文件分块上传 (> 4MB)
            else:
                return self._upload_large_file(clean_folder, file_name, local_file_path)

        except Exception as e:
            logger.error(f"❌ 上传异常: {e}")
            return False

    def _upload_large_file(self, folder_path: str, file_name: str, local_path: str) -> bool:
        """使用 Upload Session 处理大文件"""
        logger.info(f"📦 文件较大 ({os.path.getsize(local_path)/1024/1024:.2f}MB)，启用分块上传...")
        
        # 创建上传会话
        encoded_path = quote(f"{folder_path}/{file_name}", safe='/')
        session_url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/root:/{encoded_path}:/createUploadSession"
        
        session_data = self.make_request('POST', session_url)
        if not session_data or 'uploadUrl' not in session_data:
            return False
        
        upload_url = session_data['uploadUrl']
        file_size = os.path.getsize(local_path)
        chunk_size = 327680 * 10  # 约 3.2MB，必须是 327,680 字节的倍数
        
        with open(local_path, 'rb') as f:
            start = 0
            while start < file_size:
                chunk = f.read(chunk_size)
                end = start + len(chunk) - 1
                headers = {
                    'Content-Range': f'bytes {start}-{end}/{file_size}',
                    'Content-Length': str(len(chunk))
                }
                # 注意：此处不使用 make_request，因为 uploadUrl 是独立的，且不需要额外的 Auth Header
                resp = requests.put(upload_url, data=chunk, headers=headers)
                if resp.status_code not in [200, 201, 202]:
                    logger.error(f"❌ 分块上传失败: {resp.text}")
                    return False
                start += len(chunk)
                
        logger.info(f"✅ 大文件上传完成: {file_name}")
        return True
    
    def upload_pdf_string(self, file_name: str, file_content: bytes | str) -> bool:
        """
        将 PDF 直接上传到 SharePoint
        """
        try:
            # 1. 确保内容为字节流并统一编码
            if isinstance(file_content, str):
                file_bytes = file_content.encode('utf-8')
            else:
                file_bytes = file_content

            # 2. 规范化路径：仅使用文件名进行 URL 编码
            encoded_file = quote(file_name)
            target_path = f"/root:/{encoded_file}:/content"
            upload_url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}{target_path}"

            # 3. 设置必要的 Header
            # 指定 PDF 内容类型
            headers = {
                'Content-Type': 'application/pdf'
            }

            # 4. 发起请求
            # 直接使用 self.make_request，它会自动处理 Token
            response = self.make_request(
                method='PUT',
                url=upload_url,
                data=file_bytes,
                headers=headers
            )
            
            if response:
                logger.info(f"✅ HTML 上传成功: {file_name}")
                return True
            return False

        except Exception as e:
            logger.error(f"❌ HTML 字符串上传异常: {e}")
            return False
        
    # def _get_share_id(self, url: str) -> str:
    #     """将共享链接转换为 Graph 要求的 Share ID (u! 格式)"""
    #     base_url = url.split('?')[0] # 移除查询参数
    #     b64 = base64.urlsafe_b64encode(base_url.encode("utf-8")).decode("ascii")
    #     return "u!" + b64.rstrip("=")

    # def _extract_from_share_link(self, url: str) -> str:
    #     """类型1: Share ID 链接 -> 使用官方 /shares/ 接口"""
    #     share_id = self._get_share_id(url)
    #     # 共享链接最稳健的下载方式，不需要 site_id 和物理路径
    #     return f"https://graph.microsoft.com/v1.0/shares/{share_id}/driveItem/content"

    # def _extract_from_copy_link(self, url: str) -> str:
    #     """针对 Doc.aspx 类型的链接，利用 sourcedoc UUID 定位"""
    #     # 提取 UUID: {05DA444C-097C-428D-A9B0-C6F8F544EBE6}
    #     match = re.search(r'sourcedoc=\{?([A-F0-9-]+)\}?', url, re.I)
    #     if match:
    #         doc_id = match.group(1)
    #         # 注意：使用 /items/{id} 而不是 /root:/路径
    #         return f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drive/items/{doc_id}/content"
        
    #     # 如果拿不到 UUID，说明逻辑有问题，需要检查正则
    #     return ""

    # def _extract_from_simple_url(self, url: str) -> str:
    #     """类型2: 简单路径 URL -> 剥离站点/库名冗余"""
    #     # 1. 先彻底解码，消除双重编码隐患
    #     clean_path = unquote(url.split('?')[0])
        
    #     # 2. 剥离冗余 (KM_dev/Shared Documents/)
    #     # 目标是得到：Document/filename.docx
    #     relative_path = ""
    #     if '/Shared Documents/' in clean_path:
    #         relative_path = clean_path.split('/Shared Documents/')[-1]
    #     elif '/Shared Document/' in clean_path:
    #         relative_path = clean_path.split('/Shared Document/')[-1]
    #     else:
    #         # 兜底：取最后一段
    #         relative_path = clean_path.split('/')[-1]

    #     # 3. 规范化重新编码，但保留路径斜杠
    #     encoded_path = quote(relative_path.lstrip('/'), safe='/:')
    #     return f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/root:/{encoded_path}:/content"

    # def get_download_url(self, sharepoint_url: str) -> str:
    #     """主入口"""
    #     if not sharepoint_url: return ""
        
    #     # 解码一次防止双重编码
    #     decoded_url = unquote(sharepoint_url)
        
    #     # 优先级 1: 包含 Doc.aspx 或 sourcedoc 的链接 (复制出来的编辑链接)
    #     if 'Doc.aspx' in decoded_url or 'sourcedoc=' in decoded_url:
    #         return self._extract_from_copy_link(sharepoint_url)
        
    #     # 优先级 2: 包含 /Shared Documents/ 的直接路径链接
    #     elif '/Shared Documents/' in decoded_url:
    #         return self._extract_from_simple_url(sharepoint_url)
        
    #     # 优先级 3: 真正的 Share Link (u! 开头的 Base64)
    #     else:
    #         return self._extract_from_share_link(sharepoint_url)

    def get_download_url(self, sharepoint_url: str) -> str:
        """
        通用转换逻辑：将任何 SharePoint 链接转换为 Graph 下载链接
        """
        if not sharepoint_url:
            return ""

        # 1. 预处理：去除多余空格，但不进行 unquote
        # 注意：保持原始 URL 编码状态进行 Base64 转换是官方推荐做法
        target_url = sharepoint_url.strip()

        # 2. 生成通用 Share ID (u! 格式)
        # 这种方式对 'Doc.aspx'、'Shared%20Documents' 以及 'Share ID' 链接全部有效
        url_bytes = target_url.encode("utf-8")
        base64_bytes = base64.urlsafe_b64encode(url_bytes)
        base64_string = base64_bytes.decode("ascii").rstrip("=")
        share_id = "u!" + base64_string

        # 3. 返回 API 地址
        # 使用 /driveItem/content 会直接重定向到文件的二进制下载流
        return f"https://graph.microsoft.com/v1.0/shares/{share_id}/driveItem/content"

"""获取 SharePoint 客户端实例（惰性初始化）"""

_sp_client_instance = None


def get_sharepoint_client() -> SharePointClient:
    """获取 SharePoint 客户端实例（单例模式）"""
    global _sp_client_instance
    if _sp_client_instance is None:
        TENANT_ID = os.getenv("TENANT_ID")
        CLIENT_ID = os.getenv("CLIENT_ID")
        CLIENT_SECRET = os.getenv("CLIENT_SECRET")
        SITE_ID = os.getenv("SITE_ID")
        DRIVE_ID = os.getenv("DRIVE_ID")

        if not TENANT_ID or not CLIENT_ID or not CLIENT_SECRET or not SITE_ID or not DRIVE_ID:
            raise ValueError("请设置 TENANT_ID、CLIENT_ID、CLIENT_SECRET、SITE_ID 和 DRIVE_ID 环境变量")

        _sp_client_instance = SharePointClient(TENANT_ID, CLIENT_ID, CLIENT_SECRET, SITE_ID, DRIVE_ID)
    return _sp_client_instance
