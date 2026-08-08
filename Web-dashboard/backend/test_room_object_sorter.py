import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

# The local documentation/test runtime does not include OpenCV. These tests
# exercise only the pure planning helpers, so a type placeholder is sufficient.
try:
    import cv2  # noqa: F401
except ModuleNotFoundError:
    cv2_stub = types.ModuleType("cv2")
    cv2_stub.VideoCapture = object
    sys.modules["cv2"] = cv2_stub

from robot_constants import RobotConstants
import room_object_sorter as sorter
from room_object_sorter import (
    FRONT,
    LEFT,
    RIGHT,
    accepted_detection,
    camera_scan_pose,
    navigation_turn_spec,
    scan_order_after_sort,
)
from yolo_detector import Detection


class RoomObjectSorterTest(unittest.TestCase):
    def test_scan_poses_only_change_camera_rotation(self):
        home = dict(RobotConstants.HOME_SERVO_PULSES)

        for direction, expected_id6 in (
            (FRONT, 1480),
            (LEFT, 2500),
            (RIGHT, 500),
        ):
            pose = dict(camera_scan_pose(direction))
            self.assertEqual(expected_id6, pose[6])
            self.assertEqual(home[1], pose[1])
            self.assertEqual(home[3], pose[3])
            self.assertEqual(home[4], pose[4])
            self.assertEqual(home[5], pose[5])

    def test_scan_starts_on_the_basket_side(self):
        self.assertEqual(
            (LEFT, FRONT, RIGHT),
            scan_order_after_sort("purple_trash"),
        )
        self.assertEqual(
            (RIGHT, FRONT, LEFT),
            scan_order_after_sort("red_useful"),
        )

    def test_post_grab_poses_hold_id4_at_safe_basket_height(self):
        preparation_pose = dict(sorter.visual_servo.POST_GRAB_WRIST_POSE)
        self.assertEqual(1500, preparation_pose[4])
        self.assertEqual(1500, preparation_pose[5])

        for label, expected_id6 in (
            ("purple_trash", 2500),
            ("red_useful", 500),
        ):
            drop_pose = dict(
                sorter.visual_servo.post_grab_pose_for_label(label)
            )
            self.assertEqual(500, drop_pose[3])
            self.assertEqual(1500, drop_pose[4])
            self.assertEqual(expected_id6, drop_pose[6])

    def test_navigation_turn_calibration_and_sign(self):
        self.assertEqual((0.5, 0.47), navigation_turn_spec(RIGHT))
        self.assertEqual((-0.5, 0.47), navigation_turn_spec(LEFT))
        self.assertEqual((0.5, 1.04), navigation_turn_spec(RIGHT, degrees=180))

    def test_remeasurement_does_not_substitute_a_different_label(self):
        trash = Detection((1, 2, 3, 4), 0.9, 1, "purple_trash")
        useful = Detection((5, 6, 7, 8), 0.8, 0, "red_useful")
        labels = {"purple_trash", "red_useful"}

        self.assertIs(
            trash,
            accepted_detection([trash, useful], labels, "purple_trash"),
        )
        self.assertIsNone(
            accepted_detection([useful], labels, "purple_trash")
        )

    def test_main_stops_after_empty_front_left_right_and_rear(self):
        args = SimpleNamespace(
            approach_mode="floor-distance",
            home_pose="my_home",
            home_arm_only=False,
            motion="dry-run",
            speed=35,
            direction=90,
            motion_debug=False,
        )
        camera = Mock()
        motion = Mock(name="motion")

        with (
            patch.object(sorter.visual_servo, "parse_args", return_value=args),
            patch.object(sorter.visual_servo, "create_arm", return_value=Mock()),
            patch.object(sorter, "move_camera_to"),
            patch.object(sorter, "Camera", return_value=camera),
            patch.object(sorter, "create_detector", return_value=Mock()),
            patch.object(sorter, "create_motion_backend", return_value=motion),
            patch.object(sorter, "scan_directions", return_value=None),
            patch.object(sorter, "center_camera_while_turning") as turn,
            patch.object(sorter, "observe_view", return_value=None),
        ):
            self.assertEqual(0, sorter.main())

        turn.assert_called_once()
        self.assertEqual(RIGHT, turn.call_args.args[3])
        self.assertEqual(180, turn.call_args.kwargs["degrees"])
        motion.stop.assert_called()
        camera.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
