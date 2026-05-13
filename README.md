# Tax Analyzer

Production-style full-stack transaction intelligence app.

```
tax-analyzer/
├── backend/   # FastAPI API + existing Python classification/ML/export logic
└── frontend/  # Vite + React + TailwindCSS dashboard
```

The backend preserves the existing GST/TDS/POSSIBLE_GST intelligence, ML assistance, vendor intelligence, learning memory, review logic, CSV/PDF/XLSX loading, and Excel export pipeline. The frontend replaces the Streamlit prototype with a separately deployable React dashboard.

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

API docs are available at:

```text
http://localhost:8000/docs
```

Core endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/statements/upload` | Upload `.xlsx`, `.xls`, `.csv`, or table-based `.pdf` statement |
| `POST` | `/api/statements/{statement_id}/analyze` | Run transaction classification |
| `GET` | `/api/statements/{statement_id}/summary` | Fetch KPI, amount, confidence, and review summaries |
| `GET` | `/api/statements/{statement_id}/transactions` | Fetch classified transactions with filters |
| `GET` | `/api/statements/{statement_id}/export` | Export category workbook or full ZIP |

## Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The frontend expects:

```text
VITE_API_BASE_URL=http://localhost:8000/api
```

## Deployment

- Deploy `backend/` as a Python FastAPI service.
- Deploy `frontend/` as a static Vite build.
- Configure `backend/.env` `CORS_ORIGINS` to include the deployed frontend URL.
- Configure `frontend/.env` `VITE_API_BASE_URL` to point to the deployed backend API.

## Notes

PDF support is best-effort for text/table-based PDFs. Scanned or password-protected statements still require OCR or conversion before analysis.
