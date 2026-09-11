# PrivARcy Backend

A Video Privacy Protection System using a custom-trained **YOLO26**
detector and **TrOCR** text extraction, with **rule-based sensitivity
classification** and **confidence-gated human review**. Pure backend —
no GUI. Everything is a REST endpoint served by FastAPI.

## Using the existing `venv`'s installed packages (no reinstall needed)

The original `D:\PrivARcy\backend\venv` isn't included in this delivery
(too large to transfer), but it doesn't need to be — its `site-packages`
already has everything this backend needs (`fastapi`, `torch`,
`transformers`, `ultralytics`, `opencv-python`, `face-recognition`, `dlib`,
per `requirements.txt`). Two ways to reuse it instead of reinstalling:

**Option A — point a new venv at the old one's packages**
```powershell
# From D:\PrivARcy\backend, with a fresh venv activated:
python -m venv venv
venv\Scripts\activate
# Add the OLD venv's site-packages to this one's search path:
echo D:\PrivARcy\backend\venv\Lib\site-packages > venv\Lib\site-packages\old_venv.pth
```
Any `.pth` file dropped into `Lib\site-packages` adds its listed
directory to `sys.path` for every interpreter using that venv, so nothing
needs to be copied or reinstalled.

**Option B — just reuse the old venv's interpreter directly**
```powershell
D:\PrivARcy\backend\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```
If the old venv's `site-packages` already has FastAPI/uvicorn (it does —
see `requirements.txt`), this runs the new backend with zero setup.

**Option C — fresh install (only if the old venv is truly gone)**
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements-runtime.txt
```
`requirements-runtime.txt` is the minimal set for this codebase;
`requirements.txt` is the full historical freeze (kept as reference for
exact pinned versions, including the platform-specific `dlib` wheel URL
`face_recognition` needs on Windows).

Either way, run the doctor script to verify:
```powershell
python setup_backend.py --check-only
```

## Running the full app (GUI + backend, in-process)

The PyQt5 frontend runs in the same process as the pipeline (`backend/src`)
— no separate server needed. `frontend/main.py` builds one shared
`BackendService` and passes it to every page, so Settings changes,
registered faces, and the review queue all stay in sync across pages.

```bash
cd backend
pip install -r requirements-runtime.txt   # or reuse an existing venv, see below
cd ../frontend
python main.py
```

## Running the headless API instead (or alongside)

The same `backend/src` pipeline is also exposed as a REST API
(`backend/app/`), independent of the GUI — useful for automation, remote
clients, or a future web frontend. It does not need PyQt5.

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```
Interactive docs: `http://localhost:8000/docs`

Both the GUI and the API read/write the same `data/settings.json`,
`data/face_registry/`, etc., but each keeps its own in-memory job/review
state (a `BackendService` instance) — running them at the same time won't
crash, but a job started in one won't show up as a job in the other. Live
camera access is exclusive to whichever one currently has the camera open.

## Custom-trained YOLO26 weights — **read this if Review/Results are empty**

