# reminder-backend

Backend трекера привычек Reminder: HTTP API для UI и worker (планировщик + Telegram-бот).

## Быстрый старт

```bash
uv sync
cp .env.example .env          # укажите TELEGRAM_BOT_TOKEN
uv run reminder migrate
uv run reminder api --reload  # http://127.0.0.1:8000/docs
uv run reminder worker        # в отдельном терминале
```

Первый админ: запустите worker, напишите боту — он ответит вашим chat_id, затем
`uv run reminder admin grant <chat_id>` и перезапустите worker. Дальше новые люди
попадают в бот по заявке, которую админ одобряет кнопкой в Telegram.

Документация: [`AGENTS.md`](AGENTS.md) (структура и команды), [`docs/architecture.md`](docs/architecture.md),
[`docs/domain.md`](docs/domain.md), [`docs/decisions.md`](docs/decisions.md). Задачи: [`TASK.md`](TASK.md).
