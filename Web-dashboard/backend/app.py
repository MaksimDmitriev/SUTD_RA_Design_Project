from datetime import datetime
from pathlib import Path
import time

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from camera import Camera
from clip_classifier import ClipClassifier
from robot_arm import ArmController


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
FRONTEND_DIST = ROOT / "frontend" / "dist"
VALID_LABELS = {"trash", "keep", "ignore"}

for label in VALID_LABELS:
    (DATA_DIR / label).mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SortiBot Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

camera = Camera()
classifier = ClipClassifier()
arm = ArmController()
state = {
    "robot_state": "IDLE",
    "last_capture": None,
    "last_prediction": None,
    "last_error": None,
}


class ServoRequest(BaseModel):
    servo_id: int = Field(ge=1, le=6)
    angle: int = Field(ge=0, le=180)
    duration_seconds: float = Field(default=0.35, ge=0.05, le=3.0)


def set_state(robot_state: str, error: str | None = None) -> None:
    state["robot_state"] = robot_state
    state["last_error"] = error


@app.get("/api/status")
def status():
    return {
        **state,
        "classifier_available": classifier.available,
        "classifier_error": classifier.load_error,
    }


@app.get("/api/stream.mjpg")
def stream():
    def frames():
        while True:
            try:
                jpg = camera.jpeg()
                yield (
                    b"--FRAME\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                )
                time.sleep(0.04)
            except Exception as exc:
                set_state("ERROR", str(exc))
                time.sleep(0.5)

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=FRAME",
    )


@app.post("/api/capture/{label}")
def capture(label: str):
    if label not in VALID_LABELS:
        raise HTTPException(status_code=400, detail="Invalid label.")

    try:
        frame = camera.read()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = DATA_DIR / label / f"{timestamp}.jpg"
        cv2.imwrite(str(path), frame)
        state["last_capture"] = str(path)
        set_state("CAPTURED")
        return {"ok": True, "label": label, "path": str(path)}
    except Exception as exc:
        set_state("ERROR", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/predict")
def predict():
    try:
        set_state("CLASSIFYING")
        frame = camera.read()
        result = classifier.predict(frame)
        payload = {
            "label": result.label,
            "confidence": result.confidence,
            "prompt": result.prompt,
            "scores": result.scores,
        }
        state["last_prediction"] = payload
        set_state(result.label.upper())
        return payload
    except Exception as exc:
        set_state("ERROR", str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/arm/servo")
def set_arm_servo(payload: ServoRequest):
    try:
        command = arm.set_servo_angle(
            payload.servo_id,
            payload.angle,
            payload.duration_seconds,
        )
        set_state(f"SERVO_{command.servo_id}")
        return {
            "ok": True,
            "servo_id": command.servo_id,
            "angle": command.angle,
            "pulse": command.pulse,
        }
    except Exception as exc:
        set_state("ERROR", str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/arm/gripper/{state_name}")
def set_gripper(state_name: str):
    gripper_angles = {"open": 90, "close": 35}
    if state_name not in gripper_angles:
        raise HTTPException(status_code=400, detail="Use 'open' or 'close'.")

    try:
        command = arm.set_servo_angle(1, gripper_angles[state_name], 0.35)
        set_state(f"GRIPPER_{state_name.upper()}")
        return {
            "ok": True,
            "state": state_name,
            "servo_id": command.servo_id,
            "angle": command.angle,
            "pulse": command.pulse,
        }
    except Exception as exc:
        set_state("ERROR", str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/")
def index():
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {
        "message": "Backend running. Build the React frontend or use Vite dev server.",
        "api": ["/api/status", "/api/stream.mjpg", "/api/capture/{label}", "/api/predict"],
    }
