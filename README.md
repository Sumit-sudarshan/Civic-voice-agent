# Civic Voice Agent

Civic Voice Agent is an AI powered system that collects complaints and suggestions from citizens, understands them through a short conversation, classifies and prioritizes them, detects duplicates, and presents everything on an actionable dashboard for a local political leader such as an MLA, a corporator, or a panchayat head.

A citizen describes a problem in plain language (English, Hindi, or Marathi). The system asks a few follow up questions to pin down the location and the actual issue, then runs the submission through an AI pipeline that labels it, scores its urgency, extracts the key facts, and merges it with any existing report about the same problem. The leader sees a clean, deduplicated, prioritized list instead of a flood of raw messages.

The whole system can run fully offline on a normal laptop using local models through Ollama. There is no mandatory cloud dependency.

---

## Table of contents

1. [What the system does](#what-the-system-does)
2. [How it works at a high level](#how-it-works-at-a-high-level)
3. [Technology stack](#technology-stack)
4. [Prerequisites](#prerequisites)
5. [Setup, step by step](#setup-step-by-step)
6. [Running the application](#running-the-application)
7. [Optional: Hindi and Marathi translation](#optional-hindi-and-marathi-translation)
8. [Optional: using Groq instead of local Ollama](#optional-using-groq-instead-of-local-ollama)
9. [Seeding demo data](#seeding-demo-data)
10. [Running the evaluation harness](#running-the-evaluation-harness)
11. [Running the test suite](#running-the-test-suite)
12. [Configuration reference](#configuration-reference)
13. [Project structure](#project-structure)
14. [Troubleshooting](#troubleshooting)

---

## What the system does

The application has three separate surfaces, all served by the same frontend dev server once it is running (see [Running the application](#running-the-application) for the exact URLs):

1. **Citizen portal**, at `http://localhost:5173/`. A citizen logs in, starts a chat, and describes an issue. A conversational agent asks clarifying questions (for example, the exact address, the area, and the pincode), then confirms the submission. The citizen can track the status of past submissions.

2. **Leader dashboard**, at `http://localhost:5173/dashboard`. The leader sees complaints and suggestions as a filterable, sorted list. Each item shows the AI assigned category, urgency, a short summary, and how many people reported the same thing. The leader can change the status of an item and read an AI written briefing that summarizes the current situation.

3. **Evaluation console**, at `http://localhost:5173/internal-eval`. A hidden internal page (not linked from anywhere in the citizen or leader UI, reachable only by visiting this URL directly) that shows how accurately the AI pipeline is performing over time. It is meant for the engineer, not for citizens or leaders.

---

## How it works at a high level

When a citizen sends a message, it flows through these stages:

1. **Language detection.** A lightweight library guesses whether the text is English, Hindi, or Marathi. This is used only for labeling and analytics, never to change the pipeline logic.
2. **Translation (optional).** If the message is in Hindi or Marathi, it is translated to English so the downstream steps work on a single language.
3. **Gatekeeper.** An LLM decides whether the message is a valid complaint, a valid suggestion, too vague, spam, off topic, abusive, or a personal emergency. Invalid messages are stored for audit and politely rejected.
4. **Dialogue manager.** An LLM reads the conversation so far and decides which location details are still missing. A small rule based state machine then decides the next question to ask, and re-checks the model's answers so a weak model cannot silently accept bad data.
5. **Finalize pipeline (runs in the background once the conversation is complete).**
   - **Classify** the issue into a category (roads, water, electricity, sanitation, education, healthcare, safety, or other).
   - **Score urgency** for complaints (critical, high, medium, or low) with a short reason.
   - **Extract** structured fields: location, issue summary, affected parties, and the specific ask.
   - **Embed** the text into a vector using a local embedding model.
   - **Deduplicate** against recent open complaints in the same category and area using cosine similarity. A close match increments a report counter instead of creating a duplicate row.
6. **Storage.** Everything is written to a local SQLite database and shown on the dashboard.

A full visual map of this flow is available in the `diagrams/` folder (`0_full_system_overview.svg` is the complete picture, and the numbered files cover each component individually).

---

## Technology stack

**Backend**

- Python 3.11
- FastAPI for the web API, served by Uvicorn
- SQLModel (built on SQLAlchemy) over SQLite for storage
- Ollama for local LLM inference and text embeddings
- Groq as an optional cloud backend for the reasoning calls
- langdetect for language identification
- Hugging Face Transformers with PyTorch (CPU build) for Hindi and Marathi translation using AI4Bharat IndicTrans2
- Pydantic for validating every model response into a typed schema

**Frontend**

- React 18 with Vite as the build tool and dev server
- Tailwind CSS for styling
- Recharts for the statistics charts
- lucide-react for icons

**Default models**

- Reasoning: `qwen2.5:1.5b` (local through Ollama) or `llama-3.1-8b-instant` (if using Groq)
- Embeddings: `nomic-embed-text` (always local through Ollama)
- Translation: `ai4bharat/indictrans2-indic-en-dist-200M` (optional, from Hugging Face)

---

## Prerequisites

Before you start, install the following on your machine:

1. **Python 3.11 or newer.**
   - Windows: check with `python --version`.
   - macOS/Linux: check with `python3 --version`. (macOS and most Linux distributions only ship `python3`, not a bare `python` command — use `python3` and `pip3` throughout this guide unless your system has `python` aliased to Python 3.)
2. **Node.js 18 or newer, with npm.** Check with `node --version` and `npm --version`.
3. **Ollama.** Download it from [ollama.com](https://ollama.com/) and install it. After installing, make sure the Ollama service is running (on Windows and macOS it usually starts automatically and stays in the background). You can confirm it's running by opening `http://localhost:11434` in a browser — it should show a short confirmation message.

You do not need a GPU. Everything is configured to run on CPU.

---

## Optional: Hindi and Marathi translation

The chat intake flow can translate Hindi and Marathi messages into English before processing them, using AI4Bharat's IndicTrans2 model.

This step is entirely optional. Without it, the application still works from start to finish. Hindi and Marathi messages simply pass through untranslated instead of being converted, and the downstream prompts are already written to tolerate mixed language input. If you only need an English demo, you can skip this section.

To enable real translation (do this any time after completing [Setup, step by step](#setup-step-by-step), since it edits the `backend/.env` file created in Step 5):

1. Create a free account at [huggingface.co](https://huggingface.co) if you do not already have one.
2. Visit the [model page](https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M) and click **Agree and access repository**. Approval is instant and automatic.
3. Create an access token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
4. Provide the token to the app in either of these two ways:
   - Run `huggingface-cli login` from this machine and paste the token when prompted, or
   - Open `backend/.env` in a text editor and add the line `HF_TOKEN=your_token_here`.
5. Restart the backend (Terminal 1) if it was already running, so it picks up the new setting.

The first Hindi or Marathi message in any run will then download the model (roughly 200 MB) automatically. Later runs reuse the cached copy, so the download happens only once.

---

## Optional: using Groq instead of local Ollama

By default all reasoning runs locally through Ollama, which needs no API key and no internet. If you want faster responses and are willing to use a cloud service, you can route the reasoning calls (gatekeeper, classify, urgency, extract, dialogue manager, and reply composer) to Groq instead.

To switch (do this any time after completing [Setup, step by step](#setup-step-by-step), since it edits the `backend/.env` file created in Step 5):

1. Get an API key from [groq.com](https://groq.com/).
2. Open `backend/.env` in a text editor and set `GROQ_API_KEY` to your key.
3. Restart the backend (Terminal 1).

When `GROQ_API_KEY` is set, Groq handles the reasoning using `GROQ_MODEL`, and Ollama is used only for embeddings (Groq does not provide an embeddings endpoint). To go back to fully local operation, clear the `GROQ_API_KEY` value and restart. Nothing else needs to change, because both model names stay in the file at the same time and only the presence of the key decides which backend is used.


---

## Setup, step by step

The commands below assume you start from the project root directory (the folder that contains `backend/`, `frontend/`, and this README). Windows PowerShell commands are shown first, with the macOS and Linux equivalent noted where it differs. Steps with a single code block (pulling models, installing PyTorch, installing Python dependencies, installing frontend dependencies) use the exact same command on all three platforms.

### Step 1: Pull the local models (once)

Ollama needs to download the two models the app uses. This is a one time step, and requires the Ollama service to already be running (see [Prerequisites](#prerequisites)).

```bash
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text
```

You can confirm they are installed with `ollama list`.

### Step 2: Create a Python virtual environment

A virtual environment keeps this project's Python packages separate from the rest of your system.

Windows (PowerShell):

```powershell
python -m venv venv
venv\Scripts\activate
```

macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

Once active, your shell prompt will show `(venv)` at the start of the line. Every command below that starts with `pip` or `python` must be run with this virtual environment active.

### Step 3: Install PyTorch (CPU build) first

Install PyTorch from its CPU only package index. Doing this before the main install avoids accidentally downloading a large multi gigabyte GPU build. Same command on Windows, macOS, and Linux:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

(macOS/Linux: use `pip3` instead of `pip` if `pip` is not recognized inside the activated virtual environment — this is uncommon, since activating `venv` normally puts the right `pip` on your `PATH`.)

### Step 4: Install the remaining Python dependencies

```bash
pip install -r requirements.txt
```

### Step 5: Create the backend environment file

The backend reads its settings from `backend/.env`. Copy the provided example to create your own copy.

Windows (PowerShell):

```powershell
copy backend\.env.example backend\.env
```

macOS/Linux:

```bash
cp backend/.env.example backend/.env
```

The default values in this file are already set up for a fully local run, so you do not need to edit anything to get started. See the [Configuration reference](#configuration-reference) for what each setting does.

### Step 6: Install the frontend dependencies

Same command on Windows, macOS, and Linux:

```bash
cd frontend
npm install
cd ..
```

This reads `frontend/package.json` and installs React, Vite, and the rest of the frontend packages. It only needs to be run once (or again whenever the dependencies change).

At this point the setup is complete.

---

## Running the application

The application has two parts that run at the same time: the backend API and the frontend dev server. Open two terminals, both from the project root directory.

### Terminal 1: start the backend

Make sure your virtual environment is active first (`venv\Scripts\activate` on Windows, or `source venv/bin/activate` on macOS/Linux — see [Step 2](#setup-step-by-step) if you skipped setup).

Windows (PowerShell):

```powershell
$env:PYTHONPATH="backend"
uvicorn app.main:app --reload --port 8000 --app-dir backend
```

macOS/Linux:

```bash
export PYTHONPATH=backend
uvicorn app.main:app --reload --port 8000 --app-dir backend
```

Leave this terminal running. The backend is now available at `http://localhost:8000`. Verify it by opening `http://localhost:8000/health` in a browser — it should return `{"status": "ok"}`. The interactive API documentation is available at `http://localhost:8000/docs`.

The database file (`backend/civic.db`) is created automatically on the first start — no manual database setup is needed.

### Terminal 2: start the frontend

Same command on Windows, macOS, and Linux:

```bash
cd frontend
npm run dev
```

Leave this terminal running too. It will print a local URL (usually `http://localhost:5173/`); the three application surfaces are all served from that same origin, at these exact paths:

| Surface | URL |
| --- | --- |
| Citizen portal | `http://localhost:5173/` |
| Leader dashboard | `http://localhost:5173/dashboard` |
| Evaluation console | `http://localhost:5173/internal-eval` |

Open each link in its own browser tab. With both terminals running (backend on port 8000, frontend on port 5173), the application is fully usable end to end.

---


---

## Seeding demo data

To populate the dashboard with example complaints and suggestions so you can see how it looks with data, run the seed script with the backend dependencies installed and the virtual environment active:

```bash
python backend/app/db/seed.py
```

(macOS/Linux: use `python3` if `python` is not recognized.)

This is optional but recommended for a first run, so the leader dashboard is not empty.

---

## Running the evaluation harness

The evaluation harness measures how accurately the AI pipeline performs (gatekeeper accuracy, category accuracy, urgency match, duplicate detection precision and recall, extraction quality, and more).

Make sure Ollama is running and the virtual environment is active, then run:

Windows (PowerShell):

```powershell
$env:PYTHONPATH="backend"
python backend/eval/run_eval.py
```

macOS/Linux:

```bash
export PYTHONPATH=backend
python3 backend/eval/run_eval.py
```

Results are written to `backend/eval/reports/eval_<timestamp>.json`. Because this runs many local model calls, a full run can take a while on CPU.

---

## Running the test suite

Windows (PowerShell):

```powershell
$env:PYTHONPATH="backend"
python -m pytest backend/tests/ -v
```

macOS/Linux:

```bash
export PYTHONPATH=backend
python3 -m pytest backend/tests/ -v
```

---

## Configuration reference

All backend settings live in `backend/.env`. The defaults are tuned for a fully local run.

| Setting | Default | What it does |
| --- | --- | --- |
| `GROQ_API_KEY` | empty | If set, Groq handles reasoning calls. If empty, everything runs locally on Ollama. |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | The Groq model used for reasoning, when Groq is active. |
| `OLLAMA_LLM_MODEL` | `qwen2.5:1.5b` | The local Ollama model used for reasoning, when Groq is not active. |
| `EMBEDDING_MODEL` | `nomic-embed-text` | The Ollama model used to generate embeddings for duplicate detection. Always local. |
| `HF_TOKEN` | empty | Hugging Face access token for the Hindi and Marathi translation model. Optional. |
| `DB_PATH` | `civic.db` | Path to the SQLite database file. Created automatically. |
| `OLLAMA_HOST` | `http://localhost:11434` | Where the Ollama service is listening. |
| `OLLAMA_NUM_THREAD` | `4` | Number of CPU threads Ollama should use. Set this to your CPU core count for best speed. |

---

## Project structure

```
Civic-voice-agent/
├── backend/
│   ├── app/
│   │   ├── api/          FastAPI route handlers (complaints, suggestions, stats, settings, eval, intake)
│   │   ├── db/           Database session, table creation, seed script, and the separate eval metrics store
│   │   ├── llm/          LLM client, retry and JSON parsing, and one prompt schema per pipeline stage
│   │   ├── models/       SQLModel database tables and Pydantic request and response schemas
│   │   ├── pipeline/     The processing pipeline: orchestrator, stages, dedup, language, translation
│   │   ├── utils/        Logging helpers
│   │   ├── config.py     Settings loaded from .env
│   │   └── main.py       FastAPI app entry point
│   ├── eval/             Offline evaluation harness and scoring scripts
│   ├── tests/            Pytest test suite
│   └── .env.example      Template for the backend environment file
├── frontend/
│   ├── src/
│   │   ├── api/          Client side API calls and helpers
│   │   ├── components/   Reusable UI pieces (chat intake, dashboard rows, filters, cards)
│   │   ├── pages/        Full pages (Home, Suggestions, Statistics, Archive, Settings, and more)
│   │   ├── App.jsx       Top level routing between the citizen and leader surfaces
│   │   └── main.jsx      React entry point
│   ├── package.json      Frontend dependencies and scripts
│   └── vite.config.js    Vite configuration
├── requirements.txt      Python dependencies
└── README.md             This file
```

---

## Troubleshooting

**The backend cannot reach Ollama.** Make sure the Ollama service is running. You can test it by opening `http://localhost:11434` in a browser, which should show a short confirmation that Ollama is running. If you changed the port, update `OLLAMA_HOST` in `backend/.env`.

**A model is not found.** Confirm the two models were pulled with `ollama list`. If they are missing, run the `ollama pull` commands from [Step 1](#setup-step-by-step) again.

**`ModuleNotFoundError: No module named 'app'` when starting the backend.** This means `PYTHONPATH` is not set. Set it to `backend` as shown in the run commands, and make sure you are running from the project root.

**The frontend loads but shows no data.** Confirm the backend is running on port 8000, and consider running the [seed script](#seeding-demo-data) so there is demo data to display.

**Hindi or Marathi messages are not being translated.** This is expected until you complete the optional Hugging Face setup. The app keeps working and passes the original text through. Follow the [translation setup](#optional-hindi-and-marathi-translation) to enable it.

**Responses feel slow.** Local models on CPU are slower than cloud APIs. You can raise `OLLAMA_NUM_THREAD` in `backend/.env` to match your CPU core count, or switch to the optional Groq backend for faster reasoning.

**`python: command not found` on macOS/Linux.** Use `python3` and `pip3` instead of `python` and `pip` throughout this guide — most macOS and Linux installs don't alias `python` to Python 3 by default.

**Port 8000 or 5173 is already in use.** Stop whatever else is using that port, or start the backend on a different port with `--port <number>` (and adjust anywhere `localhost:8000` is referenced accordingly), or start the frontend on a different port with `npm run dev -- --port <number>`.
