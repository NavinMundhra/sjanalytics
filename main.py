import os
import json
import httpx
import pandas as pd
from io import StringIO
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="SJ Analytics WhatsApp Bot",
    description="WhatsApp bot for data analysis using Gupshup and Google Gemini",
    version="2.0.0"
)

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")  # Default to GPT-4o-mini for accuracy
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # Direct Google Gemini API key (fallback)
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash")  # Default model for direct API
GUPSHUP_API_KEY = os.getenv("GUPSHUP_API_KEY")
GUPSHUP_APP_NAME = os.getenv("GUPSHUP_APP_NAME")
GUPSHUP_SOURCE_NUMBER = os.getenv("GUPSHUP_SOURCE_NUMBER")

# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# Data source configuration - only use specific CSV file for now
PRIMARY_DATA_FILE = os.getenv("PRIMARY_DATA_FILE", "monthly_master/master.csv")

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

# In-memory cache for CSV data to avoid repeated S3 calls
_csv_cache = {}
_cache_timestamp = None
CACHE_TTL_SECONDS = 300  # 5 minutes cache


def log_interaction(
    user_phone: str,
    user_name: str,
    user_query: str,
    llm_provider: str,
    llm_model: str,
    llm_response: str,
    data_files_used: list,
    response_time_ms: float,
    success: bool,
    error_message: str = None
):
    """Log interaction details for monitoring and analytics"""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": "user_interaction",
        "user": {
            "phone": user_phone,
            "name": user_name,
            "country_code": user_phone[:2] if len(user_phone) > 2 else ""
        },
        "query": {
            "text": user_query,
            "length": len(user_query)
        },
        "llm": {
            "provider": llm_provider,
            "model": llm_model,
            "response_length": len(llm_response) if llm_response else 0
        },
        "data": {
            "files_used": data_files_used,
            "total_files": len(data_files_used)
        },
        "performance": {
            "response_time_ms": round(response_time_ms, 2)
        },
        "status": {
            "success": success,
            "error": error_message
        },
        "bot": {
            "name": GUPSHUP_APP_NAME or "sjanalytics",
            "version": "2.0.0"
        }
    }

    # Print as structured JSON log for easy parsing by log aggregators
    print(f"MONITORING_LOG: {json.dumps(log_entry)}")
    return log_entry


def get_master_csv_from_s3() -> tuple[pd.DataFrame, str]:
    """
    Fetch only the primary master CSV file from S3.
    Returns tuple of (DataFrame, filename) or (None, None) if not found.
    Uses caching to avoid repeated S3 calls.
    """
    global _csv_cache, _cache_timestamp

    if not s3_client or not S3_BUCKET_NAME:
        return None, None

    # Check cache validity
    current_time = datetime.utcnow()
    if _cache_timestamp and (current_time - _cache_timestamp).total_seconds() < CACHE_TTL_SECONDS:
        if PRIMARY_DATA_FILE in _csv_cache:
            print(f"Using cached data for {PRIMARY_DATA_FILE}")
            return _csv_cache[PRIMARY_DATA_FILE], PRIMARY_DATA_FILE

    try:
        print(f"Fetching {PRIMARY_DATA_FILE} from S3...")
        csv_obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=PRIMARY_DATA_FILE)
        csv_content = csv_obj['Body'].read().decode('utf-8')
        df = pd.read_csv(StringIO(csv_content))

        # Update cache
        _csv_cache[PRIMARY_DATA_FILE] = df
        _cache_timestamp = current_time

        print(f"Loaded CSV: {PRIMARY_DATA_FILE} ({len(df)} rows, {len(df.columns)} columns)")
        return df, PRIMARY_DATA_FILE
    except ClientError as e:
        print(f"Error fetching {PRIMARY_DATA_FILE} from S3: {e}")
        return None, None
    except Exception as e:
        print(f"Error loading CSV {PRIMARY_DATA_FILE}: {e}")
        return None, None


