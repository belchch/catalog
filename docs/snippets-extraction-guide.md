# Snippets extraction guide (private)

Repeatable procedure for extracting a Catalog backend module into the public
`catalog-showcase` repo. Keep this file in the private Catalog repo only — never
copy it into the public showcase.

## Target layout

```
catalog-showcase/
  python/<theme>/          # self-contained package
  tests/test_<theme>.py    # isolated unit tests
  pyproject.toml
  README.md
  LICENSE
  .gitignore
```

Themes in the first pass: `agent_loop`, `llm_provider`, `verify_registry`,
`text_links`.

## Per-module procedure

1. **Copy** the source file(s) into `python/<theme>/`.
2. **Self-contain imports.** Inline the few needed types or add a small local
   module. No `app.*` imports. Drop product-only side effects (prompt logs,
   agent event loggers, DB clients, workspace paths).
3. **Scrub**
   - Delete narration / intent comments.
   - Delete every internal reference: `CATALOG-*`, `ADR-*`, `step-*` ticket ids,
     "slice" / "срез", night-shift / kilo / plan-folder language.
   - Rewrite docstrings to be generic and professional (English).
   - Drop `# noqa` comments entirely (including ones that cite internals).
   - Keep concise module-level and public-API docstrings that name the skill
     demonstrated — no meta-narration about how the code was written.
4. **Decouple** product dependencies. Prefer pure inputs (e.g. an iterable of
   `(title, path)` instead of a `Database`). Prefer `Protocol` injection over
   concrete app services.
5. **Port tests.** Adapt imports; use mocks/fakes (`httpx.MockTransport`, in-process
   fake LLM providers). Never hit the network or require API keys.
6. **Verify the theme**
   - `ruff check .`
   - `pytest --cov=python/<theme> tests/test_<theme>.py`
7. **Repo-wide scrub** before publish:
   ```bash
   rg -n 'CATALOG|ADR|срез|slice|step-0|kilo|night-shift|noqa|TODO|FIXME' .
   ```
   Expect zero hits. Also confirm no `.env`, workspace content, smoke logs, or
   plan/ADR docs leaked in.

## What stays private

- This guide.
- Plane / CATALOG tickets, ADRs, night-shift plans.
- Any path under `backend/app/` that still couples to storage, API, or skills
  orchestration beyond the extracted theme.

## What the public README must say

- One-paragraph product description (English).
- Prominent banner: demonstration snippets only; not a runnable product; live
  demo on request (GitHub `@belchch`).
- Skills-demonstrated list mapped to the themes.
- How to install and run tests.
