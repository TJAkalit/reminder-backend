"""Development data: a user with the «Утро» routine and a few habits."""

import logging

from src.db.session import create_engine, create_session_factory
from src.service.habit import HabitService
from src.service.routine import RoutineService
from src.service.user import UserService

logger = logging.getLogger(__name__)

SAMPLE_HABITS = (("💧", "Стакан воды"), ("🤸", "Зарядка 10 минут"), ("📵", "Без телефона 30 минут"))


async def run_seed(chat_id: int, name: str, timezone: str) -> None:
    engine = create_engine()
    try:
        async with create_session_factory(engine)() as session:
            user, created = await UserService(session).register(chat_id, name, timezone)
            routines = RoutineService(session)
            if not created and await routines.list_routines(user):
                logger.info("User %s already has routines, nothing to do", user.id)
                return
            routine = await routines.create(
                user, "Утро", "FREQ=DAILY;BYHOUR=7;BYMINUTE=0", emoji="🌅"
            )
            for emoji, title in SAMPLE_HABITS:
                await HabitService(session).create(routine, title, emoji=emoji)
            logger.info("Seeded user %s with routine %s", user.id, routine.id)
    finally:
        await engine.dispose()
