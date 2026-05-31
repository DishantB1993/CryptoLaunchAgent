#!/usr/bin/env bash
set -euo pipefail

# Create a local virtual environment in .venv and install requirements
PY=$(command -v python3)
if [ -z "$PY" ]; then
  echo "python3 not found"
  exit 1
fi

echo "Creating virtual environment at .venv..."
$PY -m venv .venv

echo "Upgrading pip and installing requirements..."
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt

echo "Done. To activate the environment: source .venv/bin/activate"
echo "Then run: python main.py self-test"
