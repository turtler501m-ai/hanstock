# Repository Guidelines

## Project Structure

This is a Python trading and dashboard project.

- `src/`: application code
- `src/api/`: KIS, KIS futures, QuantConnect API clients
- `src/db/`: persistence helpers
- `src/futures_signals/`: Telegram futures signal collection, parsing, verification, execution
- `src/notifier/`: notification helpers
- `src/strategy/`: trading strategy, indicators, risk, allocation
- `src/utils/`: shared utilities
- `web/templates/`: dashboard templates
- `web/static/`: CSS and JavaScript
- `tests/`: unittest test suite
- `config/`: non-secret checked-in configuration such as Telegram channel definitions
- `src/integrations/`: external platform artifacts such as QuantConnect algorithms
- `tools/`: local verification and utility scripts
- `scripts/local/`: Windows local development scripts
- `scripts/vm/`: VM/Linux operation scripts
- `doc/S1.한스톡사용설명서.md`: consolidated project manual

Main entry points:

- Dashboard: `src/dashboard.py`
- Trading engine: `src/trader.py`
- Local server: `scripts/local/server.cmd`
- VM server: `scripts/vm/server.sh`

Runtime artifacts belong in `.runtime/`, `logs/`, or `data/`. Do not place generated runtime files under `src/`, `web/`, or `tests/`.

Keep the repository root clean. Only project-level files such as `README.md`, `AGENTS.md`, `requirements.txt`, `.env.example`, `.editorconfig`, `.gitattributes`, and `.gitignore` should live at the root.

Placement rules:

- New application code goes under `src/`.
- API clients go under `src/api/`.
- External platform integrations go under `src/integrations/` unless a more specific existing package owns them.
- Checked-in non-secret configuration goes under `config/`.
- Local Windows scripts go under `scripts/local/`.
- VM/Linux scripts go under `scripts/vm/`.
- Verification and maintenance tools go under `tools/`.
- Documentation is consolidated in `doc/S1.한스톡사용설명서.md`.
- Do not commit personal IDE settings; `.vscode/` is ignored.

## Local Development

Set up a local environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Run the dashboard locally:

```powershell
.\scripts\local\server.cmd restart
```

Inspect the local server:

```powershell
.\scripts\local\server.cmd status
.\scripts\local\server.cmd logs
.\scripts\local\server.cmd tail
```

Open:

```text
http://127.0.0.1:8000
```

Run the trading engine directly:

```powershell
python src\trader.py
```

## VM Operation

VM code should be updated from Git, not edited directly on the VM.

Deploy/update from local:

```powershell
.\scripts\local\deploy-vm.ps1
```

Recreate the VM project folder from a fresh clone:

```powershell
.\scripts\local\deploy-vm.ps1 -FreshClone
```

Open SSH to the VM:

```powershell
.\scripts\local\connect-vm.ps1
```

Run directly on the VM:

```bash
./scripts/vm/update.sh main
./scripts/vm/server.sh restart
./scripts/vm/server.sh status
```

## Testing

Run local verification before committing changes that affect trading logic, dashboard routes, persistence, configuration, or deployment scripts:

```powershell
powershell -ExecutionPolicy Bypass -File tools\verify-local.ps1
python -m unittest discover -s tests
```

For encoding checks:

```powershell
powershell -ExecutionPolicy Bypass -File tools\check-encoding.ps1
```

Tests use `test_*.py` naming under `tests/`. Prefer deterministic tests with mocked KIS, Telegram, Slack, QuantConnect, Bybit, and network responses.

## Coding Style

Follow `.editorconfig`: UTF-8, LF endings, final newline, and trimmed trailing whitespace for code and text files.

Use:

- Python modules/functions: `snake_case`
- Classes: `PascalCase`
- Constants and environment variables: `UPPER_SNAKE_CASE`

Keep configuration in `.env`, `.env.example`, and `src/config.py`. Do not hardcode credentials, account identifiers, tokens, or VM-specific secrets.

## Git Workflow

Use short, behavior-focused Korean or English commit subjects.

Before commit:

```powershell
git status
python -m unittest discover -s tests
```

Do not include unrelated local changes in a cleanup or infrastructure commit. If dashboard UI files are already modified for another task, leave them unstaged unless the current task explicitly includes them.

## Security

Treat live trading as guarded behavior. Keep these defaults unless intentionally testing live execution:

```text
DRY_RUN=true
TRADING_ENV=demo
ENABLE_LIVE_TRADING=false
REQUIRE_APPROVAL=true
```

Never commit:

- `.env`
- API keys, app secrets, account numbers, tokens
- Telegram session files
- local databases
- logs
- `.runtime/`
- `data/*.db`
- `data/*.sqlite`

VM `.env` and local `.env` are separate operational files. Do not copy secrets into the repository.
