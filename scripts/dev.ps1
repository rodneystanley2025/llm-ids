$ErrorActionPreference = "Stop"

if (!(Test-Path ".\.venv\Scripts\activate")) {
  python -m venv .venv
}

.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
