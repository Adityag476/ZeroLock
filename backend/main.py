"""
ZeroLeak Backend — FastAPI Application
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.db import init_db
from backend.routes import create, unlock, print_paper, investigate, audit_log

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="ZeroLeak API",
    description="Forensic Exam Custody System — Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(create.router,      prefix="/api/exams",       tags=["Exams"])
app.include_router(unlock.router,      prefix="/api/unlock",      tags=["Unlock"])
app.include_router(print_paper.router, prefix="/api/print",       tags=["Print"])
app.include_router(investigate.router, prefix="/api/investigate",  tags=["Forensics"])
app.include_router(audit_log.router,   prefix="/api/audit",       tags=["Audit"])

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "ZeroLeak API v1.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
