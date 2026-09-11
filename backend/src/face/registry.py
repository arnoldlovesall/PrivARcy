from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class FaceMatch:
    code: str | None
    name: str | None
    distance: float | None
    matched: bool


class FaceRegistry:
    """File-backed face registry that validates exactly one face per photo."""
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.index_path = self.directory / "registry.json"

    def _load(self) -> list[dict]:
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def _save(self, records: list[dict]) -> None:
        self.index_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    @staticmethod
    def _encoding(image_path: str) -> Any:
        try:
            import face_recognition
        except (ImportError, OSError) as exc:
            # On Windows this is almost always dlib's compiled extension
            # (_dlib_pybind11) failing to load — either it was built for a
            # different Python version/architecture than the one running,
            # or the Microsoft Visual C++ Redistributable it depends on
            # isn't installed. Re-raised with concrete next steps instead
            # of the raw DLL error, since "DLL load failed while importing
            # _dlib_pybind11" means nothing actionable on its own.
            raise RuntimeError(
                "Face recognition isn't available: dlib failed to load "
                f"({exc}). This usually means either (1) the installed "
                "Microsoft Visual C++ Redistributable is missing — install "
                "the latest x64 version from Microsoft — or (2) the dlib "
                "wheel doesn't match this Python's version/architecture — "
                "reinstall with `pip install --force-reinstall dlib-bin` "
                "(or `dlib`) inside this project's venv."
            ) from exc
        image = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(image)
        if len(encodings) != 1:
            raise ValueError("The photo must contain exactly one clearly visible face.")
        return encodings[0]

    def register_photo(self, code: str, name: str, image_path: str) -> dict:
        encoding = self._encoding(image_path)
        registered_at = datetime.now().isoformat(timespec="seconds")
        records = [r for r in self._load() if r["code"] != code]
        records.append({
            "code": code, "name": name, "image_path": str(image_path),
            "encoding": encoding.tolist(), "registered_at": registered_at,
        })
        self._save(records)
        return {"code": code, "name": name, "image_path": str(image_path), "registered_at": registered_at}

    def remove(self, code: str) -> None:
        self._save([r for r in self._load() if r["code"] != code])

    def list(self) -> list[dict]:
        return [
            {**{k: r.get(k) for k in ("code", "name", "image_path", "registered_at")}}
            for r in self._load()
        ]

    def verify(self, code: str) -> dict:
        """Re-encode a registered participant's stored photo and compare it
        against the encoding saved at registration time.

        This is a self-consistency check (does the registry entry still
        match its own source photo?), not a live "look at the camera"
        verification — there is no second photo to compare against here.
        A large distance would mean the registry file was hand-edited or
        the photo file was replaced/corrupted since registration.
        """
        record = next((r for r in self._load() if r["code"] == code), None)
        if record is None:
            return {"matched": False, "confidence": 0.0, "message": "No such registered participant."}
        try:
            fresh = self._encoding(record["image_path"])
        except (FileNotFoundError, ValueError) as exc:
            return {"matched": False, "confidence": 0.0, "message": str(exc)}
        stored = np.asarray(record["encoding"])
        distance = float(np.linalg.norm(fresh - stored))
        # face_recognition's typical match threshold is ~0.6; convert
        # distance to a 0-100% confidence for display purposes.
        confidence = max(0.0, min(100.0, (1 - distance / 0.6) * 100))
        matched = distance <= 0.6
        return {
            "matched": matched,
            "confidence": round(confidence, 1),
            "distance": round(distance, 4),
            "message": "Registry entry matches its source photo." if matched
                       else "Registry entry no longer matches its source photo.",
        }

    def recognize_frame(self, frame: Any, tolerance: float = .5) -> list[dict]:
        try:
            import face_recognition
        except (ImportError, OSError) as exc:
            raise RuntimeError(f"Face recognition isn't available: dlib failed to load ({exc}).") from exc
        records = self._load()
        if not records:
            return []
        rgb = frame[:, :, ::-1]
        locations = face_recognition.face_locations(rgb)
        encodings = face_recognition.face_encodings(rgb, locations)
        known = [np.asarray(r["encoding"]) for r in records]
        found = []
        for location, encoding in zip(locations, encodings):
            distances = face_recognition.face_distance(known, encoding)
            index = int(np.argmin(distances)) if len(distances) else -1
            matched = index >= 0 and float(distances[index]) <= tolerance
            top, right, bottom, left = location
            found.append({"bbox": (left, top, right, bottom), "match": FaceMatch(records[index]["code"], records[index]["name"], float(distances[index]), matched) if matched else FaceMatch(None, None, None, False)})
        return found

    # -- Liveness (used by FaceRegister.py's scan/enroll dialog) --------
    @staticmethod
    def detect_faces_with_landmarks(frame: Any) -> list[dict]:
        """One frame -> a list of {bbox, landmarks, ear} per detected face.

        `ear` is the eye-aspect-ratio (see `_eye_aspect_ratio`) — the
        primary signal `detect_blink` watches to distinguish a live person
        from a printed photo or a static image held up to the camera.
        """
        try:
            import face_recognition
        except (ImportError, OSError) as exc:
            raise RuntimeError(f"Face recognition isn't available: dlib failed to load ({exc}).") from exc

        rgb = frame[:, :, ::-1]
        locations = face_recognition.face_locations(rgb)
        landmarks_list = face_recognition.face_landmarks(rgb, locations)
        results = []
        for location, landmarks in zip(locations, landmarks_list):
            top, right, bottom, left = location
            ear = None
            if "left_eye" in landmarks and "right_eye" in landmarks:
                ear = (FaceRegistry._eye_aspect_ratio(landmarks["left_eye"])
                       + FaceRegistry._eye_aspect_ratio(landmarks["right_eye"])) / 2
            results.append({"bbox": (left, top, right, bottom), "landmarks": landmarks, "ear": ear})
        return results

    @staticmethod
    def _eye_aspect_ratio(eye_points: list[tuple[int, int]]) -> float:
        """Standard 6-point eye-aspect-ratio (Soukupova & Cech, 2016):
        vertical eye-opening distance over horizontal eye width. Drops
        sharply during a blink (eyelid closes) and recovers immediately
        after — a real person naturally blinks every few seconds, while a
        printed photo or a static image held up to the camera never does,
        which is what makes this a simple, real anti-spoofing signal
        rather than just a framing check.
        """
        p = [np.asarray(pt) for pt in eye_points]
        if len(p) < 6:
            return 1.0  # can't compute — treat as "eye open", never blocks on a bad landmark read
        vertical_1 = np.linalg.norm(p[1] - p[5])
        vertical_2 = np.linalg.norm(p[2] - p[4])
        horizontal = np.linalg.norm(p[0] - p[3])
        if horizontal == 0:
            return 1.0
        return (vertical_1 + vertical_2) / (2.0 * horizontal)

    class BlinkDetector:
        """Tracks eye-aspect-ratio across frames and reports when a full
        blink (open -> closed -> open) has been observed. Feed it one EAR
        value per frame via `update()`."""

        def __init__(self, closed_threshold: float = 0.21, min_closed_frames: int = 1):
            self.closed_threshold = closed_threshold
            self.min_closed_frames = min_closed_frames
            self._closed_streak = 0
            self.blinks = 0

        def update(self, ear: float | None) -> bool:
            """Returns True the instant a blink completes (edge-triggered,
            fires once per blink, not for every closed-eye frame)."""
            if ear is None:
                return False
            if ear < self.closed_threshold:
                self._closed_streak += 1
                return False
            if self._closed_streak >= self.min_closed_frames:
                self._closed_streak = 0
                self.blinks += 1
                return True
            self._closed_streak = 0
            return False
