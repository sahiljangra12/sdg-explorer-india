#!/bin/bash
# SDG Explorer India: one-command setup and launch for macOS.
#   Double-click this file in Finder, or run:  bash run_mac.command
# It creates a private Python environment, installs dependencies, refreshes the data from the
# official sources (falling back to the bundled verified files if you are offline), runs the
# tests and opens the dashboard in your browser.
set -euo pipefail
cd "$(dirname "$0")"

echo "== SDG Explorer India =="
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11 or newer is required (macOS's built-in python3 is usually 3.9)."
  echo "Install it from https://www.python.org/downloads/macos/ or with: brew install python@3.12"
  read -r -p "Press Enter to close..." _ || true
  exit 1
fi
echo "Using $($PY --version)"

if [ ! -x .venv/bin/python ]; then
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

if ! command -v pdftotext >/dev/null 2>&1; then
  echo "Note: pdftotext (Poppler) is not installed, so the MoSPI report will not be re-parsed; the verified"
  echo "      extract bundled with the project is used instead. To re-parse it: brew install poppler"
fi
echo "== Updating data from official sources (uses bundled files if a source is unreachable) =="
.venv/bin/python -m sdg_india all || echo "Data update reported a problem; the dashboard will use the last verified build."

echo "== Running checks =="
.venv/bin/python -m pytest -q || echo "Some checks failed; see the output above."

if [ "${SDG_NO_LAUNCH:-0}" = "1" ]; then echo "Setup complete (launch skipped)."; exit 0; fi
echo "== Opening the dashboard (press Control-C in this window to stop) =="
exec .venv/bin/python -m streamlit run app/app.py
