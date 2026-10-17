from fastapi import APIRouter

from src.api.deps import CurrentUser, SessionDep
from src.dto.routine import RoutineOut
from src.service.routine import RoutineService

router = APIRouter(prefix="/routines", tags=["routines"])


@router.get("")
async def list_routines(session: SessionDep, user: CurrentUser) -> list[RoutineOut]:
    return await RoutineService(session).list_out(user)
