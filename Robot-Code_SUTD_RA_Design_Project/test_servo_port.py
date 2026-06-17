import argparse
import sys
import time

sys.path.append("/home/pi/MasterPi")

from common.ros_robot_controller_sdk import Board


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True, help="Physical servo port to test")
    parser.add_argument("--center", type=int, default=1500)
    parser.add_argument("--delta", type=int, default=80)
    parser.add_argument("--duration", type=float, default=0.7)
    args = parser.parse_args()

    board = Board()

    positions = [
        args.center,
        args.center + args.delta,
        args.center,
        args.center - args.delta,
        args.center,
    ]

    print(f"Testing physical servo port {args.port}")
    print("Keep fingers away from the arm. Press Ctrl+C to stop.")

    try:
        for pos in positions:
            print(f"Port {args.port} -> pulse {pos}")
            board.pwm_servo_set_position(args.duration, [[args.port, pos]])
            time.sleep(args.duration + 0.3)
    finally:
        print("Returning to center")
        board.pwm_servo_set_position(0.7, [[args.port, args.center]])


if __name__ == "__main__":
    main()
