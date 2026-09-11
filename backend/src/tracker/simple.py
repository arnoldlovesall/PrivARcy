from __future__ import annotations


def _iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2-x1) * max(0, y2-y1)
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union else 0


class IoUTracker:
    def __init__(self, threshold=.5, max_missing=15):
        self.threshold, self.max_missing, self.next_id, self.tracks = threshold, max_missing, 1, {}

    def update(self, detections):
        unmatched = set(self.tracks)
        for det in detections:
            candidates = [(track_id, _iou(det.bbox, data["bbox"])) for track_id, data in self.tracks.items() if data["label"] == det.label]
            track_id, score = max(candidates, key=lambda item: item[1], default=(None, 0))
            if score < self.threshold:
                track_id, self.next_id = self.next_id, self.next_id + 1
            self.tracks[track_id] = {"bbox": det.bbox, "label": det.label, "missing": 0}
            det.track_id = track_id
            unmatched.discard(track_id)
        for track_id in unmatched:
            self.tracks[track_id]["missing"] += 1
            if self.tracks[track_id]["missing"] > self.max_missing:
                del self.tracks[track_id]
        return detections
