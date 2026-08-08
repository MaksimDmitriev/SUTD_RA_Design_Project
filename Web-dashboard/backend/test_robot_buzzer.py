import threading
import unittest

from robot_buzzer import LoopingTunePlayer, note_frequency


class RecordingBoard:
    def __init__(self):
        self.calls = []
        self.first_call = threading.Event()

    def set_buzzer(self, frequency, sounding, gap, repeat):
        self.calls.append((frequency, sounding, gap, repeat))
        self.first_call.set()


class RobotBuzzerTest(unittest.TestCase):
    def test_note_frequency(self):
        self.assertEqual(440, note_frequency("A4"))
        self.assertEqual(0, note_frequency("R"))

    def test_looping_player_finishes_current_cycle_before_stopping(self):
        board = RecordingBoard()
        tune = [("A4", 1), ("C5", 1)]
        player = LoopingTunePlayer(board, tune, bpm=6000)

        player.start()
        self.assertTrue(board.first_call.wait(timeout=1))
        player.stop_after_cycle()

        self.assertEqual(2, len(board.calls))
        self.assertEqual(note_frequency("A4"), board.calls[0][0])
        self.assertEqual(note_frequency("C5"), board.calls[1][0])


if __name__ == "__main__":
    unittest.main()
