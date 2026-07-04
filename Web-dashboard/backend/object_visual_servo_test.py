import argparse
import time
from datetime import datetime
from pathlib import Path

import cv2

from camera import Camera
from clip_classifier import ClipClassifier
from robot_ik import ArmCoordinate, KinematicsArm
from robot_motion import create_motion_backend
from yolo_detector import Detection, YoloDetector, crop_detection


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Use YOLO visual servoing to center and approach an object, then classify "
            "the crop. Optional grabbing uses MasterPi inverse kinematics."
        )
    )
    parser.add_argument(
        "--model",
        default="/home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model",
        help="Path to the YOLO NCNN model directory on the robot.",
    )
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--max-seconds", type=float, default=12.0)
    parser.add_argument("--poll-seconds", type=float, default=0.12)
    parser.add_argument(
        "--motion",
        choices=["auto", "hiwonder", "dry-run"],
        default="auto",
    )
    parser.add_argument("--speed", type=int, default=35)
    parser.add_argument(
        "--direction",
        type=int,
        default=90,
        help="Hiwonder mecanum direction angle used by stop/forward fallback.",
    )
    parser.add_argument("--motion-debug", action="store_true")
    parser.add_argument(
        "--target-x-ratio",
        type=float,
        default=0.50,
        help="Target horizontal object center in the frame.",
    )
    parser.add_argument(
        "--target-bottom-ratio",
        type=float,
        default=0.68,
        help="Stop when the bottom of the YOLO box reaches this frame height ratio.",
    )
    parser.add_argument(
        "--x-deadband-ratio",
        type=float,
        default=0.06,
        help="Allowed horizontal error before stop/grab.",
    )
    parser.add_argument(
        "--bottom-deadband-ratio",
        type=float,
        default=0.03,
        help="Allowed vertical stop-zone error before stop/grab.",
    )
    parser.add_argument("--stable-frames", type=int, default=3)
    parser.add_argument("--pickup-frames", type=int, default=2)
    parser.add_argument(
        "--ignore-cooldown-frames",
        type=int,
        default=8,
        help="Frames to keep moving after an ignored object before classifying again.",
    )
    parser.add_argument(
        "--search-y-speed",
        type=float,
        default=25.0,
        help="Forward speed while no object is visible.",
    )
    parser.add_argument("--max-x-speed", type=float, default=18.0)
    parser.add_argument("--max-y-speed", type=float, default=16.0)
    parser.add_argument(
        "--kp-x",
        type=float,
        default=70.0,
        help="Horizontal proportional gain in robot translation units.",
    )
    parser.add_argument(
        "--kp-y",
        type=float,
        default=70.0,
        help="Forward proportional gain in robot translation units.",
    )
    parser.add_argument(
        "--debug-frame-dir",
        default=None,
        help="Directory for annotated frames, for example ~/Web-dashboard/data/debug_detections.",
    )
    parser.add_argument(
        "--grab",
        action="store_true",
        help="After non-ignore classification, run a simple IK grab sequence.",
    )
    parser.add_argument(
        "--use-camera-transform",
        action="store_true",
        help="Convert YOLO pixel position to arm coordinates using MasterPi calibration.",
    )
    parser.add_argument("--grab-x-cm", type=float, default=0.0)
    parser.add_argument("--grab-y-cm", type=float, default=16.5)
    parser.add_argument("--grab-z-cm", type=float, default=2.0)
    return parser.parse_args()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def detection_geometry(frame, detection: Detection, args):
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = detection.xyxy
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    target_x = args.target_x_ratio * width
    target_bottom = args.target_bottom_ratio * height
    x_error_ratio = (center_x - target_x) / width
    bottom_error_ratio = (target_bottom - y2) / height
    return {
        "width": width,
        "height": height,
        "center_x": center_x,
        "center_y": center_y,
        "bottom_y": y2,
        "target_x": target_x,
        "target_bottom": target_bottom,
        "x_error_ratio": x_error_ratio,
        "bottom_error_ratio": bottom_error_ratio,
    }


