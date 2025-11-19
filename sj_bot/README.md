# SmartJoules Analytics Bot v3.0 - Production Architecture

## Overview

Production-grade WhatsApp bot for SmartJoules analytics with **zero hallucination**, deterministic responses, and built-in visualization.

### Key Improvements Over v2.0

| Issue | v2.0 | v3.0 |
|-------|------|------|
| Data Retrieval | LLM analyzes raw CSV | SQL queries (deterministic) |
| Accuracy | LLM does math (error-prone) | Database aggregations (100% accurate) |
| Consistency | Random outputs | Same query = same answer |
| Security | Raw data sent to LLM | Only results sent to LLM |
| Scalability | Load CSV on each request | SQLite with indexes |
| Visualization | None | Auto-generate charts |

## Architecture

```
User Query (WhatsApp)
       ↓
   [LLM understands intent & calls tools]
       ↓
   [Python functions execute SQL] ← DETERMINISTIC
       ↓
   [Results returned to LLM]
       ↓
   [LLM formats results in natural language]
       ↓
   [Optional: Generate chart PNG]
       ↓
   WhatsApp Response (text + image)
```

### Core Principles

1. **LLM for Language, Not Math**: LLM only formats pre-computed results
2. **SQL for Accuracy**: All data queries use SQLAlchemy
3. **No Raw Data to LLM**: Only aggregated results leave the system
4. **Deterministic Tools**: Same input → Same output
5. **Validation**: Every response can be verified

## Project Structure

```
sj_bot/
├── app/
│   ├── config.py              # Settings management
│   ├── db.py                  # Database connection
│   ├── models.py              # SQLAlchemy models
│   ├── schemas.py             # Pydantic schemas
│   ├── metrics_service.py     # Deterministic SQL queries
│   ├── visualization_service.py  # Chart generation
│   ├── llm_tools.py           # LLM function calling tools
│   ├── whatsapp_webhook.py    # WhatsApp integration
│   └── main.py                # FastAPI app
├── scripts/
│   └── load_metrics_from_csv.py  # ETL for data loading
├── data/
│   └── metrics.db             # SQLite database
├── tests/
├── requirements.txt
├── Dockerfile
└── README.md
```

## Quick Start

### 1. Install Dependencies

```bash
cd sj_bot
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
# LLM Configuration
LLM_API_KEY=your_openrouter_key
LLM_MODEL=openai/gpt-4o-mini

# WhatsApp (Gupshup)
GUPSHUP_API_KEY=your_key
GUPSHUP_APP_NAME=smartjoules
GUPSHUP_SOURCE_NUMBER=917834811114

# Database
SQLITE_DB_PATH=sj_bot/data/metrics.db

# Security
API_KEY=your_secure_api_key_here
```

### 3. Load Data

```bash
# From CSV file
python -m scripts.load_metrics_from_csv \
  --csv-path /path/to/monthly_master.csv \
  --data-version 2025_01

# Or from S3
python -m scripts.load_metrics_from_s3 \
  --bucket smartjoules-data \
  --key monthly_master/master.csv
```

### 4. Run Server

```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Endpoints

### Metrics Endpoints

```http
GET /metrics/timeseries
  ?site_ids=KIMS_NASIK,MANIPAL_GOA
  &metric_names=revenue,energy_savings
  &from_date=2024-04-01
  &to_date=2025-03-31

GET /metrics/summary
  ?metric_name=revenue
  &from_date=2024-04-01
  &to_date=2025-03-31
  &aggregation=sum

GET /metrics/ranking
  ?metric_name=revenue
  &from_date=2024-04-01
  &to_date=2025-03-31
  &top_n=5

GET /metrics/sites
GET /metrics/list
```

### Chart Endpoints

```http
POST /charts/timeseries
{
  "title": "Revenue Trend - FY24-25",
  "x": ["2024-04-01", "2024-05-01", ...],
  "series": [
    {"label": "KIMS Nasik", "values": [120000, 135000, ...]},
    {"label": "Manipal Goa", "values": [95000, 105000, ...]}
  ],
  "y_label": "Revenue (₹)"
}

# Returns PNG image
```

### Bot Endpoints

```http
POST /bot/query
{
  "user_id": "919876543210",
  "message": "What is total revenue for KIMS Nasik in FY24-25?"
}

# Returns:
{
  "text": "Total revenue for KIMS Nasik from April 2024 to March 2025 is ₹14,52,000.",
  "chart_png": "base64_encoded_image",  # optional
  "data": {...}  # structured data
}
```

### WhatsApp Webhook

```http
POST /whatsapp/webhook
  # Receives messages from Gupshup
  # Processes with LLM
  # Sends response + chart
