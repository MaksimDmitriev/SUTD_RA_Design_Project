# SortiBot Web Dashboard

Minimal React + FastAPI dashboard for the MasterPi robot.

## High-level system flow

Target robot behavior:

```text
robot moves forward slowly
  -> camera sees possible object
  -> LAB/color contrast detection finds a tight non-floor blob
  -> crop that blob from the frame
  -> OpenCLIP classifies crop as Trash / Keep / Ignore
  -> robot centers and approaches if the object is Trash or Keep
  -> robot grabs only after the stop position is repeatable
```

In this design:

- LAB/color contrast detection answers: **where is the non-floor object?**
- OpenCLIP answers: **what kind of object is it semantically?**
- The policy layer answers: **what should the robot do?**

YOLO is still documented below as an optional detector/training path, but it is not the current default approach.

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
    contrast_detector.py
    object_visual_servo_test.py
    test_contrast_detector_image.py
    requirements.txt
    requirements-openclip.txt
  frontend/
    package.json
    index.html
    src/
      App.jsx
      main.jsx
      styles.css
```

## Deploy and run the dashboard

Each command block says whether it runs on the laptop or on the robot.

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

### Robot: connect internet with a USB Wi-Fi adapter

Use this when the robot is in access-point mode and you do not have Ethernet. The built-in Wi-Fi can keep the robot network active, while the USB Wi-Fi adapter connects to internet Wi-Fi as a second interface.

Run this on the robot after plugging in the USB Wi-Fi adapter:

```bash
lsusb
nmcli device status
ip link
```

Good sign:

```text
wlan0  wifi  connected
wlan1  wifi  disconnected
```

Then connect `wlan1` to Wi-Fi:

```bash
sudo nmcli device wifi list ifname wlan1
sudo nmcli device wifi connect "WiFiName" password "WiFiPassword" ifname wlan1
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
  --exclude ".openclip-download-venv" \
  --exclude ".yolo-train-venv" \
  Web-dashboard/backend/ \
  pi@192.168.149.1:~/Web-dashboard/backend/

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  Web-dashboard/frontend/dist/ \
  pi@192.168.149.1:~/Web-dashboard/frontend/dist/
```

If you did not set up the SSH key, remove each `-i $HOME/.ssh/sortibot_ed25519` and `-e "ssh -i $HOME/.ssh/sortibot_ed25519"` part. You will be asked for the password `raspberrypi` for each `ssh` or `rsync` command.

### Robot: install all Python packages

Run this after SSH-ing into the robot:

```bash
cd ~/Web-dashboard/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install --no-cache-dir -r requirements.txt

python -m pip install --no-cache-dir \
  --index-url https://download.pytorch.org/whl/cpu \
  --trusted-host download.pytorch.org \
  torch torchvision

python -m pip install --no-cache-dir \
  --trusted-host pypi.org \
  --trusted-host files.pythonhosted.org \
  --trusted-host www.piwheels.org \
  -r requirements-openclip.txt
```

The package installation order matters:

1. Update installer tools: `pip`, `setuptools`, `wheel`.
2. Install dashboard packages from `requirements.txt`.
3. Install CPU-only PyTorch from the PyTorch CPU wheel index.
4. Install OpenCLIP support packages from `requirements-openclip.txt`.

Do not install `torch torchvision open_clip_torch` directly from the default PyPI index on the Raspberry Pi. That can pull large CUDA/NVIDIA packages and fill the SD card.

Verify the imports before starting the backend or robot movement scripts:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python -c "import cv2; import fastapi; import numpy; import PIL; import serial; import smbus2; import torch; import torchvision; import open_clip; print('robot Python deps OK')"
```

If this command fails with `ModuleNotFoundError`, stay in this section and reinstall the missing requirement on the robot. Do not fix it by copying a laptop `.venv`.

### Robot: start backend

Run this on the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### Laptop: open the website and internal dashboard

Open these from your laptop while connected to the robot network:

```text
Front page:
http://192.168.149.1:8000/

Internal dashboard:
http://192.168.149.1:8000/#dashboard
```

The dashboard is intentionally not linked from the front page because it is for local robot control only. If the website is deployed publicly, the dashboard API calls will not work unless the browser can still reach the robot backend.

### Laptop: internal dashboard arm controls

Open the internal dashboard from your laptop:

```text
http://192.168.149.1:8000/#dashboard
```

Use the **Arm control** panel to move the arm servos:

- Servos `2`, `3`, `4`, `5`, and `6`: set an angle from `0` to `180` degrees, then press **Set**.
- Gripper: press **Open gripper** or **Close gripper**. The gripper uses servo `1`.

Start with small movements and keep one hand near the robot power switch. If the gripper direction or range is wrong, adjust the open/close angles in `backend/app.py`.

### Laptop: sync after changes

After changing frontend or backend files, run this from your laptop. This command block syncs both parts:

- Frontend: builds React and copies `Web-dashboard/frontend/dist/` to the robot.
- Backend: copies the Python backend files to the robot.

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
  --exclude ".openclip-download-venv" \
  --exclude ".yolo-train-venv" \
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

### Robot: optional camera tuning

Run this on the robot if the camera stream is too bright or over-saturated:

```bash
v4l2-ctl -d /dev/video0 \
  --set-ctrl=brightness=-20,contrast=30,saturation=25,gamma=70,sharpness=8,backlight_compensation=0
```

Open from your laptop while connected to the robot network:

```text
Front page:
http://192.168.149.1:8000/

Internal dashboard:
http://192.168.149.1:8000/#dashboard
```

### Laptop: pull captured images from robot

Captured images are stored on the robot under `~/Web-dashboard/data/`. Run this on the laptop to pull them to your laptop storage directory:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

export SUTD_RA_DESIGN_PROJECT_DATA=$PWD/Web-dashboard/data

mkdir -p "$SUTD_RA_DESIGN_PROJECT_DATA"

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  pi@192.168.149.1:~/Web-dashboard/data/ \
  "$SUTD_RA_DESIGN_PROJECT_DATA"/
