@echo off
echo Starting Backend...
start cmd /k "cd backend && call venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

echo Starting Frontend...
start cmd /k "cd frontend && npm run dev"

echo Both services have been started in separate windows!
pause
