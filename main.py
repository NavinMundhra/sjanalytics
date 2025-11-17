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
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# Initialize S3 client
s3_client = None
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    s3_config = {
        'aws_access_key_id': AWS_ACCESS_KEY_ID,
        'aws_secret_access_key': AWS_SECRET_ACCESS_KEY,
        'region_name': AWS_REGION
    }
    # Add session token if provided (for temporary credentials)
    if AWS_SESSION_TOKEN:
        s3_config['aws_session_token'] = AWS_SESSION_TOKEN

    s3_client = boto3.client('s3', **s3_config)


def get_csv_files_from_s3() -> dict:
    """Fetch all CSV files from S3 bucket recursively (including subdirectories) and return as dictionary of DataFrames"""
    if not s3_client or not S3_BUCKET_NAME:
        return {}

    csv_data = {}
    try:
        # Use paginator to handle buckets with many files
        paginator = s3_client.get_paginator('list_objects_v2')

        # Iterate through all pages of results (handles subdirectories automatically)
        for page in paginator.paginate(Bucket=S3_BUCKET_NAME):
            if 'Contents' not in page:
                continue

            for obj in page['Contents']:
                if obj['Key'].endswith('.csv'):
                    file_name = obj['Key']
                    try:
                        csv_obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=file_name)
                        csv_content = csv_obj['Body'].read().decode('utf-8')
                        df = pd.read_csv(StringIO(csv_content))
                        csv_data[file_name] = df
                        print(f"Loaded CSV: {file_name} ({len(df)} rows)")
                    except Exception as e:
                        print(f"Error loading CSV {file_name}: {e}")
                        continue
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
        "HTTP-Referer": "https://sjanalytics.railway.app",
        "X-Title": "SJ Analytics WhatsApp Bot"
    }

    payload = {
        "model": "google/gemini-2.0-flash-exp:free",
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.7
    }

    print(f"Calling OpenRouter API with model: {payload['model']}")
    print(f"API Key (first 8 chars): {OPENROUTER_API_KEY[:8]}...")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                OPENROUTER_BASE_URL,
                headers=headers,
                json=payload
            )

            # Log response for debugging
            print(f"OpenRouter response status: {response.status_code}")
            if response.status_code != 200:
                print(f"OpenRouter response body: {response.text}")

            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
    except httpx.HTTPStatusError as e:
        print(f"HTTP error from OpenRouter: {e}")
        print(f"Response body: {e.response.text}")
        return "Sorry, I encountered an error while processing your request. Please try again later."
    except Exception as e:
        print(f"Error querying Gemini: {e}")
        return "Sorry, I encountered an unexpected error. Please try again later."