```

If you did not set up the SSH key, remove the `-e "ssh -i $HOME/.ssh/sortibot_ed25519"` line from the `rsync` command. Do not use `--delete` when pulling images unless you intentionally want your laptop copy to exactly match the robot copy.

### Laptop: pull debug detection images from robot

Debug detection images are stored on the robot under `~/Web-dashboard/data/debug_detections/`. Run this on the laptop:

```bash
mkdir -p $HOME/Desktop/sortibot_debug_detections

rsync -av \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  pi@192.168.149.1:~/Web-dashboard/data/debug_detections/ \
  $HOME/Desktop/sortibot_debug_detections/
```

### Laptop: sync captured images to robot

Run this on the laptop only if you want the robot image folder to exactly match your laptop copy:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

export SUTD_RA_DESIGN_PROJECT_DATA=$PWD/Web-dashboard/data

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  "$SUTD_RA_DESIGN_PROJECT_DATA"/ \
  pi@192.168.149.1:~/Web-dashboard/data/
```

Only use `--delete` if you are sure the laptop copy is the source of truth.

## Development mode

### Robot or laptop: backend only

Run this on the robot or laptop:

```bash
cd Web-dashboard/backend
source .venv/bin/activate
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Laptop: React dev server

This is only for local frontend development on the laptop. For the robot workflow, use the `http://192.168.149.1:8000/` addresses above.

Run this on the laptop:

```bash
cd Web-dashboard/frontend
npm install
npm run dev -- --host 0.0.0.0
```

Then open the Vite URL printed by `npm run dev`. API calls are proxied to `127.0.0.1:8000`, so dashboard API calls only work if the FastAPI backend is also running on the same laptop.

Do not use the laptop dev server for normal robot testing. Use `http://192.168.149.1:8000/` and `http://192.168.149.1:8000/#dashboard`.

## OpenCLIP deployment

OpenCLIP is used for semantic classification, not object localization. The normal flow is:

```text
camera frame -> optional crop -> OpenCLIP prompt classification -> Trash / Keep / Ignore
```

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
  rsync -av --delete \
    -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
    "$HOME/.cache/clip"/ \
    pi@192.168.149.1:~/.cache/clip/
fi

if [ -d "$HOME/.cache/huggingface" ]; then
  rsync -av --delete \
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

For the current approach, use LAB/color contrast detection to create a tight object crop before OpenCLIP classification. YOLO is optional later if the contrast assumption stops being true.

### How to improve OpenCLIP classification

In the current setup, OpenCLIP is **not retrained** when you add new images. It is used as a zero-shot classifier:

```text
image or crop -> compare with text prompts -> Trash / Keep / Ignore
```

Adding images to `~/Web-dashboard/data/trash`, `~/Web-dashboard/data/keep`, or `~/Web-dashboard/data/ignore` gives you more examples for testing, but it does not change OpenCLIP weights.

The current prompts are defined in:

```text
Web-dashboard/backend/clip_classifier.py
```

Look for:

```python
PROMPTS = {
    "trash": [...],
    "keep": [...],
    "ignore": [...],
}
```

If OpenCLIP misclassifies objects, first update those prompts. For example:

```python
PROMPTS = {
    "trash": [
        "a photo of a tissue on the floor",
        "a photo of a plastic wrapper on the floor",
        "a photo of a disposable food wrapper on the floor",
        "a photo of rubbish or waste on the floor",
    ],
    "keep": [
        "a photo of a useful personal object on the floor",
        "a photo of a toy that should be kept",
        "a photo of a sock or clothing item on the floor",
        "a photo of an object that should be picked up and saved",
    ],
    "ignore": [
        "a photo of a cable on the floor",
        "a photo of a heavy object on the floor",
        "a photo of an unsafe object on the floor",
        "a photo of floor with no relevant object",
    ],
}
```

After changing prompts, sync backend changes to the robot and restart the backend:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  --exclude ".openclip-download-venv" \
  --exclude ".yolo-train-venv" \
  Web-dashboard/backend/ \
  pi@192.168.149.1:~/Web-dashboard/backend/
```

Then run this on the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

The usual OpenCLIP improvement loop is:

```text
capture more images
  -> pull images to laptop
  -> test predictions
  -> inspect wrong examples
  -> adjust prompts and thresholds
  -> sync backend to robot
  -> test again
```

If prompt tuning is not enough, do **not** fine-tune the full OpenCLIP model first. A better next step is to freeze OpenCLIP and train a small classifier on top of OpenCLIP image embeddings.

Recommended progression:

1. Prompt tuning: fastest and easiest.
2. LAB/color contrast crop before OpenCLIP: usually improves classification because background is removed.
3. Threshold/policy tuning: send low-confidence predictions to `ignore`.
4. Train a small classifier on OpenCLIP embeddings using your captured folders.
5. Full OpenCLIP fine-tuning: only if the previous steps fail and you have a much larger dataset.

For the current robot, steps 1-3 are the right priority. Full OpenCLIP fine-tuning is heavy and not recommended on the Raspberry Pi.

## Optional YOLO detection and retraining workflow

This section is optional/reference. The current default approach is the LAB/color contrast visual-servo test below. Use this YOLO workflow only if the light-floor/non-light-object assumption is not enough, or if you later need a trained detector that works across more floor colors and object appearances.

### What YOLO should do in this project

Use YOLO for object detection/localization, not as the only trash/keep/ignore decision maker.

This is better than training YOLO directly on `trash`, `keep`, and `ignore` at the beginning, because `trash` vs `keep` is often semantic and context-dependent. For example, a toy car is an object YOLO can localize, but whether it should be kept or ignored is better handled by the classifier/policy layer.

### Important: captured images do not automatically retrain the model

When you press the dashboard capture buttons, images are saved under:

```text
~/Web-dashboard/data/trash/
~/Web-dashboard/data/keep/
~/Web-dashboard/data/ignore/
```

Those folders are useful for classification testing and OpenCLIP prompt evaluation. They are **not enough for YOLO training** because YOLO needs bounding-box labels.

For YOLO, each training image needs a label file that says where the object is:

```text
class_id x_center y_center width height
```

The coordinates are normalized from `0` to `1`. Example:

```text
0 0.512 0.438 0.214 0.180
```

So the training loop is:

```text
capture images on robot
  -> pull images to laptop
  -> draw bounding boxes with a labeling tool
  -> export dataset in YOLO format
  -> train YOLO on laptop/cloud
  -> export a small model for Raspberry Pi
  -> copy model to robot
  -> restart backend / robot logic
