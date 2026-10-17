# TASK.md — reminder-backend

Обозначения: `[ ]` — не начато, `[~]` — в работе, `[x]` — сделано.
Агент обновляет этот файл по ходу работы (см. AGENTS.md).

## Этап 0. Планирование
- [x] Зафиксировать требования и предложения по архитектуре (`docs/`)
- [x] Ответить на открытые вопросы, принять решения D-001…D-019
- [x] Выбрать формат расписания — RRULE (D-007)
- [x] Решить, когда закрывается чек-лист — до конца локальных суток (D-018)

## Этап 1. Каркас проекта
- [x] uv-проект, пакет `src` (hatchling), Python 3.14
- [x] ruff, mypy (strict), pytest (+ pytest-asyncio)
- [x] `config.py` на pydantic-settings, `.env.example`
- [x] Typer CLI: `reminder api | worker | migrate | seed | openapi`
- [x] SQLAlchemy async + aiosqlite; PRAGMA WAL / busy_timeout / foreign_keys
- [x] Тип `UTCDateTime` (TypeDecorator)
- [x] Alembic: async env, `render_as_batch=True`, naming convention
- [x] `GET /api/health`

## Этап 2. Домен и БД
- [x] Модели: User, Routine, Habit, Occurrence, HabitCheck, HabitMilestone
- [x] Первая миграция + тест «миграции = модели»
- [x] `domain/schedule.py`: RRULE, следующий запуск, запуски за день, DST, INTERVAL, описание на русском
- [x] Пресеты расписаний (каждый день / будни / выходные)
- [x] `domain/streak.py`: текущая/лучшая серия, % за 30 дней
- [x] `domain/milestone.py`: пороги, «до следующего»
- [x] `reminder seed`

## Этап 3. API для UI (read-only)
- [x] `get_current_user` по заголовку `X-User-Id`
- [x] `/api/v1/users`, `/api/v1/today`, `/api/v1/routines`
- [x] `/api/v1/habits`, `/api/v1/habits/{id}`, `/api/v1/habits/{id}/history`
- [x] `reminder openapi`

## Этап 4. Worker и Telegram-бот
- [x] `tick()`: выборка по `next_run_at`, уникальный occurrence, grace period → `missed`, догон после простоя
- [x] Отправка чек-листа (inline-клавиатура), нажатия ⬜ → ✅ → ⏭ → ⬜, редактирование сообщения
- [x] «День закрыт» после полуночи, закрытие occurrence и снятие кнопок
- [x] Поздравление с milestone
- [x] `/start`, `/help`, `/timezone`, `/cancel`
- [x] `/add` — интерактивный диалог (FSM)
- [x] `/today`, `/habits`, `/archive`
- [ ] Проверить бота вживую с реальным токеном (нужен токен от @BotFather)

## Этап 4.1. Доступ и админка в боте (D-020)
- [x] Таблица `chat_access` (pending / allowed / denied, is_admin) вместо TELEGRAM_ALLOWED_CHAT_IDS
- [x] Миграция переносит уже зарегистрированных пользователей в «доступ есть»
- [x] `AccessService`: заявки, разрешить/отклонить/отозвать, защита последнего админа
- [x] Middleware: неизвестный чат → заявка админам с кнопками «Разрешить / Отклонить»
- [x] Команды админа: `/admin`, `/users`, `/requests`, `/allow <chat_id>`, `/revoke <chat_id>`
- [x] Меню команд: админы видят свои команды (обновляется при старте worker)
- [x] CLI: `reminder admin grant | demote | list`
- [x] Планировщик и API игнорируют пользователей без доступа
- [x] Назначить владельца (416096317) админом
- [ ] Проверить заявку вживую со второго Telegram-аккаунта

## Этап 5. Переезд на PostgreSQL (перед MVP)
- [x] asyncpg, настройка `DATABASE_SCHEMA` (в `public` у роли нет CREATE — PG 15), пулы 5+5
- [x] Миграции на сервере 172.16.71.198 (PG 15, aarch64), схема `reminder`
- [x] Все тесты проходят на PostgreSQL (`TEST_DATABASE_URL`, временная схема на тест)
- [x] Разовый перенос данных из SQLite (копия: `reminder.db.bak-before-postgres`), рабочий `.env` → PG

## Этап 6. Деплой на домашний сервер (aarch64)
- [x] Dockerfile (uv, multi-stage, non-root, один образ на все роли); проверен на amd64 с PostgreSQL
- [ ] Собрать под `linux/arm64` (buildx + qemu на ПК или `docker build` на самом сервере)
- [ ] Опубликовать в ghcr.io (`ghcr.io/tjakalit/reminder-backend`)
- [ ] docker-compose: migrate → api, worker, ui; где хранить — решить

## Отложено
- [ ] Бэкапы БД

## Бэклог / идеи
- [ ] Админка в веб-UI (после входа через Telegram, D-020)
- [ ] Назначение/снятие админов командой в боте (сейчас только CLI)
- [ ] Привычка, добавленная днём, сразу появляется в сегодняшнем открытом чек-листе
- [ ] FSM-хранилище бота переживает рестарт (сейчас MemoryStorage — незаконченный /add теряется)
- [ ] Тесты хендлеров бота через `Dispatcher.feed_update` с замоканным Bot API
- [ ] Вечерняя рутина, рутины по будням/выходным (через /add уже можно создать)
- [ ] Цели вида «N раз в неделю» без фиксированного времени
- [ ] CRUD привычек и рутин через API (для редактирования из UI)
- [ ] Авторизация через Telegram: Login Widget / Mini App initData (заменит `X-User-Id`)
- [ ] Webhook вместо long polling
- [ ] Еженедельная сводка в Telegram
