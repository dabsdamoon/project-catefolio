import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.team_routes import router as team_router

# Load environment variables from .env file in project root
# backend/app/main.py -> backend -> project root
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_path)

app = FastAPI(title="Catefolio API", version="0.1.0")

# Environment-based CORS configuration
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

LOCALHOST_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:5176",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://127.0.0.1:5176",
]

CORS_ORIGINS = {
    "development": LOCALHOST_ORIGINS,
    "production": [
        "https://catefolio-web.vercel.app",
        "https://catefolio-web-staging.vercel.app",
        *LOCALHOST_ORIGINS,  # Allow local dev against Cloud Run
    ],
}

origins = CORS_ORIGINS.get(ENVIRONMENT, CORS_ORIGINS["development"])

# Allow Vercel preview deployments in production
allow_origin_regex = (
    r"https://catefolio-web-.*\.vercel\.app" if ENVIRONMENT == "production" else None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(api_router)
app.include_router(team_router)
