# Архитектура системы Reminder

> Статус: этап планирования, ключевые решения приняты (2026-10-18), см. `decisions.md`.
> Документ описывает оба репозитория.

## Компоненты

```
                 ┌──────────────────────────── Домашний сервер ─────────────────────────┐
  Браузер ──────►│ nginx (reminder-ui)                                                  │
                 │   /        → статика SPA (index.html, fallback для React Router)      │
                 │   /api/*   → proxy_pass ──► reminder api (FastAPI) ──┐               │
                 │                                                       ├──► БД*        │
  Telegram ◄────►│ reminder worker ─────────────────────────────────────┘               │
  (Bot API)      │   • scheduler loop: раз в N секунд ищет «пора отправить»             │
                 │   • aiogram long polling: нажатия кнопок чек-листа, команды          │
                 └──────────────────────────────────────────────────────────────────────┘
```

\* БД: SQLite в разработке → существующий сервер PostgreSQL перед MVP (D-003).
В разработке роль nginx выполняет dev proxy Vite (`/api` → `localhost:8000`).

| Модуль   | Где                    | Ответственность |
|----------|------------------------|-----------------|
| UI       | `reminder-ui`          | Отображение привычек, расписаний, серий, milestones |
| API      | `reminder-backend`, `reminder api` | REST для UI, OpenAPI-схема — источник типов для UI |
| Worker   | `reminder-backend`, `reminder worker` | Отправка чек-листов по расписанию, приём ответов из Telegram |
| БД       | SQLite → PostgreSQL    | Единственный источник состояния |

API и worker не общаются напрямую — только через БД. Это упрощает деплой и перезапуски.

## Почему worker = тот же пакет, но отдельный процесс

- Нет дублирования моделей и бизнес-логики.
- API можно перезапускать/масштабировать независимо от бота.
- У Telegram long polling может быть только **один** потребитель на токен — поэтому бот
  живёт в одном процессе worker, а не в каждом воркере uvicorn.

Long polling выбран вместо webhook: не нужен публичный HTTPS-адрес, работает с домашнего
сервера за NAT. Переход на webhook позже — это замена транспорта в aiogram, логика не меняется.

## Планировщик: модель «tick»

Вместо хранения задач в памяти (APScheduler, cron внутри процесса) состояние расписания в БД:

1. У каждой рутины (группы привычек) хранится `next_run_at` (UTC).
2. Worker каждые ~30 с выполняет `tick()`:
   - выбирает активные рутины с `next_run_at <= now()`;
   - создаёт запись `occurrence`; уникальный индекс `routine_id + scheduled_for` гарантирует
     отсутствие дублей при рестартах (работает и в SQLite, и в PostgreSQL — без
     `FOR UPDATE SKIP LOCKED`, worker один);
   - отправляет сообщение-чек-лист, сохраняет `telegram_message_id`;
   - вычисляет следующий `next_run_at` из правила расписания (RRULE, D-007).
3. Если worker лежал и опоздал больше чем на `grace period` (напр. 2 ч) — occurrence
   помечается `missed`, сообщение не отправляется.
4. Повторных напоминаний нет (D-015): одна отправка на occurrence.

Плюсы: переживает рестарты, идемпотентно, легко тестировать (`tick(now=...)`), `tick` можно
вызвать вручную из CLI (`reminder worker tick --once`) или даже из системного cron.

## Чек-лист в Telegram

Одно сообщение на occurrence рутины:

```
🌅 Утро · 18 окт
[ ⬜ Стакан воды      ]
[ ✅ Зарядка 10 мин   ]
[ ⬜ Без телефона 30м ]
```

Каждая строка — inline-кнопка. Нажатие → `callback_query` → отметка в БД → бот
редактирует то же сообщение (`editMessageReplyMarkup`). Когда всё выполнено — итог
и, при достижении, поздравление с milestone («🔥 21 день подряд!»).

## Безопасность (MVP)

- Доступ к боту хранится в БД (`chat_access`, D-020). Неизвестный чат создаёт заявку, админы
  одобряют её кнопкой в Telegram или выдают доступ командой `/allow <chat_id>`.
- Сервер домашний, наружу не открыт. Аутентификации в MVP нет (D-013):
  UI показывает селектор пользователя, клиент шлёт заголовок `X-User-Id`,
  бэкенд резолвит его в зависимости `get_current_user`.
- Позже — вход через Telegram Login Widget или Telegram Mini App `initData`; меняется только
  `get_current_user`.

## Время и часовые пояса

- В БД всё хранится в UTC: тип `UTCDateTime` (TypeDecorator) — в SQLite строка ISO в UTC,
  в PostgreSQL `timestamptz`.
- У пользователя есть `timezone` (IANA, напр. `Europe/Moscow`), расписание задаётся в
  локальном времени («07:00»), пересчёт через `zoneinfo` — корректно при переходах DST.
- «День» для серий считается в локальной таймзоне пользователя.

## Деплой

Сервер — **aarch64** (ARM): образы для него собираются под `linux/arm64`.

### Образы (готовы)
- `reminder-backend/Dockerfile`: uv → `python:3.14-slim`, пользователь `reminder` (uid 10001),
  `ENTRYPOINT ["reminder"]`, по умолчанию `CMD ["api"]` на `0.0.0.0:8000`. Один образ для всех
  ролей: `api`, `worker`, `migrate`, `admin …`. Конфигурация — только через env.
- `reminder-ui/Dockerfile`: `node:24-alpine` (`npm ci && npm run build`) → `nginx:1.29-alpine`.
  Конфиг `nginx/default.conf.template`: SPA fallback, `/api/` → `${API_UPSTREAM}`
  (по умолчанию `http://api:8000`), вечный кэш `/assets/*`, `no-cache` для `index.html`, gzip.
- Секреты (`.env`, токен бота) в образы не попадают (`.dockerignore`); передаются при запуске.

### Ещё не сделано
- `docker-compose.yml`: `migrate` (one-shot) → `api`, `worker`, `ui`; PostgreSQL внешний.
  Где хранить compose — решим при запуске.
- Публикация в `ghcr.io/tjakalit/…` и сборка под arm64 (buildx + qemu или сборка на сервере).

## Конфигурация (env, pydantic-settings)

| Переменная                  | Пример                                   |
|-----------------------------|------------------------------------------|
| `DATABASE_URL`              | `postgresql+asyncpg://reminder:***@172.16.71.198:5432/reminder` (или `sqlite+aiosqlite:///./reminder.db` локально) |
| `DATABASE_SCHEMA`           | `reminder` (только PostgreSQL) |
| `TELEGRAM_BOT_TOKEN`        | `123:ABC…`                               |
| `WORKER_TICK_SECONDS`       | `30`                                     |
| `WORKER_GRACE_MINUTES`      | `120`                                    |
| `LOG_LEVEL`                 | `INFO`                                   |

## Структура backend

Актуальная структура и правила слоёв — в `AGENTS.md` («Структура кода»). Код лежит в `src/`
(корневой пакет), слои: `domain` → `model`/`db` → `dto` → `service` → `api` / `bot` / `worker`.

`domain/` не зависит от БД и фреймворков → покрывается быстрыми unit-тестами
(серии и расписания — самое ошибкоопасное место).
