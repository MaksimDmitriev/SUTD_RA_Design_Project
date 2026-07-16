import importlib
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ArmCoordinate:
    x: float
    y: float
    z: float


class KinematicsArm:
    def __init__(
        self,
        open_pulse: int = 2000,
        close_pulse: int = 1500,
        home: ArmCoordinate = ArmCoordinate(0, 6, 18),
        approach_lift_cm: float = 6.0,
        min_approach_z_cm: float = 8.0,
    ):
        self.open_pulse = open_pulse
        self.close_pulse = close_pulse
        self.home = home
        self.approach_lift_cm = approach_lift_cm
        self.min_approach_z_cm = min_approach_z_cm
        self._board = None
        self._ik = None
        self._transform = None

    def _add_masterpi_paths(self) -> None:
        default_paths = [
            "/home/pi/MasterPi",
            "/home/pi/MasterPi/masterpi_sdk",
            "/home/pi/MasterPi/masterpi_sdk/common_sdk",
            "/home/pi/MasterPi/masterpi_sdk/common_sdk/common",
            "/home/pi/MasterPi/masterpi_sdk/kinematics_sdk",
        ]
        extra_paths = os.environ.get("SORTIBOT_HIWONDER_PATHS", "")
        for raw_path in [*default_paths, *extra_paths.split(":")]:
            if not raw_path:
                continue
            path = Path(raw_path)
            if path.exists() and str(path) not in sys.path:
                sys.path.insert(0, str(path))

    def load(self) -> None:
        if self._board is not None and self._ik is not None:
            return

        self._add_masterpi_paths()
        errors: list[str] = []

        board_candidates = [
            ("common.ros_robot_controller_sdk", "Board"),
            ("masterpi_sdk.common_sdk.common.ros_robot_controller_sdk", "Board"),
            ("ros_robot_controller_sdk", "Board"),
            ("common.board", "Board"),
            ("board", "Board"),
        ]
        for module_name, class_name in board_candidates:
            try:
                module = importlib.import_module(module_name)
                board_cls = getattr(module, class_name)
                self._board = board_cls()
                if not hasattr(self._board, "pwm_servo_set_position"):
                    errors.append(
                        f"{module_name}.{class_name}: no pwm_servo_set_position"
                    )
                    self._board = None
                    continue
                break
            except Exception as exc:
                errors.append(f"{module_name}.{class_name}: {exc!r}")

        ik_candidates = [
            ("kinematics.arm_move_ik", "ArmIK"),
            ("masterpi_sdk.kinematics_sdk.kinematics.arm_move_ik", "ArmIK"),
            ("arm_move_ik", "ArmIK"),
        ]
        for module_name, class_name in ik_candidates:
            try:
                module = importlib.import_module(module_name)
                ik_cls = getattr(module, class_name)
                self._ik = ik_cls()
                self._ik.board = self._board
                break
            except Exception as exc:
                errors.append(f"{module_name}.{class_name}: {exc!r}")

        if self._board is None or self._ik is None:
            raise RuntimeError(
                "Could not load MasterPi IK arm API. " + " | ".join(errors)
            )

    def load_transform(self):
        if self._transform is not None:
            return self._transform
        self._add_masterpi_paths()
        candidates = [
            "kinematics.transform",
            "masterpi_sdk.kinematics_sdk.kinematics.transform",
            "transform",
        ]
        errors: list[str] = []
        for module_name in candidates:
            try:
                self._transform = importlib.import_module(module_name)
                return self._transform
            except Exception as exc:
                errors.append(f"{module_name}: {exc!r}")
        raise RuntimeError(
            "Could not load MasterPi camera transform. " + " | ".join(errors)
        )

    def open_gripper(self, duration_seconds: float = 0.5) -> None:
        self.load()
        self._board.pwm_servo_set_position(duration_seconds, [[1, self.open_pulse]])
        time.sleep(duration_seconds)

    def close_gripper(self, duration_seconds: float = 0.5) -> None:
        self.load()
        self._board.pwm_servo_set_position(duration_seconds, [[1, self.close_pulse]])
        time.sleep(duration_seconds)

    def set_servo_pulse(
        self,
        servo_id: int,
        pulse: int,
        duration_seconds: float = 0.5,
    ) -> None:
        if servo_id < 1 or servo_id > 6:
            raise ValueError("servo_id must be between 1 and 6")
        self.load()
        self._board.pwm_servo_set_position(
            duration_seconds,
            [[servo_id, max(500, min(2500, int(pulse)))]],
        )
        time.sleep(duration_seconds)

    def set_servo_pulses(
        self,
        positions: list[tuple[int, int]],
        duration_seconds: float = 0.5,
    ) -> None:
        if not positions:
            return
        normalized = []
        for servo_id, pulse in positions:
            if servo_id < 1 or servo_id > 6:
                raise ValueError("servo_id must be between 1 and 6")
            normalized.append([servo_id, max(500, min(2500, int(pulse)))])
        self.load()
        self._board.pwm_servo_set_position(duration_seconds, normalized)
        time.sleep(duration_seconds)

    def set_servo_angle(
        self,
        servo_id: int,
        angle: int,
        duration_seconds: float = 0.5,
    ) -> None:
        clamped = max(0, min(180, int(angle)))
        pulse = int(round(500 + (clamped / 180) * 2000))
        self.set_servo_pulse(servo_id, pulse, duration_seconds)

    def move_to(
        self,
        coordinate: ArmCoordinate,
        pitch: float = -90,
        pitch_min: float = -90,
        pitch_max: float = 0,
        move_time_ms: int = 800,
    ) -> None:
        self.load()
        result = self._ik.setPitchRangeMoving(
            (coordinate.x, coordinate.y, coordinate.z),
            pitch,
            pitch_min,
            pitch_max,
            move_time_ms,
        )
        if result is False:
            raise RuntimeError(f"Arm coordinate is unreachable: {coordinate}")
        time.sleep(result[2] / 1000)

    def move_home(self) -> None:
        self.load()
        result = self._ik.setPitchRangeMoving(
            (self.home.x, self.home.y, self.home.z),
            0,
            -90,
            90,
            1500,
        )
        if result is False:
            raise RuntimeError(f"Home coordinate is unreachable: {self.home}")
        time.sleep(result[2] / 1000)

    def grab_at(
        self,
        coordinate: ArmCoordinate,
        pitch: float = -90,
        pitch_min: float = -90,
        pitch_max: float = 0,
    ) -> None:
        above = ArmCoordinate(
            coordinate.x,
            coordinate.y,
            max(coordinate.z + self.approach_lift_cm, self.min_approach_z_cm),
        )
        self.move_home()
        self.open_gripper()
        self.move_to(
            above,
            pitch=pitch,
            pitch_min=pitch_min,
            pitch_max=pitch_max,
            move_time_ms=800,
        )
        self.move_to(
            coordinate,
            pitch=pitch,
            pitch_min=pitch_min,
            pitch_max=pitch_max,
            move_time_ms=500,
        )
        self.close_gripper()
        self.move_to(
            above,
            pitch=pitch,
            pitch_min=pitch_min,
            pitch_max=pitch_max,
            move_time_ms=800,
        )
        self.move_home()

    def pixel_to_arm_coordinate(
        self,
        x: float,
        y: float,
        frame_size: tuple[int, int],
        z: float = 2,
    ) -> ArmCoordinate:
        transform = self.load_transform()
        arm_x, arm_y = transform.convertCoordinate(x, y, frame_size)
        return ArmCoordinate(float(arm_x), float(arm_y), z)
