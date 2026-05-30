# Epic E091 — PostgreSQL/Redis Checkpoint Backends

**Cíl:** Přidat produkční checkpoint backends — PostgreSQL přes `asyncpg` a Redis přes
`redis[asyncio]`. Oba dostupné jako volitelné závislosti. Docker Compose pro lokální vývoj.

**Root:** `src/agentflow/statemachine/`

---

## Scope

| Oblast | Co se mění |
|--------|-----------|
| `docker-compose.yml` (root) | Nový soubor — postgres + redis pro vývoj/testování |
| `pyproject.toml` | Nové optional deps: `postgres` a `redis` extras |
| `src/agentflow/statemachine/backends/postgres_checkpoint_store.py` | Nový `PostgresCheckpointStore` |
| `src/agentflow/statemachine/backends/redis_checkpoint_store.py` | Nový `RedisCheckpointStore` |
| `src/agentflow/statemachine/__init__.py` | Export obou stores |
| `src/agentflow/tests/statemachine/backends/test_postgres_checkpoint_store.py` | Integration tests |
| `src/agentflow/tests/statemachine/backends/test_redis_checkpoint_store.py` | Integration tests |
| `README.docker.md` (root) | Instrukce pro docker compose |
| `src/agentflow/statemachine/README.md` | Sekce o checkpoint backends |

---

## Task List

| Task | Název | Závisí na |
|------|-------|-----------|
| T010 | docker-compose + PostgresCheckpointStore + integration tests | E090 done |
| T020 | RedisCheckpointStore + integration tests + docs | T010 |

---

## T010 — docker-compose + PostgresCheckpointStore

### Docker Compose

Vytvořit `docker-compose.yml` v root projektu:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: agentflow
      POSTGRES_USER: agentflow
      POSTGRES_PASSWORD: agentflow
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentflow"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
```

### pyproject.toml extras

```toml
[project.optional-dependencies]
postgres = [
    "asyncpg>=0.29",
]
redis = [
    "redis[asyncio]>=5.0",
]
```

### PostgresCheckpointStore

Implementovat v `src/agentflow/statemachine/backends/postgres_checkpoint_store.py`.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS agentflow_checkpoints (
    run_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    state_type TEXT NOT NULL,
    state_json TEXT NOT NULL,
    active_nodes JSON NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (run_id, step)
);
```

**API:**
```python
class PostgresCheckpointStore:
    def __init__(self, dsn: str) -> None: ...
    async def connect(self) -> None:      # create pool + ensure table
    async def close(self) -> None:        # close pool
    async def __aenter__(self): ...
    async def __aexit__(self, *a): ...
    async def save(self, record: CheckpointRecord) -> None: ...
    async def load(self, run_id: str, step: int) -> CheckpointRecord: ...
    async def list_steps(self, run_id: str) -> list[int]: ...
```

Serialization: `dataclasses.asdict(record.state)` → `json.dumps()` → TEXT column.
Deserialization: accept optional `state_factory` kwarg (same pattern as `JsonFileCheckpointStore`).

### Integration tests

File: `src/agentflow/tests/statemachine/backends/test_postgres_checkpoint_store.py`

Mark all tests `@pytest.mark.integration` — skipped by default.

Use DSN from env: `POSTGRES_DSN` (default: `postgresql://agentflow:agentflow@localhost:5432/agentflow`).

Tests:
1. `test_save_and_load_roundtrip` — save then load, assert equality
2. `test_list_steps` — save 3 steps, assert list_steps returns [1,2,3]
3. `test_load_missing_raises_keyerror`
4. `test_overwrite_same_step` — save step 1 twice, load returns second

---

## T020 — RedisCheckpointStore + docs

### RedisCheckpointStore

Implementovat v `src/agentflow/statemachine/backends/redis_checkpoint_store.py`.

**Key scheme:**
```
agentflow:checkpoint:{run_id}:{step:04d}  →  JSON string (full CheckpointRecord payload)
agentflow:steps:{run_id}                  →  Redis sorted set (score=step, member=step)
```

**API:**
```python
class RedisCheckpointStore:
    def __init__(self, url: str = "redis://localhost:6379") -> None: ...
    async def connect(self) -> None:
    async def close(self) -> None:
    async def __aenter__(self): ...
    async def __aexit__(self, *a): ...
    async def save(self, record: CheckpointRecord) -> None: ...
    async def load(self, run_id: str, step: int) -> CheckpointRecord: ...
    async def list_steps(self, run_id: str) -> list[int]: ...
```

Use `redis.asyncio.from_url(self._url)` for the connection.

### Integration tests

File: `src/agentflow/tests/statemachine/backends/test_redis_checkpoint_store.py`

Mark all tests `@pytest.mark.integration` — skipped by default.

Use URL from env: `REDIS_URL` (default: `redis://localhost:6379`).

Same 4 tests as Postgres.

### Docs — README.docker.md

Vytvořit `README.docker.md` v root projektu:

```markdown
# Docker Development Environment

## Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| postgres | postgres:16-alpine | 5432 | PostgreSQL checkpoint backend |
| redis | redis:7-alpine | 6379 | Redis checkpoint backend |

## Quick Start

```bash
# Start all services
docker compose up -d

# Check health
docker compose ps

# Stop services
docker compose down
```

## Running integration tests

```bash
# Install extras
uv pip install -e ".[postgres,redis]"

# With docker services running:
pytest -m integration
```

## Cleanup

```bash
docker compose down -v  # remove containers + volumes
docker system prune -f
```
```

### Update statemachine/README.md

Přidat sekci "Checkpoint Backends" documenting:
- Existing: InMemoryCheckpointStore, JsonFileCheckpointStore
- New: PostgresCheckpointStore, RedisCheckpointStore
- Install instructions (optional deps)
- Basic usage code example

---

## Definition of Done (Epic Level)

- [ ] `docker-compose.yml` existuje s postgres + redis
- [ ] `uv pip install -e ".[postgres,redis]"` funguje
- [ ] `PostgresCheckpointStore` implementován, mypy --strict zelený
- [ ] `RedisCheckpointStore` implementován, mypy --strict zelený
- [ ] Integration tests v `backends/` (4 testy na store)
- [ ] `README.docker.md` v root
- [ ] `statemachine/README.md` — nová sekce backends
- [ ] `agentflow/statemachine/__init__.py` exportuje `PostgresCheckpointStore`, `RedisCheckpointStore`
