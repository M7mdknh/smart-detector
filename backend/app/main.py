from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.api.websocket import router as ws_router
from app.contracts.errors import ApiError
from app.logging_config import configure_logging, correlation_id_var, get_logger, new_correlation_id
from app.settings import get_settings
from app.simulation.loop import get_sim_loop

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("starting Factory Safety Sentinel backend")

    loop = get_sim_loop()
    loop.start()

    from app.inference.vision_pipeline import get_vision_worker

    get_vision_worker().start()

    yield

    await loop.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_correlation_id(request: Request, call_next):
        cid = request.headers.get("x-correlation-id") or new_correlation_id()
        correlation_id_var.set(cid)
        response = await call_next(request)
        response.headers["x-correlation-id"] = cid
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details, "correlation_id": correlation_id_var.get("")}},
        )

    app.include_router(api_router)
    app.include_router(ws_router)
    return app


app = create_app()
