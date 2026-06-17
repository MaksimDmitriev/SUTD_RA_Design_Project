import os
import threading
import time
from typing import Optional

import cv2


DEFAULT_CAMERA_SOURCE = os.environ.get(
    "SORTIBOT_CAMERA_URL",
    "http://127.0.0.1:8080?action=stream",
)


class Camera:
    def __init__(self, source: str | int = DEFAULT_CAMERA_SOURCE):
        self.source = source
        self._capture: Optional[cv2.VideoCapture] = None
        self._lock = threading.Lock()
        self._last_frame = None

    def _open(self) -> cv2.VideoCapture:
        candidates: list[str | int] = [self.source, 0]
        for source in candidates:
            cap = cv2.VideoCapture(source)
            ok, frame = cap.read()
            if ok and frame is not None:
                self._last_frame = frame
                return cap
            cap.release()
        raise RuntimeError("No camera source worked. Check camera connection/service.")

    def read(self):
        with self._lock:
            if self._capture is None or not self._capture.isOpened():
                self._capture = self._open()

            ok, frame = self._capture.read()
            if ok and frame is not None:
                self._last_frame = frame
                return frame

            self._capture.release()
            self._capture = None

            if self._last_frame is not None:
                return self._last_frame

        time.sleep(0.05)
        raise RuntimeError("Camera frame unavailable.")

    def jpeg(self, width: int = 640):
        frame = self.read()
        height = int(frame.shape[0] * (width / frame.shape[1]))
        resized = cv2.resize(frame, (width, height))
        ok, encoded = cv2.imencode(".jpg", resized)
        if not ok:
            raise RuntimeError("Failed to encode camera frame.")
        return encoded.tobytes()
