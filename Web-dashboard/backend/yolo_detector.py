from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Detection:
    xyxy: tuple[int, int, int, int]
    confidence: float
    class_id: int
    label: str


class YoloDetector:
    def __init__(
        self,
        model_path: str | Path = "/home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model",
        confidence: float = 0.25,
        image_size: int = 640,
    ):
        self.model_path = str(model_path)
        self.confidence = confidence
        self.image_size = image_size
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return

        from ultralytics import YOLO

        self._model = YOLO(self.model_path, task="detect")

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        self.load()
        result = self._model.predict(
            frame_bgr,
            imgsz=self.image_size,
            conf=self.confidence,
            verbose=False,
        )[0]

        detections: list[Detection] = []
        names = result.names or {}
        height, width = frame_bgr.shape[:2]

        for box in result.boxes:
            class_id = int(box.cls[0].item())
            confidence = float(box.conf[0].item())
            x1, y1, x2, y2 = [int(round(v)) for v in box.xyxy[0].tolist()]
            x1 = max(0, min(width - 1, x1))
            y1 = max(0, min(height - 1, y1))
            x2 = max(0, min(width, x2))
            y2 = max(0, min(height, y2))
            if x2 <= x1 or y2 <= y1:
                continue
            detections.append(
                Detection(
                    xyxy=(x1, y1, x2, y2),
                    confidence=confidence,
                    class_id=class_id,
                    label=str(names.get(class_id, class_id)),
                )
            )

        detections.sort(key=lambda item: item.confidence, reverse=True)
        return detections


def crop_detection(
    frame_bgr: np.ndarray,
    detection: Detection,
    padding_ratio: float = 0.08,
) -> np.ndarray:
    height, width = frame_bgr.shape[:2]
    x1, y1, x2, y2 = detection.xyxy
    pad_x = int((x2 - x1) * padding_ratio)
    pad_y = int((y2 - y1) * padding_ratio)

    crop_x1 = max(0, x1 - pad_x)
    crop_y1 = max(0, y1 - pad_y)
    crop_x2 = min(width, x2 + pad_x)
    crop_y2 = min(height, y2 + pad_y)
    return frame_bgr[crop_y1:crop_y2, crop_x1:crop_x2]
