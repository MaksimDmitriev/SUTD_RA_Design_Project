import argparse
import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2

from camera import Camera
from contrast_detector import ContrastBlobDetector
from robot_ik import ArmCoordinate, KinematicsArm
from robot_constants import RobotConstants
from robot_motion import create_motion_backend
from yolo_detector import Detection, YoloDetector, crop_detection
from measure_bottom_y_ratio import project_pixel_to_floor


@dataclass
class TargetPrediction:
    label: str
    confidence: float
    prompt: str
    scores: dict[str, float]


HOME_SERVO_POSES: dict[str, list[tuple[int, int]]] = {
    # Measured from the MasterPi app after positioning the arm in the desired
    # camera-home pose. Keep ID1/gripper fully open at pulse 2500.
    "my_home": list(RobotConstants.HOME_SERVO_PULSES),
}

# Fixed settings for the robot's calibrated detection-and-pickup workflow.
# These are deliberately not CLI options so normal runs remain repeatable.
# Detection stack and model deployed on the robot.
DEFAULT_DETECTOR = "yolo"
DEFAULT_CLASSIFICATION_MODE = "detector-label"
# Calibrated chassis and arm behavior.
DEFAULT_APPROACH_MODE = "floor-distance"
DEFAULT_DISTANCE_DRIVE_SPEED = 24.0
# Maximum time allowed for the camera search and chassis approach loop.
DEFAULT_MAX_RUN_SECONDS = 25.0
# Measured forward speed on the real floor when distance-drive speed is 24.
CALIBRATED_DISTANCE_DRIVE_CM_PER_SECOND = 19.0
# Consecutive detections required before the target is accepted.
DEFAULT_STABLE_DETECTION_FRAMES = 2
# Consecutive pickup-ready observations required before finishing the approach.
DEFAULT_PICKUP_READY_FRAMES = 1
# Refine the arm's x/y grab position from camera feedback before descending.
DEFAULT_ARM_VISUAL_ALIGNMENT = True
# Keep timestamped diagnostic frames and one dashboard-friendly latest frame.
DEFAULT_DEBUG_FRAME_DIRECTORY = "~/Web-dashboard/data/debug_detections"
DEFAULT_DEBUG_LATEST_FRAME = f"{DEFAULT_DEBUG_FRAME_DIRECTORY}/latest.jpg"

