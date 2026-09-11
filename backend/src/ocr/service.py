from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class OCRResult:
    text: str
    confidence: float = 0.0
    bbox: tuple[int, int, int, int] | None = None


class OCRService:
    """TrOCR-based text extraction for detected privacy regions.

    Uses a transformer encoder-decoder (default: microsoft/trocr-base-printed)
    rather than a classical OCR engine, since PrivARcy needs to read text
    under real-world video conditions: motion blur, low resolution, and
    irregular/rotated text orientations on ID cards, documents, license
    plates, and payment cards. The model is lazily loaded on first use and
    never invents text — a load or inference failure yields an empty result
    instead of a fabricated string.
    """

    def __init__(self, model_path: str = "microsoft/trocr-base-printed", device: str | None = None):
        self.model_path = model_path
        self.device = device
        self._processor = None
        self._model = None
        self.loaded: bool | None = None  # None = not attempted yet
        self.error: str | None = None

    def _load(self) -> bool:
        if self._model is not None:
            return True
        if self.loaded is False:
            return False  # already failed once this instance — don't retry every crop
        try:
            import torch
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            from transformers import logging as hf_logging

            # `microsoft/trocr-base-printed`'s checkpoint doesn't include
            # weights for the ViT encoder's pooler head (encoder.pooler.*):
            # TrOCR's generation path never calls the pooler at all — only
            # the encoder's sequence output feeds the decoder — so those
            # two tensors get freshly (randomly) initialized on every load,
            # and transformers warns about it by default. That warning is
            # expected and harmless here (it would matter if this were
            # being used as a plain image classifier via the pooler output,
            # which it isn't), so it's suppressed rather than left to look
            # like something is broken. Errors are still shown.
            hf_logging.set_verbosity_error()

            self._processor = TrOCRProcessor.from_pretrained(self.model_path)
            self._model = VisionEncoderDecoderModel.from_pretrained(self.model_path)
            self.device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
            self._model.to(self.device)
            self._model.eval()
            self.loaded = True
            return True
        except Exception as exc:
            self.loaded = False
            self.error = str(exc)
            log.warning("TrOCR unavailable (%s); text extraction skipped for this session", exc)
            return False

    def extract(self, image: Any) -> list[OCRResult]:
        """Run TrOCR over a single cropped region (a full detection ROI).

        Returns at most one OCRResult for the region — TrOCR is a
        line/region-level recognizer, unlike box-per-word engines, so the
        whole crop is treated as one text region.
        """
        if not self._load():
            return []
        try:
            import torch
            from PIL import Image
            import numpy as np

            if isinstance(image, np.ndarray):
                # Assume BGR (OpenCV) input; convert to RGB for the model.
                pil_image = Image.fromarray(image[:, :, ::-1] if image.ndim == 3 else image).convert("RGB")
            else:
                pil_image = image.convert("RGB")

            pixel_values = self._processor(images=pil_image, return_tensors="pt").pixel_values.to(self.device)
            with torch.no_grad():
                outputs = self._model.generate(
                    pixel_values, output_scores=True, return_dict_in_generate=True, max_new_tokens=64,
                )
            text = self._processor.batch_decode(outputs.sequences, skip_special_tokens=True)[0].strip()
            confidence = self._sequence_confidence(outputs)
            if not text:
                return []
            return [OCRResult(text, confidence, None)]
        except Exception as exc:
            log.warning("TrOCR inference failed: %s", exc)
            return []

    @staticmethod
    def _sequence_confidence(outputs) -> float:
        """Approximate confidence as the mean per-token generation probability."""
        try:
            import torch
            scores = outputs.scores  # tuple of (batch, vocab) logits, one per generated token
            if not scores:
                return 0.0
            probs = [torch.softmax(step, dim=-1).max().item() for step in scores]
            return float(sum(probs) / len(probs))
        except Exception:
            return 0.5
