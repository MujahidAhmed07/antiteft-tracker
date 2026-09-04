import os
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, Generator, List, Optional, Tuple

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


class ShopliftingDetectionEngine:
    def __init__(self, weights_path: str = "yolov8n.pt"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[ENGINE] Loading model on: {self.device}")
        if not os.path.exists(weights_path) and not weights_path.endswith(".pt"):
            weights_path += ".pt"
        if not os.path.exists(weights_path):
            weights_path = "yolov8n.pt"
        self.model = YOLO(weights_path)
        self.model.to(self.device)

        # Stream-scoped telemetry: keyed by session ID
        self._telemetry: Dict[str, dict] = {}
        self._active_session_id: Optional[str] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    @property
    def telemetry(self) -> dict:
        """Return telemetry for the currently active session (backward compat)."""
        with self._lock:
            if self._active_session_id and self._active_session_id in self._telemetry:
                return self._telemetry[self._active_session_id]
            return {
                "status": "Ready",
                "fps": 0.0,
                "frame_current": 0,
                "frame_total": 0,
                "alerts_count": 0,
                "active_alert": False,
                "active_alert_text": "",
                "incidents": [],
                "is_processing": False,
            }

    def get_telemetry(self, session_id: str) -> dict:
        """Return telemetry for a specific session."""
        with self._lock:
            return self._telemetry.get(session_id, self.telemetry)

    def stop_stream(self) -> None:
        """Signal the current stream to stop gracefully."""
        self._stop_event.set()

    def process_and_stream(
        self,
        video_source: str,
        output_save_path: Optional[str] = None,
        conf_threshold: float = 0.25,
        proximity_ratio: float = 0.45,
        target_width: int = 800,
    ) -> Generator[bytes, None, None]:
        """Generator yielding MJPEG frame bytes and updating live telemetry."""

        # Generate a unique session ID for this stream
        session_id = uuid.uuid4().hex[:8]
        with self._lock:
            self._active_session_id = session_id
            self._telemetry[session_id] = {
                "status": "Ready",
                "fps": 0.0,
                "frame_current": 0,
                "frame_total": 0,
                "alerts_count": 0,
                "active_alert": False,
                "active_alert_text": "",
                "incidents": [],
                "is_processing": False,
            }

        # Reset stop event for this session
        self._stop_event.clear()

        is_live_stream = False
        cap = None

        if video_source.isdigit():
            is_live_stream = True
            cap = cv2.VideoCapture(int(video_source), cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(int(video_source))
        elif video_source.startswith("http://") or video_source.startswith("https://") or video_source.startswith("rtsp://"):
            is_live_stream = True
            cap = cv2.VideoCapture(video_source)
            if not cap.isOpened() and not video_source.endswith("/video") and not video_source.endswith(".mjpg"):
                test_url = video_source.rstrip("/") + "/video"
                cap = cv2.VideoCapture(test_url)
                if cap.isOpened():
                    video_source = test_url
        else:
            if not os.path.exists(video_source):
                print(f"[ERROR] Video not found: {video_source}")
                with self._lock:
                    self._telemetry[session_id]["status"] = "Error: Video file not found."
                    self._telemetry[session_id]["is_processing"] = False
                return
            cap = cv2.VideoCapture(video_source)

        if cap is None or not cap.isOpened():
            print(f"[ERROR] Could not open video/camera source: {video_source}")
            with self._lock:
                self._telemetry[session_id]["status"] = f"Error: Could not open camera/feed ({video_source})"
                self._telemetry[session_id]["is_processing"] = False
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if not is_live_stream else 0
        if total_frames < 0:
            total_frames = 0

        with self._lock:
            t = self._telemetry[session_id]
            t["status"] = "Normal - Monitoring Active"
            t["frame_total"] = total_frames
            t["frame_current"] = 0
            t["alerts_count"] = 0
            t["incidents"] = []
            t["is_processing"] = True

        writer = None
        alert_cooldown = 0
        last_logged_alert_frame = -100
        smoothed_fps = 0.0
        prev_time = time.time()

        try:
            while cap.isOpened():
                # Check stop signal
                if self._stop_event.is_set():
                    print(f"[ENGINE] Stream stopped by user (session {session_id})")
                    break

                ret, frame = cap.read()
                if not ret:
                    break

                with self._lock:
                    self._telemetry[session_id]["frame_current"] += 1
                curr_frame_idx = self._telemetry[session_id]["frame_current"]

                # Resize frame
                frame = imutils.resize(frame, width=target_width)
                h, w = frame.shape[:2]

                # Setup video writer
                if output_save_path and writer is None:
                    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                    writer = cv2.VideoWriter(output_save_path, fourcc, 25, (w, h), True)

                # FPS Calculation (exponential moving average)
                now = time.time()
                dt = now - prev_time
                prev_time = now
                smoothed_fps = compute_smooth_fps(smoothed_fps, dt)
                with self._lock:
                    self._telemetry[session_id]["fps"] = round(smoothed_fps, 1)

                # Run YOLO Inference
                results = self.model.predict(
                    frame,
                    conf=conf_threshold,
                    device=self.device,
                    verbose=False,
                )

                # Parse detections using shared utility
                persons, target_items, custom_boxes, is_custom_model = parse_detections(
                    results, conf_threshold, self.model.names,
                )

                # Detection logic
                theft_detected = False
                thief_boxes = []
                victim_boxes = []
                status_text = "Normal - Monitoring Active"

                if is_custom_model:
                    if len(custom_boxes) > 0:
                        theft_detected = True
                        alert_cooldown = 15
                        thief_boxes = custom_boxes
                    victim_boxes = persons
                else:
                    theft_detected, thief_boxes, victim_boxes = analyze_proximity(
                        persons, proximity_ratio,
                    )
                    if theft_detected:
                        alert_cooldown = 15

                # Draw Target Items
                for (ix1, iy1, ix2, iy2, iconf, iname) in target_items:
                    draw_item_box(frame, ix1, iy1, ix2, iy2, iconf, f"Target: {iname.title()}")

                # Draw Shoplifters / Alerts in RED
                for (x1, y1, x2, y2, conf, label) in thief_boxes:
                    draw_thief_red_box(frame, x1, y1, x2, y2, conf, label)

                # Draw Normal Persons in Green
                for (x1, y1, x2, y2, conf, label) in victim_boxes:
                    draw_normal_box(frame, x1, y1, x2, y2, conf, f"{label} {conf * 100:.0f}%")

                # Handle Alert State & Telemetry
                if theft_detected or alert_cooldown > 0:
                    if alert_cooldown > 0 and not theft_detected:
                        alert_cooldown -= 1
                    status_text = "ALERT"

                    with self._lock:
                        self._telemetry[session_id]["active_alert"] = True
                        self._telemetry[session_id]["active_alert_text"] = "Alert Detected"

                        # Log incident once every 30 frames
                        if curr_frame_idx - last_logged_alert_frame > 30:
                            last_logged_alert_frame = curr_frame_idx
                            self._telemetry[session_id]["alerts_count"] += 1
                            ts = datetime.now().strftime("%H:%M:%S")
                            self._telemetry[session_id]["incidents"].append({
                                "id": self._telemetry[session_id]["alerts_count"],
                                "timestamp": ts,
                                "frame": curr_frame_idx,
                                "type": "Alert",
                                "severity": "CRITICAL",
                                "confidence": f"{round(float(thief_boxes[0][4] if thief_boxes else 0.88) * 100, 1)}%",
                            })
                else:
                    status_text = "Normal - Monitoring Active"
                    with self._lock:
                        self._telemetry[session_id]["active_alert"] = False
                        self._telemetry[session_id]["active_alert_text"] = ""

                with self._lock:
                    self._telemetry[session_id]["status"] = status_text

                # Draw HUD using shared utility
                draw_hud(frame, status_text, smoothed_fps, curr_frame_idx, self.device)

                # Write frame to file
                if writer:
                    writer.write(frame)

                # Encode to JPEG
                ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ret:
                    continue

                frame_bytes = buffer.tobytes()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )

        finally:
            if cap is not None:
                cap.release()
            if writer:
                writer.release()
            with self._lock:
                self._telemetry[session_id]["is_processing"] = False
                self._telemetry[session_id]["fps"] = 0.0
                if not self._telemetry[session_id]["status"].startswith("Error"):
                    self._telemetry[session_id]["status"] = (
                        "Completed" if not is_live_stream else "Stream Offline / Stopped"
                    )
            print(f"[ENGINE] Stream finished (session {session_id}). Output saved: {output_save_path}")
