import cv2


class RedactionEngine:
    def __init__(self, method="blur", blur_strength=31): self.method, self.blur_strength = method.lower(), max(3, blur_strength | 1)
    def apply(self, frame, regions):
        for x1, y1, x2, y2 in regions:
            x1, y1, x2, y2 = max(0,x1), max(0,y1), min(frame.shape[1],x2), min(frame.shape[0],y2)
            roi = frame[y1:y2, x1:x2]
            if roi.size == 0: continue
            if self.method == "solid mask": roi[:] = 0
            elif self.method == "pixelate":
                small = cv2.resize(roi, (max(1, roi.shape[1]//12), max(1, roi.shape[0]//12)))
                roi[:] = cv2.resize(small, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_NEAREST)
            else: roi[:] = cv2.GaussianBlur(roi, (self.blur_strength, self.blur_strength), 0)
        return frame
