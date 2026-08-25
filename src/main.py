import logging
import os
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
    """Sống chưa, và **đang chạy commit nào**.

    Trường `commit` là thứ duy nhất cho biết bản đang chạy có phải code mới nhất.
    Trước 22/08 endpoint này chỉ trả `status` + `env`, nên câu "Render đã deploy
    commit mới chưa" **không ai trả lời được từ bên ngoài** — phải mở dashboard.
    Và tệ hơn: `docs/START-HERE.md` đã ghi sẵn một cạm bẫy có thật — merge PR trên
    web thì repo mirror tụt lại và Render chạy code cũ, mà dashboard vẫn báo deploy
    thành công.

    `RENDER_GIT_COMMIT` do Render tự bơm vào container, không phải mình khai. Chạy
    ngoài Render thì không có, nên trả `"local"` — nói thật là không biết, hơn là
    đọc `git` ở runtime rồi báo commit của thư mục làm việc chứ không phải của bản
    đã build.
    """
    commit = os.getenv("RENDER_GIT_COMMIT", "")
    return {
        "status": "ok",
        "env": settings.app_env,
        "commit": commit[:7] if commit else "local",
        "branch": os.getenv("RENDER_GIT_BRANCH") or "local",
    }
