# Docker Development Environment

Infrastructure services for local development and integration testing.

## Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `postgres` | `postgres:16-alpine` | `5432` | PostgreSQL checkpoint backend |
| `redis` | `redis:7-alpine` | `6379` | Redis checkpoint backend |

## Quick Start

```bash
# Start all services in background
docker compose up -d

# Verify services are healthy
docker compose ps

# View logs
docker compose logs -f
```

## Installing optional backends

```bash
# PostgreSQL backend
uv pip install -e ".[postgres]"

# Redis backend
uv pip install -e ".[redis-backend]"

# Both
uv pip install -e ".[postgres,redis-backend]"
```

## Running integration tests

Integration tests require running Docker services and optional backend packages.

```bash
# Start services
docker compose up -d

# Install extras
uv pip install -e ".[postgres,redis-backend]"

# Run all integration tests
uv run pytest -m integration

# PostgreSQL tests only
uv run pytest tests/agentflow/statemachine/backends/test_postgres_checkpoint_store.py -m integration

# Redis tests only
uv run pytest tests/agentflow/statemachine/backends/test_redis_checkpoint_store.py -m integration
```

## Connection strings

| Service | Default DSN / URL | Override env var |
|---------|------------------|-----------------|
| PostgreSQL | `postgresql://agentflow:agentflow@localhost:5432/agentflow` | `POSTGRES_DSN` |
| Redis | `redis://localhost:6379` | `REDIS_URL` |

## Usage in code

```python
from agentflow.statemachine import PostgresCheckpointStore, RedisCheckpointStore

# PostgreSQL
async with PostgresCheckpointStore("postgresql://agentflow:agentflow@localhost/agentflow") as store:
    state = await runner.run_until(initial, predicate, store=store, run_id="run1")
    final = await runner.resume(store, "run1", from_step=2)

# Redis
async with RedisCheckpointStore("redis://localhost:6379") as store:
    state = await runner.run_until(initial, predicate, store=store, run_id="run1")
    final = await runner.resume(store, "run1", from_step=2)
```

## Maintenance

```bash
# Stop services (keep data)
docker compose down

# Stop + remove all volumes (destructive — loses all checkpoint data)
docker compose down -v

# Clean up unused Docker resources
docker system prune -f
docker volume prune -f
```
