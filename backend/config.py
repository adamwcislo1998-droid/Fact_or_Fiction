"""Settings for the local backend.

Every value can be overridden with an environment variable. Defaults keep the
project easy to start on a marker's machine without requiring a separate .env
file, while still allowing advanced users to change ports or enable the model.
"""

import os


# Environment variables are strings. This helper recognises several common
# human-friendly spellings of a true value and otherwise returns False/default.
def read_boolean(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower().strip() in ("1", "true", "yes", "on")


# Bind to localhost by default so the prototype is not exposed to other devices
# on the network. The extension and backend run on the same computer.
HOST = os.getenv("FACT_OR_FICTION_HOST", "127.0.0.1")
# Convert the environment value to an integer because Flask expects a numeric
# TCP port rather than the raw string returned by os.getenv.
PORT = int(os.getenv("FACT_OR_FICTION_PORT", "5000"))
# Debug mode is opt-in because detailed tracebacks should not normally be shown.
DEBUG = read_boolean("FACT_OR_FICTION_DEBUG")
# Heavy transformer support is deliberately optional; the rules/VADER mode is
# the portable default and needs far fewer packages and resources.
ENABLE_TRANSFORMER = read_boolean("FACT_OR_FICTION_ENABLE_TRANSFORMER")
# Name of the Hugging Face zero-shot model used only when the optional mode is
# enabled. It can be replaced without editing source code.
TRANSFORMER_MODEL = os.getenv(
    "FACT_OR_FICTION_TRANSFORMER_MODEL",
    "typeform/distilbert-base-uncased-mnli",
)
# Processing limits bound runtime and prevent a very large thread from creating
# an unexpectedly expensive request.
MAX_COMMENTS = int(os.getenv("FACT_OR_FICTION_MAX_COMMENTS", "75"))
# Character limit for the post body after the whole-request Flask limit.
MAX_TEXT_CHARS = int(os.getenv("FACT_OR_FICTION_MAX_TEXT_CHARS", "50000"))
