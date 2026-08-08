"""Play monophonic tunes on the MasterPi expansion-board buzzer."""

from __future__ import annotations

import argparse
import importlib
import math
import os
import sys
import threading
import time
from pathlib import Path


SERA_BPM = 100

# The introduction is shifted one octave upward so that the small onboard
# buzzer reproduces it clearly. Durations are measured in eighth notes.
SERA_INTRO = [
    ("C5", 1), ("C5", 1), ("R", 4),
    ("G4", 1), ("A#4", 1), ("G4", 1), ("A#4", 1), ("C5", 1),
    ("R", 4),
    ("D5", 1), ("C5", 1), ("A#4", 1), ("A#4", 1),
    ("R", 4),
    ("F4", 1), ("G4", 1), ("F4", 1), ("G4", 1), ("A#4", 1),
    ("R", 2),
    ("A#4", 1), ("R", 1),
    ("A#4", 1), ("B4", 1),
    ("R", 1),
    ("C5", 1), ("C5", 1),
    ("R", 4),
    ("G4", 1), ("A#4", 1), ("G4", 1), ("A#4", 1), ("C5", 1),
    ("R", 5),
    ("D5", 1), ("C5", 1), ("A#4", 1), ("A#4", 1),
    ("R", 4),
    ("F4", 1), ("G4", 1), ("F4", 1), ("G4", 1), ("A#4", 1),
    ("R", 2),
    ("A#4", 1), ("R", 1),
    ("A#4", 1), ("B4", 1),
    ("R", 2),
]

SERA_HOOK = [
    ("G5", 1),
    ("F#5", 1),
    ("G5", 5),
    ("F5", 2),
    ("D#5", 1),
    ("D5", 1),
    ("C5", 1),
    ("B4", 2),
    ("G4", 2),
    ("D#5", 2),
    ("D5", 1),
    ("C5", 1),
    ("C5", 1),
    ("D5", 1),
    ("C5", 10),
]

SERA_LONG_SAMPLE = SERA_INTRO + SERA_HOOK + [("R", 2)] + SERA_HOOK


def note_frequency(note: str) -> int:
    """Convert a note such as C#5 to an integer frequency in hertz."""
    if note == "R":
        return 0

    semitones = {
        "C": 0,
        "C#": 1,
        "D": 2,
        "D#": 3,
        "E": 4,
        "F": 5,
        "F#": 6,
        "G": 7,
        "G#": 8,
        "A": 9,
        "A#": 10,
        "B": 11,
    }
    pitch = note[:-1]
    octave = int(note[-1])
    midi_number = 12 * (octave + 1) + semitones[pitch]
    return round(440 * math.pow(2, (midi_number - 69) / 12))


def add_masterpi_paths() -> None:
    paths = [
        "/home/pi/MasterPi",
        "/home/pi/MasterPi/masterpi_sdk",
        "/home/pi/MasterPi/masterpi_sdk/common_sdk",
        "/home/pi/MasterPi/masterpi_sdk/common_sdk/common",
    ]
    paths.extend(os.environ.get("SORTIBOT_HIWONDER_PATHS", "").split(":"))
    for raw_path in paths:
        path = Path(raw_path)
        if raw_path and path.exists() and str(path) not in sys.path:
            sys.path.insert(0, str(path))


def load_board():
    add_masterpi_paths()
    candidates = [
        ("common.ros_robot_controller_sdk", "Board"),
        ("masterpi_sdk.common_sdk.common.ros_robot_controller_sdk", "Board"),
        ("ros_robot_controller_sdk", "Board"),
        ("common.board", "Board"),
        ("board", "Board"),
    ]
    errors = []
    for module_name, class_name in candidates:
        try:
            board = getattr(importlib.import_module(module_name), class_name)()
            if not hasattr(board, "set_buzzer"):
                errors.append(f"{module_name}.{class_name}: no set_buzzer")
                continue
            return board
        except Exception as exc:
            errors.append(f"{module_name}.{class_name}: {exc!r}")

    raise RuntimeError("Could not load MasterPi buzzer API. " + " | ".join(errors))


def play_tune(board, tune, bpm: float = SERA_BPM, dry_run: bool = False) -> None:
    """Play one complete tune cycle."""
    eighth_seconds = 30.0 / bpm

    for note, beats in tune:
        duration = eighth_seconds * beats
        frequency = note_frequency(note)

        if dry_run:
            print(f"{note:>3}  {frequency:>4} Hz  {duration:.3f} s")
        elif frequency == 0:
            time.sleep(duration)
        else:
            sounding = max(0.04, duration * 0.91)
            gap = max(0.01, duration - sounding)
            board.set_buzzer(frequency, sounding, gap, 1)
            time.sleep(duration)


class LoopingTunePlayer:
    """Loop a tune in the background and stop only at a cycle boundary."""

    def __init__(self, board, tune, bpm: float = SERA_BPM):
        self._board = board
        self._tune = tuple(tune)
        self._bpm = bpm
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("tune player has already been started")
        self._thread = threading.Thread(
            target=self._run,
            name="sortibot-buzzer",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        try:
            while not self._stop_requested.is_set():
                play_tune(self._board, self._tune, bpm=self._bpm)
        except BaseException as exc:
            self._error = exc
            print(f"[buzzer] playback stopped unexpectedly: {exc!r}")

    def stop_after_cycle(self) -> None:
        """Request shutdown and wait for the active tune cycle to finish."""
        self._stop_requested.set()
        if self._thread is not None:
            self._thread.join()
        if self._error is not None:
            raise RuntimeError("buzzer playback failed") from self._error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Play the SortiBot Sera buzzer arrangement."
    )
    parser.add_argument("--bpm", type=float, default=SERA_BPM, help="Playback tempo")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print notes without connecting to the robot controller",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.bpm <= 0:
        raise SystemExit("--bpm must be greater than zero")
    board = None if args.dry_run else load_board()
    play_tune(board, SERA_LONG_SAMPLE, bpm=args.bpm, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
