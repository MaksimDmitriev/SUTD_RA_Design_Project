"""Scan a demo room, pick visible objects, and sort them one at a time.

Unlike object_visual_servo_test.py, this workflow stays stationary while
searching. It scans front, left, and right with the arm-mounted camera, turns
the chassis toward a side detection, remeasures from the forward camera, and
then reuses the calibrated floor-distance approach. After all three views are
empty, it turns 180 degrees for one final rear check and exits successfully if
that view is also empty.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from camera import Camera
from contrast_detector import ContrastBlobDetector
from robot_constants import RobotConstants
from robot_buzzer import LoopingTunePlayer, SERA_BPM, SERA_LONG_SAMPLE
from robot_ik import ArmCoordinate, KinematicsArm
from robot_motion import create_motion_backend
from yolo_detector import Detection, YoloDetector

import object_visual_servo_test as visual_servo


FRONT = "front"
LEFT = "left"
RIGHT = "right"

SCAN_SECONDS = 2.0
TURN_YAW_RATE = 0.5
TURN_90_SECONDS = 0.47
TURN_180_SECONDS = 1.04

CAMERA_SERVO_ID = 6
CAMERA_DIRECTION_PULSES = {
    FRONT: 1480,
    LEFT: 2500,
    RIGHT: 500,
}

INITIAL_SCAN_ORDER = (FRONT, LEFT, RIGHT)


@dataclass(frozen=True)
class ScanResult:
    frame: object
    detection: Detection
    geometry: dict


def camera_scan_pose(direction: str) -> list[tuple[int, int]]:
    """Return the elevated camera-home pose facing one direction."""
    if direction not in CAMERA_DIRECTION_PULSES:
        raise ValueError(f"unknown camera direction: {direction}")

    return [
        (
            servo_id,
            CAMERA_DIRECTION_PULSES[direction]
            if servo_id == CAMERA_SERVO_ID
            else pulse,
        )
        for servo_id, pulse in RobotConstants.HOME_SERVO_PULSES
    ]


def basket_side_for_label(label: str) -> str:
    return LEFT if "trash" in label.lower() else RIGHT


def scan_order_after_sort(label: str) -> tuple[str, str, str]:
    side = basket_side_for_label(label)
    opposite = RIGHT if side == LEFT else LEFT
    return side, FRONT, opposite


def navigation_turn_spec(direction: str, degrees: int = 90) -> tuple[float, float]:
    if direction == RIGHT:
        signed_yaw_rate = +TURN_YAW_RATE
    elif direction == LEFT:
        signed_yaw_rate = -TURN_YAW_RATE
    else:
        raise ValueError("navigation turn direction must be 'left' or 'right'")

    if degrees == 90:
        duration_seconds = TURN_90_SECONDS
    elif degrees == 180:
        duration_seconds = TURN_180_SECONDS
    else:
        raise ValueError("navigation turns support only 90 or 180 degrees")
    return signed_yaw_rate, duration_seconds


def move_camera_to(args, arm: KinematicsArm, direction: str) -> None:
    pose = camera_scan_pose(direction)
    print(f"[room-sorter] camera {direction}: {pose}")
    arm.set_servo_pulses(pose, duration_seconds=args.home_servo_duration)


def turn_chassis(motion, direction: str, degrees: int = 90) -> None:
    yaw_rate, duration_seconds = navigation_turn_spec(direction, degrees)
    print(
        f"[room-sorter] chassis turn {direction} {degrees} degrees: "
        f"yaw_rate={yaw_rate:.2f} duration={duration_seconds:.2f}s"
    )
    try:
        motion.rotate(yaw_rate)
        time.sleep(duration_seconds)
    finally:
        motion.stop()


def center_camera_while_turning(
    args,
    arm: KinematicsArm,
    motion,
    direction: str,
    degrees: int = 90,
) -> None:
    """Point the camera forward while the chassis performs a calibrated turn."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        camera_move = executor.submit(move_camera_to, args, arm, FRONT)
        turn_chassis(motion, direction, degrees)
        camera_move.result()


