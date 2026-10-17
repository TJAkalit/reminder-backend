from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.texts import help_text
from src.config import Settings
from src.model import User
from src.service.errors import ValidationError
from src.service.user import UserService

router = Router(name="common")

NOT_REGISTERED = "Сначала нажмите /start"


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession, settings: Settings) -> None:
    assert message.from_user is not None
    user, created = await UserService(session).register(
        chat_id=message.chat.id,
        display_name=message.from_user.full_name,
        timezone=settings.default_timezone,
    )
    greeting = "Привет! Вы зарегистрированы." if created else "С возвращением!"
    await message.answer(
        f"{greeting}\nЧасовой пояс: <code>{escape(user.timezone)}</code> "
        "(сменить: /timezone).\n\n" + help_text()
    )


@router.message(Command("help"))
async def help_(message: Message) -> None:
    await message.answer(help_text())


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.")


@router.message(Command("timezone"))
async def timezone(
    message: Message, command: CommandObject, session: AsyncSession, user: User | None
) -> None:
    if user is None:
        await message.answer(NOT_REGISTERED)
        return
    if not command.args:
        await message.answer(
            f"Текущий часовой пояс: <code>{escape(user.timezone)}</code>\n"
            "Сменить: <code>/timezone Europe/Moscow</code> (название из базы IANA)."
        )
        return
    try:
        await UserService(session).set_timezone(user, command.args.strip())
    except ValidationError:
        await message.answer("Не знаю такой часовой пояс. Пример: <code>Europe/Moscow</code>")
        return
    await message.answer(f"Часовой пояс изменён: <code>{escape(user.timezone)}</code>")
