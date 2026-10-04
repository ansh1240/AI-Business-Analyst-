# AI Business Analyst

An AI-powered business analytics platform that analyzes business datasets,
generates KPIs, visualizations, insights, and recommendations, and answers
business questions using natural language.

## Features

- CSV/Excel data upload
- Automated data cleaning
- Data profiling
- KPI generation
- Interactive dashboards
- AI-powered business analysis
- Business insights
- Recommendations
- Anomaly detection
- Sales forecasting
- Business report generation

## Tech stack

- Frontend: React, Vite, and Recharts
- Backend: FastAPI, Pandas, and MongoDB

## Requirements

- Python 3.10+
- Node.js and npm
- MongoDB running locally on the default port (`27017`)

## Run locally

1. Create a backend environment and install dependencies:

   ```bash
   cd backend
   python -m venv .venv
   ```

   Activate the virtual environment, then run:

   ```bash
   pip install -r requirements.txt
   ```

2. Create `backend/.env` from `backend/.env.example` and set a unique,
   secure `SECRET_KEY`.

3. Start the API from the `backend` directory:

   ```bash
   uvicorn main:app --reload
   ```

4. In another terminal, start the frontend:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   Open the local URL printed by Vite (usually `http://localhost:5173`).