# SortiBot Web Dashboard

Minimal React + FastAPI dashboard for the MasterPi robot.

## Why FastAPI for the server

FastAPI is a good fit for this project because it keeps the server small while still supporting:

- MJPEG camera streaming from the robot camera.
- Simple API routes for capture, predict, status, and logs.
- Typed JSON responses that are easy for React to consume.
- Future growth into WebSockets or robot state updates without changing frameworks.

Flask would also work, but FastAPI gives cleaner API structure as the robot grows.

## Folder layout

```text
Web-dashboard/
  backend/
    app.py
    camera.py
    clip_classifier.py
    requirements.txt
  frontend/
    package.json
    index.html
    src/
      App.jsx
      main.jsx
      styles.css
```

## Run on the robot

From the robot:

```bash
cd ~/Web-dashboard/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

If the Hiwonder camera stream is not at the default URL, set:

```bash
export SORTIBOT_CAMERA_URL="http://127.0.0.1:8080?action=stream"
```

Open from your laptop while connected to the robot network:

```text
http://192.168.149.1:8000
```

## Development mode

Run the backend:

```bash
cd Web-dashboard/backend
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Run the React dev server:

```bash
cd Web-dashboard/frontend
npm install
npm run dev -- --host 0.0.0.0
```

Then open the Vite URL. API calls are proxied to `localhost:8000`.

## OpenCLIP deployment

OpenCLIP is used for semantic classification, not object localization. The normal flow is:

```text
camera frame -> optional crop -> OpenCLIP prompt classification -> Trash / Keep / Ignore
```

Install dependencies in the backend virtual environment:

```bash
python -m pip install torch torchvision
python -m pip install open_clip_torch pillow
```

The first model load may download pretrained weights. That does not send your images anywhere, but it does require internet access once. After the weights are cached, inference is local.

If the robot is in AP mode with no internet, either switch it to Wi-Fi/client mode temporarily or download the model cache on another machine and copy it to the robot.

Start with whole-frame classification or a fixed pickup-zone crop. Add YOLO later when you need bounding boxes.
