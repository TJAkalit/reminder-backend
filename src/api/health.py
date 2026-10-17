from fastapi import APIRouter
from sqlalchemy import text

from src.api.deps import SessionDep
from src.dto.base import Dto

router = APIRouter(tags=["health"])


class HealthOut(Dto):
    status: str
    database: str


@router.get("/health")
async def health(session: SessionDep) -> HealthOut:
    await session.execute(text("SELECT 1"))
    return HealthOut(status="ok", database="ok")
