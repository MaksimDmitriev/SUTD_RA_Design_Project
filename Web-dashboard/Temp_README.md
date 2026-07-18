## Run the solution:

```
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
  --search-y-speed 16 \
  --max-x-speed 48 \
  --min-x-speed 32 \
  --max-y-speed 48 \
  --min-y-speed 32 \
  --home-servo-pulses "3:1336,4:2460,5:1529,6:1480" \
  --home-servo-duration 1.5 \
  --kp-x 120 \
  --kp-y 45 \
  --uncentered-y-scale 0.3 \
  --approach-labels red_useful,purple_trash \
  --stable-frames 2 \
  --pickup-frames 1 \
  --speed 24 \
  --direction 90 \
  --home-arm-before-approach \
  --grab-x-cm 0 \
  --grab-y-cm 12.0 \
  --grab-z-cm 0.1 \
  --debug-frame-dir ~/Web-dashboard/data/debug_detections \
  --debug-latest-frame ~/Web-dashboard/data/debug_detections/latest.jpg
```

## Pull sortibot_debug_detections

```
rsync -av \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  pi@192.168.149.1:~/Web-dashboard/data/debug_detections/ \
  $HOME/Downloads/sortibot_debug_detections/
```

## Other

```
ssh pi@192.168.149.1

raspberrypi


cd $HOME/Desktop/Maksim/Robotics-Projects/SUTD_RA_Design_Project

rsync -av --delete \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  --exclude ".openclip-download-venv" \
  --exclude ".yolo-train-venv" \
  Web-dashboard/backend/ \
  pi@192.168.149.1:~/Web-dashboard/backend/



cd ~/Web-dashboard/backend
source .venv/bin/activate
python -m uvicorn app:app --host 0.0.0.0 --port 8000


http://192.168.149.1:8000/#dashboard




cd ~/Web-dashboard/backend
source .venv/bin/activate


python object_visual_servo_test.py \
  --home-arm-only \
  --home-servo-pulses "3:1336,4:2460,5:1529,6:1480" \
  --home-servo-duration 1.5
```
