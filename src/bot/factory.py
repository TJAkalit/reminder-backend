from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.bot.handlers import add, admin, checklist, common, habits
from src.bot.middleware import AccessMiddleware
from src.bot.notifier import TelegramNotifier
from src.bot.texts import ADMIN_COMMANDS, COMMANDS
from src.config import Settings


def create_bot(settings: Settings) -> Bot:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return Bot(settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    notifier: TelegramNotifier,
) -> Dispatcher:
    dp = Dispatcher()
    # Injected into handlers by parameter name.
    dp["settings"] = settings
    dp["notifier"] = notifier

    access = AccessMiddleware(session_factory)
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(access)

    # common first: /cancel and /start must work in the middle of a dialog.
    dp.include_routers(common.router, admin.router, checklist.router, habits.router, add.router)
    return dp


async def set_commands(bot: Bot, admin_chat_ids: list[int]) -> None:
    """Command menu: admins additionally see admin commands in their chat."""
    common_commands = [
        BotCommand(command=name, description=text) for name, text in COMMANDS.items()
    ]
    admin_commands = [
        BotCommand(command=name, description=text) for name, text in ADMIN_COMMANDS.items()
    ]
    await bot.set_my_commands(common_commands)
    for chat_id in admin_chat_ids:
        await bot.set_my_commands(
            common_commands + admin_commands, scope=BotCommandScopeChat(chat_id=chat_id)
        )
