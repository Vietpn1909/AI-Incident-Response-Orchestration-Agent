import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.incidents import router as incidents_router
from src.api.routes import router
from src.api.webhooks import router as webhooks_router
from src.config import configure_logging, configure_tracing, get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Gọi trước mọi thứ khác: các dòng log bên dưới và trong lúc chạy đều là
    # tiếng Việt, chưa ép UTF-8 thì console Windows in ra ký tự vỡ.
    configure_logging()

    settings = get_settings()
    tracing = "on" if configure_tracing() else "off"
    logger.info("Khởi động %s ở chế độ %s (LangSmith tracing: %s)", settings.app_name, settings.app_env, tracing)
    yield
    logger.info("Đang tắt...")


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(incidents_router, prefix="/api")
app.include_router(webhooks_router, prefix="/webhooks")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