FLOOR_DISTANCE_FINAL_OVERSHOOT_CM = 2.5
# Move ID4 to the basket-safe height before rotating toward either basket.
# Keeping this separate from the ID6 rotation prevents the end effector from
# dipping into the basket while both servos interpolate to the drop pose.
POST_GRAB_WRIST_POSE: list[tuple[int, int]] = [(4, 1500), (5, 1500)]
POST_GRAB_TRASH_POSE: list[tuple[int, int]] = [(3, 500), (4, 1500), (6, 2500)]
POST_GRAB_USEFUL_POSE: list[tuple[int, int]] = [(3, 500), (4, 1500), (6, 500)]
POST_GRAB_GRIPPER_OPEN_PULSE = 2500
POST_GRAB_HOME_POSE: list[tuple[int, int]] = list(RobotConstants.HOME_SERVO_PULSES)

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Use visual servoing to center and approach an object, then classify the "
            "crop. Optional grabbing uses MasterPi inverse kinematics."
        )
    )
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--contrast-min-area", type=float, default=45.0)
    parser.add_argument("--contrast-max-area-ratio", type=float, default=0.04)
    parser.add_argument("--contrast-lab-delta", type=float, default=45.0)
    parser.add_argument("--contrast-min-saturation", type=int, default=55)
    parser.add_argument("--contrast-dark-value", type=int, default=70)
    parser.add_argument("--contrast-max-colored-value", type=int, default=245)
    parser.add_argument("--contrast-use-lab", action="store_true")
    parser.add_argument(
        "--contrast-color-mode",
        choices=["blue", "all"],
        default="blue",
        help="Use blue to detect only blue objects. Use all for the old saturated/dark foreground detector.",
    )
    parser.add_argument("--contrast-blue-hue-min", type=int, default=90)
    parser.add_argument("--contrast-blue-hue-max", type=int, default=135)
    parser.add_argument("--contrast-blue-min-saturation", type=int, default=50)
    parser.add_argument("--contrast-blue-min-value", type=int, default=35)
    parser.add_argument("--contrast-blue-max-value", type=int, default=255)
    parser.add_argument("--contrast-process-width", type=int, default=320)
    parser.add_argument("--contrast-roi-top-ratio", type=float, default=0.15)
    parser.add_argument("--contrast-roi-bottom-ratio", type=float, default=0.82)
    parser.add_argument("--contrast-max-box-width-ratio", type=float, default=0.38)
    parser.add_argument("--contrast-max-box-height-ratio", type=float, default=0.34)
    parser.add_argument("--contrast-box-padding-ratio", type=float, default=0.25)
    parser.add_argument("--poll-seconds", type=float, default=0.12)
    parser.add_argument(
        "--motion",
        choices=["dry-run"],
        default="auto",
        help="Use --motion dry-run to test without commanding the chassis.",
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
        help="Stop when the bottom of the detected object box reaches this frame height ratio.",
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
    parser.add_argument(
        "--close-bottom-error-ratio",
        type=float,
        default=0.0,
        help=(
            "When bottom error is at or below this value, stop lateral correction. "
            "0 means the object box has reached the target bottom line."
        ),
    )
    parser.add_argument(
        "--post-pickup-drive-seconds",
        type=float,
        default=0.0,
        help=(
            "After the existing pickup-zone condition is reached, keep driving "
            "strictly forward for this many seconds before stopping/grabbing. "
            "Deprecated; use 0. The distance approach ignores this option."
        ),
    )
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
        help=(
            "Forward translate speed during ignored-object cooldown. No-object "
            "search uses --speed with the forward motion command."
        ),
    )
    parser.add_argument("--max-x-speed", type=float, default=18.0)
    parser.add_argument("--max-y-speed", type=float, default=16.0)
    parser.add_argument(
        "--min-x-speed",
        type=float,
        default=0.0,
        help="Minimum sideways correction speed while the object is outside the x deadband.",
    )
    parser.add_argument(
        "--min-y-speed",
        type=float,
        default=4.0,
        help="Minimum forward approach speed while the object is not yet in the pickup zone.",
    )
    parser.add_argument(
        "--uncentered-y-scale",
        type=float,
        default=0.35,
        help=(
            "Forward speed multiplier while the object is outside the horizontal "
            "deadband. Use 0 to center first, then advance."
        ),
    )
    parser.add_argument(
        "--invert-x-control",
        action="store_true",
        help="Reverse left/right correction if the object moves farther from center.",
    )
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
        "--grab",
        dest="grab",
        action="store_true",
        help="Run the IK grab sequence after reaching the pickup zone.",
    )
    parser.add_argument(
        "--no-grab",
        dest="grab",
        action="store_false",
        help="Stop in the pickup zone without moving the arm.",
    )
    parser.add_argument(
        "--use-camera-transform",
        action="store_true",
        help="Convert detected pixel position to arm coordinates using MasterPi calibration.",
    )
    parser.add_argument(
        "--home-arm-only",
        action="store_true",
        help="Move the arm to the configured home coordinate and exit without driving.",
    )
    parser.add_argument(
        "--home-pose",
        choices=["ik", *HOME_SERVO_POSES.keys()],
        default="my_home",
        help=(
            "Startup arm pose used before every run and by --home-arm-only. "
            "ik uses --grab-home-x/y/z; my_home replays measured servo pulses."
        ),
    )
    parser.add_argument(
        "--home-servo4-angle",
        type=int,
        default=None,
        help=(
            "Optional raw servo-4 angle to apply after IK homing, before visual "
            "servoing. Use this to tune the camera/arm startup pose."
        ),
    )
    parser.add_argument(
        "--home-servo4-pulse",
        type=int,
        default=None,
        help=(
            "Optional raw servo-4 PWM pulse to apply after IK homing. This overrides "
            "--home-servo4-angle when both are provided."
        ),
    )
    parser.add_argument("--home-servo4-duration", type=float, default=0.5)
    parser.set_defaults(grab=True)
    parser.add_argument("--grab-x-cm", type=float, default=0.0)
    parser.add_argument("--grab-y-cm", type=float, default=12.0)
    parser.add_argument("--grab-z-cm", type=float, default=0)
    parser.add_argument("--grab-home-x-cm", type=float, default=0.0)
    parser.add_argument("--grab-home-y-cm", type=float, default=6.0)
    parser.add_argument("--grab-home-z-cm", type=float, default=18.0)
    parser.add_argument("--grab-lift-cm", type=float, default=6.0)
    parser.add_argument("--grab-min-approach-z-cm", type=float, default=8.0)
    parser.add_argument("--grab-pitch", type=float, default=-90.0)
    parser.add_argument("--grab-pitch-min", type=float, default=-90.0)
    parser.add_argument("--grab-pitch-max", type=float, default=0.0)
    parser.add_argument(
        "--arm-align-target-x-ratio",
        type=float,
        default=0.50,
        help="Desired object center x ratio during arm visual alignment.",
    )
    parser.add_argument(
        "--arm-align-target-y-ratio",
        type=float,
        default=0.55,
        help="Desired object center y ratio during arm visual alignment.",
    )
    parser.add_argument(
        "--arm-align-deadband-ratio",
        type=float,
        default=0.08,
        help="Allowed image error during arm visual alignment.",
    )
    parser.add_argument(
        "--arm-align-max-steps",
        type=int,
        default=6,
        help="Maximum arm visual-alignment nudges before grabbing anyway.",
    )
    parser.add_argument(
        "--arm-align-step-cm",
        type=float,
        default=0.4,
        help="Maximum x/y arm-coordinate nudge per visual-alignment step.",
    )
    parser.add_argument(
        "--arm-align-kp-cm",
        type=float,
        default=4.0,
        help="Arm visual-alignment proportional gain in cm per image-ratio error.",
    )
    parser.add_argument(
        "--arm-align-frame-tries",
        type=int,
        default=5,
        help="Camera frames to try for each arm visual-alignment observation.",
    )
    parser.add_argument(
        "--arm-align-settle-seconds",
        type=float,
        default=0.15,
        help="Delay after each arm nudge before reading the next camera frame.",
    )
    parser.add_argument(
        "--invert-arm-align-x",
        action="store_true",
        help="Reverse x-coordinate nudges during arm visual alignment.",
    )
    parser.add_argument(
        "--invert-arm-align-y",
        action="store_true",
        help="Reverse y-coordinate nudges during arm visual alignment.",
    )
    parser.add_argument("--gripper-open-pulse", type=int, default=2500)
    parser.add_argument("--gripper-close-pulse", type=int, default=1500)
    parser.add_argument(
        "--distance-reliable-cm",
        type=float,
        default=30.0,
        help=(
            "For floor-distance approach, trust the projected floor "
            "distance as final only when the object is at or below this y distance."
        ),
    )
    parser.add_argument(
        "--distance-far-step-fraction",
        type=float,
        default=0.5,
        help=(
            "For floor-distance approach, when the object is outside the "
            "reliable range, drive this fraction of the projected y distance and "
            "then remeasure."
        ),
    )
    parser.add_argument(
        "--distance-max-step-cm",
        type=float,
        default=25.0,
        help="Maximum single forward move in cm for floor-distance approach.",
    )
    parser.add_argument(
        "--distance-min-step-cm",
        type=float,
        default=2.0,
        help=(
            "If the remaining floor-distance move is below this value, stop and "
            "grab instead of trying to command a tiny chassis move."
        ),
    )
    parser.set_defaults(distance_heading_correction=True)
    parser.add_argument(
        "--no-distance-heading-correction",
        dest="distance_heading_correction",
        action="store_false",
        help=(
            "Disable floor_x_cm heading correction for floor-distance approach."
        ),
    )
    parser.add_argument(
        "--distance-heading-deadband-cm",
        type=float,
        default=5.0,
        help=(
            "Ignore floor_x_cm while its absolute value is at or below this "
            "distance."
        ),
    )
    parser.add_argument(
        "--distance-heading-min-y-cm",
        type=float,
        default=8.0,
        help="Do not rotate from floor_x_cm when the object is closer than this.",
    )
    parser.add_argument(
        "--distance-heading-max-y-cm",
        type=float,
        default=50.0,
        help="Only use floor_x_cm heading correction inside this floor_y_cm range.",
    )
    parser.add_argument(
        "--distance-heading-max-deg",
        type=float,
        default=12.0,
        help="Maximum single heading correction angle in degrees.",
    )
    parser.add_argument(
        "--distance-heading-yaw-rate",
        type=float,
        default=0.14,
        help=(
            "Hiwonder yaw angular speed for heading correction. The SDK range is "
            "roughly -2..2."
        ),
    )
    parser.add_argument(
        "--distance-heading-deg-per-second",
        type=float,
        default=45.0,
        help=(
            "Measured robot turn rate for --distance-heading-yaw-rate. The script "
            "uses angle_deg / this value to choose turn time."
        ),
    )
    parser.add_argument(
        "--invert-distance-heading",
        action="store_true",
        help="Reverse heading correction if the robot turns away from the object.",
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
        "--camera-vfov-deg",
        type=float,
        default=None,
        help=(
            "Vertical field of view. If omitted, it is derived from "
            "the fixed horizontal field of view and frame aspect ratio."
        ),
    )
    parser.add_argument("--camera-fx-px", type=float, default=None)
    parser.add_argument("--camera-fy-px", type=float, default=None)
    parser.add_argument("--camera-cx-px", type=float, default=None)
    parser.add_argument("--camera-cy-px", type=float, default=None)
    parser.set_defaults(
        detector=DEFAULT_DETECTOR,
        model=RobotConstants.MODEL_PATH,
        approach_mode=DEFAULT_APPROACH_MODE,
        home_servo_duration=RobotConstants.HOME_SERVO_DURATION_SECONDS,
        distance_drive_speed=DEFAULT_DISTANCE_DRIVE_SPEED,
        camera_height_cm=RobotConstants.CAMERA_HEIGHT_CM,
        camera_pitch_down_deg=RobotConstants.CAMERA_PITCH_DOWN_DEG,
        camera_hfov_deg=RobotConstants.CAMERA_HORIZONTAL_FOV_DEG,
        max_seconds=DEFAULT_MAX_RUN_SECONDS,
        conf=RobotConstants.YOLO_CONFIDENCE,
        distance_drive_cm_per_second=CALIBRATED_DISTANCE_DRIVE_CM_PER_SECOND,
        stable_frames=DEFAULT_STABLE_DETECTION_FRAMES,
        pickup_frames=DEFAULT_PICKUP_READY_FRAMES,
        arm_visual_align=DEFAULT_ARM_VISUAL_ALIGNMENT,
        debug_frame_dir=DEFAULT_DEBUG_FRAME_DIRECTORY,
        debug_latest_frame=DEFAULT_DEBUG_LATEST_FRAME,
    )
    return parser.parse_args()


