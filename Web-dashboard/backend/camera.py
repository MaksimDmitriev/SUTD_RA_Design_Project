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
        self._last_frame_at = 0.0
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._last_error: str | None = None
        self._max_frame_age = float(os.environ.get("SORTIBOT_CAMERA_MAX_FRAME_AGE", "2.0"))

    def _open(self) -> cv2.VideoCapture:
        candidates: list[str | int] = [self.source, 0]
        for source in candidates:
            cap = cv2.VideoCapture(source)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok, frame = cap.read()
            if ok and frame is not None:
                with self._lock:
                    self._last_frame = frame
                    self._last_frame_at = time.monotonic()
                    self._last_error = None
                self._ready_event.set()
                return cap
            cap.release()
        raise RuntimeError("No camera source worked. Check camera connection/service.")

    def _start_reader(self) -> None:
        if self._reader_thread is not None and self._reader_thread.is_alive():
            return

        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="sortibot-camera-reader",
            daemon=True,
        )
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    if self._capture is None or not self._capture.isOpened():
                        self._capture = self._open()

                    ok, frame = self._capture.read()
                    if ok and frame is not None:
                        with self._lock:
                            self._last_frame = frame
                            self._last_frame_at = time.monotonic()
                            self._last_error = None
                        self._ready_event.set()
                        continue

                    if self._capture is not None:
                        self._capture.release()
                    self._capture = None
                    time.sleep(0.05)
                except Exception as exc:
                    with self._lock:
                        self._last_error = str(exc)
                    self._ready_event.clear()
                    if self._capture is not None:
                        self._capture.release()
                    self._capture = None
                    time.sleep(0.25)
        finally:
            if self._capture is not None:
                self._capture.release()
            self._capture = None

    def read(self):
        self._start_reader()
        if not self._ready_event.wait(timeout=2.0):
            with self._lock:
                last_error = self._last_error
            message = "Camera frame unavailable."
            if last_error:
                message += f" Last error: {last_error}"
            raise RuntimeError(message)

        with self._lock:
            if self._last_frame is None:
                raise RuntimeError("Camera frame unavailable.")
            age = time.monotonic() - self._last_frame_at
            if age > self._max_frame_age:
                raise RuntimeError(f"Camera frame is stale ({age:.2f}s old).")
            return self._last_frame.copy()

    def close(self) -> None:
        self._stop_event.set()
        if (
            self._reader_thread is not None
            and self._reader_thread.is_alive()
            and threading.current_thread() is not self._reader_thread
        ):
            self._reader_thread.join(timeout=1.0)
        if self._reader_thread is None or not self._reader_thread.is_alive():
            self._capture = None

    def jpeg(self, width: int = 640):
        frame = self.read()
        height = int(frame.shape[0] * (width / frame.shape[1]))
        resized = cv2.resize(frame, (width, height))
        ok, encoded = cv2.imencode(".jpg", resized)
        if not ok:
            raise RuntimeError("Failed to encode camera frame.")
        return encoded.tobytes()
