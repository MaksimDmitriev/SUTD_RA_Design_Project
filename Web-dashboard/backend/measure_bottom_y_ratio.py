import argparse
import json
import math
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
        "--project-floor",
        action="store_true",
        help=(
            "Project the YOLO box bottom-center pixel onto the floor plane and "
            "print estimated robot-frame x/y coordinates."
        ),
    )
    parser.add_argument(
        "--camera-height-cm",
        type=float,
        default=None,
        help="Camera optical-center height above the floor in cm.",
    )
    parser.add_argument(
        "--camera-pitch-down-deg",
        type=float,
        default=None,
        help=(
            "Camera optical-axis downward tilt from horizontal in degrees. "
            "0 means looking straight forward, 90 means looking straight down."
        ),
    )
    parser.add_argument(
        "--camera-forward-offset-cm",
        type=float,
        default=0.0,
        help="Camera optical-center offset forward from the robot reference point.",
    )
    parser.add_argument(
        "--camera-right-offset-cm",
        type=float,
        default=0.0,
        help="Camera optical-center offset right from the robot centerline.",
    )
    parser.add_argument(
        "--camera-yaw-deg",
        type=float,
        default=0.0,
        help="Optional camera yaw correction in degrees. Positive rotates right.",
    )
    parser.add_argument(
        "--camera-hfov-deg",
        type=float,
        default=62.0,
        help=(
            "Horizontal field of view used to estimate focal length when "
            "--camera-fx-px is not provided."
        ),
    )
    parser.add_argument(
        "--camera-vfov-deg",
        type=float,
        default=None,
        help=(
            "Vertical field of view used to estimate focal length. If omitted, "
            "it is derived from --camera-hfov-deg and frame aspect ratio."
        ),
    )
    parser.add_argument("--camera-fx-px", type=float, default=None)
    parser.add_argument("--camera-fy-px", type=float, default=None)
    parser.add_argument("--camera-cx-px", type=float, default=None)
    parser.add_argument("--camera-cy-px", type=float, default=None)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print one JSON object instead of human-readable lines.",
    )
    args = parser.parse_args()
    if args.project_floor and (
        args.camera_height_cm is None or args.camera_pitch_down_deg is None
    ):
        parser.error(
            "--project-floor requires --camera-height-cm and "
            "--camera-pitch-down-deg"
        )
    return args


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


def add_floor_projection(args, measurement: dict) -> None:
    if not args.project_floor:
        return
    x1, _y1, x2, y2 = measurement["xyxy"]
    bottom_center_x = (x1 + x2) / 2.0
    projection = project_pixel_to_floor(
        args,
        bottom_center_x,
        y2,
        measurement["frame_width"],
        measurement["frame_height"],
    )
    if projection is None:
        measurement["floor_projection_ok"] = False
        return
    measurement["floor_projection_ok"] = True
    measurement.update(projection)


def camera_intrinsics_from_args(args, width: int, height: int) -> tuple[float, float, float, float]:
    cx = args.camera_cx_px if args.camera_cx_px is not None else width / 2.0
    cy = args.camera_cy_px if args.camera_cy_px is not None else height / 2.0

    if args.camera_fx_px is not None:
        fx = args.camera_fx_px
    else:
        hfov = math.radians(args.camera_hfov_deg)
        fx = width / (2.0 * math.tan(hfov / 2.0))

    if args.camera_fy_px is not None:
        fy = args.camera_fy_px
    else:
        if args.camera_vfov_deg is None:
            vfov = 2.0 * math.atan(math.tan(math.radians(args.camera_hfov_deg) / 2.0) * (height / width))
        else:
            vfov = math.radians(args.camera_vfov_deg)
        fy = height / (2.0 * math.tan(vfov / 2.0))

    return fx, fy, cx, cy


def rotate_yaw(vector: tuple[float, float, float], yaw_deg: float) -> tuple[float, float, float]:
    if abs(yaw_deg) < 1e-9:
        return vector
    x, y, z = vector
    yaw = math.radians(yaw_deg)
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    return (
        x * cos_yaw + y * sin_yaw,
        -x * sin_yaw + y * cos_yaw,
        z,
    )


