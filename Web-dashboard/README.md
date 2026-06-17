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

### Laptop: first build and sync

Run this from your laptop:

```bash
cd /Users/maksimandpreeti/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

cd Web-dashboard/frontend
npm install
npm run build
cd ../..

ssh pi@192.168.149.1 "mkdir -p ~/Web-dashboard/backend ~/Web-dashboard/frontend/dist"

rsync -av --delete \
  --exclude "__pycache__" \
  --exclude ".venv" \
  Web-dashboard/backend/ \
  pi@192.168.149.1:~/Web-dashboard/backend/

rsync -av --delete \
  Web-dashboard/frontend/dist/ \
  pi@192.168.149.1:~/Web-dashboard/frontend/dist/
```

### Robot: first backend setup

Run this after SSH-ing into the robot:

```bash
cd ~/Web-dashboard/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

### Laptop: sync after changes

After changing frontend or backend files, run this from your laptop:

```bash
cd /Users/maksimandpreeti/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

cd Web-dashboard/frontend
npm run build
cd ../..

ssh pi@192.168.149.1 "mkdir -p ~/Web-dashboard/backend ~/Web-dashboard/frontend/dist"

rsync -av --delete \
  --exclude "__pycache__" \
  --exclude ".venv" \
  Web-dashboard/backend/ \
  pi@192.168.149.1:~/Web-dashboard/backend/

rsync -av --delete \
  Web-dashboard/frontend/dist/ \
  pi@192.168.149.1:~/Web-dashboard/frontend/dist/
```

### Robot: restart after sync

If the backend is already running on the robot, press `Ctrl+C`, then run:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate
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

### Robot or laptop: backend only

```bash
cd Web-dashboard/backend
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Laptop: React dev server

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
