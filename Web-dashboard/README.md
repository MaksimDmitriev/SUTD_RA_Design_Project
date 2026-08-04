# SortiBot Web Dashboard

Minimal React + FastAPI dashboard for the MasterPi robot.

## High-level system flow

Target robot behavior:

```text
robot moves forward slowly
  -> camera captures the floor scene
  -> two-class YOLO detects red_useful or purple_trash
  -> floor projection estimates the object's forward and lateral position
  -> robot moves partway, stops, re-detects, and corrects its heading
  -> arm aligns above the object and grabs it
  -> detector label selects the useful or trash release pose
```

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
    object_visual_servo_test.py
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

⚠️ Only use `--delete` if you are sure you are copying the source of truth.

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

python -m pip install --no-cache-dir ultralytics
```

The package installation order matters:

1. Update installer tools: `pip`, `setuptools`, `wheel`.
2. Install dashboard packages from `requirements.txt`.
3. Install CPU-only PyTorch from the PyTorch CPU wheel index.
4. Install the Ultralytics YOLO runtime.

Install CPU-only PyTorch before Ultralytics on the Raspberry Pi. This avoids downloading an unsuitable or unnecessarily large dependency set.

Verify the imports before starting the backend or robot movement scripts:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python -c "import cv2; import fastapi; import numpy; import PIL; import serial; import smbus2; import torch; import torchvision; import ultralytics; print('robot Python deps OK')"
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

Save the current values before changing them so you can restore the initial configuration later on if needed. 
The current values are the output of the following command:

```bash
v4l2-ctl -d /dev/video0 --all
```

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


## YOLO v2 red/purple direct-label workflow

YOLO v2 is the trained-detector path for the lab floor test. The detector has two classes, `red_useful` and `purple_trash`, and the visual-servo script uses those detector labels directly.

Dataset and training outputs are stored separately:

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

The final training dataset discussed during development contained 84 red/useful images, 102 purple/trash images, and 90 ignore or hard-negative images.

Hard negatives are images that look tempting but should not be detected: floor speckles, shadows, wall edges, wires, hands, robot body parts, reflections, and other non-target objects.

Images with the robot overlay text such as `Voltage: 7.3V` are acceptable because that overlay is part of the real robot camera output. If it causes false positives later, add more ignore/hard-negative images with the same overlay.

### Laptop: create the YOLO v2 dataset folders

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

### Laptop: label YOLO v2 images with local CVAT

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
1. Create a task under the YOLO v2 detector project.
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

### Laptop: copy exported CVAT labels into the YOLO v2 dataset

Unzip the CVAT export into:

```text
yolo_dataset_v2/cvat_export/
```

For the YOLO v2 CVAT export layout, labels are under:

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

### Laptop: train the YOLO v2 detector on Apple Silicon

Run this on the laptop:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

python3 -m venv .yolo-train-venv
source .yolo-train-venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install ultralytics
```

Train with MPS on Apple Silicon:

MPS lets PyTorch use the Apple Silicon GPU instead of running all training operations on the CPU. On this project dataset, 80 epochs completed in approximately `0.080` hours with MPS, compared with `0.90` hours on CPU. This was about 11 times faster and made repeated training practical while the dataset was being refined.

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

The training device does not affect robot deployment. The robot uses the exported NCNN model, not MPS. Training directly on the Raspberry Pi is not recommended because it is much slower and uses the robot's limited processing and storage resources.

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

### Laptop: export the YOLO v2 detector to NCNN

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

### Laptop: copy the YOLO v2 backend and model to robot

Run this on the laptop:

```bash
cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  --exclude "__pycache__" \
  --exclude ".venv" \
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

### Robot: install the YOLO runtime

Run this on the robot after the backend venv exists:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python -m pip install --no-cache-dir ultralytics
```

If the robot has no internet in access-point mode, connect internet with the USB Wi-Fi adapter first, or install the package while the robot is on an internet-connected network.

### Robot: quick YOLO model test

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

### Robot: YOLO visual-servo approach test

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

If the robot detects the object but drives past it, lower `--search-y-speed` and `--max-y-speed`, then increase `--x-deadband-ratio` slightly. Do not start gripper testing until the approach stop position is repeatable.

### Robot: current floor-distance approach and grab sequence

If the camera position changes with arm pose, put the arm into a repeatable camera pose before the approach run. For the current robot, use the measured `my_home` servo pose from the MasterPi app rather than the IK coordinate. This is more repeatable after a servo replacement because it replays the actual controller pulses.