def project_pixel_to_floor(
    args,
    u: float,
    v: float,
    width: int,
    height: int,
) -> dict | None:
    if args.camera_height_cm is None or args.camera_pitch_down_deg is None:
        raise ValueError(
            "--project-floor requires --camera-height-cm and "
            "--camera-pitch-down-deg"
        )

    fx, fy, cx, cy = camera_intrinsics_from_args(args, width, height)

    # Camera coordinates follow OpenCV convention: x right, y down, z forward.
    ray_cam_x = (u - cx) / fx
    ray_cam_y = (v - cy) / fy
    ray_cam_z = 1.0

    pitch = math.radians(args.camera_pitch_down_deg)

    # Robot coordinates: x right, y forward, z up.
    # With zero pitch, camera z points forward and camera y points down.
    ray_robot_x = ray_cam_x
    ray_robot_y = ray_cam_z * math.cos(pitch) - ray_cam_y * math.sin(pitch)
    ray_robot_z = -ray_cam_z * math.sin(pitch) - ray_cam_y * math.cos(pitch)
    ray_robot_x, ray_robot_y, ray_robot_z = rotate_yaw(
        (ray_robot_x, ray_robot_y, ray_robot_z),
        args.camera_yaw_deg,
    )

    if ray_robot_z >= -1e-6:
        return None

    scale = args.camera_height_cm / -ray_robot_z
    floor_x = args.camera_right_offset_cm + scale * ray_robot_x
    floor_y = args.camera_forward_offset_cm + scale * ray_robot_y
    floor_distance = math.hypot(floor_x, floor_y)

    return {
        "floor_x_cm": floor_x,
        "floor_y_cm": floor_y,
        "floor_distance_cm": floor_distance,
        "camera_height_cm": args.camera_height_cm,
        "camera_pitch_down_deg": args.camera_pitch_down_deg,
        "camera_forward_offset_cm": args.camera_forward_offset_cm,
        "camera_right_offset_cm": args.camera_right_offset_cm,
        "camera_yaw_deg": args.camera_yaw_deg,
        "camera_fx_px": fx,
        "camera_fy_px": fy,
        "camera_cx_px": cx,
        "camera_cy_px": cy,
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
    if measurement.get("floor_projection_ok"):
        text += (
            f" x={measurement['floor_x_cm']:.1f}cm"
            f" y={measurement['floor_y_cm']:.1f}cm"
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

    floor_measurements = [
        item for item in measurements if item.get("floor_projection_ok")
    ]
    if floor_measurements:
        averaged["floor_projection_ok"] = True
        averaged["floor_samples"] = len(floor_measurements)
        for key in [
            "floor_x_cm",
            "floor_y_cm",
            "floor_distance_cm",
            "camera_height_cm",
            "camera_pitch_down_deg",
            "camera_forward_offset_cm",
            "camera_right_offset_cm",
            "camera_yaw_deg",
            "camera_fx_px",
            "camera_fy_px",
            "camera_cx_px",
            "camera_cy_px",
        ]:
            averaged[key] = (
                sum(item[key] for item in floor_measurements)
                / len(floor_measurements)
            )
    else:
        averaged["floor_projection_ok"] = False
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
            add_floor_projection(args, measurement)
            measurements.append(measurement)
            last_frame = frame
            if not args.json:
                line = (
                    f"sample={len(measurements)} "
                    f"label={measurement['label']} "
                    f"conf={measurement['confidence']:.3f} "
                    f"bottom_y_ratio={measurement['bottom_y_ratio']:.4f} "
                    f"center_x_ratio={measurement['center_x_ratio']:.4f} "
                    f"xyxy={measurement['xyxy']}"
                )
                if measurement.get("floor_projection_ok"):
                    line += (
                        f" floor_x_cm={measurement['floor_x_cm']:.2f}"
                        f" floor_y_cm={measurement['floor_y_cm']:.2f}"
                        f" floor_distance_cm={measurement['floor_distance_cm']:.2f}"
                    )
                elif args.project_floor:
                    line += " floor_projection=not_intersecting_floor"
                print(line)
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
        if result.get("floor_projection_ok"):
            print(f"floor_samples={result['floor_samples']}")
            print(f"floor_x_cm={result['floor_x_cm']:.2f}")
            print(f"floor_y_cm={result['floor_y_cm']:.2f}")
            print(f"floor_distance_cm={result['floor_distance_cm']:.2f}")
        elif args.project_floor:
            print("floor_projection=not_intersecting_floor")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