def create_arm(args) -> KinematicsArm:
    return KinematicsArm(
        open_pulse=args.gripper_open_pulse,
        close_pulse=args.gripper_close_pulse,
        home=ArmCoordinate(
            args.grab_home_x_cm,
            args.grab_home_y_cm,
            args.grab_home_z_cm,
        ),
        approach_lift_cm=args.grab_lift_cm,
        min_approach_z_cm=args.grab_min_approach_z_cm,
    )


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
    centered = abs(x_error) <= args.x_deadband_ratio

    if bottom_error <= args.close_bottom_error_ratio:
        return 0.0, 0.0

    if centered:
        x_speed = 0.0
    else:
        # Positive x moves the chassis right in the Hiwonder movement API.
        x_speed = clamp(args.kp_x * x_error, -args.max_x_speed, args.max_x_speed)
        if args.min_x_speed > 0:
            if x_speed < 0:
                x_speed = min(x_speed, -args.min_x_speed)
            else:
                x_speed = max(x_speed, args.min_x_speed)
        if args.invert_x_control:
            x_speed = -x_speed

    if bottom_error <= args.bottom_deadband_ratio:
        y_speed = 0.0
    else:
        # Positive y moves forward. Move slower as the object reaches the pickup line.
        y_speed = clamp(args.kp_y * bottom_error, args.min_y_speed, args.max_y_speed)
        if not centered:
            y_speed *= clamp(args.uncentered_y_scale, 0.0, 1.0)

    return x_speed, y_speed