```

The model does not learn from new captures until you retrain or fine-tune it and copy the new model to the robot.

### Laptop: pull new captures before labeling

Run this on the laptop:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

export SUTD_RA_DESIGN_PROJECT_DATA=$PWD/Web-dashboard/data

mkdir -p "$SUTD_RA_DESIGN_PROJECT_DATA"

rsync -av \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  pi@192.168.149.1:~/Web-dashboard/data/ \
  "$SUTD_RA_DESIGN_PROJECT_DATA"/
```

After pulling images, keep the original captured folders as your raw dataset archive. The YOLO training dataset is a separate labeled copy prepared in the next section.

### Laptop: train YOLO

Run these steps on the laptop.

Create the YOLO dataset folders:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

mkdir -p yolo_dataset/sortibot_detector/images/train
mkdir -p yolo_dataset/sortibot_detector/images/val
mkdir -p yolo_dataset/sortibot_detector/labels/train
mkdir -p yolo_dataset/sortibot_detector/labels/val
```

Save this file as:

```text
yolo_dataset/sortibot_detector/data.yaml
```

File content:

```yaml
path: yolo_dataset/sortibot_detector
train: images/train
val: images/val
names:
  0: floor_object
```

`floor_object` means: **any visible object on the floor that the robot should stop and inspect**. It is only a detector class. It does not mean trash, keep, or ignore. YOLO will find the object box, then OpenCLIP will classify the cropped object as Trash / Keep / Ignore.

Copy selected images from the pulled capture folders into the YOLO dataset:

```text
Web-dashboard/data/trash/   -> yolo_dataset/sortibot_detector/images/train or images/val
Web-dashboard/data/keep/    -> yolo_dataset/sortibot_detector/images/train or images/val
Web-dashboard/data/ignore/  -> yolo_dataset/sortibot_detector/images/train or images/val
```

Use this split:

- Put about 80% of useful images into `images/train`.
- Put about 20% of useful images into `images/val`.
- Include images from `trash`, `keep`, and `ignore` in both splits if possible.
- Do not copy very blurry images unless you intentionally want the detector to learn that condition.
- For the one-class detector, all labeled objects use class id `0` because all boxes are `floor_object`.

Example:

```text
yolo_dataset/sortibot_detector/images/train/wrapper_001.jpg
yolo_dataset/sortibot_detector/labels/train/wrapper_001.txt

yolo_dataset/sortibot_detector/images/val/toy_car_001.jpg
yolo_dataset/sortibot_detector/labels/val/toy_car_001.txt
```

Each image must have a matching label file with the same base name:

```text
images/train/wrapper_001.jpg
labels/train/wrapper_001.txt
```

Initially, the label files are empty. Then they will contain bounding boxes:

```text
0 x_center y_center width height
```

Use a labeling tool to draw one box around each object and export YOLO-format labels. Recommended for this project: **CVAT**. It supports bounding-box annotation and YOLO export, works well for small object-detection datasets, and avoids depending on a paid dataset-hosting workflow.

Clone CVAT by using
```
git clone https://github.com/cvat-ai/cvat.git
```

Other options:

- Roboflow: convenient hosted workflow, but more platform-dependent.
- Label Studio: flexible, but more general-purpose than needed for simple YOLO boxes.
- labelImg: simple, but no longer actively developed; use it only if you want a very lightweight local tool.

### Laptop: label YOLO images with CVAT

Run this on the laptop to start CVAT from the clone inside this project:

```bash
open -a Docker
```

Wait until Docker Desktop fully starts. It can take 30-90 seconds.

Check that Docker is running:

```bash
docker info
```

If it prints system info, Docker is running. Then start CVAT:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project/cvat

docker-compose up -d
docker exec -it cvat_server bash -ic 'python3 ~/manage.py createsuperuser'
```

Open CVAT:

```text
http://localhost:8080
```

Create upload ZIP files for the train and validation images:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

mkdir -p /tmp/sortibot_cvat_uploads

(cd yolo_dataset/sortibot_detector/images/train && zip -r /tmp/sortibot_cvat_uploads/sortibot_train_images.zip .)
(cd yolo_dataset/sortibot_detector/images/val && zip -r /tmp/sortibot_cvat_uploads/sortibot_val_images.zip .)
```

In CVAT:

```text
1. Create a project or task.
2. Add one label: floor_object.
3. Create one task for train images and upload /tmp/sortibot_cvat_uploads/sortibot_train_images.zip.
4. Create one task for val images and upload /tmp/sortibot_cvat_uploads/sortibot_val_images.zip.
5. Draw one bounding box around each object.
6. Export annotations in YOLO format.
```

After exporting from CVAT, copy the exported `.txt` label files into the matching folder:

```text
train export .txt files -> yolo_dataset/sortibot_detector/labels/train/
val export .txt files   -> yolo_dataset/sortibot_detector/labels/val/
```

The label filenames must match the image filenames:

```text
yolo_dataset/sortibot_detector/images/train/20260619_155110_064113.jpg
yolo_dataset/sortibot_detector/labels/train/20260619_155110_064113.txt
```

Stop CVAT when you are done:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project/cvat

docker-compose down
```

Later, if you decide to train YOLO to detect semantic categories directly, replace the `names` block in the same file, `yolo_dataset/sortibot_detector/data.yaml`, with:

```yaml
names:
  0: trash_like_object
  1: useful_object
  2: unknown_object
```

