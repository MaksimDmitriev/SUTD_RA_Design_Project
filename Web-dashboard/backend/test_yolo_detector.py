import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from yolo_detector import YoloDetector


class YoloDetectorTest(unittest.TestCase):
    class Scalar:
        def __init__(self, value):
            self.value = value

        def item(self):
            return self.value

    class Vector(list):
        def tolist(self):
            return list(self)

    @staticmethod
    def box(confidence: float):
        return SimpleNamespace(
            cls=[YoloDetectorTest.Scalar(0.0)],
            conf=[YoloDetectorTest.Scalar(confidence)],
            xyxy=[YoloDetectorTest.Vector([10.0, 20.0, 30.0, 40.0])],
        )

    def test_retains_below_threshold_candidates_for_diagnostics(self):
        detector = YoloDetector(confidence=0.35, diagnostic_confidence=0.05)
        detector._model = Mock()
        detector._model.predict.return_value = [
            SimpleNamespace(
                names={0: "red_useful"},
                boxes=[self.box(0.42), self.box(0.27)],
            )
        ]

        frame = SimpleNamespace(shape=(60, 80, 3))
        accepted = detector.detect(frame)

        self.assertEqual([0.42], [item.confidence for item in accepted])
        self.assertEqual(
            [0.27],
            [item.confidence for item in detector.last_rejected_detections],
        )
        self.assertEqual(
            0.05,
            detector._model.predict.call_args.kwargs["conf"],
        )


if __name__ == "__main__":
    unittest.main()