def accepted_detection(
    detections: list[Detection],
    approach_labels: set[str],
    preferred_label: str | None = None,
) -> Detection | None:
    if preferred_label is not None:
        for detection in detections:
            if detection.label.lower() == preferred_label.lower():
                return detection
        return None

    for detection in detections:
        if detection.label.lower() in approach_labels:
            return detection

    return None


def observe_view(
    args,
    camera: Camera,
    detector,
    approach_labels: set[str],
    direction: str,
    preferred_label: str | None = None,
) -> ScanResult | None:
    """Observe one settled camera view for two seconds."""
    deadline = time.monotonic() + SCAN_SECONDS
    stable_label = None
    stable_count = 0

    print(f"[room-sorter] scanning {direction} for {SCAN_SECONDS:.1f}s")
    while time.monotonic() < deadline:
        frame = camera.read()
        detection = accepted_detection(
            detector.detect(frame),
            approach_labels,
            preferred_label=preferred_label,
        )

        if detection is None:
            stable_label = None
            stable_count = 0
            time.sleep(args.poll_seconds)
            continue

        label = detection.label.lower()
        if label == stable_label:
            stable_count += 1
        else:
            stable_label = label
            stable_count = 1

        geometry = visual_servo.detection_geometry(frame, detection, args)
        visual_servo.save_latest_debug_frame(
            args.debug_latest_frame,
            frame,
            detection,
            geometry,
            f"scan={direction} {label} {detection.confidence:.2f}",
        )
        print(
            f"[room-sorter] {direction} detection label={label} "
            f"confidence={detection.confidence:.3f} "
            f"stable={stable_count}/{args.stable_frames}"
        )

        if stable_count >= args.stable_frames:
            return ScanResult(frame, detection, geometry)

        time.sleep(args.poll_seconds)

    print(f"[room-sorter] no object found {direction}")
    return None


def scan_directions(
    args,
    camera: Camera,
    detector,
    arm: KinematicsArm,
    motion,
    approach_labels: set[str],
    directions: tuple[str, ...],
) -> tuple[str, ScanResult] | None:
    motion.stop()
    for direction in directions:
        move_camera_to(args, arm, direction)
        result = observe_view(
            args,
            camera,
            detector,
            approach_labels,
            direction,
        )
        if result is not None:
            return direction, result
    return None


def create_detector(args):
    if args.detector == "contrast":
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
        detector = YoloDetector(
            args.model,
            confidence=args.conf,
            image_size=args.imgsz,
        )
    detector.load()
    return detector


def create_music_player(arm: KinematicsArm) -> LoopingTunePlayer:
    """Use the arm's existing board connection for concurrent buzzer music."""
    return LoopingTunePlayer(
        arm.controller_board,
        SERA_LONG_SAMPLE,
        bpm=SERA_BPM,
    )


def release_into_basket_and_prepare_scan(
    args,
    arm: KinematicsArm,
    target_label: str,
) -> str:
    scan_side = basket_side_for_label(target_label)
    drop_pose = visual_servo.post_grab_pose_for_label(target_label)

    print(
        "[room-sorter] post-grab wrist pose "
        f"{visual_servo.POST_GRAB_WRIST_POSE}"
    )
    arm.set_servo_pulses(
        visual_servo.POST_GRAB_WRIST_POSE,
        duration_seconds=args.home_servo_duration,
    )
    print(f"[room-sorter] drop pose for {target_label}: {drop_pose}")
    arm.set_servo_pulses(
        drop_pose,
        duration_seconds=args.home_servo_duration,
    )
    print("[room-sorter] releasing gripper")
    arm.set_servo_pulse(
        1,
        visual_servo.POST_GRAB_GRIPPER_OPEN_PULSE,
        duration_seconds=0.5,
    )

    # Raise the arm into camera-home geometry without recentering ID6. This is
    # the first scan direction after a successful sort.
    move_camera_to(args, arm, scan_side)
    return scan_side


