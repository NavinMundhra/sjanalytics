import os
import json
import httpx
import pandas as pd
from io import StringIO
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="SJ Analytics WhatsApp Bot",
    description="WhatsApp bot for data analysis using Gupshup and Google Gemini",
    version="1.0.0"
)

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
GUPSHUP_API_KEY = os.getenv("GUPSHUP_API_KEY")
GUPSHUP_APP_NAME = os.getenv("GUPSHUP_APP_NAME")
GUPSHUP_SOURCE_NUMBER = os.getenv("GUPSHUP_SOURCE_NUMBER")

# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# Initialize S3 client
s3_client = None
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )


def get_csv_files_from_s3() -> dict:
    """Fetch all CSV files from S3 bucket and return as dictionary of DataFrames"""
    if not s3_client or not S3_BUCKET_NAME:
        return {}

    csv_data = {}
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME)

        if 'Contents' not in response:
            return {}

        for obj in response['Contents']:
            if obj['Key'].endswith('.csv'):
                file_name = obj['Key']
                csv_obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=file_name)
                csv_content = csv_obj['Body'].read().decode('utf-8')
                df = pd.read_csv(StringIO(csv_content))
                csv_data[file_name] = df
    except ClientError as e:
        print(f"Error fetching CSV files from S3: {e}")

    return csv_data


def get_data_summary(csv_data: dict) -> str:
    """Generate a summary of available data for the LLM context"""
    if not csv_data:
        return "No data files available."

    summary = "Available datasets:\n\n"
    for file_name, df in csv_data.items():
        summary += f"File: {file_name}\n"
        summary += f"Columns: {', '.join(df.columns.tolist())}\n"
        summary += f"Rows: {len(df)}\n"
        summary += f"Sample data (first 3 rows):\n{df.head(3).to_string()}\n\n"

    return summary


async def query_gemini(user_message: str, data_context: str) -> str:
    """Query Google Gemini via OpenRouter API"""
    if not OPENROUTER_API_KEY:
        return "OpenRouter API key not configured. Please set OPENROUTER_API_KEY environment variable."

    system_prompt = """You are a data analysis assistant for a WhatsApp bot. Your role is to:
1. Analyze data from CSV files stored in AWS S3
2. Answer user queries about the data
3. Provide insights and analysis based on the available data
4. Format responses in a clear, concise manner suitable for WhatsApp messages

Keep responses brief and mobile-friendly. Use bullet points and short paragraphs.
If asked for specific data, provide exact numbers and relevant statistics.
If the data doesn't contain information to answer the query, clearly state that."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"""Here is the available data context:

{data_context}

User Query: {user_message}

Please analyze the data and provide a helpful response to the user's query. Format your response for WhatsApp (keep it concise and easy to read on mobile)."""}
    ]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://sjanalytics.app",
        "X-Title": "SJ Analytics WhatsApp Bot"
    }

    payload = {
        "model": "google/gemini-2.0-flash-001",
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.7
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                OPENROUTER_BASE_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
    except httpx.HTTPStatusError as e:
        print(f"HTTP error from OpenRouter: {e}")
        return "Sorry, I encountered an error while processing your request. Please try again later."
    except Exception as e:
        print(f"Error querying Gemini: {e}")
        return "Sorry, I encountered an unexpected error. Please try again later."


async def send_whatsapp_message(phone_number: str, message: str):
    """Send WhatsApp message via Gupshup API"""
    if not all([GUPSHUP_API_KEY, GUPSHUP_APP_NAME, GUPSHUP_SOURCE_NUMBER]):
        print("Gupshup configuration incomplete")
        return False

    url = "https://api.gupshup.io/sm/api/v1/msg"

    headers = {
        "apikey": GUPSHUP_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "channel": "whatsapp",
        "source": GUPSHUP_SOURCE_NUMBER,
        "destination": phone_number,
        "message": json.dumps({"type": "text", "text": message}),
        "src.name": GUPSHUP_APP_NAME
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, data=data)
            response.raise_for_status()
            print(f"Message sent successfully to {phone_number}")
            return True
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")
        return False


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "SJ Analytics WhatsApp Bot",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "s3_configured": s3_client is not None,
        "openrouter_configured": OPENROUTER_API_KEY is not None,
        "gupshup_configured": all([GUPSHUP_API_KEY, GUPSHUP_APP_NAME, GUPSHUP_SOURCE_NUMBER])
    }


@app.post("/webhook/gupshup")
async def gupshup_webhook(request: Request):
    """
    Webhook endpoint for Gupshup WhatsApp messages.
    This endpoint receives incoming WhatsApp messages and responds with data analysis.
    """
    try:
        # Parse the incoming request
        content_type = request.headers.get("content-type", "")

        if "application/json" in content_type:
            payload = await request.json()
        else:
            # Gupshup often sends form-urlencoded data
            form_data = await request.form()
            payload = dict(form_data)

        print(f"Received webhook payload: {payload}")

        # Extract message details from Gupshup payload
        # Gupshup sends different payload structures, handle common ones
        message_type = payload.get("type", "")

        if message_type == "message":
            # Standard message event
            message_payload = payload.get("payload", {})
            if isinstance(message_payload, str):
                message_payload = json.loads(message_payload)

            sender = message_payload.get("sender", {})
            phone_number = sender.get("phone", "") if isinstance(sender, dict) else payload.get("mobile", "")

            message_content = message_payload.get("payload", {})
            if isinstance(message_content, dict):
                user_message = message_content.get("text", "")
            else:
                user_message = str(message_content)
        else:
            # Try alternative payload structure
            phone_number = payload.get("mobile", payload.get("sender", ""))
            user_message = payload.get("text", payload.get("message", ""))

        if not phone_number or not user_message:
            print(f"Could not extract phone number or message from payload: {payload}")
            return JSONResponse(content={"status": "ok", "message": "No message to process"})

        print(f"Processing message from {phone_number}: {user_message}")

        # Fetch data from S3
        csv_data = get_csv_files_from_s3()
        data_summary = get_data_summary(csv_data)

        # Query Gemini for analysis
        response_message = await query_gemini(user_message, data_summary)

        # Send response back via WhatsApp
        await send_whatsapp_message(phone_number, response_message)

        return JSONResponse(content={
            "status": "success",
            "message": "Response sent successfully"
        })

    except Exception as e:
        print(f"Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=200  # Return 200 to prevent Gupshup from retrying
        )


@app.post("/test/analyze")
async def test_analyze(request: Request):
    """
    Test endpoint to analyze data without WhatsApp integration.
    Send a JSON body with {"query": "your question about the data"}
    """
    try:
        body = await request.json()
        user_query = body.get("query", "")

        if not user_query:
            raise HTTPException(status_code=400, detail="Query is required")

        # Fetch data from S3
        csv_data = get_csv_files_from_s3()
        data_summary = get_data_summary(csv_data)

        # Query Gemini
        response = await query_gemini(user_query, data_summary)

        return {
            "query": user_query,
            "response": response,
            "datasets_available": list(csv_data.keys())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