def prepare_data_context(df: pd.DataFrame, filename: str) -> str:
    """
    Prepare comprehensive data context for the LLM.
    Provides COMPLETE data to avoid hallucinations.
    """
    if df is None or df.empty:
        return "No data available."

    context = f"""=== DATA SOURCE: {filename} ===

SCHEMA:
- Total Rows: {len(df)}
- Columns: {', '.join(df.columns.tolist())}

COLUMN DETAILS:
{df.dtypes.to_string()}

COMPLETE DATA (ALL {len(df)} ROWS):
{df.to_string()}

=== END OF DATA ===
"""
    return context


def get_deterministic_system_prompt() -> str:
    """
    System prompt designed for accurate, deterministic responses with zero hallucination.
    """
    return """You are a precise data analysis assistant. Your responses MUST be:

1. **STRICTLY DATA-DRIVEN**: Only use information that EXISTS in the provided data. Never make up numbers.

2. **EXACT MATCHING**: When asked about a specific month/period (e.g., "March 2025"), look for EXACT matches in the data.

3. **TRANSPARENT ABOUT LIMITATIONS**: If data doesn't exist or doesn't match the query, clearly state:
   - "The data does not contain information for [specific query]"
   - "Available periods in the data are: [list actual periods]"

4. **CALCULATION RULES**:
   - Show the exact values from the data
   - If aggregating, list which rows you're summing
   - Format numbers clearly (e.g., ₹1,23,456 or 1.23 lakhs)

5. **RESPONSE FORMAT** (for WhatsApp):
   - Keep responses concise but complete
   - Use bullet points for clarity
   - Include the source row/column when citing specific values

CRITICAL: If you cannot find the exact data requested, DO NOT guess or approximate. State clearly what data IS available."""


async def query_openrouter(user_message: str, data_context: str) -> tuple[str, str]:
    """
    Query LLM via OpenRouter API (primary provider).
    Returns tuple of (response_text, model_used) or (None, None) on failure.
    """
    if not OPENROUTER_API_KEY:
        return None, None

    system_prompt = get_deterministic_system_prompt()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"""Analyze the following data to answer the user's question.

{data_context}

USER QUESTION: {user_message}

Provide an accurate, data-driven response based ONLY on the data above. If the specific information requested is not in the data, clearly state what IS available."""}
    ]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://sjanalytics.railway.app",
        "X-Title": "SJ Analytics WhatsApp Bot"
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "max_tokens": 2000,
        "temperature": 0.1  # Low temperature for more deterministic responses
    }

    print(f"Calling OpenRouter API with model: {OPENROUTER_MODEL}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                OPENROUTER_BASE_URL,
                headers=headers,
                json=payload
            )

            print(f"OpenRouter response status: {response.status_code}")
            if response.status_code != 200:
                print(f"OpenRouter response body: {response.text}")
                return None, None

            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content'], OPENROUTER_MODEL
    except Exception as e:
        print(f"Error querying OpenRouter: {e}")
        return None, None


