import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path


def angle_to_pulse(angle: int) -> int:
    clamped = max(0, min(180, int(angle)))
    return int(round(500 + (clamped / 180) * 2000))


@dataclass
class ServoCommand:
    servo_id: int
    angle: int
    pulse: int


class ArmController:
    def __init__(self):
        self._board = None

    def _add_masterpi_paths(self) -> None:
        default_paths = [
            "/home/pi/MasterPi",
            "/home/pi/MasterPi/masterpi_sdk",
            "/home/pi/MasterPi/masterpi_sdk/common_sdk",
            "/home/pi/MasterPi/masterpi_sdk/common_sdk/common",
        ]
        extra_paths = os.environ.get("SORTIBOT_HIWONDER_PATHS", "")
        for raw_path in [*default_paths, *extra_paths.split(":")]:
            if not raw_path:
                continue
            path = Path(raw_path)
            if path.exists() and str(path) not in sys.path:
                sys.path.insert(0, str(path))

    def load(self) -> None:
        if self._board is not None:
            return

        self._add_masterpi_paths()
        candidates = [
            ("common.ros_robot_controller_sdk", "Board"),
            ("masterpi_sdk.common_sdk.common.ros_robot_controller_sdk", "Board"),
            ("ros_robot_controller_sdk", "Board"),
            ("common.board", "Board"),
            ("board", "Board"),
        ]
        errors: list[str] = []

        for module_name, class_name in candidates:
            try:
                module = importlib.import_module(module_name)
                cls = getattr(module, class_name)
                board = cls()
                if not hasattr(board, "pwm_servo_set_position"):
                    errors.append(f"{module_name}.{class_name}: no pwm_servo_set_position")
                    continue
                self._board = board
                return
            except Exception as exc:
                errors.append(f"{module_name}.{class_name}: {exc!r}")

        raise RuntimeError("Could not load MasterPi board API. " + " | ".join(errors))

    def set_servo_angle(
        self,
        servo_id: int,
        angle: int,
        duration_seconds: float = 0.35,
    ) -> ServoCommand:
        if servo_id < 1 or servo_id > 6:
            raise ValueError("servo_id must be between 1 and 6")

        self.load()
        pulse = angle_to_pulse(angle)
        self._board.pwm_servo_set_position(duration_seconds, [[servo_id, pulse]])
        return ServoCommand(servo_id=servo_id, angle=max(0, min(180, int(angle))), pulse=pulse)
