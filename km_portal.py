"""主程序启动入口。

本模块负责初始化 FastAPI 应用、加载全局配置、管理文件解析服务的生命周期，
并启动 Uvicorn 服务器。
"""

import asyncio
import signal
# import sys
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# import uvicorn
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
# from fastapi_offline import FastAPIOffline

from core.config.settings import get_app_config
from core.logger import LogConfig, LogManager
# from core.middleware.log_middleware import log_requests
from file_loader.km_engine import KmEngine
# from router import router

# --- 环境初始化 ---
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)


async def main():
    # 1. 加载配置
    app_config = get_app_config()
    
    # 2. 初始化日志
    log_conf = LogConfig(
        service_name=app_config.service_name,
        log_dir=app_config.log.dir,
        level=app_config.log.level,
        rotation=app_config.log.rotation,
        retention=app_config.log.retention,
    )
    LogManager(log_conf).setup()

    # 3. 初始化引擎
    worker = app_config.upload_workers
    check_interval = app_config.km_db_check_interval
    km_manager = KmEngine(worker, check_interval)
    
    # 4. 设置退出信号监听 (仅限类 Unix 系统)
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    
    def ask_exit():
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, ask_exit)
        except NotImplementedError:
            pass # Windows 不支持 add_signal_handler

    try:
        logger.info("正在启动 KM 服务引擎...")
        await km_manager.start()
        logger.info("KM 服务引擎已启动完成，持续运行中...")
        
        # 5. 等待停止信号或无限等待
        await stop_event.wait()
        
    except Exception as e:
        logger.exception(f"服务运行中发生异常: {e}")
    finally:
        # 6. 确保无论如何都会执行优雅关闭
        logger.info("正在执行优雅关闭流程...")
        await km_manager.stop()
        logger.info("KM 服务已安全关闭")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 这里的 KeyboardInterrupt 通常会被 signal_handler 拦截
        pass