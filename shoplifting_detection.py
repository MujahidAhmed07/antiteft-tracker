import argparse
import os
import sys
import time
from datetime import datetime
from typing import List, Optional, Tuple

import cv2
import imutils
import numpy as np
import torch
from ultralytics import YOLO

from detection_utils import (
    analyze_proximity,
    compute_smooth_fps,
    draw_hud,
    draw_item_box,
    draw_normal_box,
    draw_thief_red_box,
    parse_detections,
)

WIDTH = 800


class ShopliftingDetector:
    """Real-time AI Shoplifting and Theft Detection."""

    def __init__(
        self,
        weights_path: str = "yolov8n.pt",
        input_path: str = "demo3.mp4",
        output_path: str = "shoplifting_output.avi",
        conf_threshold: float = 0.25,
        proximity_ratio: float = 0.45,
        show_video: bool = True,
        max_frames: Optional[int] = None,
    ):
        self.input_path = input_path
        self.output_path = output_path
        self.conf_threshold = conf_threshold
        self.proximity_ratio = proximity_ratio
        self.show_video = show_video
        self.max_frames = max_frames
        self.alert_cooldown = 0

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[INFO] Using compute device: {self.device}")

        self.model = self._load_model(weights_path)
        self.cap = self._initialize_video_capture()
        self.writer: Optional[cv2.VideoWriter] = None
        self.frame_count = 0

        self.is_custom_shoplifting_model = len(self.model.names) == 2
        print(f"[INFO] Model classes: {len(self.model.names)} detected")
        print(f"[INFO] Custom Shoplifting Model Mode: {self.is_custom_shoplifting_model}")

    def _load_model(self, weights_path: str) -> YOLO:
        """Load YOLO model weights with fallback to standard weights if needed."""
        try:
            if not os.path.exists(weights_path) and not weights_path.endswith(".pt"):
                weights_path = weights_path + ".pt"

            if not os.path.exists(weights_path):
                print(f"[WARNING] Weights '{weights_path}' not found. Loading standard yolov8n.pt...")
                weights_path = "yolov8n.pt"

            model = YOLO(weights_path)
            model.to(self.device)
            print(f"[INFO] Successfully loaded model weights: {weights_path}")
            return model
        except Exception as e:
            print(f"[ERROR] Failed to load YOLO model: {e}")
            sys.exit(1)

    def _initialize_video_capture(self) -> cv2.VideoCapture:
        """Initialize video stream from file or camera."""
        if self.input_path.isdigit():
            cap = cv2.VideoCapture(int(self.input_path), cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(int(self.input_path))
        else:
            if not os.path.exists(self.input_path):
                print(f"[ERROR] Input video not found at: {self.input_path}")
                sys.exit(1)
            cap = cv2.VideoCapture(self.input_path)

        if not cap.isOpened():
            print(f"[ERROR] Failed to open video source: {self.input_path}")
            sys.exit(1)

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        print(f"[INFO] Video opened: {self.input_path} ({total_frames} frames @ {fps:.1f} FPS)")
        return cap

    def _process_frame(self, frame: np.ndarray, results) -> str:
        """Analyze frame detections using shared utilities.

        - Single person using their own phone -> Normal (Green, NO alert)
        - Thief approaching and reaching into purse/bag -> Shoplifter highlighted in RED ALERT
        - Multi-person proximity analysis via O(n^2) all-pairs check
        """
        status = "Normal - Monitoring Active"

        # Parse detections using shared utility
        persons, target_items, custom_boxes, is_custom_model = parse_detections(
            results, self.conf_threshold, self.model.names,
        )

        if len(persons) == 0 and len(custom_boxes) == 0 and len(target_items) == 0:
            if self.alert_cooldown > 0:
                self.alert_cooldown -= 1
                status = "ALERT"
            return status

        # Handle Custom 2-Class Shoplifting Model
        if is_custom_model:
            if len(custom_boxes) > 0:
                self.alert_cooldown = 15
                for (x1, y1, x2, y2, conf, label) in custom_boxes:
                    draw_thief_red_box(frame, x1, y1, x2, y2, conf, "Alert")
                status = "ALERT"
            for (x1, y1, x2, y2, conf, label) in persons:
                draw_normal_box(frame, x1, y1, x2, y2, conf, f"{label} {conf * 100:.0f}%")
            return status

        # Handle General Detection: single person case
        if len(persons) == 1:
            (px1, py1, px2, py2, pconf, plabel) = persons[0]
            draw_normal_box(frame, px1, py1, px2, py2, pconf, f"Person {pconf * 100:.0f}%")
            for (ix1, iy1, ix2, iy2, iconf, iname) in target_items:
                draw_item_box(frame, ix1, iy1, ix2, iy2, iconf, f"{iname.title()}")
            if self.alert_cooldown > 0:
                self.alert_cooldown -= 1
                status = "ALERT"
            return status

        # Multi-person proximity analysis using shared O(n^2) utility
        theft_detected, thief_boxes, victim_boxes = analyze_proximity(
            persons, self.proximity_ratio,
        )

        if theft_detected:
            self.alert_cooldown = 20

        # Draw Target Items
        for (ix1, iy1, ix2, iy2, iconf, iname) in target_items:
            draw_item_box(frame, ix1, iy1, ix2, iy2, iconf, f"Target: {iname.title()}")

        # Draw Alerts in High-Light RED
        for (x1, y1, x2, y2, conf, label) in thief_boxes:
            draw_thief_red_box(frame, x1, y1, x2, y2, conf, label)

        # Draw Normal Persons in Green
        for (x1, y1, x2, y2, conf, label) in victim_boxes:
            draw_normal_box(frame, x1, y1, x2, y2, conf, f"{label} {conf * 100:.0f}%")

        if theft_detected or self.alert_cooldown > 0:
            if self.alert_cooldown > 0 and not theft_detected:
                self.alert_cooldown -= 1
            status = "ALERT"

        return status

    def _setup_video_writer(self, frame: np.ndarray) -> None:
        """Setup video writer for saving output."""
        if self.output_path and self.writer is None:
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            fps = 25
            height, width = frame.shape[:2]
            self.writer = cv2.VideoWriter(self.output_path, fourcc, fps, (width, height), True)
            print(f"[INFO] Video writer initialized: {self.output_path} ({width}x{height} @ {fps} FPS)")

    def process_video(self) -> None:
        """Process all video frames with detection overlay."""
        print("[INFO] Starting surveillance stream...")
        start_time = time.time()
        smoothed_fps = 0.0
        prev_time = time.time()

        while True:
            ret, frame = self.cap.read()
            if not ret:
                print("\n[INFO] End of video stream reached.")
                break

            self.frame_count += 1
            if self.max_frames and self.frame_count > self.max_frames:
                print(f"\n[INFO] Reached maximum requested frame limit ({self.max_frames}).")
                break

            # Resize frame
            frame = imutils.resize(frame, width=WIDTH)

            # Calculate FPS (exponential moving average)
            curr_time = time.time()
            dt = curr_time - prev_time
            prev_time = curr_time
            smoothed_fps = compute_smooth_fps(smoothed_fps, dt)

            # Run YOLO
            results = self.model.predict(
                frame,
                conf=self.conf_threshold,
                device=self.device,
                verbose=False,
            )

            status = "Normal - Monitoring Active"
            if results and len(results[0].boxes) > 0:
                status = self._process_frame(frame, results[0])

            # Draw HUD using shared utility
            draw_hud(
                frame, status, smoothed_fps, self.frame_count, self.device,
                extra_footer="Press 'q' to Quit",
            )

            # Write frame to file
            self._setup_video_writer(frame)
            if self.writer:
                self.writer.write(frame)

            # Display GUI window
            if self.show_video:
                cv2.imshow("Shoplifting Detection", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("\n[INFO] Quit key ('q') pressed.")
                    break

            # Console progress
            if self.frame_count % 50 == 0:
                print(f"[PROGRESS] Frame {self.frame_count} | FPS: {smoothed_fps:.1f} | {status}")

        total_time = time.time() - start_time
        avg_fps = self.frame_count / total_time if total_time > 0 else 0
        print(f"[INFO] Completed: {self.frame_count} frames processed in {total_time:.2f}s (Avg: {avg_fps:.1f} FPS)")

    def cleanup(self) -> None:
        """Release capture and video writer resources."""
        self.cap.release()
        if self.writer:
            self.writer.release()
        cv2.destroyAllWindows()
        print(f"[INFO] Annotated video saved successfully to: {self.output_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="AI Shoplifting & Surveillance Detection")
    parser.add_argument("--weights", type=str, default="yolov8n.pt", help="Path to YOLO weights (.pt)")
    parser.add_argument("--input", type=str, default="demo3.mp4", help="Input video path or webcam index (0)")
    parser.add_argument("--output", type=str, default="shoplifting_output.avi", help="Output annotated video path")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--proximity", type=float, default=0.45, help="Proximity ratio (0.15-0.90)")
    parser.add_argument("--no-show", action="store_true", help="Disable display window (headless mode)")
    parser.add_argument("--max-frames", type=int, default=None, help="Maximum number of frames to process")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print("      AI SHOPLIFTING & SURVEILLANCE DETECTION SYSTEM       ")
    print("=" * 60)
    print(f" Input Video : {args.input}")
    print(f" Output Video: {args.output}")
    print(f" Model       : {args.weights}")
    print(f" Conf Limit  : {args.conf}")
    print(f" Proximity   : {args.proximity}")
    print("=" * 60)

    detector = ShopliftingDetector(
        weights_path=args.weights,
        input_path=args.input,
        output_path=args.output,
        conf_threshold=args.conf,
        proximity_ratio=args.proximity,
        show_video=not args.no_show,
        max_frames=args.max_frames,
    )
    detector.process_video()
    detector.cleanup()


if __name__ == "__main__":
    main()
