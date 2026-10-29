# Commented code edition

This copy contains extensive in-source explanations. See `COMMENTED_CODE_README.md`
for how strict JSON files are documented without breaking them.

# Fact or Fiction: The Credibility Lens


## Requirements

- Python 3.10 or later
- Google Chrome, Microsoft Edge, Brave, or another Chromium browser with Manifest V3 support
- Internet access when installing the Python packages and when opening Reddit

Node.js is not needed to use the project. It is only needed to run the optional JavaScript parser tests.

## Quick start on Windows

1. Extract the ZIP file.
2. Open Command Prompt or PowerShell in the extracted project folder.
3. Run the setup script once:


scripts\setup_windows.bat


4. Start the backend:


scripts\run_backend_windows.bat


5. Keep the backend window open while using the extension.
6. Follow the **Load the extension** instructions below.

The setup script accepts Windows installations that provide either the `py` launcher or the `python` command.

## Quick start on macOS or Linux

1. Extract the ZIP file.
2. Open a terminal in the extracted project folder.
3. Run the setup script once:

```bash
sh scripts/setup_unix.sh
```

4. Start the backend:

```bash
sh scripts/run_backend_unix.sh
```

5. Keep the backend terminal open while using the extension.
6. Follow the **Load the extension** instructions below.

Using `sh` avoids problems where ZIP extraction removes executable permissions from shell scripts.

## Check that the backend is running

Open the following address in the browser:

```text
http://127.0.0.1:5000/api/v1/health
```

A working backend returns JSON containing:

```json
{
  "ok": true,
  "status": "healthy",
  "service": "fact-or-fiction-backend",
  "transformer_enabled": false
}
```

## Load the extension

Open the extension management page for the browser:

```text
Chrome: chrome://extensions
Edge: edge://extensions
Brave: brave://extensions
```

Then:

1. Enable *Developer mode*.
2. Select *Load unpacked*.
3. Choose the `extension` folder inside this project. Do not choose the whole project folder.
4. Open an individual Reddit post whose address contains `/comments/`.
5. Open the extension and select **Analyse current post**.


## Project structure

```text
backend/app.py              Flask routes and request handling
backend/config.py           Backend settings
backend/credibility/        Text analysis and scoring code
backend/tests/              Python tests
extension/background/       Connects the page, backend and popup
extension/common/           Reddit parser and backend request code
extension/content/          Page-reading fallback
extension/popup/            Extension interface
extension/tests/            Reddit parser tests
scripts/                    Setup and startup scripts
```

The main flow is:

```text
Reddit post -> Reddit JSON parser -> page fallback if needed
            -> Flask backend -> credibility score and explanations
            -> extension popup
```

## Run the Python tests

After setup, activate the environment and run:

### Windows

```bat
cd backend
.venv\Scripts\activate
pytest -q
```

### macOS or Linux

```bash
cd backend
. .venv/bin/activate
pytest -q
```

The tests check the health endpoint, request validation, score limits, structured comment handling and the expected difference between an evidence-based example and a sensational example.

## Run the optional JavaScript tests

Node.js 18 or later is required only for this section:

```bash
cd extension
npm test
```

These tests check that the Reddit JSON parser captures top-level and nested comments and ignores deleted comments.

## Optional transformer mode

To install the optional transformer packages:

```bash
cd backend
python -m pip install -r requirements-transformer.txt
```

Enable it before starting the backend:

### Windows Command Prompt

```bat
set FACT_OR_FICTION_ENABLE_TRANSFORMER=true
python app.py
```

### Windows PowerShell

```powershell
$env:FACT_OR_FICTION_ENABLE_TRANSFORMER = "true"
python app.py
```

### macOS or Linux

```bash
FACT_OR_FICTION_ENABLE_TRANSFORMER=true python app.py
```

The model is loaded on the first analysis request. If it cannot be loaded, the standard analysis still works.
