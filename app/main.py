from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.api.routes import router
from app.database import init_db
from app.scheduler import start_scheduler_if_enabled


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    scheduler = start_scheduler_if_enabled()
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


app = FastAPI(title="Ticket Sale Assistant", version="0.1.0", lifespan=lifespan)
app.include_router(router)