def grab_sort_and_prepare_scan(
    args,
    camera: Camera,
    detector,
    arm: KinematicsArm,
    coordinate: ArmCoordinate,
    target_label: str,
    approach_labels: set[str],
) -> str:
    arm.move_home()
    arm.open_gripper()

    if args.arm_visual_align:
        coordinate = visual_servo.visually_align_arm(
            args,
            camera,
            detector,
            arm,
            coordinate,
            target_label,
            approach_labels,
        )

    above = visual_servo.coordinate_above_grab(arm, coordinate)
    print(f"[room-sorter] grabbing from coordinate {coordinate}")
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
    return release_into_basket_and_prepare_scan(args, arm, target_label)


def finish_and_sort_target(
    args,
    camera: Camera,
    detector,
    arm: KinematicsArm,
    motion,
    frame,
    detection: Detection,
    geometry: dict,
    approach_labels: set[str],
) -> str | None:
    motion.stop()
    target_label = detection.label.lower()
    print(
        f"[room-sorter] pickup zone reached for {target_label} "
        f"confidence={detection.confidence:.3f}"
    )

    if not args.grab:
        print("[room-sorter] grab disabled; stopping after the first target")
        return None

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

    print(f"[room-sorter] grabbing at {coordinate}")
    grab_sort_and_prepare_scan(
        args,
        camera,
        detector,
        arm,
        coordinate,
        target_label,
        approach_labels,
    )
    return target_label


def approach_and_sort(
    args,
    camera: Camera,
    detector,
    arm: KinematicsArm,
    motion,
    target_label: str,
    approach_labels: set[str],
) -> str | None:
    """Remeasure and run the existing calibrated floor-distance approach."""
    deadline = time.monotonic() + args.max_seconds
    stable_count = 0

    while time.monotonic() < deadline:
        frame = camera.read()
        detection = accepted_detection(
            detector.detect(frame),
            approach_labels,
            preferred_label=target_label,
        )
        if detection is None or detection.label.lower() != target_label.lower():
            stable_count = 0
            motion.stop()
            print(f"[room-sorter] remeasuring: {target_label} not visible")
            time.sleep(args.poll_seconds)
            continue

        stable_count += 1
        geometry = visual_servo.detection_geometry(frame, detection, args)
        if stable_count < args.stable_frames:
            motion.stop()
            time.sleep(args.poll_seconds)
            continue

        projection = visual_servo.floor_projection_from_detection(
            args,
            frame,
            detection,
        )
        if projection is None:
            motion.stop()
            print("[room-sorter] floor projection unavailable; remeasuring")
            time.sleep(args.poll_seconds)
            continue

        move_cm, move_reason, finishes_approach = (
            visual_servo.distance_approach_move_cm(projection, args)
        )
        print(
            f"[room-sorter] target={target_label} "
            f"floor_x={projection['floor_x_cm']:.2f}cm "
            f"floor_y={projection['floor_y_cm']:.2f}cm "
            f"move={move_cm:.2f}cm reason={move_reason!r}"
        )

        if move_cm <= 0.0:
            return finish_and_sort_target(
                args,
                camera,
                detector,
                arm,
                motion,
                frame,
                detection,
                geometry,
                approach_labels,
            )

        heading_angle, heading_reason = (
            visual_servo.heading_correction_from_projection(projection, args)
        )
        if abs(heading_angle) > 1e-3:
            duration = visual_servo.rotate_for_heading_correction(
                motion,
                heading_angle,
                args.distance_heading_yaw_rate,
                args.distance_heading_deg_per_second,
            )
            print(
                f"[room-sorter] heading correction={heading_angle:.2f}deg "
                f"duration={duration:.2f}s; {heading_reason}; remeasuring"
            )
            stable_count = 0
            time.sleep(0.5)
            continue

        duration = visual_servo.drive_forward_for_distance(
            motion,
            move_cm,
            args.distance_drive_speed,
            args.distance_drive_cm_per_second,
        )
        print(
            f"[room-sorter] drove {move_cm:.2f}cm for {duration:.2f}s; "
            "remeasuring"
        )
        stable_count = 0

        if finishes_approach:
            return finish_and_sort_target(
                args,
                camera,
                detector,
                arm,
                motion,
                frame,
                detection,
                geometry,
                approach_labels,
            )

        time.sleep(args.poll_seconds)

    motion.stop()
    print(f"[room-sorter] timed out while approaching {target_label}")
    return None


