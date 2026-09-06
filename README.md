# ScreenEasy

ScreenEasy is a FastAPI and LangGraph candidate-screening application. It evaluates resumes and GitHub profiles, stores jobs and shortlisted candidates in PostgreSQL, processes test results, and supports interview scheduling.

## Agent Workflows

The application uses four LangGraph workflows. Their generated diagrams are available through `python generate_agent_images.py`.

### 1. Screening Workflow

Used by `POST /api/screen` for a new job.

![Screening workflow](agent_images/screening_workflow.png)

```text
Load candidates -> Process job description -> Analyze JD ->
Evaluate candidates -> Rank candidates -> Save shortlist -> Send test emails
```

- Analyzes the job description with the LLM.
- Evaluates each candidate through the candidate workflow.
- Stores the job and shortlisted candidates in PostgreSQL.
- Sends assessment emails to shortlisted candidates.
- Returns a unique `job_id`. Keep it safe for later access.

### 2. Candidate Workflow

Runs once for each candidate inside the screening workflow.

![Candidate workflow](agent_images/candidate_workflow.png)

```text
Extract links -> Download resume -> Resume evaluation
						 |-> GitHub analysis -> GitHub evaluation
						 |-> Calculate overall score
```

- Downloads and reads the resume, then deletes the temporary PDF.
- Uses the LLM to score the resume.
- Reads GitHub profile and repository information.
- Uses the LLM to score GitHub relevance.
- Calculates the final candidate score and shortlist status.

### 3. Test Results Workflow

Used by `POST /api/upload-test-results` after a job already exists.

![Test results workflow](agent_images/test_results_workflow.png)

```text
Load test file -> Extract test results -> Match candidates -> Save results
```

- Requires the saved `job_id`.
- Reads CSV or Excel test results.
- Matches rows by candidate ID, email, or name.
- Updates test score, final score, and qualification status in PostgreSQL.
- Does not run screening again and does not send test emails.

### 4. Interview Workflow

Used by `POST /api/interviews/schedule` for an eligible candidate.

![Interview workflow](agent_images/interview_workflow.png)

```text
Validate candidate -> Create meeting -> Create calendar invite ->
Save interview -> Send interview email
```

- Verifies the candidate belongs to the supplied `job_id`.
- Creates the meeting and calendar invite.
- Saves interview details in PostgreSQL.
- Sends the interview invitation email.

## Requirements

- Python 3.12+
- PostgreSQL 14+
- Git
- Docker Desktop, only for the Docker setup
- API credentials for Groq, GitHub, and Resend for the full workflow

## Configuration

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Set these values in `.env`:

```env
GROQ_API_KEY=...
GITHUB_TOKEN=...
RESEND_API_KEY=...
EMAIL_FROM=...
TEST_LINK=...
```

For a manually installed PostgreSQL database, use either URL format:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
```

or:

```env
POSTGRE_DB_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE
```

`DATABASE_URL` takes precedence. Do not use `localhost` when the application runs in a separate container; use the database service hostname instead.

## Manual Setup

### Windows PowerShell

From the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Linux or macOS

```bash
chmod +x setup.sh
./setup.sh
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000` and check `http://localhost:8000/health`.

The manual setup expects PostgreSQL to already be running and reachable through `DATABASE_URL` or `POSTGRE_DB_URL`. The application creates and migrates its tables on the first database operation.

## Docker Compose Setup

Docker Compose runs the API and PostgreSQL on the same `screeneasy-network` bridge network.

1. Create `.env` from `.env.example` and set the API credentials.
2. Set a strong `POSTGRES_PASSWORD`.
3. Start the services:

```powershell
docker compose --env-file .env up -d --build
```

Check the services:

```powershell
docker compose ps
docker compose logs -f app
```

Open `http://localhost:8000`.

Stop the services without deleting database data:

```powershell
docker compose down
```

Do not use `docker compose down -v` unless you intentionally want to delete the PostgreSQL data volume.

## Production Docker Run

Build the image:

```bash
docker build -t screeneasy-app .
```

Run it against an existing PostgreSQL server:

```bash
docker run --env-file .env -e PORT=8000 -p 8000:8000 screeneasy-app
```

The `.env` used here must contain a reachable production `DATABASE_URL`. It must not point to `localhost` unless PostgreSQL runs inside the same container, which is not recommended.

## Render Deployment

Use the repository Dockerfile:

- Environment: `Docker`
- Root Directory: blank, unless the repository contains an outer project folder
- Dockerfile Path: `Dockerfile`
- Build Command: empty
- Start Command: empty
- Health Check Path: `/health`

Create a Render PostgreSQL service and set its internal connection URL as `DATABASE_URL`. Add the API credentials as Render environment variables. Render supplies `PORT`; the Dockerfile uses it automatically.

## Agent Workflow Images

Generate Mermaid source and PNG images for all compiled workflows:

```powershell
python generate_agent_images.py
```

Output is written to `agent_images/`:

- `screening_workflow.png`
- `candidate_workflow.png`
- `interview_workflow.png`
- `test_results_workflow.png`

The `.mmd` files are also generated as a fallback when PNG rendering is unavailable.

## API Endpoints

- `GET /health`
- `POST /api/screen`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/latest`
- `GET /api/candidates?job_id=...`
- `GET /api/dashboard/stats?job_id=...`
- `POST /api/upload-test-results`
- `POST /api/interviews/schedule`

A screening response returns a `job_id`. Keep it safe. It is required later to retrieve the job and upload test results without running screening again.

## Development Checks

```powershell
python -m compileall -q app main.py
git diff --check
```

Never commit `.env`, uploaded candidate files, resumes, credentials, or API keys. Rotate any credential that has been exposed.
