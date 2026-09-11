import cv2


class VideoReader:
    def __init__(self, path):
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened(): raise ValueError(f"Cannot open video: {path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
    def __iter__(self):
        while True:
            ok, frame = self.cap.read()
            if not ok: break
            yield frame
    def close(self): self.cap.release()


class VideoWriter:
    def __init__(self, path, fps, size):
        self.writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
        if not self.writer.isOpened(): raise ValueError(f"Cannot create output: {path}")
    def write(self, frame): self.writer.write(frame)
    def close(self): self.writer.release()
