$ErrorActionPreference = 'Stop'

if (-not (Test-Path '.venv')) {
    python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

New-Item -ItemType Directory -Force -Path uploads, resumes | Out-Null

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Created .env from .env.example. Add your credentials before starting the app.'
}

Write-Host 'Manual setup complete.'
Write-Host 'Activate with: .\.venv\Scripts\Activate.ps1'
Write-Host 'Run with: uvicorn main:app --host 127.0.0.1 --port 8000 --reload'
