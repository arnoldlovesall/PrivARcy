from __future__ import annotations

from pathlib import Path

import cv2

from ..video.io import VideoReader


class FrameExtractor:
    """Pulls still frames out of raw video for building/growing a YOLO26
    training set — this is the "Frame Extraction" stage upstream of
    labeling, distinct from ProcessingPipeline's own frame loop (which
    reads frames to run inference on, not to save them to disk).
    """

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract(self, video_path: str | Path, every_n_frames: int = 30,
                prefix: str | None = None, max_frames: int | None = None) -> list[str]:
        """Save every Nth frame as a JPEG. Returns the saved file paths.

        `every_n_frames` defaults to 30 (roughly one frame/second at 30fps)
        — dense frame-by-frame extraction produces a training set full of
        near-duplicate images, which hurts a detector more than it helps.
        """
        video_path = Path(video_path)
        prefix = prefix or video_path.stem
        reader = VideoReader(str(video_path))
        saved = []
        try:
            for index, frame in enumerate(reader):
                if index % max(1, every_n_frames) != 0:
                    continue
                out_path = self.output_dir / f"{prefix}_frame{index:06d}.jpg"
                cv2.imwrite(str(out_path), frame)
                saved.append(str(out_path))
                if max_frames and len(saved) >= max_frames:
                    break
        finally:
            reader.close()
        return saved