For the current stage, keep one class named `floor_object` because OpenCLIP will classify the crop.

### Laptop: back up YOLO dataset

Run this on the laptop after creating or updating the YOLO dataset. It mirrors `yolo_dataset/sortibot_detector/` into `$SUTD_RA_DESIGN_PROJECT_YOLO_DATASET` and removes files from the destination that no longer exist in the local dataset.

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

mkdir -p "$SUTD_RA_DESIGN_PROJECT_YOLO_DATASET"

rsync -av --delete \
  yolo_dataset/sortibot_detector/ \
  "$SUTD_RA_DESIGN_PROJECT_YOLO_DATASET"/
```

After the dataset is prepared, install Ultralytics and train:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

python3 -m venv .yolo-train-venv
source .yolo-train-venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install ultralytics

yolo detect train \
  model=$PWD/yolo26n.pt \
  data=$PWD/yolo_dataset/sortibot_detector/data.yaml \
  imgsz=640 \
  epochs=80 \
  batch=8 \
  project=$PWD/runs/sortibot \
  name=floor_object_detector
```

If your Ultralytics version does not have `yolo26n.pt`, use the nano model available in that version, for example `yolo11n.pt`.

On an Apple Silicon laptop, you can try:

```bash
yolo detect train \
  model=$PWD/yolo26n.pt \
  data=$PWD/yolo_dataset/sortibot_detector/data.yaml \
  imgsz=640 \
  epochs=80 \
  batch=8 \
  device=mps \
  project=$PWD/runs/sortibot \
  name=floor_object_detector
```

Observed training time on this dataset:

```text
80 epochs completed in 0.080 hours with MPS.
80 epochs completed in 0.90 hours with CPU.
```

Training on the Raspberry Pi itself is not recommended. It is much slower and can fill the SD card. Train on the laptop or a cloud GPU, then copy only the exported model to the robot.

### Laptop: back up YOLO training runs

Do not save `runs/` inside `$SUTD_RA_DESIGN_PROJECT_YOLO_DATASET`. The dataset backup command uses `--delete`, so it should mirror only the dataset. Keep training outputs in a separate backup location.

Run this on the laptop after training:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

: "${SUTD_RA_DESIGN_PROJECT_YOLO_RUNS:?Set SUTD_RA_DESIGN_PROJECT_YOLO_RUNS first}"

mkdir -p "$SUTD_RA_DESIGN_PROJECT_YOLO_RUNS"

rsync -av --delete \
  runs/sortibot/ \
  "$SUTD_RA_DESIGN_PROJECT_YOLO_RUNS"/
```

### Laptop: validate and export for Raspberry Pi

Run this on the laptop:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project
source .yolo-train-venv/bin/activate

yolo detect val \
  model=$PWD/runs/sortibot/floor_object_detector/weights/best.pt \
  data=$PWD/yolo_dataset/sortibot_detector/data.yaml \
  imgsz=640 \
  project=$PWD/runs/sortibot \
  name=floor_object_detector_val

yolo export \
  model=$PWD/runs/sortibot/floor_object_detector/weights/best.pt \
  format=ncnn \
  imgsz=640
```

The export should create a folder similar to:

```text
runs/sortibot/floor_object_detector/weights/best_ncnn_model/
```

NCNN is preferred for Raspberry Pi because it is optimized for ARM/mobile inference.

### Laptop: copy YOLO model to robot

Run this on the laptop:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

ssh -i $HOME/.ssh/sortibot_ed25519 pi@192.168.149.1 \
  "mkdir -p ~/Web-dashboard/models/detector"

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  $PWD/runs/sortibot/floor_object_detector/weights/best_ncnn_model/ \
  pi@192.168.149.1:~/Web-dashboard/models/detector/sortibot_yolo_ncnn_model/
```

Model files should stay out of git. Store the active robot model here:

```text
~/Web-dashboard/models/detector/sortibot_yolo_ncnn_model/
```

The matching local laptop path can be:

```text
Web-dashboard/models/detector/sortibot_yolo_ncnn_model/
```

but it is ignored by git.

### Robot: install YOLO runtime package

Run this on the robot after CPU-only PyTorch is already installed:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python -m pip install --no-cache-dir ultralytics
```

Do not install YOLO/Ultralytics before the CPU-only PyTorch step. Otherwise pip may try to pull a large or wrong PyTorch dependency set.

### Robot: quick YOLO model test

Run this on the laptop first to copy the latest backend code to the robot:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  --exclude ".openclip-download-venv" \
  --exclude ".yolo-train-venv" \
  Web-dashboard/backend/ \
  pi@192.168.149.1:~/Web-dashboard/backend/
```

Run this on the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python - <<'PY'
from ultralytics import YOLO

model = YOLO("/home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model")
results = model("/home/pi/Web-dashboard/data/trash/20260619_155044_618393.jpg", imgsz=640, conf=0.25)
print(results[0].boxes)
PY
```

Use any existing image path on the robot if that sample image is not present.

Expected output is either a `Boxes(...)` object with detections or an empty boxes object if the model runs but does not detect anything in that image.

Example successful output with a detection:

```text
ultralytics.engine.results.Boxes object with attributes:
...
cls: tensor([0.])
conf: tensor([0.82])
xyxy: tensor([[123.4, 210.5, 356.7, 420.1]])
```

Example successful output with no detections:

```text
ultralytics.engine.results.Boxes object with attributes:
...
cls: tensor([])
conf: tensor([])
xyxy: tensor([], size=(0, 4))
```

If you see an import error, model path error, or NCNN loading error, the runtime package or copied model folder is not set up correctly.

### Robot: legacy YOLO + ultrasonic one-meter object search test

This is a legacy/reference test from the earlier implementation. It uses the custom YOLO model plus ultrasonic distance. The current recommended approach is the LAB/color contrast visual-servo test in the next section.

This test drives forward, checks camera frames with YOLO, stops when a `floor_object` is detected, crops the detected box, then classifies the crop with OpenCLIP as `Trash`, `Keep`, or `Ignore`.