def is_pickup_ready(geometry: dict, args) -> bool:
    if geometry["bottom_error_ratio"] > args.bottom_deadband_ratio:
        return False

    return abs(geometry["x_error_ratio"]) <= args.x_deadband_ratio


def floor_projection_from_detection(args, frame, detection: Detection) -> dict | None:
    height, width = frame.shape[:2]
    x1, _y1, x2, y2 = detection.xyxy
    bottom_center_x = (x1 + x2) / 2.0
    return project_pixel_to_floor(args, bottom_center_x, y2, width, height)


def distance_approach_move_cm(projection: dict, args) -> tuple[float, str, bool]:
    floor_y = projection["floor_y_cm"]
    if floor_y <= args.distance_min_step_cm:
        return 0.0, "inside final window", True

    finishes_approach = False
    if floor_y <= args.distance_reliable_cm:
        move_cm = floor_y + FLOOR_DISTANCE_FINAL_OVERSHOOT_CM
        reason = "reliable final move"
        finishes_approach = True
    else:
        fraction = clamp(args.distance_far_step_fraction, 0.05, 0.95)
        move_cm = clamp(
            min(
                floor_y * fraction,
                floor_y - args.distance_reliable_cm,
            ),
            0.0,
            args.distance_max_step_cm,
        )
        reason = "far partial move"
        if move_cm < args.distance_min_step_cm:
            move_cm = floor_y + FLOOR_DISTANCE_FINAL_OVERSHOOT_CM
            reason = "near reliable boundary; final move"
            finishes_approach = True

    if move_cm < args.distance_min_step_cm:
        return 0.0, f"{reason}; below min step", finishes_approach
    return move_cm, reason, finishes_approach


def drive_forward_for_distance(motion, move_cm: float, speed: float, cm_per_second: float) -> float:
    if move_cm <= 0:
        return 0.0
    if cm_per_second <= 0:
        raise ValueError("distance drive calibration must be greater than 0 cm/s")
    duration_seconds = move_cm / cm_per_second
    motion.translate(0.0, speed)
    time.sleep(duration_seconds)
    motion.stop()
    return duration_seconds


