## Run the solution:

```
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
  --target-bottom-ratio 0.9 \
  --x-deadband-ratio 0.09 \
  --bottom-deadband-ratio 0.04 \
  --close-bottom-error-ratio 0.0 \
  --search-y-speed 16 \
  --max-x-speed 48 \
  --min-x-speed 32 \
  --max-y-speed 48 \
  --min-y-speed 32 \
  --home-servo-pulses "3:1336,4:2460,5:1529,6:1480" \
  --home-servo-duration 1.5 \
  --post-pickup-drive-seconds 0.5 \
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
  --debug-latest-frame ~/Web-dashboard/data/debug_detections/latest.jpg \
  --arm-visual-align \
  --arm-align-target-x-ratio 0.50 \
  --arm-align-target-y-ratio 0.55 \
  --arm-align-deadband-ratio 0.08 \
  --arm-align-max-steps 6 \
  --arm-align-step-cm 0.4
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



OTHER POSE:

python object_visual_servo_test.py \
  --home-arm-only \
  --home-servo-pulses "3:600,4:2000,5:1300,6:1600" \
  --home-servo-duration 1.5






python object_visual_servo_test.py \
  --home-arm-only \
  --home-pose ik \
  --grab-home-x-cm 0 \
  --grab-home-y-cm 12.0 \
  --grab-home-z-cm 0.1



  -----
looking at the floor

python object_visual_servo_test.py \
  --home-arm-only \
  --home-servo-pulses "3:800,4:2460,5:1529,6:1405" \
  --home-servo-duration 1.5

  -----




  rsync -av \
  -e "ssh -i $HOME/.ssh/sortibot_ed25519" \
  pi@192.168.149.1:~/Web-dashboard/data/debug_detections/ \
  $HOME/Downloads/sortibot_debug_detections/
```


measuring 


Loading /home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model for NCNN inference...
sample=1 label=red_useful conf=0.790 bottom_y_ratio=0.4854 center_x_ratio=0.4680 xyxy=(282, 201, 317, 233)
sample=2 label=red_useful conf=0.809 bottom_y_ratio=0.4854 center_x_ratio=0.4680 xyxy=(281, 200, 318, 233)
sample=3 label=red_useful conf=0.834 bottom_y_ratio=0.4854 center_x_ratio=0.4672 xyxy=(281, 201, 317, 233)
sample=4 label=red_useful conf=0.609 bottom_y_ratio=0.4833 center_x_ratio=0.4680 xyxy=(282, 201, 317, 232)
sample=5 label=red_useful conf=0.904 bottom_y_ratio=0.4854 center_x_ratio=0.4672 xyxy=(281, 200, 317, 233)

average_samples=5
label=red_useful
bottom_y_ratio=0.4850
center_x_ratio=0.4677
box_height_ratio=0.0671
distance from the front edge of chassis: 74cm



---


Loading /home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model for NCNN inference...
sample=1 label=red_useful conf=0.770 bottom_y_ratio=0.5250 center_x_ratio=0.4352 xyxy=(259, 216, 298, 252)
sample=2 label=red_useful conf=0.756 bottom_y_ratio=0.5250 center_x_ratio=0.4352 xyxy=(258, 216, 299, 252)
sample=3 label=red_useful conf=0.792 bottom_y_ratio=0.5250 center_x_ratio=0.4344 xyxy=(258, 216, 298, 252)
sample=4 label=red_useful conf=0.717 bottom_y_ratio=0.5229 center_x_ratio=0.4352 xyxy=(259, 216, 298, 251)
sample=5 label=red_useful conf=0.788 bottom_y_ratio=0.5250 center_x_ratio=0.4352 xyxy=(259, 216, 298, 252)

average_samples=5
label=red_useful
bottom_y_ratio=0.5246
center_x_ratio=0.4350
box_height_ratio=0.0746
distance from the front edge of chassis: 64cm