def main() -> int:
    args = visual_servo.parse_args()
    if args.approach_mode != "floor-distance":
        raise ValueError("room_object_sorter.py requires floor-distance approach mode")
    if args.home_pose != "my_home":
        raise ValueError("room_object_sorter.py requires the my_home camera pose")

    approach_labels = set(RobotConstants.APPROACH_LABELS)
    arm = visual_servo.create_arm(args)
    move_camera_to(args, arm, FRONT)
    if args.home_arm_only:
        print("[room-sorter] arm homed; exiting")
        return 0

    print("[room-sorter] loading camera and detector")
    camera = Camera()
    detector = create_detector(args)
    motion_mode = "hiwonder" if args.motion == "auto" else args.motion
    motion = create_motion_backend(
        mode=motion_mode,
        speed=args.speed,
        direction=args.direction,
        debug=args.motion_debug,
    )
    print(f"[room-sorter] motion backend: {motion.name}")

    scan_order = INITIAL_SCAN_ORDER
    sorted_count = 0
    music = None

    try:
        music = create_music_player(arm)
        music.start()
        print("[room-sorter] Sera buzzer music started")

        while True:
            found = scan_directions(
                args,
                camera,
                detector,
                arm,
                motion,
                approach_labels,
                scan_order,
            )

            if found is None:
                print(
                    "[room-sorter] front, left, and right are empty; "
                    "checking behind"
                )
                center_camera_while_turning(
                    args,
                    arm,
                    motion,
                    RIGHT,
                    degrees=180,
                )
                rear_result = observe_view(
                    args,
                    camera,
                    detector,
                    approach_labels,
                    "rear",
                )
                if rear_result is None:
                    print(
                        "[room-sorter] all four directions scanned; "
                        f"no objects remain; sorted={sorted_count}; stopping"
                    )
                    return 0
                found_direction = FRONT
                scan_result = rear_result
            else:
                found_direction, scan_result = found

            target_label = scan_result.detection.label.lower()
            if found_direction in {LEFT, RIGHT}:
                print(
                    f"[room-sorter] {target_label} found {found_direction}; "
                    "centering camera and turning chassis"
                )
                center_camera_while_turning(
                    args,
                    arm,
                    motion,
                    found_direction,
                )
                remeasured = observe_view(
                    args,
                    camera,
                    detector,
                    approach_labels,
                    FRONT,
                    preferred_label=target_label,
                )
                if remeasured is None:
                    print(
                        "[room-sorter] side target was not visible after the "
                        "turn; restarting the scan from the new heading"
                    )
                    scan_order = INITIAL_SCAN_ORDER
                    continue

            sorted_label = approach_and_sort(
                args,
                camera,
                detector,
                arm,
                motion,
                target_label,
                approach_labels,
            )
            if sorted_label is None:
                print("[room-sorter] target was not sorted; stopping safely")
                return 0

            sorted_count += 1
            scan_order = scan_order_after_sort(sorted_label)
            print(
                f"[room-sorter] sorted {sorted_label}; total={sorted_count}; "
                f"next scan order={scan_order}"
            )
    finally:
        motion.stop()
        camera.close()
        if music is not None:
            print("[room-sorter] waiting for the current music cycle to finish")
            try:
                music.stop_after_cycle()
            except RuntimeError as exc:
                print(f"[room-sorter] buzzer shutdown warning: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