`YOLO26` isn't a real Ultralytics-shipped architecture name — it's this
project's own custom-trained model. Until you provide real trained
weights, `YoloDetector` will **always** fail to load `yolo26n.pt`
(ultralytics doesn't recognize that name), which means **every video
processes with zero detections** — Process.py will still say "Finished",
but Review and Results will legitimately have nothing to show. This is
not a wiring bug; it's what "no model loaded" looks like, by design
(a missing model should never crash a job).

**Check this first, before assuming something's broken:** open
Settings → System Diagnostics → Run Diagnostics. It tries loading the
YOLO detector, TrOCR, and face_recognition right now and tells you
exactly which ones work and why not (also logged to
`backend/logs/privarcy.log`). Process.py's completion banner does the
same check automatically whenever a video finishes with 0 detections.

Once you have real weights: drop the file into `models/` and point
`AppConfig` at it, either via `PUT /settings`
(`{"model_path": "models/yolo26_privarcy.pt"}`), the Settings page, or by
editing `data/settings.json` directly.

## Training data growth (Frame Extraction -> Dataset Pipeline -> data.yaml -> Active Learning)

The pieces that turn raw video + human review into a growing training set
for your own YOLO26 weights:

- **Frame Extraction** (`src/dataset/frame_extraction.py`) — pulls still
  frames out of a video (`every_n_frames` apart, to avoid near-duplicate
  images) for manual labeling. `POST /dataset/extract-frames`.
- **Dataset Pipeline** (`src/dataset/pipeline.py`) — owns the on-disk YOLO
  layout (`data/dataset/images/{train,val}`, `labels/{train,val}`),
  assigns new samples to train/val, and converts a pixel bbox into a
  normalized YOLO label line.
- **data.yaml** (`src/dataset/data_yaml.py`) — generates the Ultralytics
  training config pointing at that layout. `POST /dataset/regenerate-data-yaml`.
- **Active Learning** (`src/dataset/active_learning.py`) — closes the
  loop: a detection only reaches the confidence-gated Review queue when
  the model was *uncertain* about it. When a human **confirms** one
  (GUI or `POST /review/{id}/decision`), that becomes a verified label for
  exactly the kind of input the current model struggles with, and gets
  added straight into the dataset — no manual export step. Rejected items
  aren't added (no correct bbox to train on).

Once the dataset has enough confirmed samples, retrain with the regular
Ultralytics CLI: `yolo train data=data/dataset/data.yaml model=yolo11n.pt
epochs=100`, then point `model_path` at the resulting weights.

## Endpoint map (was: which GUI page)

| Endpoint(s)                                            | Was              |
|----------------------------------------------------------|------------------|
| `GET /home/overview`                                      | `Home.py`        |
| `POST /process/upload`, `/process/start`, `/process/status/{id}`, `/process/cancel/{id}` | `Process.py`     |
| `GET /live/cameras`, `/live/start`, `/live/stop`, `/live/frame`, `/live/stats`, `/live/audit-log` | `Live.py`        |
| `GET /review/queue`, `/review/categories`, `POST /review/{id}/decision` | `Review.py`      |
| `GET /results/{job_id}`, `/results/{job_id}/export`, `POST /results/reset` | `Results.py`     |
| `GET /faces`, `POST /faces/register`, `DELETE /faces/{code}` | `FaceRegister.py` |
| `GET/PUT /settings`, `GET /settings/diagnostics`           | `Settings.py`    |
| `GET /dataset/status`, `/dataset/extract-frames`, `/dataset/regenerate-data-yaml` | (new — training data growth) |

## Tests

```bash
pytest tests/
```

## Performance / GPU acceleration

Live-stream lag is usually a CPU-inference problem. Three levers, in order
of impact:

1. **Settings -> Performance Profile -> Inference Device**. If you have an
   NVIDIA GPU, plain `pip install torch` (as in `requirements-runtime.txt`)
   installs the **CPU-only** build regardless -- you need the CUDA build
   explicitly:
   ```bash
   pip uninstall torch
   pip install torch --index-url https://download.pytorch.org/whl/cu121
   ```
   (match `cu121`/etc. to your installed CUDA version -- see
   https://pytorch.org/get-started/locally/). `ultralytics` (YOLO) then
   picks up CUDA automatically once torch reports it as available; no
   separate GPU package is needed for detection. Settings -> System
   Diagnostics shows which device is actually in use after this.
2. **Detection Resolution** (Settings -> Performance Profile) -- downscales
   frames before YOLO inference; inference cost scales with resolution, so
   50% resolution is roughly 4x cheaper than 100%.
3. **Detection Interval** -- runs full detection every Nth captured frame
   instead of every frame.

None of these require code changes -- they're all in Settings. If you're
still on CPU, expect noticeably better throughput just from #2 and #3
alone; TrOCR (OCR) is the single most expensive step per detection, and
`ocr_cache_passes` (in `AppConfig`, not yet exposed in the GUI) already
avoids re-running it every pass for the same tracked object.

## Temporal smoothing (prevents redaction-box flicker)

`src/smoothing/temporal.py` — a raw per-frame detection box wobbles a few
pixels frame-to-frame even for a stationary object, visible as flicker
once redacted. `TemporalSmoother` keeps a rolling window
(`AppConfig.temporal_smoothing`, default 5 frames) per tracked object
(keyed by `IoUTracker`'s track_id) and redacts using the moving average
instead of the raw box. Detection, OCR, and the confidence-gated decision
all still use the current, unsmoothed box — only the drawn redaction
region is smoothed. Wired into both `ProcessingPipeline` (file processing)
and `LiveSession` (live camera).

## Correction feedback mechanism (Correction Log)

`src/correction/log.py` — every reviewer decision (Confirm/Reject) on a
flagged detection is logged to a local SQLite database
(`data/correction_log.db`). This is deliberately separate from
**Active Learning** (`src/dataset/active_learning.py`): active learning
grows the *YOLO26 training set* for eventual retraining; the Correction
Log instead improves the *rule-based sensitivity classifier* — the
regex patterns in `PrivacyTextClassifier` — **without retraining any
model at all**.

`POST /review/refine-classifier` (or Settings -> Correction Feedback ->
"Refine Classifier from Corrections") recomputes a confidence weight per
pattern from the accumulated log: a pattern reviewers keep rejecting
(frequent false positives) gets down-weighted — below a threshold it's
treated as benign outright — while a consistently-confirmed pattern gets
a mild boost. Weights persist to `data/classifier_weights.json` and are
loaded by every subsequent `ProcessingPipeline`/`LiveSession`, so
accuracy improves across sessions. Run this occasionally as the log
builds up, not after every single decision — it needs a meaningful
sample (5+ decisions per pattern by default) to adjust anything.