Run this on the robot first without moving the motors:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python object_search_test.py --motion dry-run --max-seconds 5
```

Expected log with an object:

```text
[test] motion backend: dry-run
[motion] dry-run forward
[2026-07-01T15:10:30] detected floor_object confidence=0.856 box=(260, 178, 345, 265)
[2026-07-01T15:10:30] detected Trash confidence=0.982 prompt='a photo of a plastic wrapper on the floor'
```

Expected log with no object:

```text
[test] motion backend: dry-run
[motion] dry-run forward
[test] no object detected
```

Then run the movement test on the robot. Use `--motion auto` for normal testing because it loads the MasterPi/Hiwonder mecanum API:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python object_search_test.py \
  --motion auto \
  --distance-meters 1.0 \
  --meters-per-second 0.20 \
  --stop-distance-cm 15 \
  --speed 35 \
  --direction 90
```

The `1.0` meter distance is a timed maximum: `distance-meters / meters-per-second`. With `--stop-distance-cm 15`, the robot keeps moving after YOLO first sees an object, then stops when the ultrasonic sensor reports about `15 cm` or less. Start with `15` to `20 cm`; reduce toward `10 cm` only after it stops reliably.

Adjust `--meters-per-second`, `--speed`, `--direction`, and `--stop-distance-cm` after testing on the floor. If the robot does not move forward with `--direction 90`, stop the test and try the correct Hiwonder mecanum direction for forward motion.

You can also force the Hiwonder backend directly:

```bash
python object_search_test.py --motion hiwonder --max-seconds 5
```

## YOLO v2 red/purple direct-label workflow

This is the current trained-detector path for the lab floor test. Keep it separate from the older optional YOLO workflow above:

- Old YOLO flow: one class named `floor_object`, then OpenCLIP decides `trash`, `keep`, or `ignore`.
- YOLO v2 flow: two detector classes named `red_useful` and `purple_trash`; the visual-servo script can use those detector labels directly.

Use separate folders so v1 and v2 files do not overwrite each other:

```text
yolo_dataset_v2/sortibot_detector/
runs_v2/sortibot/red_purple_detector/
```

### Laptop: collect robot-camera images

Use robot-camera images, not phone images. The model must learn the robot camera's exposure, lens distortion, floor texture, object size, and low viewpoint.

Recommended minimum dataset:

```text
red_useful:      60-100 images with boxes
purple_trash:    60-100 images with boxes
ignore:          30-50 empty-floor images with no boxes
hard negatives:  20-40 images with no boxes
```

Hard negatives are images that look tempting but should not be detected: floor speckles, shadows, wall edges, wires, hands, robot body parts, reflections, and other non-target objects.

Images with the robot overlay text such as `Voltage: 7.3V` are acceptable because that overlay is part of the real robot camera output. If it causes false positives later, add more ignore/hard-negative images with the same overlay.

### Laptop: create the v2 dataset folders

Run this on the laptop:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

mkdir -p yolo_dataset_v2/raw/keep
mkdir -p yolo_dataset_v2/raw/trash
mkdir -p yolo_dataset_v2/raw/ignore

mkdir -p yolo_dataset_v2/sortibot_detector/images/train
mkdir -p yolo_dataset_v2/sortibot_detector/images/val
mkdir -p yolo_dataset_v2/sortibot_detector/labels/train
mkdir -p yolo_dataset_v2/sortibot_detector/labels/val
```

Store the raw captures here:

```text
yolo_dataset_v2/raw/keep/    -> red cube / useful object
yolo_dataset_v2/raw/trash/   -> purple trash object
yolo_dataset_v2/raw/ignore/  -> empty floor and hard negatives
```

Then copy selected images into the train/val image folders.

Do not split frame-by-frame from one continuous sequence. Keep whole object positions/chunks together. A good split is about 80% train and 20% validation, but the validation set must include different positions/distances/angles from the train set.

Save this file as `yolo_dataset_v2/sortibot_detector/data.yaml`:

```yaml
path: yolo_dataset_v2/sortibot_detector
train: images/train
val: images/val

names:
  0: red_useful
  1: purple_trash
```

### Laptop: label v2 images with local CVAT

Run local CVAT from the project clone:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

git clone https://github.com/cvat-ai/cvat.git

open -a Docker
```

Wait until Docker Desktop is running, then:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project/cvat

docker-compose up -d
docker exec -it cvat_server bash -ic 'python3 ~/manage.py createsuperuser'
```

Open CVAT:

```text
http://localhost:8080
```

Create one project or task with exactly these labels:

```text
red_useful
purple_trash
```

Prepare one upload ZIP from the images you want to label:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

mkdir -p /tmp/sortibot_cvat_uploads

(cd yolo_dataset_v2/raw && zip -r /tmp/sortibot_cvat_uploads/sortibot_yolo_v2_raw.zip keep trash ignore)
```

In CVAT:

```text
1. Create a task under the v2 project.
2. Upload /tmp/sortibot_cvat_uploads/sortibot_yolo_v2_raw.zip.
3. Draw boxes only around the red useful object and the purple trash object.
4. Leave ignore, empty-floor, and hard-negative images with no boxes.
5. Export task dataset.
6. Format: YOLO 1.1.
7. Save images: yes.
```

It is normal that the exported images do not visually show boxes. YOLO export stores boxes in `.txt` label files, not burned into the image pixels.

Stop CVAT when finished:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project/cvat