def command_from_geometry(geometry: dict, args) -> tuple[float, float]:
    x_error = geometry["x_error_ratio"]
    bottom_error = geometry["bottom_error_ratio"]

    if abs(x_error) <= args.x_deadband_ratio:
        x_speed = 0.0
    else:
        # Positive x moves the chassis right in the Hiwonder translation API.
        x_speed = clamp(args.kp_x * x_error, -args.max_x_speed, args.max_x_speed)

    if bottom_error <= args.bottom_deadband_ratio:
        y_speed = 0.0
    else:
        # Positive y moves forward. Move slower as the object reaches the pickup line.
        y_speed = clamp(args.kp_y * bottom_error, 4.0, args.max_y_speed)

    return x_speed, y_speed


def is_pickup_ready(geometry: dict, args) -> bool:
    return (
        abs(geometry["x_error_ratio"]) <= args.x_deadband_ratio
        and geometry["bottom_error_ratio"] <= args.bottom_deadband_ratio
    )


def annotate_frame(frame, detection: Detection, geometry: dict, text: str):
    annotated = frame.copy()
    x1, y1, x2, y2 = detection.xyxy
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.circle(
        annotated,
        (int(geometry["center_x"]), int(geometry["center_y"])),
        5,
        (0, 255, 255),
        -1,
    )
    cv2.line(
        annotated,
        (int(geometry["target_x"]), 0),
        (int(geometry["target_x"]), geometry["height"]),
        (255, 255, 0),
        1,
    )
    cv2.line(
        annotated,
        (0, int(geometry["target_bottom"])),
        (geometry["width"], int(geometry["target_bottom"])),
        (255, 255, 0),
        1,
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


def save_debug_frame(directory: str | None, frame, detection, geometry, text: str) -> None:
    if not directory:
        return
    output_dir = Path(directory).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = datetime.now().strftime("%Y%m%dT%H%M%S_%f") + ".jpg"
    cv2.imwrite(str(output_dir / filename), annotate_frame(frame, detection, geometry, text))
    print(f"[debug] saved {output_dir / filename}")


def main() -> int:
    args = parse_args()

    print("[visual-servo] loading camera")
    camera = Camera()
    print("[visual-servo] loading YOLO detector")
    detector = YoloDetector(args.model, confidence=args.conf, image_size=args.imgsz)
    detector.load()
    print("[visual-servo] loading OpenCLIP classifier")
    classifier = ClipClassifier()
    classifier.load()

    motion = create_motion_backend(
        mode=args.motion,
        speed=args.speed,
        direction=args.direction,
        debug=args.motion_debug,
    )
    print(f"[visual-servo] motion backend: {motion.name}")
    print("[visual-servo] searching")

    started_at = time.monotonic()
    stable_count = 0
    pickup_count = 0
    ignore_cooldown = 0
    active_prediction = None
    last_log_at = 0.0

    try:
        while time.monotonic() - started_at < args.max_seconds:
            frame = camera.read()
            detections = detector.detect(frame)

            if not detections:
                stable_count = 0
                pickup_count = 0
                if active_prediction is None:
                    motion.translate(0, args.search_y_speed)
                    if time.monotonic() - last_log_at >= 1.0:
                        print("[visual-servo] no object visible; slow search forward")
                        last_log_at = time.monotonic()
                else:
                    motion.stop()
                    if time.monotonic() - last_log_at >= 1.0:
                        print("[visual-servo] target lost after classification; stopping")
                        last_log_at = time.monotonic()
                time.sleep(args.poll_seconds)
                continue

            detection = detections[0]
            stable_count += 1
            geometry = detection_geometry(frame, detection, args)
            x_speed, y_speed = command_from_geometry(geometry, args)

            if ignore_cooldown > 0:
                ignore_cooldown -= 1
                motion.translate(0, args.search_y_speed)
                print(
                    "[visual-servo] ignored object cooldown; "
                    f"remaining={ignore_cooldown}"
                )
                time.sleep(args.poll_seconds)
                continue

            if stable_count < args.stable_frames:
                motion.translate(0, 0)
                print(
                    "[visual-servo] stabilizing "
                    f"{stable_count}/{args.stable_frames} "
                    f"conf={detection.confidence:.3f} box={detection.xyxy}"
                )
                time.sleep(args.poll_seconds)
                continue

            if active_prediction is None:
                motion.stop()
                detected_at = datetime.now().isoformat(timespec="seconds")
                crop = crop_detection(frame, detection)
                active_prediction = classifier.predict(crop)
                text = (
                    f"{detection.label} {detection.confidence:.2f} "
                    f"{active_prediction.label} {active_prediction.confidence:.2f}"
                )
                save_debug_frame(args.debug_frame_dir, frame, detection, geometry, text)
                print(
                    f"[{detected_at}] classified {active_prediction.label.title()} "
                    f"confidence={active_prediction.confidence:.3f} "
                    f"prompt={active_prediction.prompt!r}"
                )
                print(f"[{detected_at}] scores={active_prediction.scores}")

                if active_prediction.label == "ignore":
                    print(f"[{detected_at}] ignore label; continuing search")
                    active_prediction = None
                    stable_count = 0
                    pickup_count = 0
                    ignore_cooldown = args.ignore_cooldown_frames
                    time.sleep(args.poll_seconds)
                    continue

                print(
                    f"[{detected_at}] {active_prediction.label} object; "
                    "approaching pickup zone"
                )

            ready = is_pickup_ready(geometry, args)
            pickup_count = pickup_count + 1 if ready else 0

            print(
                "[visual-servo] "
                f"target={active_prediction.label} "
                f"conf={detection.confidence:.3f} "
                f"x_err={geometry['x_error_ratio']:.3f} "
                f"bottom_err={geometry['bottom_error_ratio']:.3f} "
                f"cmd=({x_speed:.1f},{y_speed:.1f}) "
                f"pickup={pickup_count}/{args.pickup_frames}"
            )

            if pickup_count >= args.pickup_frames:
                motion.stop()
                detected_at = datetime.now().isoformat(timespec="seconds")
                text = (
                    f"{detection.label} {detection.confidence:.2f} "
                    f"{active_prediction.label} {active_prediction.confidence:.2f} "
                    f"xerr={geometry['x_error_ratio']:.2f} "
                    f"berr={geometry['bottom_error_ratio']:.2f}"
                )
                save_debug_frame(args.debug_frame_dir, frame, detection, geometry, text)
                print(
                    f"[{detected_at}] stopped on {detection.label} "
                    f"confidence={detection.confidence:.3f} box={detection.xyxy}"
                )
                print(
                    f"[{detected_at}] target classification "
                    f"{active_prediction.label.title()} "
                    f"confidence={active_prediction.confidence:.3f} "
                    f"prompt={active_prediction.prompt!r}"
                )
                print(f"[{detected_at}] scores={active_prediction.scores}")

                if args.grab:
                    arm = KinematicsArm()
                    if args.use_camera_transform:
                        coordinate = arm.pixel_to_arm_coordinate(
                            geometry["center_x"],
                            geometry["bottom_y"],
                            (geometry["width"], geometry["height"]),
                            z=args.grab_z_cm,
                        )
                    else:
                        coordinate = ArmCoordinate(
                            args.grab_x_cm,
                            args.grab_y_cm,
                            args.grab_z_cm,
                        )
                    print(f"[{detected_at}] grabbing at {coordinate}")
                    arm.grab_at(coordinate)

                return 0

            motion.translate(x_speed, y_speed)
            save_debug_frame(args.debug_frame_dir, frame, detection, geometry, "tracking")
            time.sleep(args.poll_seconds)

        motion.stop()
        print("[visual-servo] timed out without reaching pickup zone")
        return 0
    finally:
        motion.stop()


if __name__ == "__main__":
    raise SystemExit(main())
