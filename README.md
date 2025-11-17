# SJ Analytics WhatsApp Bot

A WhatsApp bot webhook that uses Google Gemini (via OpenRouter) to analyze CSV data stored in AWS S3 and respond to user queries.

## Features

- **Gupshup WhatsApp Integration**: Receives and responds to WhatsApp messages
- **AWS S3 Data Storage**: Fetches CSV files from your S3 bucket
- **Google Gemini AI**: Uses Gemini 2.0 Flash for intelligent data analysis
- **FastAPI Backend**: High-performance async API
- **Railway Deployment Ready**: Pre-configured for Railway deployment

## Architecture

```
User (WhatsApp) → Gupshup → Webhook → S3 (CSV Data) → Gemini AI → Response
```

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/NavinMundhra/sjanalytics.git
cd sjanalytics
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required environment variables:
- `OPENROUTER_API_KEY`: Your OpenRouter API key
- `GUPSHUP_API_KEY`: Your Gupshup API key
- `GUPSHUP_APP_NAME`: Your Gupshup app name
- `GUPSHUP_SOURCE_NUMBER`: Your WhatsApp business number
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key
- `S3_BUCKET_NAME`: Your S3 bucket containing CSV files

### 4. Run locally

```bash
python main.py
```

Or with uvicorn:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### Health Check
- `GET /` - Basic health check
- `GET /health` - Detailed health check with service status

### Webhooks
- `POST /webhook/gupshup` - Main webhook for Gupshup WhatsApp messages

### Testing
- `POST /test/analyze` - Test data analysis without WhatsApp integration

Example test request:
```bash
curl -X POST http://localhost:8000/test/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the total sales for last month?"}'
```

## Deployment on Railway

1. Create a new project on [Railway](https://railway.app)
2. Connect your GitHub repository
3. Add all environment variables in Railway's settings
4. Deploy! Railway will automatically detect the Python project

### Configure Gupshup Webhook

After deployment, set your Gupshup webhook URL to:
```
https://your-railway-app.up.railway.app/webhook/gupshup
```

## S3 Data Format

Place your CSV files in your S3 bucket. The bot will automatically:
1. List all CSV files in the bucket
2. Load them into memory
3. Provide data context to Gemini for analysis

### Tips for Best Results

- Use descriptive column names in your CSVs
- Include headers in all CSV files
- Keep data clean and well-formatted
- Organize related data in separate CSV files

## Example Use Cases

- "What are the top 5 products by sales?"
- "Show me the average revenue per customer"
- "Compare this month's performance to last month"
- "Give me a summary of the inventory data"

## Security Considerations

- Never commit `.env` file to version control
- Use IAM roles with minimal permissions for S3 access
- Rotate API keys regularly
- Consider implementing rate limiting for production

## License

MIT License
