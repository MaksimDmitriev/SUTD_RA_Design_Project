import argparse
import json
import time
from pathlib import Path

import cv2

from camera import Camera
from robot_ik import KinematicsArm
from yolo_detector import Detection, YoloDetector


def parse_servo_pulses(value: str) -> list[tuple[int, int]]:
    positions = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            servo_id_raw, pulse_raw = item.split(":", 1)
            servo_id = int(servo_id_raw)
            pulse = int(pulse_raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "servo pulses must use servo_id:pulse pairs, for example "
                "3:1336,4:2460,5:1529,6:1480"
            ) from exc
        if servo_id < 1 or servo_id > 6:
            raise argparse.ArgumentTypeError("servo_id must be between 1 and 6")
        if pulse < 500 or pulse > 2500:
            raise argparse.ArgumentTypeError("pulse must be between 500 and 2500")
        positions.append((servo_id, pulse))
    if not positions:
        raise argparse.ArgumentTypeError("at least one servo_id:pulse pair is required")
    return positions


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Detect an object and print the YOLO box bottom_y_ratio for "
            "camera-distance calibration."
        )
    )
    parser.add_argument(
        "--model",
        default="/home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model",
        help="Path to the custom YOLO model directory on the robot.",
    )
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument(
        "--labels",
        default="red_useful,purple_trash",
        help="Comma-separated labels to accept. Empty means any label.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=5,
        help="Number of successful detections to average.",
    )
    parser.add_argument(
        "--max-frame-tries",
        type=int,
        default=30,
        help="Maximum camera frames to inspect before giving up.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=0.12,
        help="Delay between camera reads.",
    )
    parser.add_argument(
        "--home-servo-pulses",
        type=parse_servo_pulses,
        default=None,
        help=(
            "Optional comma-separated servo_id:pulse camera pose, for example "
            "3:1336,4:2460,5:1529,6:1480."
        ),
    )
    parser.add_argument("--home-servo-duration", type=float, default=1.5)
    parser.add_argument(
        "--debug-frame",
        default=None,
        help="Optional path for an annotated frame, for example /tmp/bottom_ratio.jpg.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print one JSON object instead of human-readable lines.",
    )
    return parser.parse_args()


def choose_detection(
    detections: list[Detection],
    allowed_labels: set[str],
) -> Detection | None:
    if not allowed_labels:
        return detections[0] if detections else None
    for detection in detections:
        if detection.label.lower() in allowed_labels:
            return detection
    return None


def detection_measurement(frame, detection: Detection) -> dict:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = detection.xyxy
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    return {
        "label": detection.label,
        "confidence": detection.confidence,
        "xyxy": detection.xyxy,
        "frame_width": width,
        "frame_height": height,
        "center_x_ratio": center_x / width,
        "center_y_ratio": center_y / height,
        "bottom_y_ratio": y2 / height,
        "top_y_ratio": y1 / height,
        "box_height_ratio": (y2 - y1) / height,
        "box_width_ratio": (x2 - x1) / width,
    }


def annotate_frame(frame, measurement: dict):
    annotated = frame.copy()
    x1, y1, x2, y2 = measurement["xyxy"]
    center_x = int(measurement["center_x_ratio"] * measurement["frame_width"])
    bottom_y = int(measurement["bottom_y_ratio"] * measurement["frame_height"])
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.circle(annotated, (center_x, bottom_y), 5, (0, 255, 255), -1)
    cv2.line(
        annotated,
        (0, bottom_y),
        (measurement["frame_width"], bottom_y),
        (255, 255, 0),
        1,
    )
    text = (
        f"{measurement['label']} {measurement['confidence']:.2f} "
        f"bottom_y_ratio={measurement['bottom_y_ratio']:.3f}"
    )
    cv2.putText(
        annotated,
        text,
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
    )
    return annotated


def average_measurements(measurements: list[dict]) -> dict:
    first = measurements[0]
    averaged = {
        "label": first["label"],
        "samples": len(measurements),
        "frame_width": first["frame_width"],
        "frame_height": first["frame_height"],
    }
    for key in [
        "confidence",
        "center_x_ratio",
        "center_y_ratio",
        "bottom_y_ratio",
        "top_y_ratio",
        "box_height_ratio",
        "box_width_ratio",
    ]:
        averaged[key] = sum(item[key] for item in measurements) / len(measurements)
    averaged["last_xyxy"] = measurements[-1]["xyxy"]
    return averaged


def main() -> int:
    args = parse_args()
    allowed_labels = {
        label.strip().lower()
        for label in args.labels.split(",")
        if label.strip()
    }

    if args.home_servo_pulses is not None:
        arm = KinematicsArm()
        if not args.json:
            print(f"homing arm with servo pulses: {args.home_servo_pulses}")
        arm.set_servo_pulses(
            args.home_servo_pulses,
            duration_seconds=args.home_servo_duration,
        )

    camera = Camera()
    detector = YoloDetector(args.model, confidence=args.conf, image_size=args.imgsz)
    detector.load()

    measurements = []
    last_frame = None
    try:
        for _ in range(max(1, args.max_frame_tries)):
            frame = camera.read()
            detections = detector.detect(frame)
            detection = choose_detection(detections, allowed_labels)
            if detection is None:
                time.sleep(args.poll_seconds)
                continue

            measurement = detection_measurement(frame, detection)
            measurements.append(measurement)
            last_frame = frame
            if not args.json:
                print(
                    f"sample={len(measurements)} "
                    f"label={measurement['label']} "
                    f"conf={measurement['confidence']:.3f} "
                    f"bottom_y_ratio={measurement['bottom_y_ratio']:.4f} "
                    f"center_x_ratio={measurement['center_x_ratio']:.4f} "
                    f"xyxy={measurement['xyxy']}"
                )
            if len(measurements) >= max(1, args.frames):
                break
            time.sleep(args.poll_seconds)
    finally:
        camera.close()

    if not measurements:
        message = (
            "No accepted object detection found. Check --labels, --conf, model path, "
            "camera pose, and object visibility."
        )
        if args.json:
            print(json.dumps({"ok": False, "error": message}))
        else:
            print(message)
        return 1

    result = average_measurements(measurements)
    if args.debug_frame and last_frame is not None:
        output_path = Path(args.debug_frame).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), annotate_frame(last_frame, measurements[-1]))
        if not args.json:
            print(f"debug_frame={output_path}")

    if args.json:
        print(json.dumps({"ok": True, **result}))
    else:
        print("")
        print(f"average_samples={result['samples']}")
        print(f"label={result['label']}")
        print(f"bottom_y_ratio={result['bottom_y_ratio']:.4f}")
        print(f"center_x_ratio={result['center_x_ratio']:.4f}")
        print(f"box_height_ratio={result['box_height_ratio']:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
