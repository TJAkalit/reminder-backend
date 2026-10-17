import asyncio
import json
import logging
from pathlib import Path

import typer
from alembic.config import Config

from src.config import get_settings

app = typer.Typer(help="Reminder: habit tracker backend", no_args_is_help=True)

ROOT = Path(__file__).resolve().parent.parent


def _setup_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


@app.command()
def api(
    host: str | None = typer.Option(None, help="Defaults to API_HOST"),
    port: int | None = typer.Option(None, help="Defaults to API_PORT"),
    reload: bool = typer.Option(False, help="Auto-reload on code changes (development)"),
) -> None:
    """Run the HTTP API for the UI."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.api.app:create_app",
        factory=True,
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=reload,
        log_level=settings.log_level.lower(),
    )


@app.command()
def worker(
    once: bool = typer.Option(False, help="Run a single scheduler tick without the bot and exit"),
) -> None:
    """Run the scheduler and the Telegram bot (long polling)."""
    from src.worker.runner import run_worker

    _setup_logging()
    asyncio.run(run_worker(get_settings(), once=once))


@app.command()
def migrate(revision: str = typer.Argument("head")) -> None:
    """Apply database migrations (alembic upgrade)."""
    from alembic import command

    _setup_logging()
    command.upgrade(_alembic_config(), revision)


@app.command()
def seed(
    chat_id: int = typer.Option(..., help="Telegram chat id of the user"),
    name: str = typer.Option("Developer", help="Display name"),
    timezone: str | None = typer.Option(None, help="IANA timezone, defaults to DEFAULT_TIMEZONE"),
) -> None:
    """Create a user with the «Утро» routine at 07:00 and sample habits (development)."""
    from src.worker.seed import run_seed

    _setup_logging()
    asyncio.run(run_seed(chat_id, name, timezone or get_settings().default_timezone))


admin_app = typer.Typer(help="Bot access and admins (D-020)", no_args_is_help=True)
app.add_typer(admin_app, name="admin")


def _run_access(action: str, chat_id: int | None = None) -> None:
    from src.worker.admin import run_admin

    _setup_logging()
    asyncio.run(run_admin(action, chat_id))


@admin_app.command("grant")
def admin_grant(chat_id: int = typer.Argument(..., help="Telegram chat id")) -> None:
    """Make a chat an admin (also grants access). Restart the worker to update the menu."""
    _run_access("grant", chat_id)


@admin_app.command("demote")
def admin_demote(chat_id: int = typer.Argument(..., help="Telegram chat id")) -> None:
    """Remove admin rights (access stays). The last admin cannot be demoted."""
    _run_access("demote", chat_id)


@admin_app.command("list")
def admin_list() -> None:
    """Show all chats with their access status."""
    _run_access("list")


@app.command()
def openapi(
    output: Path | None = typer.Option(
        None, "--output", "-o", help="File to write, default stdout"
    ),
) -> None:
    """Print the OpenAPI schema (used to generate UI types)."""
    from src.api.app import create_app

    schema = json.dumps(create_app().openapi(), ensure_ascii=False, indent=2)
    if output is None:
        typer.echo(schema)
    else:
        output.write_text(schema + "\n", encoding="utf-8")
        typer.echo(f"Written {output}")


if __name__ == "__main__":
    app()
