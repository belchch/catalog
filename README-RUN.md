# Catalog — how to run

**English** | [Русский](README-RUN.ru.md)

The main path is **native** (Python venv / `uv tool install`, Node/pnpm for UI development). Do **not** use Docker for local document work — see the section at the end.

After these steps you will have a backend, a UI, and an open workspace folder with your files.

---

## Fast path: `uv tool install` (from git)

PyPI is not used yet (the package name is not finalized). The install is from the repository; building the wheel needs **uv**, **Node.js**, and **pnpm** (a hook packages the frontend).

```bash
uv tool install "git+https://github.com/belchch/catalog.git#subdirectory=backend"
catalog
```

The `catalog` command starts uvicorn on `127.0.0.1:8000` and opens a browser. Keys can be set via env (`OPENROUTER_API_KEY` / `ZAI_API_KEY`) or later through the `/setup` API (the first-run screen is a separate UI step). Persist goes into the global `app.db`, not a CWD `.env`.

---

## One-time setup (dev from source)

1. **Python 3.11+** (3.13 is more convenient) — [https://www.python.org/downloads/](https://www.python.org/downloads/)
2. **Node.js** and **pnpm** — [https://nodejs.org/](https://nodejs.org/) · then `npm install -g pnpm`
3. An LLM provider key (env overrides persist):
  - default is **OpenRouter**: `OPENROUTER_API_KEY` (+ a tool-capable `OPENROUTER_DEFAULT_MODEL`);
  - or **z.ai** (`APP_PROVIDER=zai`, `ZAI_API_KEY`) — see `backend/.env.example`.

---

## 1. Backend environment

From the repository root:

```bash
cd backend
cp .env.example .env
```

Open `backend/.env` and set at least (for CI/dev; in the product, keys can live in the app db):

- `OPENROUTER_API_KEY=...` (or a z.ai key when `APP_PROVIDER=zai`)
- `OPENROUTER_DEFAULT_MODEL=...` — a model with function-calling / tool use

Leave the rest as is. Document paths are not set in `.env`: you pick the folder in the UI.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn catalog.main:app --reload
# or: catalog --no-browser
```

Check: [http://localhost:8000/health](http://localhost:8000/health)

Leave this terminal running.

---

## 2. Frontend

In **another** terminal:

```bash
cd frontend
pnpm install
pnpm run dev
```

Open in a browser: [http://localhost:5173](http://localhost:5173)

---

## 3. Open or create a workspace folder

In the UI, pick a folder (“Open workspace” / folder picker):

| Folder | What happens |
| --- | --- |
| Empty (no Catalog marker) | Prompt to **create** a workspace → confirm |
| Ordinary files, no `.catalog` | Index preview → **confirm initialization** |
| Already a workspace (has `.catalog/index.db`) | Opens immediately; the index is refreshed if needed |

Documents stay **ordinary files in the chosen folder**. Internal data lives only in `.catalog/` (including `index.db`); you do not need to edit it by hand.

Global settings and the list of known workspaces live in the OS data directory (on macOS — `~/Library/Application Support/catalog`, otherwise `~/.local/share/catalog`), not next to the source tree and not in a Docker volume.

---

## Stop

In each terminal (backend / frontend) — **Ctrl+C**.

---

## End-to-end run (golden path)

You need a configured `backend/.env` and the samples at the repo root (`samples/golden.docx`, `samples/golden2.docx`). The script creates a temporary workspace folder with `.catalog/index.db` and runs ingest → plan → skill → apply:

```bash
cd backend
source .venv/bin/activate   # if not already active
python scripts/golden_run.py
```

Success: `=== GOLDEN RUN PASSED ===` at the end, plus a JSON report.

---

## If something does not work

| Symptom | What to do |
| --- | --- |
| Missing key / LLM errors | Check `backend/.env`: the key is set; the model supports tool use |
| Port **8000** is busy | Stop the other process or `uvicorn ... --port 8001` |
| Port **5173** is busy | Vite will offer another port, or stop the conflicting process |
| `pnpm: command not found` | `npm install -g pnpm` |
| Backend does not start after install | Activate the venv, then from `backend/` run `pip install -e ".[dev]"` again |
| HTTP **409** `workspace not open` | No folder is open in the UI yet — open a workspace (step 3) |
| 409 when switching folders | Wait for the active skill run to finish, then switch |

If nothing helps — send the terminal output (backend and/or frontend).

---

## Obsolete for local use: Docker

The Docker wrapper lives in `deploy/` (`deploy/docker-compose.yml`, volume `catalog-data` → `/data`, `deploy/Catalog.command` / `deploy/Build.command`) — this is **not** the product path for working with documents on your machine. A named volume is no longer “where my files live”.

The scripts and image are kept as a starting point for a possible server deploy and may lag behind the code. For day-to-day local work, use the native path above.
