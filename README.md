# Ahoum Events Platform — Backend

A Django + DRF events backend with email-OTP auth, role-based access control,
Postgres full-text search, capacity-respecting enrollments, and scheduled email
notifications. Two roles: **Seeker** (browses and enrolls) and **Facilitator**
(creates and manages events).

Built for the Ahoum backend task. The interesting parts aren't the endpoints —
every brief produces those — they're the decisions at the edges: keeping Django's
default `User` while signup exposes no username, OTP done like a security engineer,
capacity that holds under a thundering herd, and scheduled mail that never
double-sends. Those are written up in [Design decisions](#design-decisions--tradeoffs).

- **Live demo:** _(added after deploy — see [Deployment](#deployment))_
- **API docs (Swagger):** `/api/docs/` · **OpenAPI schema:** `/api/schema/`
- **Postman collection:** [`docs/postman_collection.json`](docs/postman_collection.json)
- **Architecture & ER diagram:** [`docs/architecture.md`](docs/architecture.md)

---

## Quickstart (Docker — one command)

```bash
docker compose up --build
```

That builds the image and starts five services — API, Postgres, Redis, a Celery
worker, and Celery beat. On startup the web container runs migrations, collects
static files, and seeds demo data. When it's up:

- API: <http://localhost:8000/api/>
- Swagger UI: <http://localhost:8000/api/docs/>

Seeded demo accounts (all already verified, password `demopass123!`):

| Role | Email |
|------|-------|
| Facilitator | `facilitator@demo.ahoum.com` |
| Seeker | `seeker@demo.ahoum.com` |
| Seeker | `seeker2@demo.ahoum.com` |

Emails (OTP, follow-ups, reminders) use the console backend in the demo — watch
them in the logs: `docker compose logs -f worker`.

## Quickstart (local, without Docker)

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and a running Postgres + Redis.

```bash
cp .env.example .env            # adjust DATABASE_URL / REDIS_URL if needed
uv sync                         # install deps (incl. dev)
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py runserver
# in separate shells, for scheduled mail:
uv run celery -A config worker -l info
uv run celery -A config beat -l info
```

A `Makefile` wraps the common commands — run `make help` to see them
(`make migrate`, `make run`, `make test`, `make seed`, `make up`, …).

## Environment variables

| Variable | Purpose | Default (dev) |
|----------|---------|---------------|
| `DJANGO_SETTINGS_MODULE` | Which settings module | `config.settings.local` |
| `DJANGO_SECRET_KEY` | Secret key (required in prod) | dev placeholder |
| `DJANGO_DEBUG` | Debug mode | `true` local |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts | `localhost,127.0.0.1` |
| `DATABASE_URL` | Postgres DSN | `postgres://ahoum:ahoum@localhost:5432/ahoum` |
| `REDIS_URL` | Celery broker | `redis://localhost:6379/0` |
| `EMAIL_URL` | Email transport (`consolemail://` or SMTP) | `consolemail://` |
| `CELERY_TASK_ALWAYS_EAGER` | Run tasks inline (no worker) | `false` |
| `OTP_TTL_SECONDS` / `OTP_MAX_ATTEMPTS` / `OTP_RESEND_COOLDOWN_SECONDS` | OTP policy | `300` / `5` / `60` |

See [`.env.example`](.env.example) for the full list.

## Running the tests

```bash
make test          # or: uv run pytest
```

55 tests covering the auth/OTP edges, the RBAC matrix, search/filter/ordering,
enrollment rules, scheduled-mail idempotency, the error contract, and — the
headline — a **real threaded race** for the last seat
([`tests/test_concurrency.py`](tests/test_concurrency.py)). CI runs ruff + the
suite against a Postgres service container on every push
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

---

## API overview

All endpoints are under `/api/` and require a `Bearer <access>` JWT except the
auth endpoints and the docs. Responses are DRF-paginated
(`{count, next, previous, results}`); errors follow a single contract
(see below).

| Method & path | Role | Notes |
|---|---|---|
| `POST /api/auth/signup` | anon | `{email, password, role}` → sends OTP |
| `POST /api/auth/verify-email` | anon | `{email, otp}` → marks verified |
| `POST /api/auth/resend-otp` | anon | 60s cooldown, generic response |
| `POST /api/auth/login` | anon | `{email, password}` → `{access, refresh}` |
| `POST /api/auth/refresh` | anon | rotates refresh token (old one blacklisted) |
| `GET /api/auth/me` | any | current user + role + verification |
| `GET /api/events/` | any | filters: `location, language, starts_after, starts_before, q`; `ordering`; upcoming-first by default |
| `POST /api/events/` | facilitator | create |
| `GET /api/events/{id}/` | any | retrieve |
| `PATCH/DELETE /api/events/{id}/` | owner facilitator | update/delete |
| `GET /api/events/mine/` | facilitator | own events + `total_enrollments`, `available_seats` |
| `POST /api/events/{id}/enroll/` | seeker | enroll (capacity- and concurrency-safe) |
| `POST /api/events/{id}/cancel/` | seeker | cancel own enrollment |
| `GET /api/enrollments/?when=upcoming\|past` | seeker | list own enrollments |

### Error contract

Every error response — validation, auth, permission, 404, domain rule, even an
unhandled 500 — has the same shape:

```json
{ "detail": "This event has reached its capacity.", "code": "event_full" }
```

Validation errors add a per-field `errors` map. Codes are a fixed enum
([`apps/common/errors.py`](apps/common/errors.py)) so clients never match on
message strings. Enforced by a custom exception handler
([`apps/common/exceptions.py`](apps/common/exceptions.py)).

---

## Design decisions & tradeoffs

### 1. Default `User` model, but signup takes no username

The spec mandates Django's default `User` (which requires a unique `username`)
while forbidding a `username` field in signup. I generate an opaque
`uuid4().hex[:30]` username at creation — never derived from the email, since
emails are PII and normalize-collide. Role and verification state live on a
`Profile` (OneToOne → User).

Django's default `User.email` is **not unique**, which is a real bug for an
email-login system. Rather than swap the User model (disallowed), I close the gap
at the database level with a **case-insensitive unique index**
(`CREATE UNIQUE INDEX … ON auth_user (LOWER(email))`, see
[`accounts/migrations/0002`](apps/accounts/migrations/0002_roles_and_email_unique.py)).
That's the strongest possible guarantee — it holds even against raw SQL.

### 2. RBAC via Django Groups (not a role string check)

Signup adds each user to a `seeker` or `facilitator` **Group**, and the DRF
permission classes (`IsSeeker`, `IsFacilitator`, `IsEventOwnerOrReadOnly`) key off
group membership. This uses Django's real permission machinery as the brief asks,
and leaves room to attach granular `Permission`s later. The JWT carries a `role`
claim for client convenience, but the server never trusts it — permissions
re-check the database.

### 3. OTP handled like a security engineer

- Only a **salted hash** of the 6-digit code is stored (`make_password` /
  `check_password`), never the code.
- 5-minute TTL, 5-attempt cap (then the code is dead), 60-second resend cooldown.
- The attempt counter **persists even on a wrong guess** — the verify path commits
  the increment and *then* raises, because raising inside the transaction would
  roll the increment back (a subtle bug this codebase explicitly avoids and tests).
- **Anti-enumeration:** signup and resend return an identical generic response
  whether or not the email exists, so the API can't be used to probe which emails
  are registered. _Tradeoff:_ a user gets less precise feedback; for an auth
  surface that's the right trade. An alternative (explicit `409`/`429`) is noted
  in the code.

### 4. Capacity under concurrency — the centerpiece

Two requests racing for the last seat must not both win. The enroll path
([`enrollments/services.py`](apps/enrollments/services.py)) opens a transaction,
takes a **row lock on the event** (`select_for_update`), then counts active
enrollments against capacity — so contending transactions serialize instead of
both reading "0 of 1 taken".

The database is the backstop regardless of app code: a **partial unique
constraint** `(event, seeker) WHERE status = 'enrolled'` makes a double active
enrollment impossible, while still allowing re-enrollment after a cancel
(cancellations flip `status` and keep the row — an audit trail, not a delete).

This is proved, not asserted: [`tests/test_concurrency.py`](tests/test_concurrency.py)
spawns 12 threads through a barrier at one 3-seat event and checks that exactly 3
win; a second test fires one seeker at an event 8 times concurrently and confirms
a single active enrollment.

### 5. Scheduled mail that never double-sends

The naive approach ("email everyone who enrolled between 60 and 65 minutes ago")
is fragile — miss a beat tick and people are skipped; overlap and they're emailed
twice. Instead there's an **`EmailLog`** table with a unique constraint on
`(enrollment, kind)`. The beat tasks select eligible enrollments that *lack* a log
row, then `get_or_create` the row before sending. The unique constraint makes the
whole thing idempotent under retries, overlapping runs, and worker crashes. Two
tasks run every 5 minutes: a follow-up 1h after enrollment and a reminder within
the hour before an event starts. Proven by running each task twice and asserting a
single email ([`tests/test_notifications.py`](tests/test_notifications.py)).

### 6. Thin views, logic in services

Views and serializers do I/O shaping only; business rules live in `services.py`
functions (`signup`, `verify_email`, `enroll`, `cancel`) that raise typed
`DomainError`s. This keeps the rules testable in isolation and the HTTP layer
boring.

### Other choices

- **Full-text search**: `q` uses a Postgres `SearchVector` backed by a **GIN
  index**, OR'd with `icontains` so partial tokens the stemmer would miss still
  match. Other filters and ordering are indexed (`starts_at`, `language`,
  `location`, `(location, starts_at)`).
- **JWT lifetimes**: 15-min access, 7-day refresh, with rotation + blacklist of
  the old refresh token on every refresh.
- **Settings split**: `base/local/test/production`, all env-driven via
  `django-environ` (12-factor). Production turns on SSL redirect, HSTS, secure
  cookies, and proxy-header handling.

---

## Deployment

The repo includes a [`render.yaml`](render.yaml) blueprint targeting Render
(web service + managed Postgres + Key Value/Redis). On Render's free tier there
are no separate background workers, so the demo runs gunicorn + the Celery worker
+ beat together in one service via `honcho` ([`Procfile`](Procfile)) — explicitly
a demo compromise; in production these are separate scalable services (as they are
in `docker-compose.yml`).

_Live URL: added here after deploy._

## Project layout

```
apps/
  common/         TimeStampedModel, ErrorCode, DomainError, exception handler, pagination, seed
  accounts/       Profile, EmailOTP, auth services, JWT login, RBAC permissions
  events/         Event model, search FilterSet, CRUD, facilitator dashboard
  enrollments/    Enrollment, concurrency-safe enroll/cancel, listings
  notifications/  EmailLog, email rendering, Celery tasks (OTP + scheduled mail)
config/           settings/{base,local,test,production}, urls, celery, wsgi
tests/            mirrors apps; factories; conftest; test_concurrency
docs/             architecture.md, postman_collection.json
```
