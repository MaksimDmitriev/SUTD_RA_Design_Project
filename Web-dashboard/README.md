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

Run this on the robot first with `--motion dry-run` if you only want to verify detections and commands without motor movement. Omit `--motion` for the real MasterPi test.

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python object_visual_servo_test.py \
  --distance-reliable-cm 30.0 \
  --distance-far-step-fraction 0.5 \
  --distance-max-step-cm 25.0
```

Expected behavior:

- If the red cube is visible, the script should print `red_useful` and approach it.
- If the purple object is visible, the script should print `purple_trash` and approach it.
- If only floor/ignore objects are visible, the script should not approach a false box.
- The latest annotated frame is written to `~/Web-dashboard/data/debug_detections/latest.jpg`.

If the robot detects the object but drives past it, lower `--search-y-speed` and `--max-y-speed`, then increase `--x-deadband-ratio` slightly. Do not start gripper testing until the approach stop position is repeatable.

### Robot: current floor-distance approach and grab sequence

If the camera position changes with arm pose, put the arm into a repeatable camera pose before the approach run. For the current robot, use the measured `my_home` servo pose from the MasterPi app rather than the IK coordinate. This is more repeatable after a servo replacement because it replays the actual controller pulses.

This is not meant to be magic: the arm servos are controlled by PWM pulse values. A pulse value is the low-level target position sent to one servo. We first moved the arm manually/in the MasterPi app until the camera saw the object from a useful angle, then read the actual pulse values from the controller. Replaying the same pulses puts the joints back into that same camera pose every run. ID1 is the gripper and is kept fully open at pulse 2500 in the home pose.

The fixed home pose is `ID1=2500, ID3=1336, ID4=2460, ID5=1529, ID6=1480`, replayed over 1.5 seconds. Run `python object_visual_servo_test.py --home-arm-only` to command it.

For calibration history, the recorded intermediate pose was `ID1=500, ID3=600, ID4=600, ID5=2300, ID6=600`, and the recorded wall-facing pose was `ID3=1500, ID4=2500, ID5=1500, ID6=1500`. These alternate pulse sets are documentation only; `object_visual_servo_test.py` intentionally no longer accepts arbitrary home pulses.

The temporary notes also recorded another test pose (`ID3=600, ID4=2000, ID5=1300, ID6=1600`) and a floor-looking pose (`ID3=800, ID4=2460, ID5=1529, ID6=1405`).

The intermediate pose was used because small requested changes—such as moving a PWM value from 500 to 520 or 530—sometimes produced no visible movement. The exact cause was not confirmed and could involve an internal control threshold, servo resolution, backlash, or static friction. Starting from a clearly different pose improved the repeatability of the final camera position.

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

To check the floor projection independently, run the dedicated measurement script on the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python measure_bottom_y_ratio.py \
  --debug-frame ~/Web-dashboard/data/debug_detections/floor_projection.jpg
```

The model, confidence, accepted labels, five-frame sample count, arm home pose,
home duration, and calibrated camera geometry are fixed in
`backend/robot_constants.py` and shared with the visual-servo workflow.
The script always projects each detection's bottom-center pixel onto the floor
and reports the estimated robot-frame coordinates.

Two recorded five-frame checks gave `bottom_y_ratio=0.4850` at 74 cm and `bottom_y_ratio=0.5246` at 64 cm from the front edge of the chassis. The closer object appearing lower in the frame is consistent with the floor-projection geometry.

The `--grab-x-cm`, `--grab-y-cm`, and `--grab-z-cm` values are the starting arm capture point used after the robot stops near the object.

After closing the gripper, the script lifts the object, moves to a release pose, opens the gripper, then returns to the raw camera home pose. The release pose depends on the detector label:

- `purple_trash`: first set `ID5=1500`, then set `ID3=500, ID4=2200, ID6=2500`.
- `red_useful`: first set `ID5=1500`, then set `ID3=500, ID4=2200, ID6=500`.
- After release: set `ID1=2500, ID3=1336, ID4=2460, ID5=1529, ID6=1480`.

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python object_visual_servo_test.py \
  --distance-reliable-cm 30.0 \
  --distance-far-step-fraction 0.5 \
  --distance-max-step-cm 25.0
```

Before every run, the script moves the arm to the fixed `my_home` pose and keeps the gripper open at pulse 2500. The floor projection then uses that pose's calibrated camera geometry: optical-center height `19.6 cm`, downward pitch `17.2°`, and horizontal field of view `79.1°`.

The remaining command arguments are:

- `--distance-reliable-cm 30.0`: at or below this projected forward distance, trust the measurement for the final approach move. Farther away, the robot moves only partway and measures again.
- `--distance-far-step-fraction 0.5`: when the object is outside the reliable range, drive half of the projected forward distance before stopping and remeasuring.
- `--distance-max-step-cm 25.0`: cap any single forward movement at 25 cm so a bad projection cannot command one long drive.

#### Robot: left drift and the “move a bit” check

The initial straight-drive checks measured left drift of 3, 6, 11, 14, and 26 cm after 1, 2, 3, 4, and 5 seconds respectively.

The following five-second check helped because it uses `motion.translate(0, 24)`. On the MasterPi backend, `translate` applies the small default yaw correction `+0.017`; the simpler `forward()` path uses yaw `0`. The move therefore tested the compensated drive path—it did not mechanically fix the wheels. No post-change drift distances were recorded, so the improvement is qualitative.

Run this only with clear space in front of the robot:

```bash
cd ~/Web-dashboard/backend
source .venv/bin/activate

python - <<'PY'
import time
from robot_motion import create_motion_backend

speed = 24
seconds = 5.0
motion = create_motion_backend(mode="auto", speed=speed, direction=90)

print(f"Driving forward at speed={speed} for {seconds}s")
try:
    motion.translate(0, speed)
    time.sleep(seconds)
finally:
    motion.stop()
print("Stopped")
PY
```

The floor-distance approach also uses `translate`, so its timed forward moves receive the same yaw correction.

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
