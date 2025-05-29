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