This is not meant to be magic: the arm servos are controlled by PWM pulse values. A pulse value is the low-level target position sent to one servo. We first moved the arm manually/in the MasterPi app until the camera saw the object from a useful angle, then read the actual pulse values from the controller. Replaying the same pulses puts the joints back into that same camera pose every run. ID1 is the gripper, so it is not part of the camera home pose.

How one pulse value maps to the same joint angle:

A hobby servo is basically a small closed-loop position controller.

```text
input pulse width -> target shaft angle
internal sensor reads current shaft angle
servo motor turns until current angle matches target angle
```

So `1336` is not an arbitrary number to the robot code. It is a pulse width command. The controller repeatedly sends a signal to servo ID3 where the high part of the signal is about `1336` microseconds wide. The servo electronics interpret that pulse width as a target angle.

For example:

```text
ID3 currently at random angle
you send pulse 1336
servo ID3 treats 1336 as its target
servo ID3 rotates until its internal feedback says it reached that target
```

Do not use `--grab-home-x-cm`, `--grab-home-y-cm`, and `--grab-home-z-cm` as the normal camera startup pose unless you are intentionally testing IK. An IK `x,y,z` coordinate describes the end-effector point in space, not the full camera pose. The same end-effector point can still depend on pitch limits, solver choice, servo calibration, and how a replaced servo was mounted. For the camera startup pose we need the same joint angles because the camera is attached to the arm, so raw pulse replay is the more repeatable choice.

```bash
python object_visual_servo_test.py \
  --home-arm-only \
  --home-servo-pulses "3:1336,4:2460,5:1529,6:1480" \
  --home-servo-duration 1.5
```

After copying the updated backend, the same pose is also available as:

```bash
python object_visual_servo_test.py \
  --home-arm-only \
  --home-pose my_home
```

For the actual detect, approach, and grab run, keep `--home-arm-before-approach` in the command so every run starts from the same arm/camera pose. Do not add `--no-grab` for this run; grabbing is enabled by default.

The current preferred chassis approach is `--approach-mode floor-distance`. It projects the YOLO box bottom-center pixel onto the floor plane, estimates `floor_x_cm` and `floor_y_cm`, drives only part of the estimated forward distance while far away, stops, re-detects, and repeats. Inside the configured heading-correction range, it uses `floor_x_cm` to estimate the angle to the object, rotates a little, stops, and remeasures before driving straight. Once the object is inside the trusted near range, it drives to `floor_y_cm + 2.5 cm`, stops, and starts the arm grab sequence. The extra 2.5 cm compensates for the camera being mounted behind the practical arm pickup workspace. This replaces the old final push and does not use the chassis x/bottom proportional controller for the last mile.

The `--grab-x-cm`, `--grab-y-cm`, and `--grab-z-cm` values below are the starting arm capture point used after the robot stops near the object. With `--arm-visual-align`, the camera checks the object again while the arm is hovering above that point and makes small `x/y` IK nudges before the final low grab.

After closing the gripper, the script lifts the object, moves to a release pose, opens the gripper, then returns to the raw camera home pose. The release pose depends on the detector label:

- `purple_trash`: first set `ID5=1500`, then set `ID3=500, ID4=2200, ID6=2500`.
- `red_useful`: first set `ID5=1500`, then set `ID3=500, ID4=2200, ID6=500`.
- After release: set `ID1=2500, ID3=1336, ID4=2460, ID5=1529, ID6=1480`.

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python object_visual_servo_test.py \
  --motion auto \
  --approach-mode floor-distance \
  --detector yolo \
  --classification-mode detector-label \
  --model /home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model \
  --max-seconds 25 \
  --conf 0.35 \
  --home-servo-pulses "1:2500,3:1336,4:2460,5:1529,6:1480" \
  --home-servo-duration 1.5 \
  --open-gripper-before-approach \
  --camera-height-cm 19.6 \
  --camera-pitch-down-deg 17.2 \
  --camera-hfov-deg 79.1 \
  --distance-reliable-cm 30.0 \
  --distance-far-step-fraction 0.5 \
  --distance-max-step-cm 25.0 \
  --distance-drive-speed 24 \
  --distance-drive-cm-per-second 19.0 \
  --distance-heading-deadband-cm 5.0 \
  --distance-heading-min-y-cm 8.0 \
  --distance-heading-max-y-cm 50.0 \
  --distance-heading-max-deg 12.0 \
  --distance-heading-yaw-rate 0.2 \
  --distance-heading-deg-per-second 45.0 \
  --approach-labels red_useful,purple_trash \
  --stable-frames 2 \
  --pickup-frames 1 \
  --speed 24 \
  --direction 90 \
  --home-arm-before-approach \
  --arm-visual-align \
  --arm-align-target-x-ratio 0.50 \
  --arm-align-target-y-ratio 0.55 \
  --arm-align-deadband-ratio 0.08 \
  --arm-align-max-steps 6 \
  --arm-align-step-cm 0.4 \
  --grab-x-cm 0 \
  --grab-y-cm 12.0 \
  --grab-z-cm 0.1 \
  --debug-frame-dir ~/Web-dashboard/data/debug_detections \
  --debug-latest-frame ~/Web-dashboard/data/debug_detections/latest.jpg
