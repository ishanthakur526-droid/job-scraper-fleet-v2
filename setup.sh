#!/usr/bin/env sh
# JobFleet setup for macOS and Linux: installs into .venv, then asks what you are looking for.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "Step 1 of 2: installing JobFleet (one time, about a minute)..."
  if command -v uv >/dev/null 2>&1; then
    uv sync --quiet
  else
    PY=""
    for candidate in python3 python; do
      if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
        PY="$candidate"; break
      fi
    done
    if [ -z "$PY" ]; then
      echo "Python 3.11 or newer is needed: https://www.python.org/downloads/ (or 'brew install python', 'sudo apt install python3')."
      exit 2
    fi
    "$PY" -m venv .venv
    .venv/bin/python -m pip install --quiet --upgrade pip
    .venv/bin/python -m pip install --quiet -e .
  fi
fi

echo "Step 2 of 2: tell JobFleet what you are looking for."
.venv/bin/python -m jobfleet setup
echo "All set! Run ./run.sh to find jobs. For a daily run: .venv/bin/jobfleet schedule"