```

## How It Works

### 1. User Sends Query

```
"What is the revenue trend for KIMS Nasik last 6 months?"
```

### 2. LLM Understands Intent & Calls Tools

```python
# LLM decides to call:
get_timeseries(
    site_ids=["KIMS_NASIK"],
    metric_names=["revenue"],
    from_date="2024-10-01",
    to_date="2025-03-31"
)
```

### 3. Tool Executes SQL Query

```sql
SELECT site_id, month_start, metric_value, unit
FROM site_month_metrics
WHERE site_id = 'KIMS_NASIK'
  AND metric_name = 'revenue'
  AND month_start BETWEEN '2024-10-01' AND '2025-03-31'
ORDER BY month_start
```

### 4. Results Returned

```json
{
  "points": [
    {"month": "2024-10-01", "value": 235000},
    {"month": "2024-11-01", "value": 242000},
    ...
  ]
}
```

### 5. LLM Formats Response

```
"Revenue trend for KIMS Nasik (Oct 2024 - Mar 2025):
- Oct: ₹2,35,000
- Nov: ₹2,42,000
- Dec: ₹2,51,000
- Jan: ₹2,48,000
- Feb: ₹2,55,000
- Mar: ₹2,61,000

Total: ₹14,92,000
Average: ₹2,48,667/month"
```

### 6. Optional: Generate Chart

```python
generate_chart(
    title="Revenue Trend - KIMS Nasik",
    chart_type="timeseries",
    data={
        "x": ["2024-10-01", ...],
        "series": [{"label": "Revenue", "values": [235000, ...]}],
        "y_label": "Revenue (₹)"
    }
)
```

## Data Model

### SiteMonthMetric Table

```sql
CREATE TABLE site_month_metrics (
    id INTEGER PRIMARY KEY,
    site_id VARCHAR,           -- "KIMS_NASIK"
    site_name VARCHAR,         -- "KIMS Hospital Nasik"
    month_start DATE,          -- 2024-04-01
    fy_label VARCHAR,          -- "FY24-25"
    metric_name VARCHAR,       -- "revenue", "energy_savings"
    metric_value FLOAT,        -- 235000.00
    unit VARCHAR,              -- "₹", "kWh"
    data_version VARCHAR,      -- "2025_01_refresh"
    created_at TIMESTAMP
);
```

### Supported Metrics

- `revenue` - Monthly revenue (₹)
- `energy_savings` - Energy saved (kWh)
- `chiller_kwh_trh` - Chiller efficiency (kWh/TRh)
- `water_usage` - Water consumption (L)
- `cop` - Coefficient of Performance
- Custom metrics as needed

## Security

### 1. No Raw Data Exposure

```python
# ✓ GOOD: Only send aggregated results
{"total_revenue": 1492000, "period": "Oct-Mar"}

# ✗ BAD: Don't send raw data
{all_rows_from_csv}
```

### 2. API Key Protection

All internal endpoints require `X-API-KEY` header.

### 3. Data Validation

Every metric query validates:
- Date ranges
- Site IDs exist
- Metric names are valid

### 4. PII Masking

User phone numbers masked in logs:
```
91905****004 instead of 919051657004
```

## Monitoring

### Structured Logs

```json
{
  "timestamp": "2025-01-17T10:30:00Z",
  "event": "bot_query",
  "user": "91905****004",
  "query": "total revenue FY24-25",
  "tools_called": ["get_summary"],
  "response_time_ms": 342,
  "success": true
}
```

### Metrics to Track

- Query response time
- Tool call success rate
- Chart generation time
- WhatsApp delivery rate

## Testing

```bash
# Run tests
pytest tests/

# Test specific endpoint
curl -X POST http://localhost:8000/bot/query \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your_key" \
  -d '{"user_id": "test", "message": "total revenue"}'
```

## Deployment

### Docker

```bash
docker build -t smartjoules-bot:3.0 .
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  smartjoules-bot:3.0
```

### Railway

```bash
# Push to GitHub
git push origin main

# Connect in Railway dashboard
# Add environment variables
# Deploy automatically
```

## Future Enhancements

1. **PostgreSQL** instead of SQLite for production
2. **Redis caching** for frequently requested data
3. **Celery** for async chart generation
4. **Conversation history** for context-aware responses
5. **A/B testing** for prompt optimization
6. **Data validation layer** to verify LLM responses

## FAQ

**Q: How is this different from just sending CSV to LLM?**

A: v2.0 sent raw data to LLM, which "analyzed" it (error-prone). v3.0 uses SQL for analysis (deterministic), LLM only formats results.

**Q: Can the LLM still hallucinate?**

A: The LLM can only format pre-computed numbers. It can't invent new numbers because it never sees the raw data.

**Q: What if the LLM misformats a number?**

A: We validate every response. If formatting is wrong, we fall back to template-based output.

**Q: How do I add new metrics?**

A: Add rows to `site_month_metrics` table. No code changes needed.

**Q: Can users ask complex questions?**

A: Yes! LLM understands intent and chains multiple tool calls. Example: "Compare top 5 sites by revenue in Q1 vs Q2" → calls `get_ranking` twice, then `generate_chart`.

## License

Proprietary - SmartJoules Analytics