def heading_correction_from_projection(projection: dict, args) -> tuple[float, str]:
    if not args.distance_heading_correction:
        return 0.0, "disabled"

    floor_x = projection["floor_x_cm"]
    floor_y = projection["floor_y_cm"]
    if floor_y < args.distance_heading_min_y_cm:
        return 0.0, "object too close for heading correction"
    if floor_y > args.distance_heading_max_y_cm:
        return 0.0, "object too far for heading correction"
    if abs(floor_x) <= args.distance_heading_deadband_cm:
        return 0.0, "floor_x inside heading deadband"

    raw_angle_deg = math.degrees(math.atan2(floor_x, max(floor_y, 1e-6)))
    angle_deg = clamp(
        raw_angle_deg,
        -abs(args.distance_heading_max_deg),
        abs(args.distance_heading_max_deg),
    )
    if args.invert_distance_heading:
        angle_deg = -angle_deg

    return angle_deg, f"alpha={raw_angle_deg:.1f}deg"


def rotate_for_heading_correction(
    motion,
    angle_deg: float,
    yaw_rate: float,
    deg_per_second: float,
) -> float:
    if abs(angle_deg) <= 1e-3:
        return 0.0
    if deg_per_second <= 0:
        raise ValueError("--distance-heading-deg-per-second must be greater than 0")
    duration_seconds = abs(angle_deg) / deg_per_second
    signed_yaw_rate = math.copysign(abs(yaw_rate), angle_deg)
    motion.rotate(signed_yaw_rate)
    time.sleep(duration_seconds)
    motion.stop()
    return duration_seconds


def coordinate_above_grab(arm: KinematicsArm, coordinate: ArmCoordinate) -> ArmCoordinate:
    return ArmCoordinate(
        coordinate.x,
        coordinate.y,
        max(coordinate.z + arm.approach_lift_cm, arm.min_approach_z_cm),
    )


def post_grab_pose_for_label(label: str) -> list[tuple[int, int]]:
    if "trash" in label.lower():
        return POST_GRAB_TRASH_POSE
    return POST_GRAB_USEFUL_POSE


def release_and_return_home_after_grab(
    args,
    arm: KinematicsArm,
    target_label: str,
) -> None:
    drop_pose = post_grab_pose_for_label(target_label)
    print(
        "[visual-servo] post-grab wrist pose "
        f"{POST_GRAB_WRIST_POSE}"
    )
    arm.set_servo_pulses(
        POST_GRAB_WRIST_POSE,
        duration_seconds=args.home_servo_duration,
    )
    print(
        "[visual-servo] post-grab drop pose for "
        f"{target_label}: {drop_pose}"
    )
    arm.set_servo_pulses(
        drop_pose,
        duration_seconds=args.home_servo_duration,
    )
    print("[visual-servo] releasing gripper")
    arm.set_servo_pulse(
        1,
        POST_GRAB_GRIPPER_OPEN_PULSE,
        duration_seconds=0.5,
    )
    print(
        "[visual-servo] returning arm to camera home servo pose "
        f"{POST_GRAB_HOME_POSE}"
    )
    arm.set_servo_pulses(
        POST_GRAB_HOME_POSE,
        duration_seconds=args.home_servo_duration,
    )


def best_detection_for_alignment(
    detections: list[Detection],
    target_label: str,
    approach_labels: set[str],
) -> Detection | None:
    matching = [
        detection
        for detection in detections
        if detection.label.lower() == target_label.lower()
    ]
    if matching:
        return matching[0]

    acceptable = [
        detection
        for detection in detections
        if detection.label.lower() in approach_labels
    ]
    if acceptable:
        return acceptable[0]

    return None


def read_alignment_detection(
    camera: Camera,
    detector,
    target_label: str,
    approach_labels: set[str],
    frame_tries: int,
) -> tuple[object | None, Detection | None, dict | None]:
    attempts = max(1, frame_tries)
    for _ in range(attempts):
        frame = camera.read()
        detections = detector.detect(frame)
        detection = best_detection_for_alignment(detections, target_label, approach_labels)
        if detection is None:
            continue
        geometry = detection_geometry_for_alignment(frame, detection)
        return frame, detection, geometry
    return None, None, None


def detection_geometry_for_alignment(frame, detection: Detection) -> dict:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = detection.xyxy
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    return {
        "width": width,
        "height": height,
        "center_x": center_x,
        "center_y": center_y,
        "x_ratio": center_x / width,
        "y_ratio": center_y / height,
    }


