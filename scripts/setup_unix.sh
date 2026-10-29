#!/usr/bin/env sh
# Stop immediately if a required setup command fails.
set -e

# Resolve the backend relative to this script, so the command works regardless
# of the user's current terminal directory.
cd "$(dirname "$0")/../backend"

# Prefer the conventional python3 command, but support systems where Python 3 is
# exposed as python. command -v checks availability without launching Python.
if command -v python3 >/dev/null 2>&1; then
  PYTHON_COMMAND=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_COMMAND=python
else
  echo "Python 3 was not found. Install Python 3.10 or later and try again."
  exit 1
fi

# Create a project-local virtual environment only when it does not already
# exist. This isolates dependencies from the user's global Python installation.
if [ ! -d .venv ]; then
  "$PYTHON_COMMAND" -m venv .venv
fi

# Activate the environment in this shell and install the lightweight default
# requirements. Transformer packages remain a separate opt-in installation.
. .venv/bin/activate
python -m pip install -r requirements.txt

# Show the exact next command after successful installation.
printf '\nSetup complete. Start the backend with:\nsh scripts/run_backend_unix.sh\n'