async def query_gemini_direct(user_message: str, data_context: str) -> tuple[str, str]:
    """
    Query Google Gemini directly (fallback provider).
    Returns tuple of (response_text, model_used) or (None, None) on failure.
    """
    if not GOOGLE_API_KEY:
        return None, None

    system_prompt = get_deterministic_system_prompt()

    full_prompt = f"""{system_prompt}

Analyze the following data to answer the user's question.

{data_context}

USER QUESTION: {user_message}

Provide an accurate, data-driven response based ONLY on the data above. If the specific information requested is not in the data, clearly state what IS available."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GOOGLE_MODEL}:generateContent?key={GOOGLE_API_KEY}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": full_prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,  # Low temperature for deterministic responses
            "maxOutputTokens": 2000,
        }
    }

    print(f"Calling Google Gemini API with model: {GOOGLE_MODEL}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)

            print(f"Google Gemini response status: {response.status_code}")
            if response.status_code != 200:
                print(f"Google Gemini response body: {response.text}")
                return None, None

            response.raise_for_status()
            result = response.json()

            if "candidates" in result and len(result["candidates"]) > 0:
                candidate = result["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    parts = candidate["content"]["parts"]
                    if len(parts) > 0 and "text" in parts[0]:
                        return parts[0]["text"], GOOGLE_MODEL

            print(f"Unexpected Gemini response structure: {result}")
            return None, None
    except Exception as e:
        print(f"Error querying Google Gemini directly: {e}")
        return None, None


async def query_llm(user_message: str, data_context: str) -> tuple[str, str, str]:
    """
    Query LLM with fallback: OpenRouter (GPT-4o-mini) first, then Google Gemini.
    Returns tuple of (response_text, provider_name, model_name).
    """

    # Try OpenRouter first (GPT-4o-mini is more accurate for data analysis)
    if OPENROUTER_API_KEY:
        print("Attempting OpenRouter API (primary)...")
        result, model = await query_openrouter(user_message, data_context)
        if result:
            return result, "OpenRouter", model
        print("OpenRouter failed, trying Google Gemini as fallback...")

    # Fallback to direct Google Gemini API
    if GOOGLE_API_KEY:
        print("Attempting Google Gemini API (fallback)...")
        result, model = await query_gemini_direct(user_message, data_context)
        if result:
            return result, "Google", model
        print("Google Gemini also failed.")

    # Both failed
    if not OPENROUTER_API_KEY and not GOOGLE_API_KEY:
        return "No LLM API configured. Please set either OPENROUTER_API_KEY or GOOGLE_API_KEY.", "None", "None"

    return "Sorry, I encountered an error while processing your request. Please try again later.", "Error", "None"


async def send_whatsapp_message(phone_number: str, message: str):
    """Send WhatsApp message via Gupshup API"""
    if not all([GUPSHUP_API_KEY, GUPSHUP_APP_NAME, GUPSHUP_SOURCE_NUMBER]):
        print("Gupshup configuration incomplete")
        return False

    url = "https://api.gupshup.io/wa/api/v1/msg"

    headers = {
        "apikey": GUPSHUP_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache"
    }

    clean_phone = phone_number.replace("+", "").replace(" ", "").replace("-", "")
    clean_source = GUPSHUP_SOURCE_NUMBER.replace("+", "").replace(" ", "").replace("-", "")

    data = {
        "channel": "whatsapp",
        "source": clean_source,
        "destination": clean_phone,
        "message": json.dumps({"type": "text", "text": message}),
        "src.name": GUPSHUP_APP_NAME
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, data=data)
            print(f"Gupshup response status: {response.status_code}")
            response.raise_for_status()
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
        "version": "2.0.0"
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "s3_configured": s3_client is not None,
        "openrouter_configured": OPENROUTER_API_KEY is not None,
        "google_api_configured": GOOGLE_API_KEY is not None,
        "primary_llm": "OpenRouter" if OPENROUTER_API_KEY else ("Google" if GOOGLE_API_KEY else "None"),
        "primary_model": OPENROUTER_MODEL if OPENROUTER_API_KEY else GOOGLE_MODEL,
        "primary_data_file": PRIMARY_DATA_FILE,
        "gupshup_configured": all([GUPSHUP_API_KEY, GUPSHUP_APP_NAME, GUPSHUP_SOURCE_NUMBER])
    }


@app.get("/debug/llm")
async def debug_llm():
    """Debug endpoint to verify LLM configuration"""
    return {
        "openrouter_configured": OPENROUTER_API_KEY is not None,
        "openrouter_model": OPENROUTER_MODEL,
        "google_configured": GOOGLE_API_KEY is not None,
        "google_model": GOOGLE_MODEL,
        "primary_provider": "OpenRouter (GPT-4o-mini)" if OPENROUTER_API_KEY else "Google Gemini",
        "fallback_provider": "Google Gemini" if (OPENROUTER_API_KEY and GOOGLE_API_KEY) else "None",
        "temperature": 0.1,
        "note": "Using low temperature (0.1) for deterministic responses. OpenRouter/GPT-4o-mini is primary for better accuracy."
    }


@app.get("/debug/data")
async def debug_data():
    """Debug endpoint to check data loading"""
    df, filename = get_master_csv_from_s3()
    if df is not None:
        return {
            "status": "success",
            "file": filename,
            "rows": len(df),
            "columns": df.columns.tolist(),
            "sample_data": df.head(3).to_dict(orient='records'),
            "cached": _cache_timestamp is not None
        }
    else:
        return {
            "status": "error",
            "message": f"Could not load {PRIMARY_DATA_FILE}",
            "s3_configured": s3_client is not None,
            "bucket": S3_BUCKET_NAME
        }


@app.post("/webhook/gupshup")
async def gupshup_webhook(request: Request):
    """Webhook endpoint for Gupshup WhatsApp messages"""
    start_time = datetime.utcnow()

    try:
        content_type = request.headers.get("content-type", "")

        if "application/json" in content_type:
            payload = await request.json()
        else:
            form_data = await request.form()
            payload = dict(form_data)
            if "payload" in payload and isinstance(payload["payload"], str):
                try:
                    payload["payload"] = json.loads(payload["payload"])
                except json.JSONDecodeError:
                    pass

        print(f"Received webhook payload: {json.dumps(payload, indent=2)}")

        event_type = payload.get("type", "")
        phone_number = ""
        user_message = ""
        user_name = "Unknown"

        if event_type == "message":
            message_payload = payload.get("payload", {})
            if isinstance(message_payload, str):
                try:
                    message_payload = json.loads(message_payload)
                except json.JSONDecodeError:
                    message_payload = {}

            sender = message_payload.get("sender", {})
            if isinstance(sender, dict):
                phone_number = sender.get("phone", "")
                user_name = sender.get("name", "Unknown")
            if not phone_number:
                phone_number = message_payload.get("source", "")

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
                user_message = inner_payload.get("text", inner_payload.get("caption", ""))
            else:
                user_message = str(inner_payload)

        elif event_type == "message-event":
            print("Received message event (delivery/read receipt), ignoring")
            return JSONResponse(content={"status": "ok", "message": "Event acknowledged"})
        else:
            phone_number = payload.get("mobile", payload.get("sender", payload.get("source", "")))
            user_message = payload.get("text", payload.get("message", ""))

        if not phone_number or not user_message:
            print(f"Could not extract phone number or message from payload")
            return JSONResponse(content={"status": "ok", "message": "No message to process"})

        print(f"Processing message from {phone_number} ({user_name}): {user_message}")

        # Load only the master CSV file
        df, filename = get_master_csv_from_s3()

        if df is None:
            error_msg = f"Unable to load data file {PRIMARY_DATA_FILE}. Please contact support."
            await send_whatsapp_message(phone_number, error_msg)

            # Log the failed interaction
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            log_interaction(
                user_phone=phone_number,
                user_name=user_name,
                user_query=user_message,
                llm_provider="None",
                llm_model="None",
                llm_response=error_msg,
                data_files_used=[],
                response_time_ms=response_time,
                success=False,
                error_message="Failed to load data from S3"
            )

            return JSONResponse(content={"status": "error", "message": "Data load failed"})

        # Prepare comprehensive data context
        data_context = prepare_data_context(df, filename)

        print(f"Data context prepared: {len(data_context)} characters")

        # Query LLM for analysis
        response_message, provider, model = await query_llm(user_message, data_context)

        print(f"LLM Response ({provider}/{model}): {response_message[:200]}...")

        # Send response back via WhatsApp
        send_success = await send_whatsapp_message(phone_number, response_message)

        # Calculate response time and log interaction
        response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        log_interaction(
            user_phone=phone_number,
            user_name=user_name,
            user_query=user_message,
            llm_provider=provider,
            llm_model=model,
            llm_response=response_message,
            data_files_used=[filename] if filename else [],
            response_time_ms=response_time,
            success=send_success and provider != "Error",
            error_message=None if send_success else "Failed to send WhatsApp message"
        )

        return JSONResponse(content={
            "status": "success",
            "message": "Response sent successfully",
            "provider": provider,
            "model": model,
            "response_time_ms": round(response_time, 2)
        })

    except Exception as e:
        print(f"Error processing webhook: {e}")
        import traceback
        traceback.print_exc()

        # Log error
        response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_interaction(
            user_phone=phone_number if phone_number else "unknown",
            user_name=user_name if 'user_name' in dir() else "unknown",
            user_query=user_message if 'user_message' in dir() else "unknown",
            llm_provider="Error",
            llm_model="None",
            llm_response="",
            data_files_used=[],
            response_time_ms=response_time,
            success=False,
            error_message=str(e)
        )

        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=200
        )


@app.post("/test/analyze")
async def test_analyze(request: Request):
    """Test endpoint for data analysis without WhatsApp"""
    try:
        body = await request.json()
        user_query = body.get("query", "")

        if not user_query:
            raise HTTPException(status_code=400, detail="Query is required")

        df, filename = get_master_csv_from_s3()

        if df is None:
            raise HTTPException(status_code=500, detail=f"Failed to load {PRIMARY_DATA_FILE}")

        data_context = prepare_data_context(df, filename)
        response, provider, model = await query_llm(user_query, data_context)

        return {
            "query": user_query,
            "response": response,
            "provider": provider,
            "model": model,
            "data_file": filename,
            "data_rows": len(df)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/improvements")
async def get_improvements():
    """
    Suggestions for production improvements.
    """
    return {
        "current_version": "2.0.0",
        "improvements": [
            {
                "category": "Data Accuracy",
                "suggestions": [
                    "Implement semantic search (embeddings) for better query understanding",
                    "Add query validation to ensure user intent matches available data",
                    "Pre-compute common aggregations (monthly totals, averages) for instant retrieval",
                    "Add data validation layer to verify LLM responses against actual data"
                ]
            },
            {
                "category": "Performance",
                "suggestions": [
                    "Use Redis for distributed caching instead of in-memory cache",
                    "Implement async data loading on app startup",
                    "Add response streaming for faster perceived response times",
                    "Consider using a vector database (Pinecone, Weaviate) for large datasets"
                ]
            },
            {
                "category": "Scalability",
                "suggestions": [
                    "Add message queue (RabbitMQ/SQS) for async processing",
                    "Implement rate limiting per user",
                    "Add horizontal scaling with load balancer",
                    "Use database (PostgreSQL) for conversation history"
                ]
            },
            {
                "category": "Monitoring & Observability",
                "suggestions": [
                    "Integrate with Datadog/New Relic for APM",
                    "Set up alerts for error rates and response times",
                    "Add distributed tracing for end-to-end visibility",
                    "Implement A/B testing for different prompts"
                ]
            },
            {
                "category": "Security",
                "suggestions": [
                    "Add API authentication for webhook endpoints",
                    "Implement input sanitization and validation",
                    "Add PII masking in logs",
                    "Enable request signing verification for Gupshup"
                ]
            },
            {
                "category": "User Experience",
                "suggestions": [
                    "Add conversation context (remember previous queries)",
                    "Implement intent classification (data query vs. help request)",
                    "Add suggested queries based on available data",
                    "Support data visualization (charts as images)"
                ]
            },
            {
                "category": "Reliability",
                "suggestions": [
                    "Add circuit breaker pattern for external API calls",
                    "Implement retry logic with exponential backoff",
                    "Add health checks for all dependencies",
                    "Set up automated failover to backup LLM providers"
                ]
            }
        ],
        "priority_actions": [
            "1. Validate LLM responses against actual data before sending",
            "2. Add conversation history for context",
            "3. Pre-compute common metrics for instant accurate responses",
            "4. Set up proper monitoring and alerting"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
