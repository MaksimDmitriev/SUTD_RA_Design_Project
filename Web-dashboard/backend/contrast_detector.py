from pathlib import Path

import cv2
import numpy as np

from yolo_detector import Detection


class ContrastBlobDetector:
    def __init__(
        self,
        min_area: float = 45.0,
        max_area_ratio: float = 0.04,
        lab_delta: float = 45.0,
        min_saturation: int = 55,
        dark_value: int = 70,
        max_colored_value: int = 245,
        use_lab_contrast: bool = False,
        color_mode: str = "blue",
        blue_hue_min: int = 90,
        blue_hue_max: int = 135,
        blue_min_saturation: int = 50,
        blue_min_value: int = 35,
        blue_max_value: int = 255,
        process_width: int = 320,
        roi_top_ratio: float = 0.15,
        roi_bottom_ratio: float = 0.82,
        max_box_width_ratio: float = 0.38,
        max_box_height_ratio: float = 0.34,
        box_padding_ratio: float = 0.25,
    ):
        if color_mode not in {"all", "blue"}:
            raise ValueError("color_mode must be 'all' or 'blue'")

        self.min_area = min_area
        self.max_area_ratio = max_area_ratio
        self.lab_delta = lab_delta
        self.min_saturation = min_saturation
        self.dark_value = dark_value
        self.max_colored_value = max_colored_value
        self.use_lab_contrast = use_lab_contrast
        self.color_mode = color_mode
        self.blue_hue_min = blue_hue_min
        self.blue_hue_max = blue_hue_max
        self.blue_min_saturation = blue_min_saturation
        self.blue_min_value = blue_min_value
        self.blue_max_value = blue_max_value
        self.process_width = process_width
        self.roi_top_ratio = roi_top_ratio
        self.roi_bottom_ratio = roi_bottom_ratio
        self.max_box_width_ratio = max_box_width_ratio
        self.max_box_height_ratio = max_box_height_ratio
        self.box_padding_ratio = box_padding_ratio

    def load(self) -> None:
        return

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        original_h, original_w = frame_bgr.shape[:2]
        if original_w <= 0 or original_h <= 0:
            return []

        process_h = max(1, int(original_h * (self.process_width / original_w)))
        resized = cv2.resize(
            frame_bgr,
            (self.process_width, process_h),
            interpolation=cv2.INTER_AREA,
        )

        mask = self._build_mask(resized)
        contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]

        scale_x = original_w / self.process_width
        scale_y = original_h / process_h
        processed_area = self.process_width * process_h
        max_area = processed_area * self.max_area_ratio

        detections: list[Detection] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < self.min_area or area > max_area:
                continue

            x, y, width, height = cv2.boundingRect(contour)
            if width <= 1 or height <= 1:
                continue

            if width / self.process_width > self.max_box_width_ratio:
                continue
            if height / process_h > self.max_box_height_ratio:
                continue

            aspect = width / height
            if aspect > 6.0 or aspect < 0.15:
                continue

            extent = area / float(width * height)
            if extent < 0.12:
                continue

            padding_x = int(round(width * self.box_padding_ratio))
            padding_y = int(round(height * self.box_padding_ratio))
            x1 = max(0, min(original_w - 1, int(round((x - padding_x) * scale_x))))
            y1 = max(0, min(original_h - 1, int(round((y - padding_y) * scale_y))))
            x2 = max(0, min(original_w, int(round((x + width + padding_x) * scale_x))))
            y2 = max(0, min(original_h, int(round((y + height + padding_y) * scale_y))))
            if x2 <= x1 or y2 <= y1:
                continue

            score = self._score_contour(mask, contour, x, y, width, height)
            detections.append(
                Detection(
                    xyxy=(x1, y1, x2, y2),
                    confidence=score,
                    class_id=0,
                    label="contrast_object",
                )
            )

        detections.sort(
            key=lambda item: (item.confidence, self._box_area(item.xyxy)),
            reverse=True,
        )
        return detections

    def _build_mask(self, frame_bgr: np.ndarray) -> np.ndarray:
        height, width = frame_bgr.shape[:2]
        blurred = cv2.GaussianBlur(frame_bgr, (5, 5), 0)

        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]

        if self.color_mode == "blue":
            hue = hsv[:, :, 0]
            foreground = (
                self._hue_mask(hue, self.blue_hue_min, self.blue_hue_max)
                & (saturation >= self.blue_min_saturation)
                & (value >= self.blue_min_value)
                & (value <= self.blue_max_value)
            )
        else:
            colored = (saturation >= self.min_saturation) & (value <= self.max_colored_value)
            dark = value <= self.dark_value
            foreground = colored | dark

        if self.use_lab_contrast and self.color_mode == "all":
            lab = cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB).astype(np.float32)
            floor_lab = self._estimate_floor_lab(lab)
            lab_distance = np.linalg.norm(lab - floor_lab, axis=2)
            foreground = foreground | (lab_distance >= self.lab_delta)

        mask = np.where(foreground, 255, 0).astype(np.uint8)

        roi_top = int(height * self.roi_top_ratio)
        roi_bottom = int(height * self.roi_bottom_ratio)
        mask[:roi_top, :] = 0
        mask[roi_bottom:, :] = 0

        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        close_kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel)
        return mask

    @staticmethod
    def _score_contour(
        mask: np.ndarray,
        contour: np.ndarray,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> float:
        area = float(cv2.contourArea(contour))
        extent = area / max(float(width * height), 1.0)
        local = mask[y : y + height, x : x + width]
        fill_ratio = float(cv2.countNonZero(local)) / max(float(width * height), 1.0)
        compactness = min(1.0, max(0.0, (extent + fill_ratio) / 2.0))
        return min(1.0, max(0.05, compactness))

    @staticmethod
    def _estimate_floor_lab(lab: np.ndarray) -> np.ndarray:
        height, width = lab.shape[:2]
        strip = max(4, int(width * 0.12))
        top = int(height * 0.35)
        left = lab[top:, :strip, :]
        right = lab[top:, width - strip :, :]
        samples = np.concatenate((left.reshape(-1, 3), right.reshape(-1, 3)), axis=0)
        return np.median(samples, axis=0)

    @staticmethod
    def _hue_mask(hue: np.ndarray, hue_min: int, hue_max: int) -> np.ndarray:
        hue_min = int(np.clip(hue_min, 0, 179))
        hue_max = int(np.clip(hue_max, 0, 179))
        if hue_min <= hue_max:
            return (hue >= hue_min) & (hue <= hue_max)
        return (hue >= hue_min) | (hue <= hue_max)

    @staticmethod
    def _box_area(xyxy: tuple[int, int, int, int]) -> int:
        x1, y1, x2, y2 = xyxy
        return max(0, x2 - x1) * max(0, y2 - y1)


def save_mask_preview(
    path: str | Path,
    frame_bgr: np.ndarray,
    detector: ContrastBlobDetector,
) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    original_h, original_w = frame_bgr.shape[:2]
    process_h = max(1, int(original_h * (detector.process_width / original_w)))
    resized = cv2.resize(
        frame_bgr,
        (detector.process_width, process_h),
        interpolation=cv2.INTER_AREA,
    )
    mask = detector._build_mask(resized)
    cv2.imwrite(str(output_path), mask)
