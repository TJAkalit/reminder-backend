"""Worker process: scheduler loop + Telegram long polling in one asyncio loop (D-005, D-006)."""

import asyncio
import logging
from contextlib import suppress
from datetime import timedelta

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.bot.factory import create_bot, create_dispatcher, set_commands
from src.bot.notifier import TelegramNotifier
from src.config import Settings
from src.db.session import create_engine, create_session_factory
from src.domain.clock import now_utc
from src.service.access import AccessService
from src.service.notifier import ChecklistNotifier
from src.service.scheduler import SchedulerService, TickReport

logger = logging.getLogger(__name__)


async def run_tick(
    session_factory: async_sessionmaker[AsyncSession],
    notifier: ChecklistNotifier,
    grace: timedelta,
) -> TickReport:
    async with session_factory() as session:
        report = await SchedulerService(session, notifier, grace).tick(now_utc())
    if report.sent or report.missed or report.closed or report.failed:
        logger.info("Tick: %s", report)
    return report


async def scheduler_loop(
    session_factory: async_sessionmaker[AsyncSession],
    notifier: ChecklistNotifier,
    settings: Settings,
) -> None:
    grace = timedelta(minutes=settings.worker_grace_minutes)
    while True:
        try:
            await run_tick(session_factory, notifier, grace)
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(settings.worker_tick_seconds)


async def run_worker(settings: Settings, *, once: bool = False) -> None:
    engine = create_engine()
    session_factory = create_session_factory(engine)
    bot = create_bot(settings)
    notifier = TelegramNotifier(bot)
    try:
        if once:
            await run_tick(
                session_factory, notifier, timedelta(minutes=settings.worker_grace_minutes)
            )
            return

        dp = create_dispatcher(settings, session_factory, notifier)
        scheduler: asyncio.Task[None] | None = None

        async def on_startup(bot: Bot) -> None:
            nonlocal scheduler
            async with session_factory() as session:
                admins = await AccessService(session).admin_chat_ids()
            await set_commands(bot, admins)
            if not admins:
                logger.warning(
                    "No admins yet: write to the bot, then run `reminder admin grant <chat_id>`"
                )
            scheduler = asyncio.create_task(scheduler_loop(session_factory, notifier, settings))
            logger.info(
                "Worker started: polling + scheduler every %ss", settings.worker_tick_seconds
            )

        async def on_shutdown() -> None:
            if scheduler is not None:
                scheduler.cancel()
                with suppress(asyncio.CancelledError):
                    await scheduler

        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await engine.dispose()
