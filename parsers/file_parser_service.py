import asyncio
import signal
from loguru import logger
from .file_processor import FileProcessor
from services.km_meta import KMFileMetaService


class ParseService:
    def __init__(self, parallel_workers=5, check_interval=60):
        # 关闭事件
        self.shutdown_event = asyncio.Event()
        
        # 共享状态
        self.workers: list[asyncio.Task] = []
        self.file_queue = asyncio.Queue()
        
        # 配置参数
        self.parallel_workers = parallel_workers
        self.check_interval = check_interval

        self.meta_service = KMFileMetaService()

    async def _db_check_loop(self):
        """生产者循环：只负责往队列丢数据"""
        while not self.shutdown_event.is_set():
            try:
                await self._check_new_files()
                # 优化：支持快速响应关闭的 sleep
                for _ in range(self.check_interval):
                    if self.shutdown_event.is_set(): break
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"DB轮询错误: {e}")
                await asyncio.sleep(10)

    async def _worker_loop(self, worker_id):
        """常驻工作协程：只要不关闭，就一直从队列拿活干"""
        logger.debug(f"Worker-{worker_id} 已启动并等待任务...")
        
        while not self.shutdown_event.is_set():
            try:
                # 使用 timeout 确保能定期回到循环头部检查 shutdown_event
                try:
                    queue_item = await asyncio.wait_for(
                        self.file_queue.get(), 
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                file = queue_item

                try:
                    logger.info(f"Worker-{worker_id} 开始处理: {file.asset_id}")
                    await FileProcessor().process_asset(file)
                except Exception as e:
                    logger.error(f"Worker-{worker_id} 处理 Asset 出错: {e}")
                    # 确保异常情况下也更新为失败状态
                    await self.meta_service.update_asset_metadata(file.asset_id, processed_flag="F")
                finally:
                    # 必须调用 task_done，否则 join() 会阻塞
                    self.file_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker-{worker_id} 意外错误: {e}")
                await asyncio.sleep(1)

    async def _check_new_files(self):
        """检查数据库中的新 Asset 并加入队列"""
        try:
            logger.debug("正在检查数据库中的待处理的 Asset...")
            pending_files = await self.meta_service.retrieve_asset_metadata(offset=0, limit=10, processed_flag="N")
            logger.debug(f"从数据库中检索到 {len(pending_files)} 个待处理 Asset")
            
            if pending_files:
                logger.info(f"发现 {len(pending_files)} 个新 Asset 需要处理")
                processed_count = 0
                
                for file in pending_files:
                    try:
                        logger.debug(f"将 Asset {file.asset_id} 加入队列")
                        logger.info(f"更新 Asset {file.asset_id} 的状态为正在处理")
                        await self.meta_service.update_asset_metadata(file.asset_id, processed_flag="P")
                        await self.file_queue.put((file))
                        processed_count += 1

                    except Exception as e:
                        logger.error(f"将 Asset {file.asset_id} 加入队列失败: {e}")
                        # 加入队列失败时也要标记为失败，避免卡在 P 状态
                        await self.meta_service.update_asset_metadata(file.asset_id, processed_flag="F")
                
                logger.info(f"成功将 {processed_count}/{len(pending_files)} 个 Asset 加入队列")
            
            logger.debug(f"当前队列大小: {self.file_queue.qsize()}")
                
        except Exception as e:
            logger.error(f"检查新 Asset 失败: {str(e)}", exc_info=True)
            raise

    def _handle_shutdown(self, signum, frame):
        """处理关闭信号"""
        logger.info(f"接收到关闭信号 {signum}")
        self.shutdown_event.set()

    async def start_services(self):
        # 1. 信号处理
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        logger.info("等待微服务就绪...")
        await asyncio.sleep(10)

        # 2. 预先启动固定数量的 Worker (常驻)
        for i in range(self.parallel_workers):
            task = asyncio.create_task(self._worker_loop(i), name=f"Worker-{i}")
            self.workers.append(task)

        # 3. 启动数据库轮询 (生产者)
        db_task = asyncio.create_task(self._db_check_loop())
        
        logger.info(f"服务已启动，并发 Worker 数: {self.parallel_workers}")

        try:
            # 只需等待 db_task 或 shutdown 事件
            await asyncio.wait(
                [db_task], 
                return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            await self._shutdown_services()

    async def _shutdown_services(self):
        """关闭所有服务"""
        logger.info("正在停止所有服务...")
        
        # 设置关闭事件
        self.shutdown_event.set()
        
        # 取消所有工作协程
        for worker in self.workers:
            if not worker.done():
                worker.cancel()
        
        # 等待工作协程完成
        if self.workers:
            await asyncio.wait(
                self.workers,
                timeout=5,
                return_when=asyncio.ALL_COMPLETED
            )
        
        # 清空队列（可选）
        while not self.file_queue.empty():
            try:
                self.file_queue.get_nowait()
                self.file_queue.task_done()
            except asyncio.QueueEmpty:
                break
        
        logger.info(f"服务已停止，最终队列大小: {self.file_queue.qsize()}")


# 外部调用接口
async def start_file_parse_service(max_parallel_workers: int, check_interval: int):
    """启动文件解析服务"""
    service = ParseService(max_parallel_workers, check_interval)
    await service.start_services()
