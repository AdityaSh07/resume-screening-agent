#!/usr/bin/env sh
set -eu

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

mkdir -p uploads resumes

if [ ! -f .env ]; then
    cp .env.example .env
    printf '%s\n' 'Created .env from .env.example. Add your credentials before starting the app.'
fi

printf '%s\n' 'Manual setup complete.'
printf '%s\n' 'Activate with: . .venv/bin/activate'
printf '%s\n' 'Run with: uvicorn main:app --host 0.0.0.0 --port 8000 --reload'
