# CryptoLaunchAgent

Phase 1 — Project scaffold for a paper-trading crypto launch hunter targeting BSC.

This repository contains the initial project structure and placeholders. No trading logic is included yet.

Requirements

- Python 3.12 or newer is required for this project.

Phase 1 layout

Files and directories created in Phase 1:
- `src/` — Source code
- `config/` — Configuration files (placeholder)
- `logs/` — Log files (placeholder)
- `data/` — Persistent data storage (placeholder)
- `requirements.txt` — Python dependencies (placeholder)
- `main.py` — Project entry point (placeholder)
- `.gitignore` — Files to ignore in git (placeholder)

Usage

1. Create or populate a virtual environment with Python 3.12+.
2. Populate `requirements.txt` with required packages.
3. Implement modules under `src/`.
4. Run `python3 main.py` to start (after implementation).

Setup (virtualenv)

If you see errors installing packages system-wide (e.g. "externally-managed-environment"), create a local virtual environment and install dependencies into it. From the project root run:

```bash
# create venv and install deps into `.venv` (recommended)
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt

# then run (example):
.venv/bin/python main.py self-test
```

Alternatively use the helper script `scripts/setup_env.sh`.