def visually_align_arm(
    args,
    camera: Camera,
    detector,
    arm: KinematicsArm,
    coordinate: ArmCoordinate,
    target_label: str,
    approach_labels: set[str],
) -> ArmCoordinate:
    aligned = ArmCoordinate(coordinate.x, coordinate.y, coordinate.z)
    above = coordinate_above_grab(arm, aligned)
    print(f"[visual-servo] arm visual align: moving above {above}")
    arm.move_to(
        above,
        pitch=args.grab_pitch,
        pitch_min=args.grab_pitch_min,
        pitch_max=args.grab_pitch_max,
        move_time_ms=800,
    )
    time.sleep(args.arm_align_settle_seconds)

    x_sign = -1.0 if args.invert_arm_align_x else 1.0
    y_sign = -1.0 if args.invert_arm_align_y else 1.0

    for step_index in range(max(0, args.arm_align_max_steps)):
        frame, detection, geometry = read_alignment_detection(
            camera,
            detector,
            target_label,
            approach_labels,
            args.arm_align_frame_tries,
        )
        if detection is None or geometry is None:
            print(
                "[visual-servo] arm visual align: no detection; "
                "using current grab coordinate"
            )
            return aligned

        x_error = geometry["x_ratio"] - args.arm_align_target_x_ratio
        y_error = geometry["y_ratio"] - args.arm_align_target_y_ratio
        print(
            "[visual-servo] arm visual align "
            f"{step_index + 1}/{args.arm_align_max_steps} "
            f"label={detection.label} conf={detection.confidence:.3f} "
            f"x_err={x_error:.3f} y_err={y_error:.3f} "
            f"coord=({aligned.x:.2f},{aligned.y:.2f},{aligned.z:.2f})"
        )

        if (
            abs(x_error) <= args.arm_align_deadband_ratio
            and abs(y_error) <= args.arm_align_deadband_ratio
        ):
            print("[visual-servo] arm visual align: target in alignment window")
            return aligned

        dx = clamp(
            args.arm_align_kp_cm * x_error * x_sign,
            -args.arm_align_step_cm,
            args.arm_align_step_cm,
        )
        dy = clamp(
            args.arm_align_kp_cm * y_error * y_sign,
            -args.arm_align_step_cm,
            args.arm_align_step_cm,
        )
        aligned = ArmCoordinate(aligned.x + dx, aligned.y + dy, aligned.z)
        above = coordinate_above_grab(arm, aligned)
        print(
            "[visual-servo] arm visual align: nudging above "
            f"({above.x:.2f},{above.y:.2f},{above.z:.2f})"
        )
        arm.move_to(
            above,
            pitch=args.grab_pitch,
            pitch_min=args.grab_pitch_min,
            pitch_max=args.grab_pitch_max,
            move_time_ms=400,
        )
        time.sleep(args.arm_align_settle_seconds)

    print("[visual-servo] arm visual align: max steps reached")
    return aligned


def grab_with_optional_alignment(
    args,
    camera: Camera,
    detector,
    arm: KinematicsArm,
    coordinate: ArmCoordinate,
    target_label: str,
    approach_labels: set[str],
) -> ArmCoordinate:
    arm.move_home()
    arm.open_gripper()

    if args.arm_visual_align:
        coordinate = visually_align_arm(
            args,
            camera,
            detector,
            arm,
            coordinate,
            target_label,
            approach_labels,
        )

    above = coordinate_above_grab(arm, coordinate)
    print(f"[visual-servo] arm grabbing from aligned coordinate {coordinate}")
    arm.move_to(
        above,
        pitch=args.grab_pitch,
        pitch_min=args.grab_pitch_min,
        pitch_max=args.grab_pitch_max,
        move_time_ms=500,
    )
    arm.move_to(
        coordinate,
        pitch=args.grab_pitch,
        pitch_min=args.grab_pitch_min,
        pitch_max=args.grab_pitch_max,
        move_time_ms=500,
    )
    arm.close_gripper()
    arm.move_to(
        above,
        pitch=args.grab_pitch,
        pitch_min=args.grab_pitch_min,
        pitch_max=args.grab_pitch_max,
        move_time_ms=800,
    )
    release_and_return_home_after_grab(args, arm, target_label)
    return coordinate


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


def save_latest_debug_frame(path: str | None, frame, detection, geometry, text: str) -> None:
    if not path:
        return
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), annotate_frame(frame, detection, geometry, text))


def finish_target(
    args,
    camera: Camera,
    detector,
    motion,
    frame,
    detection: Detection,
    geometry: dict,
    active_prediction: TargetPrediction,
    approach_labels: set[str],
    final_forward_speed: float = 0.0,
) -> int:
    if (
        args.approach_mode != "floor-distance"
        and args.post_pickup_drive_seconds > 0
        and final_forward_speed > 0.001
    ):
        print(
            "[visual-servo] pickup zone reached; final drive "
            f"{args.post_pickup_drive_seconds:.2f}s "
            f"cmd=(0.0,{final_forward_speed:.1f})"
        )
        motion.translate(0.0, final_forward_speed)
        time.sleep(args.post_pickup_drive_seconds)

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
        arm = create_arm(args)
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
        final_coordinate = grab_with_optional_alignment(
            args,
            camera,
            detector,
            arm,
            coordinate,
            active_prediction.label,
            approach_labels,
        )
        if args.arm_visual_align:
            print(
                f"[{detected_at}] arm visual align final coordinate "
                f"{final_coordinate}"
            )
    else:
        print(f"[{detected_at}] grab disabled; leaving object in pickup zone")

    return 0


