from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import sys
import logging
from pathlib import Path

# Add the app directory to Python path (needed for Vercel serverless)
app_dir = Path(__file__).parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

# Load .env from the app directory (works regardless of where project is cloned)
env_path = app_dir / ".env"
load_dotenv(dotenv_path=env_path)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Detect if running on Vercel (serverless) or locally
IS_SERVERLESS = os.getenv("VERCEL", False) or os.getenv("AWS_LAMBDA_FUNCTION_NAME", False)

# Log OpenRouter key status
logger.info(
    "OpenRouter API key: "
    + ("Loaded" if os.getenv("OPENROUTER_API_KEY") else "Missing")
)
logger.info(f"Running in {'serverless' if IS_SERVERLESS else 'server'} mode")

from api.generate import router as generate_router
from api.generate_stream import router as generate_stream_router
from api.verify import router as verify_router
from api.navigation import router as navigation_router
from api.chunks import router as chunks_router
from api.qa import router as qa_router
from api.chat import router as chat_router

# Only import scheduler in non-serverless mode
if not IS_SERVERLESS:
    from services.qa_scheduler import qa_scheduler

app = FastAPI(
    title="Swoop Intelligence API",
    description="Chunk-based automotive service intelligence platform with anti-hallucination verification",
    version="1.0.0",
)


@app.on_event("startup")
async def startup_event():
    if not IS_SERVERLESS:
        qa_scheduler.start()
        logger.info("QA Scheduler started")
    else:
        logger.info("Serverless mode - QA Scheduler disabled (use cron jobs instead)")


@app.on_event("shutdown")
async def shutdown_event():
    if not IS_SERVERLESS:
        qa_scheduler.stop()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate_router, prefix="/api", tags=["Generation"])
app.include_router(generate_stream_router, prefix="/api", tags=["Generation"])
app.include_router(verify_router, prefix="/api/verify", tags=["Verification"])
app.include_router(navigation_router, prefix="/api", tags=["Navigation"])
app.include_router(chunks_router, prefix="/api", tags=["Chunks"])
app.include_router(qa_router, prefix="/api", tags=["QA"])
app.include_router(chat_router, prefix="/api", tags=["Chat"])


@app.get("/")
async def root():
    return {
        "service": "Swoop Intelligence API",
        "status": "online",
        "message": "The brain is awake. Ready to generate SOURCE-VERIFIED chunks.",
        "version": "1.0.0 - Anti-Hallucination Edition",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


# Vercel serverless handler
handler = app
