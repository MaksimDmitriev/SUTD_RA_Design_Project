import argparse
import time
from datetime import datetime

from camera import Camera
from clip_classifier import ClipClassifier
from robot_motion import create_motion_backend
from yolo_detector import YoloDetector, crop_detection


def parse_args():
    parser = argparse.ArgumentParser(
        description="Drive forward, stop on YOLO object detection, then classify the crop."
    )
    parser.add_argument(
        "--model",
        default="/home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model",
        help="Path to the YOLO NCNN model directory on the robot.",
    )
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--distance-meters", type=float, default=1.0)
    parser.add_argument(
        "--meters-per-second",
        type=float,
        default=0.20,
        help="Approximate speed used to convert distance to a timed drive.",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Override the timed drive duration.",
    )
    parser.add_argument("--poll-seconds", type=float, default=0.20)
    parser.add_argument(
        "--motion",
        choices=["auto", "hiwonder", "shell", "dry-run"],
        default="auto",
    )
    parser.add_argument("--speed", type=int, default=35)
    parser.add_argument(
        "--direction",
        type=int,
        default=90,
        help="Hiwonder mecanum direction angle. Adjust if 90 is not forward.",
    )
    parser.add_argument(
        "--motion-debug",
        action="store_true",
        help="Print attempted motion imports and failures.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    drive_seconds = args.max_seconds
    if drive_seconds is None:
        drive_seconds = args.distance_meters / args.meters_per_second

    print("[test] loading camera")
    camera = Camera()
    print("[test] loading YOLO detector")
    detector = YoloDetector(args.model, confidence=args.conf, image_size=args.imgsz)
    detector.load()
    print("[test] loading OpenCLIP classifier")
    classifier = ClipClassifier()
    classifier.load()

    motion = create_motion_backend(
        mode=args.motion,
        speed=args.speed,
        direction=args.direction,
        debug=args.motion_debug,
    )
    print(f"[test] motion backend: {motion.name}")
    print(f"[test] drive window: {drive_seconds:.2f}s")

    started_at = time.monotonic()
    motion.forward()
    try:
        while time.monotonic() - started_at < drive_seconds:
            frame = camera.read()
            detections = detector.detect(frame)

            if detections:
                motion.stop()
                detected_at = datetime.now().isoformat(timespec="seconds")
                detection = detections[0]
                crop = crop_detection(frame, detection)
                prediction = classifier.predict(crop)
                label_title = prediction.label.title()

                print(
                    f"[{detected_at}] detected {detection.label} "
                    f"confidence={detection.confidence:.3f} box={detection.xyxy}"
                )
                print(
                    f"[{detected_at}] detected {label_title} "
                    f"confidence={prediction.confidence:.3f} "
                    f"prompt={prediction.prompt!r}"
                )
                print(f"[{detected_at}] scores={prediction.scores}")
                return 0

            time.sleep(args.poll_seconds)

        motion.stop()
        print("[test] no object detected")
        return 0
    finally:
        motion.stop()


if __name__ == "__main__":
    raise SystemExit(main())
