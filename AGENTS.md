# Repository Guidelines

## Project Structure & Module Organization

This is a Python trading and dashboard project. Core application code lives in `src/`: API clients under `src/api/`, persistence under `src/db/`, signal collection under `src/futures_signals/`, notification helpers under `src/notifier/`, strategy logic under `src/strategy/`, and shared utilities under `src/utils/`. The FastAPI dashboard entry point is `src/dashboard.py`; the trading engine entry point is `src/trader.py`.

Tests are in `tests/` and follow `test_*.py` naming. Web assets are split between `web/templates/` for Jinja templates and `web/static/` for CSS and JavaScript. Operational scripts are in the repository root and `tools/`. Runtime artifacts such as logs, caches, databases, and generated files belong in `logs/`, `data/`, `.runtime/`, or `__pycache__/`, not in source directories.

## Build, Test, and Development Commands

Set up a local environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Run the dashboard locally:

```powershell
.\server.cmd restart
```

Open `http://127.0.0.1:8000`. Use `.\server.cmd status`, `logs`, or `tail` to inspect the background server.

Run the trading engine directly:

```powershell
python src\trader.py
```

Run local verification and tests:

```powershell
powershell -ExecutionPolicy Bypass -File tools\verify-local.ps1
python -m unittest discover -s tests
```

## Coding Style & Naming Conventions

Follow `.editorconfig`: UTF-8, LF endings, final newline, and trimmed trailing whitespace for code and text files. Use Python modules and functions in `snake_case`, classes in `PascalCase`, and constants/environment variables in `UPPER_SNAKE_CASE`. Keep configuration in `.env` and `src/config.py`; do not hardcode credentials or account identifiers.

## Testing Guidelines

Add tests next to related coverage in `tests/`, using names like `test_trader_core.py` or `test_futures_signal_parser.py`. Prefer deterministic unit tests with mocked API responses for KIS, Telegram, Slack, and exchange integrations. Run the full unittest discovery before committing changes that affect trading logic, dashboard routes, persistence, or configuration.

## Commit & Pull Request Guidelines

Recent history uses short, descriptive commit subjects, sometimes in Korean, such as `대시보드 탭 분리 및 계좌정보 추가`. Keep subjects concise and behavior-focused. Pull requests should describe the change, list verification commands run, call out `.env` or migration impacts, and include screenshots for dashboard UI changes.

## Security & Configuration Tips

Treat live trading as guarded behavior. Keep `DRY_RUN=true`, `TRADING_ENV=demo`, and `ENABLE_LIVE_TRADING=false` unless intentionally testing live execution. Never commit `.env`, API keys, account numbers, tokens, local databases, or logs.
