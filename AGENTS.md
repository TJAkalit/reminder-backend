# AGENTS.md — reminder-backend

Контекст для ИИ-агентов. Разработка ведётся на разных ПК, поэтому **всё важное о проекте
хранится в репозитории**, а не в памяти агента. Файл читается в начале каждой сессии.

## Правила для агентов (обязательно)

1. **Ничего не коммитить и не пушить**, пока владелец явно не попросит. Это касается `git commit`,
   `git push`, `git tag`, создания веток/PR. Изменения остаются в рабочем дереве.
2. **Вести `TASK.md`**: перед началом работы отметить задачу как «в работе», по завершении —
   отметить выполненной; новые идеи и найденные проблемы добавлять в бэклог.
3. **Обновлять этот `AGENTS.md`**, если принято архитектурное решение, изменились соглашения,
   команды запуска или структура проекта. Решения фиксировать в `docs/decisions.md`.
4. Решения со статусом `proposed` в `docs/decisions.md` не считаются принятыми — перед
   реализацией уточнить у владельца.
5. Язык документации и общения — русский. Код, идентификаторы, коммиты — на английском.

## О проекте

**Reminder** — pet-проект для трекинга привычек. Telegram-бот в заданное время присылает
чек-лист привычек (MVP — утренние привычки, напр. в 07:00), пользователь отмечает выполненные
кнопками прямо в сообщении. Веб-UI показывает привычки, расписание, серии (streaks) и отметки
о достижениях (milestones: 7, 21, 30… дней подряд).

Проект будет расти: новые группы привычек (вечер, будни/выходные), другие временные паттерны.

Репозитории (лежат рядом в одном каталоге):

| Репозиторий        | Назначение                                                  |
|--------------------|-------------------------------------------------------------|
| `reminder-backend` | API (FastAPI), воркер (планировщик + Telegram-бот), БД, миграции |
| `reminder-ui`      | SPA (Vite + React + TS), собирается в статику для nginx      |

## Документация

- `docs/architecture.md` — архитектура всей системы (оба репозитория), процессы, деплой.
- `docs/domain.md` — доменная модель, расписания, правила подсчёта серий и milestones.
- `docs/decisions.md` — журнал архитектурных решений (ADR-lite) и открытые вопросы.
- `TASK.md` — текущие задачи.

## Стек (принят, см. decisions.md)

Python 3.14 (`requires-python >=3.14`), uv, FastAPI, SQLAlchemy 2.1 (async), Alembic, Pydantic v2 + pydantic-settings,
aiogram 3 (Telegram, long polling), Typer (CLI), ruff, mypy, pytest.

БД: **PostgreSQL 15** (asyncpg) на домашнем сервере 172.16.71.198 (aarch64), БД `reminder`,
схема `reminder` (`DATABASE_SCHEMA`) — D-003. SQLite (aiosqlite) по-прежнему поддерживается:
им пользуются быстрые тесты и можно работать локально без сервера.
Код обязан оставаться переносимым: без диалект-специфичных типов, время через `UTCDateTime`,
Alembic с `render_as_batch=True`.

## Ключевые решения (кратко)

- Привычки сгруппированы в рутины; рутина = расписание = одно сообщение-чек-лист (D-008).
- Планировщик — `tick()` по `next_run_at` в БД; повторных напоминаний нет (D-006, D-015).
- Серии — по запланированным occurrence; `skipped` рвёт серию (D-009, D-014).
- Чек-лист можно отмечать до конца локальных суток, потом он закрывается (D-018).
- Milestones — значки 7/14/21/30/66/100/180/365 (D-017).
- Привычки добавляются интерактивной командой бота `/add` (D-016).
- Аутентификации нет: UI выбирает пользователя, заголовок `X-User-Id` (D-013).
- Доступ к боту — в БД (`chat_access`), заявки и команды админа в боте, первый админ — CLI (D-020).
- Расписание рутины — RRULE (RFC 5545) в локальном времени пользователя, `python-dateutil` (D-007).
- Деплой — отложен.

