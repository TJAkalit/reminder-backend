"""CLI side of access management: bootstrap the first admin without the bot."""

import typer

from src.db.session import create_engine, create_session_factory
from src.service.access import AccessService
from src.service.errors import ServiceError


async def run_admin(action: str, chat_id: int | None) -> None:
    engine = create_engine()
    try:
        async with create_session_factory(engine)() as session:
            service = AccessService(session)
            try:
                if action == "grant" and chat_id is not None:
                    entry = await service.set_admin(chat_id, True)
                    typer.echo(f"Admin: {entry.telegram_chat_id} ({entry.label})")
                elif action == "demote" and chat_id is not None:
                    entry = await service.set_admin(chat_id, False)
                    typer.echo(f"Not an admin anymore: {entry.telegram_chat_id} ({entry.label})")
                else:
                    for entry in await service.entries():
                        crown = " admin" if entry.is_admin else ""
                        typer.echo(
                            f"{entry.telegram_chat_id}\t{entry.status.value}{crown}\t{entry.label}"
                        )
            except ServiceError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(1) from exc
    finally:
        await engine.dispose()
