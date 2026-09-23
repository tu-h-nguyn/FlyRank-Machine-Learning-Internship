import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.database import SessionLocal
from app.services.alerts import run_with_retry

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
settings = get_settings()


async def worker_loop():
    while True:
        await asyncio.to_thread(run_with_retry, SessionLocal, settings.worker_retry_count)
        await asyncio.sleep(settings.worker_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if settings.background_worker_enabled:
        task = asyncio.create_task(worker_loop())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(title=settings.app_name, version='1.0.0', lifespan=lifespan)
app.include_router(router)
