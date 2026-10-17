from src.dto.base import Dto


class UserOut(Dto):
    id: int
    display_name: str
    timezone: str
