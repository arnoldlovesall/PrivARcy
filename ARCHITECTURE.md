# PrivARcy Architecture Guide

## Project Overview

**PrivARcy: A Video Privacy Protection System Using Custom-Trained YOLO26
and TrOCR with Rule-Based Sensitivity Classification and Confidence-Gated
Human Review.**

PrivARcy is a desktop application: a PyQt5 GUI (`frontend/`) driving a
framework-agnostic pipeline (`backend/src/`). Every GUI page is also
independently exposed as a REST API (`backend/app/`) for headless/remote
use — the two share the same `backend/src` code, just through different
transports (a Qt slot call vs. an HTTP request).

## Folder layout

`venv/` is **not** inside `backend/` — it lives at the project root,
alongside `backend/` and `frontend/`, and is never packaged or shipped;
it only exists on your machine.

```
PrivARcy/                     <- project root
|-- ARCHITECTURE.md           <- this file
|-- venv/                     <- your virtual environment (own folder, not inside backend/)
|-- docs/
|   `-- legacy-frontend/      <- historical notes from the pre-rewrite PyQt frontend
|-- backend/                  <- everything Python: core pipeline + optional REST API
|   |-- README.md             <- setup + how to run
|   |-- requirements.txt      <- full pinned freeze
|   |-- requirements-runtime.txt  <- minimal set actually needed here
|   |-- setup_backend.py      <- folder creation + dependency doctor
|   |-- setup_backend.bat
|   |
|   |-- app/                  <- FastAPI service (optional — GUI does not need this running)
|   |   |-- main.py           <- app factory, router registration, /health
|   |   |-- deps.py           <- shared BackendService singleton
|   |   |-- schemas.py        <- pydantic request/response models
|   |   `-- routers/
|   |       |-- home.py       <- GET /home/overview, /home/history
|   |       |-- process.py    <- upload/start/status/cancel a video job
|   |       |-- live.py       <- camera discovery, start/stop, live frame/stats
|   |       |-- review.py     <- confidence-gated queue, 5 category boxes, decisions, refine-classifier
|   |       |-- results.py    <- summary, MP4 export, reset
|   |       |-- faces.py      <- register/list/remove/verify participant faces
|   |       |-- settings.py   <- GET/PUT pipeline configuration, diagnostics
|   |       `-- dataset.py    <- frame extraction, dataset status, data.yaml regeneration
|   |
|   |-- src/                  <- core algorithms, framework-agnostic (no PyQt, no FastAPI)
|   |   |-- config/           <- AppConfig (thresholds, redaction, performance, device) + persistence
|   |   |-- detectors/        <- YoloDetector (custom-trained YOLO26 via ultralytics)
|   |   |-- ocr/              <- OCRService (TrOCR: microsoft/trocr-base-printed)
|   |   |-- classifiers/      <- PrivacyTextClassifier (rule-based PII sensitivity, correction-weighted)
|   |   |-- decision/         <- PrivacyDecisionEngine (confidence-gated review)
|   |   |-- tracker/          <- IoUTracker (temporal track IDs across frames)
|   |   |-- smoothing/        <- TemporalSmoother (prevents redaction-box flicker)
|   |   |-- redaction/        <- RedactionEngine (blur/pixelate/solid mask)
|   |   |-- face/             <- FaceRegistry (consent matching + blink-liveness for enrollment)
|   |   |-- video/            <- VideoReader / VideoWriter (OpenCV I/O)
|   |   |-- pipeline/         <- ProcessingPipeline — wires all of the above for file processing
|   |   |-- live/             <- LiveSession — same pipeline, two-thread capture/detect split, live camera
|   |   |-- workers/          <- ProcessingWorker — plain background-thread job runner (FastAPI path)
|   |   |-- review/           <- ReviewStore — the confidence-gated human review queue, 5 category boxes
|   |   |-- results/          <- ResultsStore (per-job detail) + ProcessingHistoryStore (Home activity feed)
|   |   |-- dataset/          <- FrameExtractor, DatasetPipeline, data.yaml, ActiveLearningStore
|   |   |-- correction/       <- CorrectionLogStore — reviewer-decision log, refines classifier weights
|   |   |-- integration/      <- BackendService — single orchestration point every page/router calls into
|   |   `-- utils/            <- logging (console + backend/logs/privarcy.log)
|   |
|   |-- data/                 <- runtime state (gitignored contents)
|   |   |-- uploads/, output/, face_registry/, review_frames/, dataset/
|   |   |-- settings.json, correction_log.db, classifier_weights.json
|   |-- models/               <- place custom-trained YOLO26 weights here (e.g. yolo26n.pt)
|   |-- logs/                 <- privarcy.log
|   |-- temp/
|   `-- tests/
|       `-- test_core.py
|
`-- frontend/                 <- PyQt5 GUI — this is what you actually run day to day
    |-- main.py                <- entry point: `python main.py`. Builds one shared BackendService.
    |-- qt_worker.py            <- the only file that wraps backend/src's pipeline in a QThread
    |-- Home.py                 <- dashboard: stats + Recent Activity (ProcessingHistoryStore)
    |-- Process.py               <- upload/start/cancel a video job, progress
    |-- Live.py                  <- camera picker, resolution, live preview, audit log
    |-- Review.py                <- confidence-gated queue, Confirm/Reject
    |-- Results.py               <- summary, category breakdown, export video/report
    |-- FaceRegister.py           <- register from photo, or live "Scan Face" with blink liveness
    |-- Settings.py               <- thresholds, performance, diagnostics, correction feedback
    |-- components.py, styles.py  <- shared widgets / theming
    `-- assets/
```

