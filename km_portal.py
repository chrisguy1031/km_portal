"""主程序启动入口。

本模块负责初始化 FastAPI 应用、加载全局配置、管理文件解析服务的生命周期，
并启动 Uvicorn 服务器。
"""
import sys
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
    loop = asyncio.get_running_loop()

    # 定义平滑关闭函数
    async def shutdown(sig_name):
        logger.info(f"收到信号 {sig_name}, 准备关闭服务...")
        stop_event.set()

    # 注册信号处理 (适配 Windows 和 Linux)
    if sys.platform != 'win32':
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s.name)))
    else:
        # Windows 下 signal 模块仍是首选
        def handle_exit(*args):
            # 在同步环境中触发异步事件
            loop.call_soon_threadsafe(stop_event.set)
        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)

    try:
        await km_manager.start()
        await stop_event.wait() # 阻塞点
    except Exception as e:
        logger.exception(f"运行时异常: {e}")
    finally:
        logger.info("开始执行清理逻辑...")
        # 强制设置一个超时，防止清理逻辑本身卡死
        try:
            await asyncio.wait_for(km_manager.stop(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("清理超时，强制退出")
        logger.info("服务已退出")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序已手动退出")