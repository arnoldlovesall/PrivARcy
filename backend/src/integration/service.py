from __future__ import annotations

from ..config import AppConfig
from ..classifiers import PrivacyTextClassifier
from ..correction import CorrectionLogStore
from ..dataset import ActiveLearningStore, DatasetPipeline, FrameExtractor
from ..face import FaceRegistry
from ..live import LiveSession, discover_cameras
from ..results import ResultsStore, ProcessingHistoryStore
from ..review import ReviewStore
from ..workers.processing_worker import ProcessingWorker


class BackendService:
    """Single orchestration point for the whole PrivARcy backend.

    Owns the shared AppConfig, the review/results stores, the face
    registry, background processing jobs, and the live-camera session.
    Every FastAPI router in `app/routers/` talks to the app only through
    this object -- it is the direct successor to the PyQt pages' scattered
    `self._backend` calls (Process.start_processing, FaceRegister.register_face,
    Live's camera handling, Review's queue, Results' summary), now
    consolidated into one place instead of spread across GUI widgets.
    """

    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.load()
        self.config.ensure_directories()

        self.review_store = ReviewStore()
        self.results_store = ResultsStore()
        self.history_store = ProcessingHistoryStore()
        self.registry = FaceRegistry(self.config.registry_dir)
        self.live_session: LiveSession | None = None

        # Training-data growth: FrameExtractor pulls stills from raw video,
        # DatasetPipeline organizes them (+ labels) into YOLO layout,
        # ActiveLearningStore closes the loop by turning human-confirmed
        # review items back into new labeled training examples.
        self.frame_extractor = FrameExtractor(self.config.dataset_dir / "extracted_frames")
        self.dataset_pipeline = DatasetPipeline(self.config.dataset_dir)
        self.active_learning = ActiveLearningStore(self.dataset_pipeline)

        # Correction feedback mechanism: every reviewer decision on a
        # flagged detection is logged here; refine_classifier() (call
        # periodically, e.g. from Settings) turns the accumulated log into
        # updated PrivacyTextClassifier pattern weights, persisted to
        # classifier_weights_path so future ProcessingPipeline/LiveSession
        # instances pick them up automatically. Improves detection
        # accuracy across sessions without retraining YOLO26/TrOCR.
        self.correction_log = CorrectionLogStore(self.config.correction_log_path)

        self._jobs: dict[str, ProcessingWorker] = {}
        self.session_source_path: str | None = None
        self.session_output_path: str | None = None
        self.session_detections: list[dict] = []

    # -- Settings (was: Settings.py) -----------------------------------
    def get_settings(self) -> dict:
        return self.config.to_dict()

    def update_settings(self, **kwargs) -> dict:
        self.config.update(**kwargs)
        self.config.save()
        return self.config.to_dict()

    # -- Processing jobs (was: Process.py) ------------------------------
    def start_processing(self, video_path: str, source_name: str | None = None) -> ProcessingWorker:
        worker = ProcessingWorker(
            video_path, self.config, source_name, self.review_store,
            on_completed=lambda result: self._on_job_completed(worker.job_id, result),
        )
        self._jobs[worker.job_id] = worker
        worker.start()
        return worker

    def _on_job_completed(self, job_id: str, result) -> None:
        categories = {}
        for event in result.detections:
            categories[event["category"]] = categories.get(event["category"], 0) + 1
        self.results_store.set(
            job_id, output_path=result.output_path, frames_processed=result.frames,
            total_redactions=result.redactions, categories=categories,
            summary={
                "total_detections": len(result.detections),
                "auto_redacted": result.redactions,
                "avg_fps": None,
            },
        )
        self.remember_session(result.source_path, result.output_path, result.detections)
        self.history_store.record(
            source_name=job_id, frames=result.frames,
            total_detections=len(result.detections), redactions=result.redactions,
            output_path=result.output_path,
        )

    def get_job(self, job_id: str) -> ProcessingWorker | None:
        return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.cancel()
        return True

    def list_jobs(self) -> list[dict]:
        return [job.status() for job in self._jobs.values()]

    def record_history(self, source_name: str, frames: int, total_detections: int,
                        redactions: int, output_path: str | None = None) -> dict:
        """Record a completed job in the Home page's Recent Activity feed.

        Called from the GUI path (Process.py's QtProcessingWorker, which
        bypasses start_processing()/_on_job_completed above entirely) as
        well as being implicitly covered by the FastAPI job path.
        """
        return self.history_store.record(source_name, frames, total_detections, redactions, output_path).to_dict()

    def get_history(self, limit: int | None = None) -> list[dict]:
        return [entry.to_dict() for entry in self.history_store.recent(limit)]

    # -- Review queue (was: Review.py) ----------------------------------
    def review_queue(self):
        return self.review_store

    def decide_review_item(self, item_id: int, decision: str):
        """Record a human decision on a review item. Feeds two separate
        downstream mechanisms:
        - if confirmed: ActiveLearningStore adds it as a new training
          sample (for eventually retraining YOLO26 — see dataset_status())
        - always (confirmed or rejected): CorrectionLogStore logs it, for
          refine_classifier() to later adjust rule pattern weights (no
          retraining involved at all)
        Used by both the FastAPI /review/{id}/decision endpoint and the
        GUI's Review page.
        """
        item = self.review_store.decide(item_id, decision)
        if item is not None:
            if item.status == "confirmed":
                self.active_learning.record_confirmed(item)
            self.correction_log.log_decision(item.id, item.category, item.classification, item.status)
            for event in self.session_detections:
                if event.get("id") == item.id:
                    event["status"] = item.status
        return item

    def refine_classifier(self, min_samples: int = 5) -> dict:
        """Recompute PrivacyTextClassifier pattern weights from the
        correction log and persist them — call this periodically (e.g. a
        button on Settings), not after every single decision, so it's
        acting on a meaningful sample of reviewer feedback rather than
        overreacting to one or two decisions.
        """
        weights = self.correction_log.refine_pattern_weights(min_samples)
        classifier = PrivacyTextClassifier(self.config.classifier_weights_path)
        classifier.pattern_weights.update(weights)
        classifier.save_weights()
        return {"updated_patterns": weights, "total_corrections_logged": self.correction_log.total_logged()}

    # -- Dataset / active learning (custom YOLO26 training data) --------
    def extract_frames(self, video_path: str, every_n_frames: int = 30) -> list[str]:
        return self.frame_extractor.extract(video_path, every_n_frames)

    def dataset_status(self) -> dict:
        counts = self.dataset_pipeline.counts()
        return {
            "dataset_dir": str(self.config.dataset_dir),
            "class_names": self.dataset_pipeline.class_names,
            "train_images": counts["train"],
            "val_images": counts["val"],
        }

    def regenerate_data_yaml(self) -> str:
        return str(self.dataset_pipeline.regenerate_data_yaml())

    # -- Results (was: Results.py) --------------------------------------
    def results(self):
        return self.results_store

    def remember_session(self, source_path: str | None, output_path: str | None,
                         detections: list[dict] | None = None) -> None:
        self.session_source_path = source_path
        self.session_output_path = output_path
        self.session_detections = list(detections or [])

    def finalize_session_output(self) -> str | None:
        """Rebuild the shareable MP4 after review so Confirm is burned in."""
        from ..pipeline import reconstruct_redacted_video

        if not self.session_source_path or not self.session_output_path:
            return self.session_output_path
        confirmed = any(
            ev.get("action") == "review" and ev.get("status") == "confirmed"
            for ev in self.session_detections
        )
        if not confirmed:
            return self.session_output_path
        reconstruct_redacted_video(
            self.session_source_path, self.session_output_path,
            self.session_detections, self.config,
        )
        return self.session_output_path

    def reset_session(self) -> None:
        self.review_store.clear()
        self.results_store.reset()
        self.session_source_path = None
        self.session_output_path = None
        self.session_detections = []

    # -- Faces (was: FaceRegister.py) ------------------------------------
    def register_face(self, code: str, name: str, image_path: str) -> dict:
        return self.registry.register_photo(code, name, image_path)

    def remove_face(self, code: str) -> None:
        self.registry.remove(code)

    def verify_face(self, code: str) -> dict:
        return self.registry.verify(code)

    def list_faces(self) -> list[dict]:
        return self.registry.list()

    # -- Live camera (was: Live.py) ---------------------------------------
    def discover_cameras(self) -> list[dict]:
        return discover_cameras()

    def start_live(self, camera_index: int, width: int | None = None,
                   height: int | None = None, fps: int | None = None) -> bool:
        if self.live_session and self.live_session.is_live:
            self.live_session.stop()
        self.live_session = LiveSession(self.config, self.review_store)
        return self.live_session.start(camera_index, width, height, fps)

    def stop_live(self) -> dict:
        info: dict = {}
        if self.live_session:
            info = self.live_session.stop() or {}
            if info.get("output_path"):
                self.session_output_path = info["output_path"]
        return info

    def restart_live_if_active(self) -> bool:
        """Re-create the live session with the same camera/resolution so
        it picks up the latest AppConfig values.

        LiveSession's detector/decision-engine/redactor read config values
        once at construction, not on every frame — so a Settings change
        (thresholds, redaction method, enabled classes, ...) would
        otherwise never reach an already-running live stream until it was
        manually stopped and restarted. Called from Settings after saving.
        """
        session = self.live_session
        if session is None or not session.is_live or session.camera_index is None:
            return False
        camera_index = session.camera_index
        width, height, fps = session.requested_resolution or (None, None, None)
        return self.start_live(camera_index, width, height, fps)

    # -- Home overview (was: Home.py) -------------------------------------
    def overview(self) -> dict:
        return {
            "pending_reviews": self.review_store.pending_count(),
            "registered_faces": len(self.registry.list()),
            "active_jobs": sum(1 for j in self._jobs.values() if j.state == "processing"),
            # From history_store, not len(self._jobs) — the GUI's
            # QtProcessingWorker path never touches self._jobs at all (that
            # registry only exists for the FastAPI /process/* endpoints),
            # so "Videos Processed" would always read 0 in the desktop app
            # otherwise. history_store.record() is called from both paths.
            "completed_jobs": len(self.history_store.recent()),
            "live_active": bool(self.live_session and self.live_session.is_live),
        }

    # -- Diagnostics --------------------------------------------------------
    def diagnostics(self) -> dict:
        """Attempt to load each model component and report whether it
        actually works, without processing a whole video first.

        Exists because every one of these fails *silently* by design (a
        processing job should never crash just because, say, the face
        registry's dlib dependency is broken on this machine) — which
        means a broken/missing model otherwise looks identical to "this
        video legitimately had zero detections" from the GUI's point of
        view. This is what Process.py and Settings.py surface so that
        distinction is visible instead of just an empty Review queue with
        no explanation.
        """
        from ..detectors import YoloDetector
        from ..ocr import OCRService

        detector = YoloDetector(self.config.model_path, self.config.low_threshold, self.config.device)
        detector_ok = detector._load()

        ocr = OCRService(self.config.ocr_model_path)
        ocr_ok = ocr._load()

        face_ok, face_error = True, None
        try:
            import face_recognition  # noqa: F401
        except Exception as exc:
            face_ok, face_error = False, str(exc)

        return {
            "detector": {
                "loaded": detector_ok, "model_path": self.config.model_path,
                "device": detector.device, "error": detector.error,
            },
            "ocr": {
                "loaded": ocr_ok, "model_path": self.config.ocr_model_path,
                "device": ocr.device, "error": ocr.error,
            },
            "face_recognition": {"loaded": face_ok, "error": face_error},
        }
