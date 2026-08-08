class RobotConstants:
    """Fixed settings shared by the robot detection and calibration workflows."""

    MODEL_PATH = "/home/pi/Web-dashboard/models/detector/sortibot_yolo_ncnn_model"
    YOLO_CONFIDENCE = 0.35
    APPROACH_LABELS = frozenset({"red_useful", "purple_trash"})
    MEASUREMENT_FRAMES = 5

    HOME_SERVO_PULSES = (
        (1, 2500),
        (3, 1336),
        (4, 2460),
        (5, 1529),
        (6, 1480),
    )
    HOME_SERVO_DURATION_SECONDS = 1.5

    CAMERA_HEIGHT_CM = 19.6
    CAMERA_PITCH_DOWN_DEG = 17.2
    CAMERA_HORIZONTAL_FOV_DEG = 79.1
