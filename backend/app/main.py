"""PrivARcy backend entrypoint.

A Video Privacy Protection System using a custom-trained YOLO26 detector
and TrOCR text extraction, with rule-based sensitivity classification and
confidence-gated human review. This app is the pure-backend successor to
the PyQt5 frontend: every former page (Home, Process, Live, Review,
Results, FaceRegister, Settings) is now a router under app/routers/,
talking to one shared BackendService.

Run with:
    uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .deps import get_service
from .routers import dataset, faces, home, live, process, results, review, settings

app = FastAPI(
    title="PrivARcy",
    description=(
        "Video Privacy Protection System using a custom-trained YOLO26 "
        "detector and TrOCR text extraction, with rule-based sensitivity "
        "classification and confidence-gated human review."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(home.router)
app.include_router(process.router)
app.include_router(live.router)
app.include_router(review.router)
app.include_router(results.router)
app.include_router(faces.router)
app.include_router(settings.router)
app.include_router(dataset.router)


@app.on_event("startup")
def startup() -> None:
    get_service().config.ensure_directories()


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
