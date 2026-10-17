# AGENTS.md

FastAPI + SQLAlchemy (async) + SQLite backend for a cram-school system. This repo is the
`backend` only; the Angular frontend lives in a sibling directory. Comments and user-facing
messages are Traditional Chinese (zh-TW) — keep new strings consistent.

## Commands

Run everything from this directory (imports are `app.*`; DB/uploads paths are relative to CWD).

- Install: `pip install -r requirements.txt` (Python 3.10+ locally; Docker image uses 3.11)
- Dev server: `uvicorn app.main:app --reload` → http://127.0.0.1:8000 (`/docs`, health at `/api/v1/health`)
- Tests: `python -m pytest tests -q`
  - `pytest` is **not** in `requirements.txt`; install it separately.
  - Single test: `python -m pytest tests/test_attendance_service.py::AttendanceServiceTest::test_m03_is_attendance_and_idempotent`
  - Tests are `unittest.IsolatedAsyncioTestCase`, use temp SQLite files, and need no external services.
- Seed only the default admin: `python -m app.seed` → `admin@cramschool.com` / `admin`

There is no configured linter/formatter (no ruff/black/pyproject). Do **not** reformat: router
files intentionally use dense multi-statement lines.

## Schema / migrations (biggest gotcha)

Alembic is a dependency but is **not used** — there is no `alembic/` dir or `alembic.ini`.
Migrations are hand-rolled in `app/database.py`, run at startup by `init_db()` (called from
`main.py` startup, before seeding):

- New tables: just define the model; `Base.metadata.create_all` creates it.
- New columns on existing tables: add an `ALTER TABLE ... ADD COLUMN` entry to
  `_add_missing_columns()`. Errors are swallowed, so it is idempotent.
- Changing constraints/nullability (SQLite can't `ALTER`): write a table-rebuild helper like
  `_migrate_students_nullable_user_id()` and call it from `init_db()`.

Startup also seeds the default admin when the `users` table is empty, so a fresh DB is usable
immediately. New SQLAlchemy models must also be exported in `app/models/__init__.py`.

## Wiring

- Routers are mounted under `/api/v1`. To add one, create `app/routers/<name>.py` and register it
  in `app/routers/__init__.py` (`routers` list).
- Layers: `routers/` (HTTP) → `services/` (logic) → `models/` (ORM); request/response shapes in `schemas/`.
  Formatting is done by hand in routers (dicts / Pydantic responses), not via ORM serialization.
- Config: `app/config.py` (`pydantic-settings`) reads `.env` at repo root. `.env` is gitignored but
  already present locally with real secrets; `.env.example` is the template. `CORS_ORIGINS` must be a
  JSON array (e.g. `["http://localhost:4200"]`) — the "comma-separated" comment is wrong.

## Auth & errors

- JWT bearer auth via `app/middleware/auth_middleware.py`; use the role deps (`require_admin`,
  `require_teacher_or_admin`, `require_student`, `require_any_authenticated`).
- `POST /api/v1/punch-events` is the exception: authenticated by `X-Api-Key` (`PUNCH_API_KEY`), not JWT.
- Prefer the custom exceptions in `app/utils/exceptions.py` (`NotFoundException`, `ConflictException`, …)
  which render a `{code, message, details}` envelope. Some older routers raise raw `HTTPException`;
  don't copy that for new code.

## Domain quirks

- Timezone is fixed `TAIPEI_TZ = timezone(timedelta(hours=8))` (`app/services/attendance_service.py`).
  Attendance/punch logic must use it; avoid naive datetimes (a past bug caused 500s on `/auth/refresh`).
- Course `start_time`/`end_time` are stored as `"HHMM"` strings (e.g. `"1830"`); format to `"HH:MM"`
  only in responses. `days_of_week` is a string like `"1,3,5"`.
- Public GET endpoints set `Cache-Control` via `settings.public_cache_control()` (`no-store` while
  `PUBLIC_CACHE_MAX_AGE <= 0`). Do the same for new public listings.
- Uploads are served statically at `/uploads` (plus `/banners`, `/teachers` aliases).

## Dead code

`app/routers/teacheronor.teacher.py` is corrupted (undefined names) and is **not** imported. Ignore
or delete it — the real honors router is `app/routers/honor.py`.

## Deploy

`Dockerfile` builds a slim image running `uvicorn app.main:app` on port 8080 with a `/api/v1/health`
healthcheck. `tests/`, `data/`, `uploads/`, and `.env` are excluded via `.dockerignore`.
