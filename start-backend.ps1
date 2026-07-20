# Start the RadAssist API (FastAPI on port 8000)
$env:PYTHONUTF8 = '1'
Set-Location "$PSScriptRoot\backend"
& .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
