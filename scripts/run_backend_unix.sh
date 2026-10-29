#!/usr/bin/env sh
# -e stops on errors; -u treats missing variables as errors.
set -eu

# Run from the backend directory even when invoked from the project root.
cd "$(dirname "$0")/../backend"

# Give a useful instruction instead of failing with a vague missing-file error.
if [ ! -x .venv/bin/python ]; then
  echo "Backend environment not found. Run scripts/setup_unix.sh first."
  exit 1
fi

# Replace the shell process with Python so interruption/exit signals are passed
# directly to Flask.
exec .venv/bin/python app.py
