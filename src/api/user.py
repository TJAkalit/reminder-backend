from fastapi import APIRouter

from src.api.deps import SessionDep
from src.dto.user import UserOut
from src.service.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(session: SessionDep) -> list[UserOut]:
    """Users for the UI selector (no authentication in the MVP)."""
    return await UserService(session).list_users()
