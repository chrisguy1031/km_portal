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


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     """管理应用程序的生命周期。

#     在应用启动时初始化文件解析引擎并启动服务；
#     在应用关闭时确保资源安全回收。

#     Args:
#         app: FastAPI 实例。
#     """
#     # 设置服务名称到 app.state（供中间件使用）
#     app.state.service_name = get_app_config().service_name

#     # 启动阶段
#     # 初始化KM服务引擎
#     worker = get_app_config().upload_workers
#     check_interval = get_app_config().km_db_check_interval
#     km_manager = KmEngine(worker, check_interval)
#     logger.info("正在启动KM服务引擎...")
#     try:
#         await km_manager.start()
#         logger.info("所有KM子服务已就绪")
#     except Exception as e:
#         logger.error(f"KM服务启动失败: {e}")
#         # 根据业务需求决定是否在启动失败时退出进程

#     yield  # 应用运行中

#     # 关闭阶段
#     logger.info("应用正在关闭，执行清理任务...")
#     try:
#         await km_manager.stop()    
#         logger.info("KM服务引擎已安全关闭")
#     except Exception as e:
#         logger.error(f"KM服务清理失败: {e}")


# def create_app() -> FastAPI:
#     """创建并配置 FastAPI 应用程序。

#     读取全局配置，初始化日志系统，挂载路由及中间件。

#     Returns:
#         FastAPI: 配置完成的应用实例。
#     """
#     try:
#         app_config = get_app_config()

#         # 1. 初始化日志中心
#         log_conf = LogConfig(
#             service_name=app_config.service_name,
#             log_dir=app_config.log.dir,
#             level=app_config.log.level,
#             rotation=app_config.log.rotation,
#             retention=app_config.log.retention,
#         )
#         LogManager(log_conf).setup()

#         logger.debug("正在配置 FastAPI 实例...")

#         # 2. 实例化应用 (支持离线文档)
#         app = FastAPI(
#             title=app_config.title,
#             description=app_config.description,
#             version=app_config.service_version,
#             debug=app_config.debug,
#             lifespan=lifespan,  # 注入生命周期引擎
#         )

#         # 3. 中间件配置
#         app.add_middleware(
#             CORSMiddleware,
#             allow_origins=["*"],
#             allow_credentials=True,
#             allow_methods=["*"],
#             allow_headers=["*"],
#         )

#         # 4. 请求日志中间件
#         app.middleware("http")(log_requests)

#         # 6. 路由注册
#         app.include_router(router)

#         return app

#     except Exception as e:
#         logger.critical(f"应用创建失败: {e}")
#         raise


# def handle_exit_signal(sig, frame):
#     """处理系统退出信号 (SIGINT, SIGTERM)。

#     Args:
#         sig: 信号编号。
#         frame: 当前堆栈帧。
#     """
#     logger.warning(f"接收到信号 {sig}，准备强制退出...")
#     # 注意：在 lifespan 模式下，uvicorn 会优雅处理正常关闭，
#     # 这里的 sys.exit 主要是针对双击 Ctrl+C 等强制情况
#     sys.exit(0)


# async def start_server():
#     """配置并运行 Uvicorn 异步服务器。"""
#     app = create_app()
#     app_config = get_app_config()
#     service_host = app_config.service_host
#     service_port = app_config.service_port

#     logger.info(f"服务启动于: http://{service_host}:{service_port}")

#     config = uvicorn.Config(
#         app=app,
#         host=service_host,
#         port=service_port,
#         log_level="info",
#         access_log=False,  # 交由 loguru 处理以减少冗余
#     )
#     server = uvicorn.Server(config)
#     await server.serve()


# if __name__ == "__main__":
#     # 注册退出信号处理
#     signal.signal(signal.SIGINT, handle_exit_signal)
#     signal.signal(signal.SIGTERM, handle_exit_signal)

#     try:
#         asyncio.run(start_server())
#     except KeyboardInterrupt:
#         pass
#     except Exception as e:
#         logger.exception(f"服务器异常崩溃: {e}")


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