## Структура кода (`src/` — корневой пакет, импорты `from src.… import …`)

Слоистая «чистая архитектура» с послаблениями ради удобства: сервисы работают с
`AsyncSession` SQLAlchemy напрямую (отдельного слоя репозиториев нет), DTO возвращаются
сервисами сразу в формате ответа API.

| Папка          | Что лежит | Зависит от |
|----------------|-----------|------------|
| `src/domain/`  | Чистая логика без БД и фреймворков: расписания (RRULE), серии, milestones, время/TZ, enum'ы | — |
| `src/model/`   | ORM-модели SQLAlchemy, по файлу на сущность | domain, db |
| `src/db/`      | `Base`, naming convention, `UTCDateTime`, `str_enum`, engine/сессии, PRAGMA SQLite | config |
| `src/dto/`     | Pydantic-схемы ответов API и представление чек-листа для бота | domain |
| `src/service/` | Бизнес-логика (сценарии): user, routine, habit, checklist, today, scheduler, progress | domain, model, dto |
| `src/api/`     | Роутеры FastAPI (по файлу на сущность), `deps.py`, `app.py` | service, dto |
| `src/bot/`     | aiogram: handlers, клавиатуры, тексты, middleware, `TelegramNotifier` | service, dto |
| `src/worker/`  | Цикл планировщика + запуск polling, seed | service, bot |
| `src/cli.py`   | Typer: точки входа процессов | всё |

Правила:
- `domain/` ничего не импортирует из остальных слоёв.
- `service/` не знает про FastAPI и aiogram. Отправка в Telegram — через порт
  `service/notifier.py::ChecklistNotifier`; реализация — `bot/notifier.py`, в тестах — `FakeNotifier`.
- Сервисы, которые меняют данные, сами делают `commit()`.
- Время — всегда aware UTC; в сервисы передаётся `now` (для тестов), по умолчанию `now_utc()`.
- Отношения моделей объявлены `lazy="raise"`: связанные данные грузим явно
  (`selectinload`/`joinedload`), иначе в async будет ошибка.
- Изменил модели → `uv run alembic revision --autogenerate -m "..."`, проверить файл миграции.
  Тест `tests/test_migrations.py` падает, если модели и миграции разошлись.

## Команды

```bash
uv sync                                  # зависимости (+ dev)
cp .env.example .env                     # настройки (TELEGRAM_BOT_TOKEN и т.д.)
uv run reminder migrate                  # alembic upgrade head
uv run reminder seed --chat-id <id>      # dev-данные: пользователь + «Утро 07:00» + 3 привычки
uv run reminder api --reload             # HTTP API на 127.0.0.1:8000, docs: /docs
uv run reminder worker                   # планировщик + Telegram-бот (long polling)
uv run reminder worker --once            # один tick планировщика без бота
uv run reminder openapi -o openapi.json  # схема для генерации типов UI
uv run reminder admin grant <chat_id>    # назначить админа (и открыть доступ)
uv run reminder admin list               # кто имеет доступ

uv run pytest                            # тесты на SQLite в памяти (быстро)
TEST_DATABASE_URL=postgresql+asyncpg://reminder:***@172.16.71.198:5432/reminder \
  uv run pytest                          # те же тесты на PostgreSQL, временная схема на тест
uv run ruff format . && uv run ruff check .
uv run mypy src tests                    # strict

docker build -t reminder-backend .       # образ (для сервера: buildx --platform linux/arm64)
docker run --env-file .env reminder-backend migrate   # роли: api (по умолчанию) | worker | migrate | admin
```

На этом ПК `uv` установлен в pyenv: `~/.pyenv/versions/3.14.7/bin/uv` (не в PATH).

## Состояние

Реализованы этапы 1–4 (каркас, домен, API, worker + бот). Работа с ботом проверена только
тестами — вживую с реальным токеном ещё не запускался. См. `TASK.md`.
