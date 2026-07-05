from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bhavai.settings_router import router as settings_router
from bhavai.skills_router import router as skills_router
app = FastAPI(title="BhavAI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings_router)
app.include_router(skills_router)