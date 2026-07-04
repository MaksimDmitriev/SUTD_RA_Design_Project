import importlib
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class MotionBackend(Protocol):
    name: str

    def forward(self) -> None:
        ...

    def translate(self, velocity_x: float, velocity_y: float) -> None:
        ...

    def stop(self) -> None:
        ...


@dataclass
class DryRunMotion:
    name: str = "dry-run"

    def forward(self) -> None:
        print("[motion] dry-run forward")

    def translate(self, velocity_x: float, velocity_y: float) -> None:
        print(f"[motion] dry-run translate x={velocity_x:.1f} y={velocity_y:.1f}")

    def stop(self) -> None:
        print("[motion] dry-run stop")


class ShellMotion:
    name = "shell"

    def __init__(self, forward_cmd: str, stop_cmd: str):
        self.forward_cmd = forward_cmd
        self.stop_cmd = stop_cmd
        self._process: subprocess.Popen | None = None

    def forward(self) -> None:
        print(f"[motion] shell forward: {self.forward_cmd}")
        self._process = subprocess.Popen(shlex.split(self.forward_cmd))

    def translate(self, velocity_x: float, velocity_y: float) -> None:
        raise RuntimeError(
            "Shell motion only supports forward/stop. Use --motion auto or "
            "--motion hiwonder for visual servoing."
        )

    def stop(self) -> None:
        print(f"[motion] shell stop: {self.stop_cmd}")
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
        subprocess.run(shlex.split(self.stop_cmd), check=False)


class HiwonderMecanumMotion:
    name = "hiwonder-mecanum"

    def __init__(self, chassis, speed: int, direction: int):
        self.chassis = chassis
        self.speed = speed
        self.direction = direction

    def forward(self) -> None:
        print(
            f"[motion] hiwonder forward speed={self.speed} "
            f"direction={self.direction}"
        )
        self.chassis.set_velocity(self.speed, self.direction, 0)

    def translate(self, velocity_x: float, velocity_y: float) -> None:
        print(
            f"[motion] hiwonder translate x={velocity_x:.1f} "
            f"y={velocity_y:.1f}"
        )
        self.chassis.translation(float(velocity_x), float(velocity_y))

    def stop(self) -> None:
        print("[motion] hiwonder stop")
        try:
            self.chassis.set_velocity(0, self.direction, 0)
        except TypeError:
            self.chassis.set_velocity(0, 0, 0)


def _load_hiwonder_backend(
    speed: int,
    direction: int,
    debug: bool = False,
) -> MotionBackend | None:
    default_paths = [
        "/home/pi/MasterPi",
        "/home/pi/MasterPi/masterpi_sdk",
        "/home/pi/MasterPi/masterpi_sdk/common_sdk",
        "/home/pi/MasterPi/masterpi_sdk/common_sdk/common",
        "/home/pi/MasterPi/HiwonderSDK",
        "/home/pi/MasterPi/Functions",
        "/home/pi/MasterPi/functions",
    ]
    extra_paths = os.environ.get("SORTIBOT_HIWONDER_PATHS", "")
    for raw_path in [*default_paths, *extra_paths.split(":")]:
        if not raw_path:
            continue
        path = Path(raw_path)
        if path.exists() and str(path) not in sys.path:
            sys.path.insert(0, str(path))
            if debug:
                print(f"[motion] added Python path: {path}")
        elif debug:
            print(f"[motion] Python path not found or already added: {path}")

    candidates = [
        ("common.mecanum", "MecanumChassis"),
        ("masterpi_sdk.common_sdk.common.mecanum", "MecanumChassis"),
        ("HiwonderSDK.mecanum", "MecanumChassis"),
        ("hiwonder.mecanum", "MecanumChassis"),
        ("hiwonder.MecanumControl", "MecanumChassis"),
        ("MecanumControl", "MecanumChassis"),
        ("mecanum", "MecanumChassis"),
        ("MecanumChassis", "MecanumChassis"),
    ]

    for module_name, class_name in candidates:
        try:
            if debug:
                print(f"[motion] trying {module_name}.{class_name}")
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            chassis = cls()
            if not hasattr(chassis, "set_velocity"):
                if debug:
                    print(
                        f"[motion] {module_name}.{class_name} has no set_velocity"
                    )
                continue
            print(f"[motion] loaded {module_name}.{class_name}")
            return HiwonderMecanumMotion(chassis, speed=speed, direction=direction)
        except Exception as exc:
            if debug:
                print(f"[motion] failed {module_name}.{class_name}: {exc!r}")
            continue

    return None


def create_motion_backend(
    mode: str = "auto",
    speed: int = 35,
    direction: int = 90,
    debug: bool = False,
) -> MotionBackend:
    if mode == "dry-run":
        return DryRunMotion()

    forward_cmd = os.environ.get("SORTIBOT_MOVE_FORWARD_CMD")
    stop_cmd = os.environ.get("SORTIBOT_STOP_CMD")
    if mode in {"auto", "shell"} and forward_cmd and stop_cmd:
        return ShellMotion(forward_cmd=forward_cmd, stop_cmd=stop_cmd)

    if mode in {"auto", "hiwonder"}:
        backend = _load_hiwonder_backend(
            speed=speed,
            direction=direction,
            debug=debug,
        )
        if backend is not None:
            return backend

    if mode == "auto":
        print("[motion] no motion backend found; using dry-run")
        return DryRunMotion()

    if mode == "shell":
        raise RuntimeError(
            "Motion backend 'shell' needs both environment variables: "
            "SORTIBOT_MOVE_FORWARD_CMD and SORTIBOT_STOP_CMD. "
            "For the MasterPi robot, use --motion auto or --motion hiwonder."
        )

    raise RuntimeError(
        f"Motion backend '{mode}' is unavailable. "
        "Use --motion auto, --motion hiwonder, or --motion dry-run."
    )
