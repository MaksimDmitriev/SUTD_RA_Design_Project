# SortiBot Web Dashboard

Minimal React + FastAPI dashboard for the MasterPi robot.

## High-level system flow

Target robot behavior:

```text
robot moves forward slowly
  -> camera sees possible object
  -> YOLO detects object box
  -> robot stops if box is inside the pickup/search zone
  -> crop object from the frame
  -> OpenCLIP classifies crop as Trash / Keep / Ignore
  -> robot decides: throw away, keep, or ignore
```

In this design:

- YOLO answers: **where is the object?**
- OpenCLIP answers: **what kind of object is it semantically?**
- The policy layer answers: **what should the robot do?**

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

### Robot: start backend

Run this on the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate
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
  --exclude ".openclip-download-venv" \
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
http://192.168.149.1:8000
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

Start with whole-frame classification or a fixed pickup-zone crop. Add YOLO later when you need bounding boxes.

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
2. YOLO crop before OpenCLIP: usually improves classification because background is removed.
3. Threshold/policy tuning: send low-confidence predictions to `ignore`.
4. Train a small classifier on OpenCLIP embeddings using your captured folders.
5. Full OpenCLIP fine-tuning: only if the previous steps fail and you have a much larger dataset.

For the current robot, steps 1-3 are the right priority. Full OpenCLIP fine-tuning is heavy and not recommended on the Raspberry Pi.

## YOLO detection and retraining workflow

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

### Robot: one-meter object search test

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

Then run the movement test on the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python object_search_test.py \
  --motion auto \
  --distance-meters 1.0 \
  --meters-per-second 0.20 \
  --speed 35 \
  --direction 90
```

The `1.0` meter distance is a timed estimate: `distance-meters / meters-per-second`. Adjust `--meters-per-second`, `--speed`, and `--direction` after testing on the floor. If the robot does not move forward with `--direction 90`, stop the test and try the correct Hiwonder mecanum direction for forward motion.

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

If automatic Hiwonder motion loading does not work on the robot, use shell commands as a fallback:

```bash
export SORTIBOT_MOVE_FORWARD_CMD="replace-with-forward-command"
export SORTIBOT_STOP_CMD="replace-with-stop-command"

python object_search_test.py --motion shell --max-seconds 5
```

The script always sends `stop` in a `finally` block, so it should stop the motors even if detection/classification raises an error.

### How to refresh the model after adding images

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
