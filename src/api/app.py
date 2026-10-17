from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api import habit, health, routine, today, user
from src.db.session import create_engine, create_session_factory
from src.service.errors import ForbiddenError, NotFoundError, ServiceError, ValidationError

_STATUS_BY_ERROR: dict[type[ServiceError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ForbiddenError: status.HTTP_403_FORBIDDEN,
    ValidationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


async def _service_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    code = next(
        (code for cls, code in _STATUS_BY_ERROR.items() if isinstance(exc, cls)),
        status.HTTP_400_BAD_REQUEST,
    )
    return JSONResponse(status_code=code, content={"detail": str(exc)})


def create_app(session_factory: async_sessionmaker[AsyncSession] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if session_factory is not None:
            app.state.session_factory = session_factory
            yield
            return
        engine = create_engine()
        app.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Reminder API", version="0.1.0", lifespan=lifespan)
    app.add_exception_handler(ServiceError, _service_error_handler)

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    v1 = APIRouter(prefix="/v1")
    for module in (user, today, routine, habit):
        v1.include_router(module.router)
    api.include_router(v1)
    app.include_router(api)
    return app
