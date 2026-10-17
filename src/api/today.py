from fastapi import APIRouter

from src.api.deps import CurrentUser, SessionDep
from src.dto.today import TodayOut
from src.service.today import TodayService

router = APIRouter(prefix="/today", tags=["today"])


@router.get("")
async def get_today(session: SessionDep, user: CurrentUser) -> TodayOut:
    """Today's routines in the user's timezone with the status of every habit."""
    return await TodayService(session).get(user)
