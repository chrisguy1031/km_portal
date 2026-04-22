"""主程序启动入口。

本模块负责初始化 FastAPI 应用、加载全局配置、管理文件解析服务的生命周期，
并启动 Uvicorn 服务器。
"""

import asyncio
import signal
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

from core.config.settings import get_app_config
from core.logger import LogConfig, LogManager
# from core.middleware.log_middleware import log_requests
from file_loader.km_engine import KmEngine
# from router import router

# --- 环境初始化 ---
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

# 全局变量，确保关闭时能访问到
km_manager = None

async def main():
    global km_manager

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
    
    # 4. 监听退出信号
    stop_event = asyncio.Event()

    def handle_exit(*args):
        logger.info("收到退出信号，准备关闭服务...")
        stop_event.set()

    # 绑定信号
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    try:
        logger.info("正在启动 KM 服务引擎...")
        await km_manager.start()
        logger.info("KM 服务引擎已启动完成，持续运行中...")
        
        # 等待退出信号
        await stop_event.wait()

    except Exception as e:
        logger.exception(f"服务运行异常: {e}")

    finally:
        # 安全关闭
        logger.info("正在执行优雅关闭...")
        if km_manager:
            await km_manager.stop()
        logger.info("KM 服务已安全关闭")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序已手动退出")