async def send_whatsapp_message(phone_number: str, message: str):
    """Send WhatsApp message via Gupshup API"""
    if not all([GUPSHUP_API_KEY, GUPSHUP_APP_NAME, GUPSHUP_SOURCE_NUMBER]):
        print("Gupshup configuration incomplete")
        print(f"  API Key set: {bool(GUPSHUP_API_KEY)}")
        print(f"  App Name: {GUPSHUP_APP_NAME}")
        print(f"  Source Number: {GUPSHUP_SOURCE_NUMBER}")
        return False

    url = "https://api.gupshup.io/wa/api/v1/msg"

    headers = {
        "apikey": GUPSHUP_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache"
    }

    # Ensure phone number is in correct format (no + sign, just digits)
    clean_phone = phone_number.replace("+", "").replace(" ", "").replace("-", "")
    clean_source = GUPSHUP_SOURCE_NUMBER.replace("+", "").replace(" ", "").replace("-", "")

    data = {
        "channel": "whatsapp",
        "source": clean_source,
        "destination": clean_phone,
        "message": json.dumps({"type": "text", "text": message}),
        "src.name": GUPSHUP_APP_NAME
    }

    print(f"Sending message to {clean_phone} from {clean_source}")
    print(f"App name: {GUPSHUP_APP_NAME}")
    print(f"API Key (first 8 chars): {GUPSHUP_API_KEY[:8]}...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, data=data)

            # Log response details for debugging
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")

            response.raise_for_status()
            print(f"Message sent successfully to {clean_phone}")
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


@app.get("/debug/gupshup")
async def debug_gupshup():
    """
    Debug endpoint to verify Gupshup configuration.
    Shows configuration details (without exposing full API key).
    """
    api_key_info = "Not set"
    if GUPSHUP_API_KEY:
        api_key_info = f"{GUPSHUP_API_KEY[:8]}...{GUPSHUP_API_KEY[-4:]}" if len(GUPSHUP_API_KEY) > 12 else "Set but too short"

    return {
        "gupshup_api_key": api_key_info,
        "gupshup_app_name": GUPSHUP_APP_NAME or "Not set",
        "gupshup_source_number": GUPSHUP_SOURCE_NUMBER or "Not set",
        "all_configured": all([GUPSHUP_API_KEY, GUPSHUP_APP_NAME, GUPSHUP_SOURCE_NUMBER]),
        "note": "If you're getting 401 errors, verify: 1) API key is correct from Gupshup dashboard, 2) App name matches exactly, 3) Source number is your sandbox/WhatsApp Business number"
    }


@app.post("/webhook/gupshup")
async def gupshup_webhook(request: Request):
    """
    Webhook endpoint for Gupshup WhatsApp messages.
    This endpoint receives incoming WhatsApp messages and responds with data analysis.

    Expected Gupshup payload structure:
    {
        "app": "AppName",
        "timestamp": 1580227766370,
        "version": 2,
        "type": "message",
        "payload": {
            "id": "message_id",
            "source": "919876543210",
            "type": "text",
            "payload": {
                "text": "user message here"
            },
            "sender": {
                "phone": "919876543210",
                "name": "User Name",
                "country_code": "91",
                "dial_code": "9876543210"
            }
        }
    }
    """
    try:
        # Parse the incoming request
        content_type = request.headers.get("content-type", "")

        if "application/json" in content_type:
            payload = await request.json()
        else:
            # Gupshup may send form-urlencoded data
            form_data = await request.form()
            payload = dict(form_data)
            # If payload field exists as string, parse it
            if "payload" in payload and isinstance(payload["payload"], str):
                try:
                    payload["payload"] = json.loads(payload["payload"])
                except json.JSONDecodeError:
                    pass

        print(f"Received webhook payload: {json.dumps(payload, indent=2)}")

        # Extract message details from Gupshup payload
        event_type = payload.get("type", "")
        phone_number = ""
        user_message = ""

        if event_type == "message":
            # Standard Gupshup message event structure
            message_payload = payload.get("payload", {})

            # Handle case where payload might be a string
            if isinstance(message_payload, str):
                try:
                    message_payload = json.loads(message_payload)
                except json.JSONDecodeError:
                    message_payload = {}

            # Get phone number from sender object or source field
            sender = message_payload.get("sender", {})
            if isinstance(sender, dict):
                phone_number = sender.get("phone", "")
            if not phone_number:
                phone_number = message_payload.get("source", "")

            # Get message content based on message type
            message_type = message_payload.get("type", "")
            inner_payload = message_payload.get("payload", {})

            if isinstance(inner_payload, str):
                try:
                    inner_payload = json.loads(inner_payload)
                except json.JSONDecodeError:
                    inner_payload = {"text": inner_payload}

            if message_type == "text" and isinstance(inner_payload, dict):
                user_message = inner_payload.get("text", "")
            elif isinstance(inner_payload, dict):
                # Handle other message types (image, audio, etc.)
                user_message = inner_payload.get("text", inner_payload.get("caption", ""))
            else:
                user_message = str(inner_payload)

        elif event_type == "message-event":
            # This is a delivery/read receipt, not a user message
            print("Received message event (delivery/read receipt), ignoring")
            return JSONResponse(content={"status": "ok", "message": "Event acknowledged"})
        else:
            # Try alternative/legacy payload structure
            phone_number = payload.get("mobile", payload.get("sender", payload.get("source", "")))
            user_message = payload.get("text", payload.get("message", ""))

        if not phone_number or not user_message:
            print(f"Could not extract phone number or message from payload")
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
