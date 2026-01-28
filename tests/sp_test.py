import sys
import os
import asyncio
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv

load_dotenv()

# Add both project root and backend directory to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Use absolute imports from project root
from services.sharepoint import get_sharepoint_client

# 使用示例
def demo_usage():
    """演示如何使用整合后的 SharePointClient 类"""
    sp_client = get_sharepoint_client()

    # 1. 获取站点信息
    print("=== 1. 获取站点信息 ===")
    response = sp_client.get_sehub_site()
    print(response)
    if response and 'id' in response:
        site_id = response.get('id')
        print(f"SEHUB 站点 ID: {site_id}")
    else:
        print("获取 SEHUB 站点失败")
    
    if not site_id:
        print("站点 ID 为空，无法获取驱动器信息")
        return
    else:
        sp_client.site_id = site_id
    
    # 2. 获取驱动器信息
    print("=== 2. 获取驱动器信息 ===")
    response = sp_client.get_drives_by_site_id()
    print(response)
    if response and 'value' in response:
        drive = response.get('value')[0] # type: ignore
        drive_id = drive.get('id')
        print(f"默认驱动器 ID: {drive_id}")
    else:
        print("获取默认驱动器失败")

    if not drive_id:
        print("驱动器 ID 为空，无法获取列表信息")
        return
    else:
        sp_client.drive_id = drive_id

    # 3. 获取站点列表
    print("=== 3. 获取站点列表 ===")
    lists = sp_client.get_lists_with_details()
    id = None
    for list_info in lists:
        print(list_info)
        name = list_info.get('name')
        if name == "Shared Documents":
            id = list_info.get('id')
        print(f"Shared Documents 列表 ID: {id}")

    if not id:
        print("列表 ID 为空，无法获取列表信息")
        return

    # 4. 获取列表中的所有文件
    print("=== 4. 获取列表中的所有文件 ===")
    items = sp_client.get_list_items(list_id=id)
    if items:
        documents = sp_client.get_file_list(items)
        print(documents)
    
    # 5. 单文件下载示例
    print(f"\n=== 5. 单文件下载 ===")
    total = len(documents)
    print(f"总文件数: {total}")
    doc = documents[total-2] # 选择最后一个文件进行下载
    file_name = doc['name']
    download_url = doc['download_url']
    print(f"文件名称: {file_name}")
    print(f"下载 URL: {download_url}")
    
    success = sp_client.download_file(
        sharepoint_url=download_url,
        local_save_path=f"./{file_name}"
    )
    if success:
        print(f"✅ 文件 {file_name} 下载成功")
    else:
        print(f"❌ 文件 {file_name} 下载失败")

    # # 4. 单文件上传示例
    # print(f"\n=== 4. sharepoint 单文件上传 ===")
    # doc_name = "数学1.txt"
    # local_file_path = f"./{doc_name}"
    # folder_path = "test_folder"
    # success = sp_client.upload_file(
    #     folder_path=folder_path,
    #     local_file_path=local_file_path
    # )
    # if success:
    #     print(f"✅ 文件 {doc_name} 上传成功到 {folder_path}")
    # else:
    #     print(f"❌ 文件 {doc_name} 上传失败到 {folder_path}")
    

if __name__ == "__main__":
    
    # 运行演示
    demo_usage()

    

    