docker-compose down
```

### Laptop: copy exported CVAT labels into the v2 dataset

Unzip the CVAT export into:

```text
yolo_dataset_v2/cvat_export/
```

For the current CVAT export layout, labels are under:

```text
yolo_dataset_v2/cvat_export/obj_train_data/keep/
yolo_dataset_v2/cvat_export/obj_train_data/trash/
yolo_dataset_v2/cvat_export/obj_train_data/ignore/
```

Copy each exported `.txt` file beside the matching train/val split. Empty `.txt` files are correct for ignore and hard-negative images.

If the image files are already split into `images/train` and `images/val`, run:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

mkdir -p yolo_dataset_v2/sortibot_detector/labels/train
mkdir -p yolo_dataset_v2/sortibot_detector/labels/val

find yolo_dataset_v2/sortibot_detector/images/train -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) -print0 |
while IFS= read -r -d '' image_path; do
  base="$(basename "${image_path%.*}")"
  label_path="$(find yolo_dataset_v2/cvat_export/obj_train_data -name "$base.txt" -print -quit)"
  if [ -n "$label_path" ]; then
    cp "$label_path" "yolo_dataset_v2/sortibot_detector/labels/train/$base.txt"
  else
    : > "yolo_dataset_v2/sortibot_detector/labels/train/$base.txt"
  fi
done

find yolo_dataset_v2/sortibot_detector/images/val -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) -print0 |
while IFS= read -r -d '' image_path; do
  base="$(basename "${image_path%.*}")"
  label_path="$(find yolo_dataset_v2/cvat_export/obj_train_data -name "$base.txt" -print -quit)"
  if [ -n "$label_path" ]; then
    cp "$label_path" "yolo_dataset_v2/sortibot_detector/labels/val/$base.txt"
  else
    : > "yolo_dataset_v2/sortibot_detector/labels/val/$base.txt"
  fi
done
```

Sanity-check the dataset before training:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

find yolo_dataset_v2/sortibot_detector/images/train -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) | wc -l
find yolo_dataset_v2/sortibot_detector/labels/train -type f -name '*.txt' | wc -l

find yolo_dataset_v2/sortibot_detector/images/val -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) | wc -l
find yolo_dataset_v2/sortibot_detector/labels/val -type f -name '*.txt' | wc -l

