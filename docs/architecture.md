# Architecture

## System components

```mermaid
flowchart LR
    Client[Client / Postman] -->|HTTPS + JWT| Web[Django + DRF<br/>gunicorn]
    Web --> PG[(PostgreSQL<br/>FTS + constraints)]
    Web -->|enqueue| Redis[(Redis broker)]
    Worker[Celery worker] --> Redis
    Worker --> PG
    Worker -->|SMTP / console| Mail[(Email)]
    Beat[Celery beat<br/>every 5 min] -->|schedule| Redis
```

The web process serves the API and enqueues tasks (OTP emails) on Redis. A Celery
worker consumes them; Celery beat periodically enqueues the two scheduled-mail
jobs. Postgres holds all state and enforces the hard invariants (capacity,
single active enrollment, unique email, single email-per-kind).

## Request lifecycle (thin view → service)

```mermaid
flowchart TD
    A[HTTP request] --> B[DRF view + permission classes]
    B --> C[Serializer: validate / shape I/O]
    C --> D[service function]
    D -->|business rule violated| E[raise DomainError]
    D -->|ok| F[(DB write in transaction)]
    E --> G[custom exception handler]
    G --> H["{detail, code}"]
    F --> I[serialized response]
```

## Data model

```mermaid
erDiagram
    USER ||--|| PROFILE : has
    USER ||--o{ EMAILOTP : "receives"
    USER ||--o{ EVENT : "creates (facilitator)"
    USER ||--o{ ENROLLMENT : "enrolls (seeker)"
    EVENT ||--o{ ENROLLMENT : "has"
    ENROLLMENT ||--o{ EMAILLOG : "triggers"
    GROUP ||--o{ USER : "role membership"

    USER {
        int id PK
        string username "opaque uuid"
        string email "UNIQUE(lower(email))"
        string password "hashed"
    }
    PROFILE {
        int user_id FK
        string role "seeker|facilitator"
        datetime email_verified_at
    }
    EMAILOTP {
        int user_id FK
        string code_hash "salted"
        datetime expires_at
        smallint attempts
        datetime invalidated_at
    }
    EVENT {
        int id PK
        string title
        text description
        string language
        string location
        datetime starts_at
        datetime ends_at
        int capacity "nullable = unlimited"
        int created_by FK
    }
    ENROLLMENT {
        int id PK
        int event_id FK
        int seeker_id FK
        string status "enrolled|canceled"
        datetime canceled_at
    }
    EMAILLOG {
        int id PK
        int enrollment_id FK
        string kind "follow_up|reminder"
        datetime sent_at
    }
```

### Key constraints & indexes

| Table | Constraint / index | Why |
|-------|-------------------|-----|
| `auth_user` | `UNIQUE (LOWER(email))` partial index | email-login uniqueness the default User lacks |
| `events_event` | `CHECK (ends_at > starts_at)`, `CHECK (capacity >= 1 OR NULL)` | reject invalid events at the DB |
| `events_event` | GIN index on `to_tsvector(title, description)` | fast full-text `q` search |
| `events_event` | btree on `starts_at`, `language`, `location`, `(location, starts_at)` | filter/order without scans |
| `enrollments_enrollment` | `UNIQUE (event, seeker) WHERE status='enrolled'` | at most one *active* enrollment; re-enroll after cancel allowed |
| `notifications_emaillog` | `UNIQUE (enrollment, kind)` | idempotent scheduled mail |

## The enroll race, sequenced

```mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Postgres (event row)
    A->>DB: BEGIN; SELECT ... FOR UPDATE (event)
    B->>DB: BEGIN; SELECT ... FOR UPDATE (event)
    Note over B,DB: B blocks on A's row lock
    A->>DB: count active vs capacity → seat free → INSERT enrollment
    A->>DB: COMMIT (lock released)
    DB-->>B: lock acquired
    B->>DB: count active vs capacity → full → no insert
    B-->>B: raise EventFull (409)
```

Without the row lock both requests would read the pre-insert count and both
insert. The partial unique constraint would still stop a *duplicate* enrollment,
but not overselling distinct seekers — which is exactly why the lock, not just the
constraint, is required.