def main() -> int:
    args = parse_args()
    classification_mode = DEFAULT_CLASSIFICATION_MODE
    approach_labels = set(RobotConstants.APPROACH_LABELS)

    arm = create_arm(args)
    if args.home_pose != "ik":
        positions = HOME_SERVO_POSES[args.home_pose]
        print(
            f"[visual-servo] homing arm to {args.home_pose} servo pose "
            f"{positions}"
        )
        arm.set_servo_pulses(
            positions,
            duration_seconds=args.home_servo_duration,
        )
    else:
        print(
            "[visual-servo] homing arm to "
            f"({args.grab_home_x_cm:.1f}, {args.grab_home_y_cm:.1f}, "
            f"{args.grab_home_z_cm:.1f}) before approach"
        )
        arm.move_home()
    if args.home_servo4_pulse is not None:
        print(
            "[visual-servo] setting startup servo 4 pulse "
            f"{args.home_servo4_pulse}"
        )
        arm.set_servo_pulse(
            4,
            args.home_servo4_pulse,
            duration_seconds=args.home_servo4_duration,
        )
    elif args.home_servo4_angle is not None:
        print(
            "[visual-servo] setting startup servo 4 angle "
            f"{args.home_servo4_angle}"
        )
        arm.set_servo_angle(
            4,
            args.home_servo4_angle,
            duration_seconds=args.home_servo4_duration,
        )
    if args.home_arm_only:
        print("[visual-servo] arm homed; exiting")
        return 0

    print("[visual-servo] loading camera")
    camera = Camera()
    if args.detector == "contrast":
        print(f"[visual-servo] loading {args.contrast_color_mode} contrast detector")
        detector = ContrastBlobDetector(
            min_area=args.contrast_min_area,
            max_area_ratio=args.contrast_max_area_ratio,
            lab_delta=args.contrast_lab_delta,
            min_saturation=args.contrast_min_saturation,
            max_colored_value=args.contrast_max_colored_value,
            dark_value=args.contrast_dark_value,
            use_lab_contrast=args.contrast_use_lab,
            color_mode=args.contrast_color_mode,
            blue_hue_min=args.contrast_blue_hue_min,
            blue_hue_max=args.contrast_blue_hue_max,
            blue_min_saturation=args.contrast_blue_min_saturation,
            blue_min_value=args.contrast_blue_min_value,
            blue_max_value=args.contrast_blue_max_value,
            process_width=args.contrast_process_width,
            roi_top_ratio=args.contrast_roi_top_ratio,
            roi_bottom_ratio=args.contrast_roi_bottom_ratio,
            max_box_width_ratio=args.contrast_max_box_width_ratio,
            max_box_height_ratio=args.contrast_max_box_height_ratio,
            box_padding_ratio=args.contrast_box_padding_ratio,
        )
    else:
        print("[visual-servo] loading custom YOLO detector")
        detector = YoloDetector(args.model, confidence=args.conf, image_size=args.imgsz)
    detector.load()
    classifier = None
    if classification_mode == "openclip":
        from clip_classifier import ClipClassifier

        print("[visual-servo] loading OpenCLIP classifier")
        classifier = ClipClassifier()
        classifier.load()
    else:
        print("[visual-servo] using detector labels for classification")

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
    last_forward_speed = 0.0

    try:
        while time.monotonic() - started_at < args.max_seconds:
            frame = camera.read()
            detections = detector.detect(frame)

            if not detections:
                stable_count = 0
                pickup_count = 0
                if active_prediction is None:
                    motion.forward()
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
            if active_prediction is not None:
                tracked_detection = best_detection_for_alignment(
                    detections,
                    active_prediction.label,
                    approach_labels,
                )
                if tracked_detection is None:
                    stable_count = 0
                    pickup_count = 0
                    motion.stop()
                    if time.monotonic() - last_log_at >= 1.0:
                        print(
                            "[visual-servo] target label missing after "
                            "classification; stopping"
                        )
                        last_log_at = time.monotonic()
                    time.sleep(args.poll_seconds)
                    continue
                detection = tracked_detection
            stable_count += 1
            geometry = detection_geometry(frame, detection, args)
            x_speed, y_speed = command_from_geometry(geometry, args)
            detection_text = (
                f"{detection.label} {detection.confidence:.2f} "
                f"xerr={geometry['x_error_ratio']:.2f} "
                f"berr={geometry['bottom_error_ratio']:.2f}"
            )
            save_latest_debug_frame(
                args.debug_latest_frame,
                frame,
                detection,
                geometry,
                detection_text,
            )

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
                if classification_mode == "openclip":
                    crop = crop_detection(frame, detection)
                    active_prediction = classifier.predict(crop)
                else:
                    label = detection.label.lower()
                    active_prediction = TargetPrediction(
                        label=label,
                        confidence=detection.confidence,
                        prompt="detector-label",
                        scores={label: detection.confidence},
                    )
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

                if active_prediction.label not in approach_labels:
                    print(
                        f"[{detected_at}] {active_prediction.label} label is not "
                        f"in approach labels {sorted(approach_labels)}; continuing search"
                    )
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

            if args.approach_mode == "floor-distance":
                projection = floor_projection_from_detection(args, frame, detection)
                if projection is None:
                    pickup_count = 0
                    motion.stop()
                    print(
                        "[visual-servo] floor-distance projection unavailable; "
                        "stopping and remeasuring"
                    )
                    time.sleep(args.poll_seconds)
                    continue

                move_cm, move_reason, finishes_approach = distance_approach_move_cm(
                    projection,
                    args,
                )
                ready = move_cm <= 0.0
                pickup_count = pickup_count + 1 if ready else 0
                drive_speed = args.distance_drive_speed
                print(
                    "[visual-servo] "
                    f"target={active_prediction.label} "
                    f"conf={detection.confidence:.3f} "
                    f"floor_x={projection['floor_x_cm']:.2f}cm "
                    f"floor_y={projection['floor_y_cm']:.2f}cm "
                    f"move={move_cm:.2f}cm reason={move_reason!r} "
                    f"pickup={pickup_count}/{args.pickup_frames}"
                )

                if pickup_count >= args.pickup_frames:
                    return finish_target(
                        args,
                        camera,
                        detector,
                        motion,
                        frame,
                        detection,
                        geometry,
                        active_prediction,
                        approach_labels,
                    )

                if move_cm > 0.0:
                    heading_angle_deg, heading_reason = heading_correction_from_projection(
                        projection,
                        args,
                    )
                    if abs(heading_angle_deg) > 1e-3:
                        save_debug_frame(
                            args.debug_frame_dir,
                            frame,
                            detection,
                            geometry,
                            (
                                "floor-heading "
                                f"x={projection['floor_x_cm']:.1f}cm "
                                f"y={projection['floor_y_cm']:.1f}cm "
                                f"turn={heading_angle_deg:.1f}deg"
                            ),
                        )
                        duration = rotate_for_heading_correction(
                            motion,
                            heading_angle_deg,
                            args.distance_heading_yaw_rate,
                            args.distance_heading_deg_per_second,
                        )
                        print(
                            "[visual-servo] floor-distance heading correction "
                            f"{heading_angle_deg:.2f}deg for {duration:.2f}s "
                            f"at yaw_rate={args.distance_heading_yaw_rate:.2f}; "
                            f"{heading_reason}; remeasuring"
                        )
                        stable_count = 0
                        time.sleep(0.5)
                        continue

                    save_debug_frame(
                        args.debug_frame_dir,
                        frame,
                        detection,
                        geometry,
                        (
                            "floor-distance "
                            f"y={projection['floor_y_cm']:.1f}cm "
                            f"move={move_cm:.1f}cm"
                        ),
                    )
                    duration = drive_forward_for_distance(
                        motion,
                        move_cm,
                        drive_speed,
                        args.distance_drive_cm_per_second,
                    )
                    if finishes_approach:
                        print(
                            "[visual-servo] floor-distance final move complete "
                            f"({move_cm:.2f}cm for {duration:.2f}s "
                            f"at speed={drive_speed:.1f}); "
                            "starting finish/grab sequence"
                        )
                        return finish_target(
                            args,
                            camera,
                            detector,
                            motion,
                            frame,
                            detection,
                            geometry,
                            active_prediction,
                            approach_labels,
                        )
                    print(
                        "[visual-servo] floor-distance drove forward "
                        f"{move_cm:.2f}cm for {duration:.2f}s "
                        f"at speed={drive_speed:.1f}; remeasuring"
                    )
                    stable_count = 0
                    time.sleep(args.poll_seconds)
                    continue

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
                final_forward_speed = last_forward_speed or args.min_y_speed
                return finish_target(
                    args,
                    camera,
                    detector,
                    motion,
                    frame,
                    detection,
                    geometry,
                    active_prediction,
                    approach_labels,
                    final_forward_speed=final_forward_speed,
                )

            if y_speed > 0.001:
                last_forward_speed = y_speed
            motion.translate(x_speed, y_speed)
            save_debug_frame(args.debug_frame_dir, frame, detection, geometry, "tracking")
            time.sleep(args.poll_seconds)

        motion.stop()
        print("[visual-servo] timed out without reaching pickup zone")
        return 0
    finally:
        motion.stop()
        camera.close()


if __name__ == "__main__":
    raise SystemExit(main())
