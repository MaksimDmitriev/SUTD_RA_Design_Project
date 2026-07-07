import argparse
from pathlib import Path

import cv2

from contrast_detector import ContrastBlobDetector, save_mask_preview
from object_visual_servo_test import annotate_frame, detection_geometry


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the LAB/color contrast detector on one saved robot camera image."
    )
    parser.add_argument("image", help="Path to a saved robot camera image.")
    parser.add_argument("--min-area", type=float, default=45.0)
    parser.add_argument("--max-area-ratio", type=float, default=0.04)
    parser.add_argument("--lab-delta", type=float, default=45.0)
    parser.add_argument("--min-saturation", type=int, default=55)
    parser.add_argument("--dark-value", type=int, default=70)
    parser.add_argument("--max-colored-value", type=int, default=245)
    parser.add_argument("--use-lab", action="store_true")
    parser.add_argument("--process-width", type=int, default=320)
    parser.add_argument("--roi-top-ratio", type=float, default=0.15)
    parser.add_argument("--roi-bottom-ratio", type=float, default=0.82)
    parser.add_argument("--max-box-width-ratio", type=float, default=0.38)
    parser.add_argument("--max-box-height-ratio", type=float, default=0.34)
    parser.add_argument("--box-padding-ratio", type=float, default=0.25)
    parser.add_argument("--target-x-ratio", type=float, default=0.50)
    parser.add_argument("--target-bottom-ratio", type=float, default=0.68)
    parser.add_argument(
        "--output",
        default=None,
        help="Output annotated image path. Defaults to IMAGE.contrast.jpg.",
    )
    parser.add_argument(
        "--mask-output",
        default=None,
        help="Optional output path for the raw contrast mask.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    frame = cv2.imread(args.image)
    if frame is None:
        raise RuntimeError(f"Could not read image: {args.image}")

    detector = ContrastBlobDetector(
        min_area=args.min_area,
        max_area_ratio=args.max_area_ratio,
        lab_delta=args.lab_delta,
        min_saturation=args.min_saturation,
        max_colored_value=args.max_colored_value,
        dark_value=args.dark_value,
        use_lab_contrast=args.use_lab,
        process_width=args.process_width,
        roi_top_ratio=args.roi_top_ratio,
        roi_bottom_ratio=args.roi_bottom_ratio,
        max_box_width_ratio=args.max_box_width_ratio,
        max_box_height_ratio=args.max_box_height_ratio,
        box_padding_ratio=args.box_padding_ratio,
    )
    detections = detector.detect(frame)
    print(f"detections={len(detections)}")
    for idx, detection in enumerate(detections):
        print(
            f"{idx}: label={detection.label!r} "
            f"confidence={detection.confidence:.3f} box={detection.xyxy}"
        )

    output_path = (
        Path(args.output).expanduser()
        if args.output
        else Path(args.image).with_suffix(".contrast.jpg")
    )
    if detections:
        geometry = detection_geometry(frame, detections[0], args)
        text = f"{detections[0].label} {detections[0].confidence:.2f}"
        output = annotate_frame(frame, detections[0], geometry, text)
    else:
        output = frame

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), output)
    print(f"saved={output_path}")

    if args.mask_output:
        save_mask_preview(args.mask_output, frame, detector)
        print(f"mask_saved={Path(args.mask_output).expanduser()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