```

Tune these values one at a time:

- `--approach-mode floor-distance`: use floor projection instead of the older chassis x/bottom proportional controller for the last-mile approach.
- `--camera-height-cm`, `--camera-pitch-down-deg`, `--camera-hfov-deg`: camera calibration values for the fixed home pose. If the camera or home pose changes, recalibrate these.
- `--distance-reliable-cm`: once projected `floor_y_cm` is at or below this value, trust it for the final move. Start with `30.0` because the recent measured tests were accurate around `20-32 cm`.
- `--distance-far-step-fraction`: when the object is farther than the reliable range, move only this fraction of projected `floor_y_cm`, then stop and remeasure.
- `--distance-max-step-cm`: maximum single forward move. Keep this bounded so one bad far estimate cannot cause a long overshoot.
- `--distance-drive-speed`: Hiwonder forward speed used during timed distance moves.
- `--distance-drive-cm-per-second`: measured real forward speed for `--distance-drive-speed`. Tune this on the actual floor; if it is wrong, the robot will drive the wrong physical distance.
- `--distance-heading-deadband-cm`: ignore horizontal projected offset while `abs(floor_x_cm)` is this small or smaller.
- `--distance-heading-min-y-cm`, `--distance-heading-max-y-cm`: only rotate from `floor_x_cm` inside this forward-distance range. This avoids noisy far-away correction and avoids turning when the object is already under the camera.
- `--distance-heading-max-deg`: maximum single turn before stopping and remeasuring.
- `--distance-heading-yaw-rate`: Hiwonder yaw speed used for the turn. The SDK uses about `-2..2`; keep this conservative.
- `--distance-heading-deg-per-second`: measured real turn rate for the selected yaw rate. If this is wrong, the angle estimate can be correct but the robot will turn the wrong physical amount.
- `--invert-distance-heading`: add this if `floor_x_cm` correction turns the robot away from the object.
- `--post-pickup-drive-seconds`: deprecated. Keep it omitted or `0`; the floor-distance approach ignores the old final push.
- `--arm-visual-align`: after the chassis has stopped, the arm opens the gripper, moves above the grab coordinate, looks through the camera again, and nudges the IK `x/y` coordinate before lowering to grab.
- `--arm-align-target-x-ratio`, `--arm-align-target-y-ratio`: where the object center should appear in the camera frame during arm alignment. Start with `0.50,0.55`; tune these if the gripper is correctly positioned while the object appears slightly off-center in the camera.
- `--arm-align-deadband-ratio`: how close the object center must be to the arm-alignment target point before the script stops nudging and grabs.
- `--arm-align-step-cm`: maximum arm-coordinate movement per alignment nudge. Keep this small; `0.4` means each correction is at most 4 mm.
- `--invert-arm-align-x`, `--invert-arm-align-y`: add one of these if an arm nudge moves the object farther from the target point in the camera image.
- `--home-arm-before-approach`: use this when the arm changes the camera position. It moves the arm before the camera loop starts.
- `--home-pose my_home`: current preferred startup pose. It replays measured PWM servo pulses `ID3=1336`, `ID4=2460`, `ID5=1529`, `ID6=1480`. ID1/gripper is not included.
- `--home-servo-pulses`: override the named home pose with measured values, for example `3:1336,4:2460,5:1529,6:1480`.
- `--home-servo-duration`: how long, in seconds, the controller should take to move from the current joint positions to the requested pulse positions. For example, `--home-servo-duration 1.5` means move over about 1.5 seconds; `1.0` means move faster, over about 1 second.
- `--grab-home-x-cm`, `--grab-home-y-cm`, `--grab-home-z-cm`: only used when `--home-pose ik` is selected.
- `--speed`: controls the no-object search speed when using the Hiwonder forward command.
- `--approach-labels`: keep this set to `red_useful,purple_trash` for the YOLO v2 detector.


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

### Refresh the YOLO v2 model after adding images

When you capture more robot-camera images:

1. Run **Laptop: pull captured images from robot**.
2. Add suitable images to `yolo_dataset_v2` and preserve scene-based train/validation splitting.
3. Draw bounding boxes in CVAT and export YOLO 1.1 labels. Keep hard-negative label files empty.
4. Retrain or fine-tune YOLO11n on the Mac with `device=mps`.
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