awk '{print $1}' yolo_dataset_v2/sortibot_detector/labels/train/*.txt yolo_dataset_v2/sortibot_detector/labels/val/*.txt | sort | uniq -c
find yolo_dataset_v2/sortibot_detector/labels -type f -name '*.txt' -empty | wc -l
```

Expected class IDs:

```text
0 -> red_useful
1 -> purple_trash
```

The image count and label count should match for each split. Empty label files are expected for ignore and hard-negative images.

### Laptop: train YOLO v2 on Apple Silicon

Run this on the laptop:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

python3 -m venv .yolo-train-venv
source .yolo-train-venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install ultralytics
```

Train with MPS on Apple Silicon:

```bash
yolo detect train \
  model=yolo11n.pt \
  data="$PWD/yolo_dataset_v2/sortibot_detector/data.yaml" \
  imgsz=640 \
  epochs=80 \
  batch=8 \
  device=mps \
  project="$PWD/runs_v2/sortibot" \
  name=red_purple_detector
```

If MPS fails, use CPU:

```bash
yolo detect train \
  model=yolo11n.pt \
  data="$PWD/yolo_dataset_v2/sortibot_detector/data.yaml" \
  imgsz=640 \
  epochs=80 \
  batch=8 \
  device=cpu \
  project="$PWD/runs_v2/sortibot" \
  name=red_purple_detector
```

The training device does not affect robot deployment. The robot uses the exported NCNN model, not MPS.

### Laptop: validate predictions visually

Run prediction on the validation split:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project
source .yolo-train-venv/bin/activate

yolo detect predict \
  model="$PWD/runs_v2/sortibot/red_purple_detector/weights/best.pt" \
  source="$PWD/yolo_dataset_v2/sortibot_detector/images/val" \
  imgsz=640 \
  conf=0.25 \
  project="$PWD/runs_v2/sortibot" \
  name=red_purple_detector_val_predict
```

Inspect the generated images:

```text
runs_v2/sortibot/red_purple_detector_val_predict/
```

Good signs:

- Red cube images are labeled `red_useful`.
- Purple object images are labeled `purple_trash`.
- Empty floor and hard-negative images have no boxes.
- Small/far objects are detected at least often enough for the robot to approach during a 12 second test.

### Laptop: export YOLO v2 to NCNN

Run this on the laptop:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project
source .yolo-train-venv/bin/activate

yolo export \
  model="$PWD/runs_v2/sortibot/red_purple_detector/weights/best.pt" \
  format=ncnn \
  imgsz=640
```

The export should create:

```text
runs_v2/sortibot/red_purple_detector/weights/best_ncnn_model/
```

Expected files:

```text
metadata.yaml
model.ncnn.bin
model.ncnn.param
model_ncnn.py
```

### Laptop: copy YOLO v2 backend and model to robot

Run this on the laptop:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  --exclude ".openclip-download-venv" \
  --exclude ".yolo-train-venv" \
  Web-dashboard/backend/ \
  pi@192.168.149.1:~/Web-dashboard/backend/

ssh -i $HOME/.ssh/sortibot_ed25519 pi@192.168.149.1 \
  "mkdir -p ~/Web-dashboard/models/detector/sortibot_yolo_ncnn_model"

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  runs_v2/sortibot/red_purple_detector/weights/best_ncnn_model/ \
  pi@192.168.149.1:~/Web-dashboard/models/detector/sortibot_yolo_ncnn_model/
```

Do not copy the laptop `.venv`, `runs_v2/`, or raw dataset to the robot. The robot needs only:

```text
~/Web-dashboard/backend/
~/Web-dashboard/models/detector/sortibot_yolo_ncnn_model/
```

### Robot: install YOLO runtime for v2

Run this on the robot after the backend venv exists:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python -m pip install --no-cache-dir ultralytics
```

If the robot has no internet in access-point mode, connect internet with the USB Wi-Fi adapter first, or install the package while the robot is on an internet-connected network.

### Robot: quick YOLO v2 model test

Run this on the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python - <<'PY'
from ultralytics import YOLO

model = YOLO("/home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model", task="detect")
print(model.names)
PY
```

Expected names:

```text
{0: 'red_useful', 1: 'purple_trash'}
```

If this fails with `No module named ultralytics`, install the YOLO runtime in the robot venv. If it fails with a model path error, copy the NCNN folder again.

### Robot: YOLO v2 visual-servo approach test

Run this on the robot first with `--motion dry-run` if you only want to verify detections and commands without motor movement. Use `--motion auto` for the real MasterPi test.

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python object_visual_servo_test.py \
  --motion auto \
  --detector yolo \
  --classification-mode detector-label \
  --model /home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model \
  --max-seconds 12 \
  --conf 0.35 \
  --target-bottom-ratio 0.68 \
  --x-deadband-ratio 0.06 \
  --bottom-deadband-ratio 0.03 \
  --close-bottom-error-ratio 0.0 \
  --close-x-deadband-ratio 0.18 \
  --search-y-speed 20 \
  --max-x-speed 18 \
  --max-y-speed 20 \
  --uncentered-y-scale 0.35 \
  --approach-labels red_useful,purple_trash \
  --stable-frames 3 \
  --pickup-frames 2 \
  --debug-frame-dir ~/Web-dashboard/data/debug_detections \
  --debug-latest-frame ~/Web-dashboard/data/debug_detections/latest.jpg
```

Expected behavior:

- If the red cube is visible, the script should print `red_useful` and approach it.
- If the purple object is visible, the script should print `purple_trash` and approach it.
- If only floor/ignore objects are visible, the script should not approach a false box.
- The latest annotated frame is written to `~/Web-dashboard/data/debug_detections/latest.jpg`.

If the script says `unrecognized arguments: --classification-mode`, the backend code on the robot is old. Copy `Web-dashboard/backend/` to the robot again.

If the robot detects the object but drives past it, lower `--search-y-speed` and `--max-y-speed`, then increase `--close-x-deadband-ratio` slightly. Do not start gripper testing until the approach stop position is repeatable.

### Robot: LAB/color contrast visual-servo approach test

This is the recommended approach for the current demo assumption: the floor is light, and target objects are darker or more saturated than the floor. The LAB/color contrast detector finds a compact non-floor blob, OpenCLIP classifies the crop as `trash`, `keep`, or `ignore`, then the robot uses mecanum `translation(x, y)` commands to center and approach only if the classification label is in `--approach-labels`.

The pickup zone is not a classifier decision. It is only the camera position where the gripper should be able to reach the already-classified object.

Run this on the laptop first to copy the latest backend code to the robot:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  --exclude ".openclip-download-venv" \
  --exclude ".yolo-train-venv" \
  Web-dashboard/backend/ \
  pi@192.168.149.1:~/Web-dashboard/backend/
```

Optional but recommended: test the detector on a saved robot image before moving the robot:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project
source .yolo-train-venv/bin/activate

python Web-dashboard/backend/test_contrast_detector_image.py \
  "$HOME/Desktop/sortibot_debug_detections/latest.jpg" \
  --color-mode blue \
  --output "$HOME/Desktop/sortibot_debug_detections/latest.contrast.jpg" \
  --mask-output "$HOME/Desktop/sortibot_debug_detections/latest.mask.jpg"
```

Expected output is one or more detections with a tight box around the actual blue object, not a large floor region or non-blue object.

Run this on the robot first without moving the motors:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python object_visual_servo_test.py \
  --motion dry-run \
  --max-seconds 5 \
  --detector contrast \
  --contrast-color-mode blue \
  --debug-frame-dir ~/Web-dashboard/data/debug_detections \
  --debug-latest-frame ~/Web-dashboard/data/debug_detections/latest.jpg
```

Expected output is a stream of `no object visible`, `stabilizing`, `classified Trash/Keep/Ignore`, or `cmd=(x,y)` messages. The robot approaches only when the OpenCLIP label is included in `--approach-labels`. Use `trash,keep,ignore` while tuning movement with test objects; use `trash,keep` for real behavior.

Then run this on the robot with the MasterPi motion backend:

If the camera position changes with arm pose, put the arm into a repeatable camera pose before the approach run. This uses the same IK home coordinate as the grab sequence:

```bash
python object_visual_servo_test.py \
  --home-arm-only \
  --grab-home-x-cm 0 \
  --grab-home-y-cm 3 \
  --grab-home-z-cm 28
```

For the actual approach run, keep `--home-arm-before-approach` in the command so every run starts from the same arm/camera pose.

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python object_visual_servo_test.py \
  --motion auto \
  --detector yolo \
  --classification-mode detector-label \
  --model /home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model \
  --max-seconds 25 \
  --conf 0.35 \
  --target-x-ratio 0.50 \
  --target-bottom-ratio 0.94 \
  --x-deadband-ratio 0.06 \
  --bottom-deadband-ratio 0.04 \
  --close-bottom-error-ratio 0.0 \
  --close-x-deadband-ratio 0.20 \
  --search-y-speed 16 \
  --max-x-speed 48 \
  --min-x-speed 32 \
  --max-y-speed 48 \
  --min-y-speed 32 \
  --grab-home-x-cm 0 \
  --grab-home-y-cm 3 \
  --grab-home-z-cm 28 \
  --kp-x 120 \
  --kp-y 45 \
  --uncentered-y-scale 0.3 \
  --approach-labels red_useful,purple_trash \
  --stable-frames 2 \
  --pickup-frames 1 \
  --speed 24 \
  --direction 90 \
  --home-arm-before-approach \
  --debug-frame-dir ~/Web-dashboard/data/debug_detections \
  --debug-latest-frame ~/Web-dashboard/data/debug_detections/latest.jpg
```

Tune these values one at a time:

- `--contrast-color-mode`: use `blue` for the current demo so only blue objects are detected. Use `all` only if you intentionally want the old saturated/dark foreground detector.
- `--contrast-blue-hue-min`, `--contrast-blue-hue-max`: widen this range if a blue object is missed because the camera sees it as cyan or purple; narrow it if other colors are detected.
- `--contrast-blue-min-saturation`: lower it if pale blue objects are missed; raise it if gray floor regions are detected.
- `--contrast-blue-min-value`, `--contrast-blue-max-value`: adjust these if blue objects are missed in shadows or glare.
- `--contrast-use-lab`: leave this off on rough/textured floors. LAB contrast can treat normal floor texture as an object. Use it only on smoother floors.
- `--contrast-lab-delta`: only matters when `--contrast-use-lab` is enabled. Lower it if objects are missed; raise it if floor texture is detected.
- `--contrast-min-saturation`: lower it if colored objects are missed; raise it if floor texture is detected.
- `--contrast-dark-value`: raise it if dark objects are missed; lower it if shadows are detected.
- `--contrast-min-area`: lower it if small objects are missed; raise it if noise is detected.
- `--contrast-max-area-ratio`: lower it if huge floor/background regions are detected.
- `--contrast-max-box-width-ratio`, `--contrast-max-box-height-ratio`: lower these if the detector draws wide boxes over the floor instead of a compact object.
- `--contrast-roi-top-ratio`: increase it if the detector sees wall/background above the floor; decrease it if far objects are cut off.
- `--contrast-roi-bottom-ratio`: decrease it if the detector sees the green voltage overlay or nearby floor texture.
- `--target-bottom-ratio`: increase it if the robot stops too far away; decrease it if it gets too close.
- `--home-arm-before-approach`: use this when the arm changes the camera position. It moves the arm to `--grab-home-x-cm`, `--grab-home-y-cm`, `--grab-home-z-cm` before the camera loop starts.
- `--speed`: controls the no-object search speed when using the Hiwonder forward command.
- `--max-y-speed`: decrease this if the robot overshoots the object during visual-servo approach.
- `--x-deadband-ratio`: increase this if the robot keeps correcting left/right instead of stopping.
- `--close-bottom-error-ratio`: keep this at `0.0` so the robot stops lateral correction once the object reaches the stop line.
- `--close-x-deadband-ratio`: increase this if the robot reaches the object but keeps strafing past it instead of stopping.
- `--uncentered-y-scale`: use `0.35` so the robot creeps forward while correcting left/right. If this is `0`, the robot tries pure sideways centering first; on some floors this can look like the robot detected the object but did not move.
- `--invert-x-control`: add this if the object moves farther from the center line while tracking.
- `--approach-labels`: use `trash,keep,ignore` while tuning movement with a test object; use `trash,keep` for real behavior.
- `--ignore-cooldown-frames`: increase this if the same ignored object is classified repeatedly.

If the script prints `no object visible` but the robot does not move, check the motion backend line. It must be `motion backend: hiwonder-mecanum`, not `dry-run`. If it is `hiwonder-mecanum` and still does not move, increase `--speed` to `35`.

The visual-servo script now runs the IK grab sequence automatically after the robot reaches the pickup zone. While tuning movement only, add `--no-grab` so the robot stops without moving the arm:

```bash
python object_visual_servo_test.py \
  --motion auto \
  --max-seconds 12 \
  --detector contrast \
  --target-bottom-ratio 0.68 \
  --debug-frame-dir ~/Web-dashboard/data/debug_detections \
  --debug-latest-frame ~/Web-dashboard/data/debug_detections/latest.jpg \
  --no-grab
```

When the robot reliably stops in a grabbable position, remove `--no-grab` and tune the fixed capture-coordinate grab:

```bash
python object_visual_servo_test.py \
  --motion auto \
  --max-seconds 12 \
  --detector contrast \
  --target-bottom-ratio 0.68 \
  --debug-frame-dir ~/Web-dashboard/data/debug_detections \
  --debug-latest-frame ~/Web-dashboard/data/debug_detections/latest.jpg \
  --grab-x-cm 0 \
  --grab-y-cm 16.5 \
  --grab-z-cm 2
```

The default grab coordinate comes from the Hiwonder color-sorting sample capture point. It may need calibration on the real robot. Gripper and approach parameters can be adjusted with `--gripper-open-pulse`, `--gripper-close-pulse`, `--grab-lift-cm`, `--grab-pitch`, `--grab-pitch-min`, and `--grab-pitch-max`.

Test the ultrasonic sensor by itself on the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python - <<'PY'
from robot_sonar import SonarDistanceSensor
import time

sensor = SonarDistanceSensor()
for _ in range(10):
    print(f"{sensor.read_cm():.1f} cm")
    time.sleep(0.2)
PY
```

The MasterPi sonar API returns millimeters. The SortiBot wrapper converts it to centimeters.

If the script prints `motion backend: dry-run`, it did not find the robot motion API. Run this on the robot and inspect the import failures:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python object_search_test.py --motion auto --motion-debug --max-seconds 2
```

If the debug output includes `ModuleNotFoundError("No module named 'serial'")`, install the serial package in the robot venv:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python -m pip install --no-cache-dir pyserial
```

If the ultrasonic sensor fails with `ModuleNotFoundError("No module named 'smbus2'")`, install the I2C package in the robot venv:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python -m pip install --no-cache-dir smbus2
```

For the current MasterPi setup, use `--motion auto` or `--motion hiwonder`.

The script always sends `stop` in a `finally` block, so it should stop the motors even if detection/classification raises an error.

### How to refresh the optional YOLO model after adding images

This applies only if you are using the optional YOLO path. The current LAB/color contrast detector does not require YOLO retraining; tune the `--contrast-*` parameters instead.

When you capture more images:

1. Run **Laptop: pull new captures before labeling**.
2. Add useful images to the YOLO dataset.
3. Draw bounding boxes and export YOLO labels.
4. Retrain or fine-tune YOLO on the laptop.
5. Export the new `best.pt` to NCNN.
6. Copy the exported model folder to `~/Web-dashboard/models/detector/sortibot_yolo_ncnn_model/`.
7. Restart the backend so it loads the new model.

Run this on the robot to restart the backend:

```bash
# If uvicorn is already running, press Ctrl+C first.

cd ~/Web-dashboard/backend
source .venv/bin/activate
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```
