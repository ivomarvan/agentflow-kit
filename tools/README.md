# Tools

Standalone command-line utilities for this repository.

## dot2html

Convert a Graphviz DOT file to an interactive HTML graph page using the same
rendering pipeline as `agentflow graph` / `graph --browser` (`GraphRenderer.dot_to_html`).

**Prerequisite:** Graphviz system binary (`dot`) — `sudo apt install graphviz`

```bash
# After uv sync (editable install from repo root)
dot2html -i g.dot -o g.html

# Equivalent without the console script entry point
uv run python -m tools.dot2html -i g.dot -o g.html
```

Tooltips from DOT `tooltip=` attributes are extracted automatically so hover
panels work for agentflow-generated DOT files.
