---
paths:
  - "**/*.py"
---

# Python style rules

Match the surrounding code. There is no formatter config; `ruff check .` with the pinned ruff 0.8.4 is the gate.

## File shape

- Module docstring first. Say what the module does and, where it applies, how it differs from `INSIGHTOPS_BLUEPRINT.md`.
- Then `from __future__ import annotations`, then imports grouped stdlib → third-party → `app.*`.
- Use absolute imports from the package root (`from app.tools.db_tools import read_db`), never relative imports.

## Types

- Annotate every function signature, using modern syntax: `list[dict[str, Any]]`, `str | None`, `Literal[...]`.
- API request/response shapes are Pydantic `BaseModel` in `app/models.py`; internal services are `@dataclass`; graph state is the `AgentState` `TypedDict`.

## Comments and docstrings

- Every public class and function gets a one-line docstring.
- Add **single-line `#` comments** on non-obvious lines and on each logical block, saying *why*, not *what*. This is a deliberate house style; keep it on new code.

## Naming and structure

- `snake_case` for functions, variables and modules; `PascalCase` for classes; `UPPER_SNAKE` for constants; a `_leading_underscore` for module-private helpers and cached singletons.
- Process-wide services are exposed via a `get_*()` factory backed by a module-level `_NAME: Type | None = None`. Configuration is read only through `get_settings()`; never read `os.environ` for app settings (except `INSIGHTOPS_DATA_DIR` and `DATABASE_URL` in scripts, which already do).
- A new setting goes into `Settings` in `app/config.py` with a safe local default **and** into `.env.example`.

## Errors

- API layer: raise `HTTPException` with a specific status (400 for bad input or a guardrail hit, 404 for an unknown id), chaining with `from exc`.
- Catching a broad `Exception` is allowed only where the code deliberately degrades to a local fallback (DB, audit, file stores, optional imports). Every such `except` gets a comment saying what the fallback is.
- Remove unused imports and variables instead of suppressing the lint warning.
