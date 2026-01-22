from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file if it exists
# This ensures environment variables are loaded before any modules that need them
project_root = Path(__file__).parent.parent
env_path = project_root / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create FastAPI app
app = FastAPI(title="Trackly API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from app.api.search import router as search_router
app.include_router(search_router, prefix="/api")

@app.get("/")
async def root():
    return {
        "name": "Trackly API",
        "version": "1.0.0",
        "status": "running",
        "description": "API for tracking and search functionality",
        "documentation": "/docs",
    }