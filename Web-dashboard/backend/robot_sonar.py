import importlib
import os
import sys
import time
from pathlib import Path


class SonarDistanceSensor:
    def __init__(self):
        self._sonar = None

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
        if self._sonar is not None:
            return

        self._add_masterpi_paths()
        candidates = [
            ("common.sonar", "Sonar"),
            ("masterpi_sdk.common_sdk.common.sonar", "Sonar"),
            ("sonar", "Sonar"),
        ]
        errors: list[str] = []

        for module_name, class_name in candidates:
            try:
                module = importlib.import_module(module_name)
                cls = getattr(module, class_name)
                sonar = cls()
                if not hasattr(sonar, "getDistance"):
                    errors.append(f"{module_name}.{class_name}: no getDistance")
                    continue
                self._sonar = sonar
                return
            except Exception as exc:
                errors.append(f"{module_name}.{class_name}: {exc!r}")

        raise RuntimeError("Could not load MasterPi sonar API. " + " | ".join(errors))

    def read_cm(self, samples: int = 3, delay_seconds: float = 0.03) -> float:
        self.load()
        values = []

        for index in range(max(1, samples)):
            raw_mm = float(self._sonar.getDistance())
            if raw_mm > 0:
                values.append(raw_mm / 10.0)
            if index < samples - 1:
                time.sleep(delay_seconds)

        if not values:
            raise RuntimeError("Sonar returned no valid distance readings")

        values.sort()
        return values[len(values) // 2]
