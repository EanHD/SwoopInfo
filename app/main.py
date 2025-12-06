from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the app directory to Python path (needed for Vercel serverless)
app_dir = Path(__file__).parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Detect if running on Vercel (serverless)
IS_SERVERLESS = os.getenv("VERCEL", False) or os.getenv("AWS_LAMBDA_FUNCTION_NAME", False)
logger.info(f"Running in {'serverless' if IS_SERVERLESS else 'server'} mode")

app = FastAPI(
    title="Swoop Intelligence API",
    description="Chunk-based automotive service intelligence platform with anti-hallucination verification",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import routers with error handling for serverless
routers_loaded = []

try:
    from api.generate import router as generate_router
    app.include_router(generate_router, prefix="/api", tags=["Generation"])
    routers_loaded.append("generate")
except Exception as e:
    logger.warning(f"Failed to load generate router: {e}")

try:
    from api.generate_stream import router as generate_stream_router
    app.include_router(generate_stream_router, prefix="/api", tags=["Generation"])
    routers_loaded.append("generate_stream")
except Exception as e:
    logger.warning(f"Failed to load generate_stream router: {e}")

try:
    from api.verify import router as verify_router
    app.include_router(verify_router, prefix="/api/verify", tags=["Verification"])
    routers_loaded.append("verify")
except Exception as e:
    logger.warning(f"Failed to load verify router: {e}")

try:
    from api.navigation import router as navigation_router
    app.include_router(navigation_router, prefix="/api", tags=["Navigation"])
    routers_loaded.append("navigation")
except Exception as e:
    logger.warning(f"Failed to load navigation router: {e}")

try:
    from api.chunks import router as chunks_router
    app.include_router(chunks_router, prefix="/api", tags=["Chunks"])
    routers_loaded.append("chunks")
except Exception as e:
    logger.warning(f"Failed to load chunks router: {e}")

try:
    from api.qa import router as qa_router
    app.include_router(qa_router, prefix="/api", tags=["QA"])
    routers_loaded.append("qa")
except Exception as e:
    logger.warning(f"Failed to load qa router: {e}")

try:
    from api.chat import router as chat_router
    app.include_router(chat_router, prefix="/api", tags=["Chat"])
    routers_loaded.append("chat")
except Exception as e:
    logger.warning(f"Failed to load chat router: {e}")

try:
    from api.parts_pricing import router as parts_pricing_router
    app.include_router(parts_pricing_router, tags=["Parts Pricing"])
    routers_loaded.append("parts_pricing")
except Exception as e:
    logger.warning(f"Failed to load parts_pricing router: {e}")

try:
    from api.labor_times import router as labor_times_router
    app.include_router(labor_times_router, tags=["Labor Times"])
    routers_loaded.append("labor_times")
except Exception as e:
    logger.warning(f"Failed to load labor_times router: {e}")

try:
    from api.vehicles import router as vehicles_router
    app.include_router(vehicles_router, prefix="/api/vehicles", tags=["Vehicles"])
    routers_loaded.append("vehicles")
except Exception as e:
    logger.warning(f"Failed to load vehicles router: {e}")

logger.info(f"Routers loaded: {routers_loaded}")


@app.get("/")
async def root():
    return {
        "service": "Swoop Intelligence API",
        "status": "online",
        "message": "The brain is awake. Ready to generate SOURCE-VERIFIED chunks.",
        "version": "1.0.0 - Anti-Hallucination Edition",
        "routers_loaded": routers_loaded,
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "routers": len(routers_loaded)}
