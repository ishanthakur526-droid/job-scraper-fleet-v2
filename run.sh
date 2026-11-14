#!/usr/bin/env sh
# Find jobs now (macOS/Linux). Extra options are passed through, e.g. ./run.sh --skip-llm
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo "Run ./setup.sh first."; exit 2; fi
export PYTHONUTF8=1
.venv/bin/python -m jobfleet run --config-dir config --output-dir outputs "$@"
code=$?
echo "Dashboard: $(pwd)/outputs/dashboard.html"
exit $code
