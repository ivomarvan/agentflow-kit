# agentflow.statemachine.testing

Testing utilities for state machine graphs — deterministic test doubles
that allow unit tests to run without real LLM calls.

## Contents

| Module | Purpose |
|--------|---------|
| `fakes.py` | `FakeVertex`, `FakeLlmConnector`, `make_fake_context` |
| `fixtures.py` | pytest fixtures: `fake_ctx`, `make_state_graph` |

## Usage

```python
# In a test file
from src.agentflow.statemachine.testing import FakeVertex, make_fake_context
from src.agentflow.statemachine.signal import StdSignal

ctx = make_fake_context()
vertex = FakeVertex(signal=StdSignal.ok, patch=None)
signal, patch = await vertex.run(state, ctx)
assert vertex.calls == 1
```

```python
# With FakeLlmConnector
from src.agentflow.statemachine.testing import FakeLlmConnector

connector = FakeLlmConnector()
connector.queue_responses(["Hello!", "Goodbye!"])
response = connector.chat([{"role": "user", "content": "Hi"}])
assert response.text == "Hello!"
```

## Design Notes

- `testing/` is a **production module** (lives in `src/`, not `tests/`).
  This makes the fakes importable by any downstream package that depends on
  `agentflow.statemachine`, not just tests in this repo.
- `FakeLlmConnector.config` raises `NotImplementedError` — tests must not
  call `connector.config` or `connector.describe()`.

## pytest fixtures

`fixtures.py` defines pytest fixtures but is **not** a `conftest.py`.
To activate them project-wide, import in `conftest.py`:

```python
from src.agentflow.statemachine.testing.fixtures import fake_ctx, make_state_graph
```
