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

### Laptop: connect by SSH

Run this from your laptop:

```bash
ssh pi@192.168.149.1
```

Password:

```text
raspberrypi
```

### Laptop: optional SSH key setup

Run this once from your laptop to avoid repeated password prompts during `ssh` and `rsync`:

```bash
ssh-keygen -t ed25519 -f $HOME/.ssh/sortibot_ed25519 -C sortibot
```

Run this on the laptop to copy the public key to the robot:

```bash
cat $HOME/.ssh/sortibot_ed25519.pub | ssh pi@192.168.149.1 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

Run this on the laptop to test the key:

```bash
ssh -i $HOME/.ssh/sortibot_ed25519 pi@192.168.149.1
```

### Laptop: first build and sync

Run this from your laptop:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

cd Web-dashboard/frontend
npm install
npm run build
cd ../..

ssh -i $HOME/.ssh/sortibot_ed25519 pi@192.168.149.1 "mkdir -p ~/Web-dashboard/backend ~/Web-dashboard/frontend/dist"

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  Web-dashboard/backend/ \
  pi@192.168.149.1:~/Web-dashboard/backend/

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  Web-dashboard/frontend/dist/ \
  pi@192.168.149.1:~/Web-dashboard/frontend/dist/
```

If you did not set up the SSH key, remove each `-i $HOME/.ssh/sortibot_ed25519` and `-e "ssh -i $HOME/.ssh/sortibot_ed25519"` part. You will be asked for the password `raspberrypi` for each `ssh` or `rsync` command.

### Robot: first backend setup

Run this after SSH-ing into the robot:

```bash
cd ~/Web-dashboard/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### Laptop: sync after changes

After changing frontend or backend files, run this from your laptop:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

cd Web-dashboard/frontend
npm run build
cd ../..

ssh -i $HOME/.ssh/sortibot_ed25519 pi@192.168.149.1 "mkdir -p ~/Web-dashboard/backend ~/Web-dashboard/frontend/dist"

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  Web-dashboard/backend/ \
  pi@192.168.149.1:~/Web-dashboard/backend/

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  Web-dashboard/frontend/dist/ \
  pi@192.168.149.1:~/Web-dashboard/frontend/dist/
```

### Robot: restart after sync

If the backend is already running on the robot, press `Ctrl+C`, then run:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Run this on the robot if the Hiwonder camera stream is not at the default URL:

```bash
export SORTIBOT_CAMERA_URL="http://127.0.0.1:8080?action=stream"
```

### Robot: optional camera tuning

Run this on the robot if the camera stream is too bright or over-saturated:

```bash
v4l2-ctl -d /dev/video0 \
  --set-ctrl=brightness=-20,contrast=30,saturation=25,gamma=70,sharpness=8,backlight_compensation=0
```

Open from your laptop while connected to the robot network:

```text
http://192.168.149.1:8000
```

### Laptop: pull captured images from robot

Captured images are stored on the robot under `~/Web-dashboard/data/`. Run this on the laptop to pull them to your laptop storage directory:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

export SUTD_RA_DESIGN_PROJECT_DATA=$PWD/Web-dashboard/data

mkdir -p "$SUTD_RA_DESIGN_PROJECT_DATA"

rsync -av \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  pi@192.168.149.1:~/Web-dashboard/data/ \
  "$SUTD_RA_DESIGN_PROJECT_DATA"/
```

If you did not set up the SSH key, remove the `-e "ssh -i $HOME/.ssh/sortibot_ed25519"` line from the `rsync` command. Do not use `--delete` when pulling images unless you intentionally want your laptop copy to exactly match the robot copy.

### Laptop: push captured images to robot

Run this on the laptop to push your laptop dataset storage directory back to the robot:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

export SUTD_RA_DESIGN_PROJECT_DATA=$PWD/Web-dashboard/data

rsync -av \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  "$SUTD_RA_DESIGN_PROJECT_DATA"/ \
  pi@192.168.149.1:~/Web-dashboard/data/
```

If you did not set up the SSH key, remove the `-e "ssh -i $HOME/.ssh/sortibot_ed25519"` line from the `rsync` command. Do not use `--delete` when pushing images unless you intentionally want the robot copy to exactly match your laptop copy.

## Development mode

### Robot or laptop: backend only

Run this on the robot or laptop:

```bash
cd Web-dashboard/backend
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Laptop: React dev server

Run this on the laptop:

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

Do not install `torch torchvision open_clip_torch` directly from the default PyPI index on the Raspberry Pi. That can pull large CUDA/NVIDIA packages such as `nvidia-*`, `cuda-*`, and `triton`, which are not useful on the robot and can fill the SD card.

There are two requirements files on purpose:

- `requirements.txt` contains the basic dashboard/server/camera packages.
- `requirements-openclip.txt` contains OpenCLIP support packages and is installed only after CPU-only PyTorch is installed.

This split prevents a normal `pip install -r requirements.txt` from accidentally pulling the wrong PyTorch/CUDA dependency set on the Raspberry Pi.

### Robot: create the backend virtual environment

Run this on the robot:

```bash
cd ~/Web-dashboard/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

### Robot: install dashboard packages

Run this on the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate
python -m pip install --no-cache-dir -r requirements.txt
```

### Robot: install CPU-only PyTorch

Run this on the robot. This avoids CUDA/NVIDIA packages:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python -m pip install --no-cache-dir \
  --index-url https://download.pytorch.org/whl/cpu \
  --trusted-host download.pytorch.org \
  torch torchvision
```

### Robot: install OpenCLIP packages

Run this on the robot after CPU-only PyTorch is installed:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python -m pip install --no-cache-dir \
  --trusted-host pypi.org \
  --trusted-host files.pythonhosted.org \
  --trusted-host www.piwheels.org \
  -r requirements-openclip.txt
```

If SSL works normally on the robot, the `--trusted-host` options are not needed. They are included because internet sharing through another laptop may cause certificate verification failures.

### Robot: verify OpenCLIP packages

Run this on the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python -c "import torch; import torchvision; import open_clip; print(torch.__version__); print('OpenCLIP OK')"
```

Expected output should include `+cpu`, for example:

```text
2.12.1+cpu
OpenCLIP OK
```

The first model load may download pretrained weights. That does not send your images anywhere, but it does require internet access once. After the weights are cached, inference is local.

If the robot is in AP mode with no internet, either switch it to Wi-Fi/client mode temporarily or download the model cache on another machine and copy it to the robot.

### Laptop: download OpenCLIP weights

Run this on the laptop to download/cache the same OpenCLIP model weights used by the backend:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project/Web-dashboard/backend

python3 -m venv .openclip-download-venv
source .openclip-download-venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install torch torchvision open_clip_torch pillow

python - <<'PY'
from clip_classifier import ClipClassifier

classifier = ClipClassifier()
classifier.load()
print("OpenCLIP weights downloaded into the local cache.")
PY
```

### Laptop: copy OpenCLIP weights to robot

Run this on the laptop after downloading the weights:

```bash
ssh -i $HOME/.ssh/sortibot_ed25519 pi@192.168.149.1 "mkdir -p ~/.cache/clip ~/.cache/huggingface"

if [ -d "$HOME/.cache/clip" ]; then
  rsync -av \
    -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
    "$HOME/.cache/clip"/ \
    pi@192.168.149.1:~/.cache/clip/
fi

if [ -d "$HOME/.cache/huggingface" ]; then
  rsync -av \
    -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
    "$HOME/.cache/huggingface"/ \
    pi@192.168.149.1:~/.cache/huggingface/
fi
```

If you did not set up the SSH key, remove each `-i $HOME/.ssh/sortibot_ed25519` and `-e "ssh -i $HOME/.ssh/sortibot_ed25519"` part.

Copying these cache folders only copies model weights. The robot still needs the Python packages installed in `.venv`.

### Robot: check copied OpenCLIP weights

Run this on the robot:

```bash
du -h -d 2 ~/.cache/huggingface 2>/dev/null
du -h -d 2 ~/.cache/clip 2>/dev/null
```

For the current backend model, a useful sign is a cache directory like:

```text
~/.cache/huggingface/hub/models--laion--CLIP-ViT-B-32-laion2B-s34B-b79K
```

### Robot: verify OpenCLIP model load

Run this on the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python -c "from clip_classifier import ClipClassifier; c=ClipClassifier(); c.load(); print('OpenCLIP model loaded OK')"
```

If this prints `OpenCLIP model loaded OK`, packages and weights are working.

### Robot: optional storage cleanup

Run this on the robot to reclaim temporary package/cache space:

```bash
rm -rf ~/.cache/pip
rm -rf /tmp/pip-*
sudo apt-get clean
df -h
```

Start with whole-frame classification or a fixed pickup-zone crop. Add YOLO later when you need bounding boxes.
