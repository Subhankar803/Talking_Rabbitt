# Talking Rabbitt — AI-Powered Business Intelligence Dashboard!

An AI-powered "talking dashboard" that ingests business spreadsheets, automatically
analyzes them, and lets users converse with the data in natural language — by text
or voice — instead of reading static charts.

Built for **Crazy Build 2026** (JISCE Coding Club Hackathon).

## What it does

1. **Upload** a CSV/Excel file — it's cleaned (nulls filled, duplicates dropped,
   dates parsed) and its columns are automatically classified.
2. **Dashboard** — KPI cards, trend charts, top/worst performers, and anomaly
   detection are generated automatically, no configuration needed.
3. **Ask Rabbitt** — a chat assistant (text or voice) that calls real analytics
   functions as LLM tools, so every answer is grounded in your actual data.
4. **Forecast** — projects any numeric metric forward using scikit-learn
   linear regression on the historical trend.
5. **Executive report** — an auto-generated business health summary with
   risks, strengths, weaknesses, and prioritized recommendations.

## Architecture

```
frontend/          HTML5 + CSS3 + vanilla JS (no framework, no build step)
backend/
  main.py          FastAPI app entrypoint
  config.py        Environment configuration
  database.py      SQLAlchemy engine/session (MySQL)
  models.py        ORM models (datasets, chat_history, reports, recommendations, forecasts)
  schemas.py       Pydantic request/response contracts
  crud.py          All DB reads/writes
  routes/          One file per feature area (upload, analytics, chat, forecast, recommendation, voice)
  services/        Business logic — zero HTTP/DB knowledge, pure functions
    pandas_processor.py     cleaning, typing, KPIs — pure pandas
    analytics_engine.py     trends, anomalies, comparisons, risk detection
    forecast_engine.py      scikit-learn regression forecasting
    recommendation_engine.py rule-based recommendations grounded in analytics
    report_engine.py        executive summary assembly
    chat_engine.py          LLM tool-calling orchestration (Anthropic API)
    visualization_engine.py shapes analytics output into Chart.js-ready specs
    dataset_cache.py        in-memory + parquet cache of cleaned dataframes
  utils/           logger, validators, generic helpers
database/schema.sql MySQL DDL (matches models.py)
```

**Key design decision:** MySQL stores only *metadata* — dataset info, chat
history, reports, recommendations, forecasts. The actual cleaned dataframe
lives in memory and as a parquet cache file, keyed by `dataset_id`. This
keeps every analytics/chat request fast without hammering the database.

## How the conversational AI works

The chat engine exposes the analytics functions (`get_trend`, `detect_anomalies`,
`compare_dimension`, `top_bottom_performers`, `forecast_metric`) to the LLM as
tools. When a user asks "why did sales drop?", the model decides which tool(s)
to call, the backend executes them against the real dataframe, and the results
are fed back to the LLM to produce a grounded natural-language answer plus a
matching chart. If no `ANTHROPIC_API_KEY` is set, the app still runs — chat
falls back to a clear message and the Dashboard/Forecast/Report pages work
independently.

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up MySQL
```bash
mysql -u root -p < database/schema.sql
```
Or let the app create tables automatically on first run (it calls
`Base.metadata.create_all()` on startup) — just make sure the
`talking_rabbitt` database itself exists first:
```sql
CREATE DATABASE talking_rabbitt;
```

### 3. Configure environment
```bash
cp .env.example .env
# edit .env with your MySQL credentials and ANTHROPIC_API_KEY
```

### 4. Run
```bash
cd backend
uvicorn main:app --reload --port 8000
```
Open **http://localhost:8000**

## Demo flow for judges

1. Home → Upload a CSV (e.g. sample sales data) → watch the cleaning report populate live.
2. Dashboard → KPI cards, trend line, and risk signals appear automatically.
3. Ask Rabbitt → type or speak: *"Why did sales drop?"* / *"Which category performed best?"*
   — watch it call a tool and answer with a chart.
4. Forecast → pick a metric → get a 6-month projection with confidence score.
5. Executive report → one-page business health summary + prioritized recommendations.

## Tech stack

Frontend: HTML5, CSS3, vanilla JS, Chart.js, Web Speech API
Backend: FastAPI, SQLAlchemy, MySQL, Pandas, NumPy, scikit-learn
AI: Anthropic API (Claude) with tool-calling for grounded conversational analytics