## Pipeline

```
video frame
   |
   v
YOLO26 detector (custom-trained) --> IoU tracker --> per-detection bbox + label + confidence
   |
   v (for text-bearing categories: ID, Document, Credential, License Plate)
TrOCR text extraction (robust to blur, low resolution, rotated text)
   |
   v
Rule-based sensitivity classifier (regex PII patterns -> sensitive | benign)
   |    weighted by CorrectionLogStore's accumulated reviewer feedback
   v
Confidence-gated decision engine
   |-- known/consented face             -> allow (never redacted)
   |-- sensitive OCR text OR conf >= Thigh -> auto-redact
   |-- Tlow <= conf < Thigh              -> human Review queue
   `-- conf < Tlow                       -> discard as noise
   |
   v
Temporal smoothing (moving average per tracked object, prevents flicker)
   |
   v
Redaction engine (blur | pixelate | solid mask) -> output video
```

Confirmed review items additionally feed **ActiveLearningStore**
(`src/dataset/`), which is a separate downstream path from the pipeline
above — see "Two feedback loops" below.

## The five Review "boxes"

Every detection is normalized into exactly one of five categories before it
can reach the confidence-gated review queue (`GET /review/categories`):

| Category        | Source YOLO26 classes                          |
|------------------|------------------------------------------------|
| `FACE`           | face                                            |
| `ID`             | id card, government ID, date-of-birth text      |
| `DOCUMENT`       | document, screen, confidential marking           |
| `CREDENTIAL`     | credit card, debit card, payment card            |
| `LICENSE_PLATE`  | license plate                                    |

OCR-derived PII signals (e.g. a matched card-number pattern) can promote a
detection into a different category than its raw YOLO26 label -- e.g. a
"document" box whose extracted text matches a payment-card pattern is
reclassified as `CREDENTIAL` -- because the *content*, not just the visual
class, determines what kind of sensitive information it is.

## Two feedback loops (don't confuse them)

A confirmed Review decision feeds **both**, for different purposes:

| | Active Learning (`src/dataset/`) | Correction Log (`src/correction/`) |
|---|---|---|
| Improves | YOLO26 (via eventual retraining) | The rule-based classifier's pattern weights |
| Trigger | Confirmed items only | Every decision, confirmed or rejected |
| Storage | `data/dataset/` (YOLO images+labels+data.yaml) | `data/correction_log.db` (SQLite) |
| Applied | Manually, by retraining with the Ultralytics CLI | Automatically, next time a pipeline/session is built, once `refine_classifier()` is run |
| Retrains a model? | Yes (you do this yourself) | No — only adjusts classifier weights |

## Why FastAPI *and* PyQt5

Every GUI page is a thin wrapper around a `BackendService` method
(`start_processing`, `register_face`, `discover_cameras`, `decide_review_item`,
...). The FastAPI routers under `backend/app/routers/` call the exact
same methods on the exact same class — nothing about detection, OCR,
classification, or the decision logic differs between the two; only the
transport does (a Qt slot call vs. an HTTP request). `backend/src` itself
imports neither PyQt5 nor FastAPI, so it works under both without
modification.

## Frontend notes

- One `BackendService` instance, created once in `main.py`, passed into
  every page — not one per page. Settings changes, the review queue, and
  the face registry are consistent everywhere as a result.
- `qt_worker.py` is the *only* place PyQt touches `ProcessingPipeline`
  (wraps it in a `QThread` so Process.py's progress bar gets real
  signals); `backend/src` stays framework-free otherwise.
- `Live.py` doesn't run detection itself — it polls `LiveSession`
  (`backend/src/live/`), which runs capture and detection on two separate
  threads so a slow detection pass never stalls the preview.
- `FaceRegister.py`'s "Scan Face (Live)" requires an observed blink
  (eye-aspect-ratio based) before it'll capture, so a printed photo held
  to the camera can't be used to enroll a face that was never present.
