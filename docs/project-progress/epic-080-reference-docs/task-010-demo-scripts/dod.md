# DoD — E080 T010 Parallel-Research-with-Loop Demo

- [ ] Demo file created (`04_parallel_research_loop.py` or `05_...`).
- [ ] Loop terminates in ≤3 Research iterations (max revision_count check).
- [ ] Graph uses custom `ReviewSignal` enum with `approved` + `needs_revision`.
- [ ] Demo runs end-to-end: `python ...` exits 0, prints final report.
- [ ] `ruff check` passes.
- [ ] `mypy --strict --follow-imports=skip` passes.
- [ ] Full regression: `pytest src/agentflow/tests/ -v -m "not integration"` (no new prod code → same count).
