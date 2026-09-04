"""
Shared drawing and detection utilities for the Shoplifting Detection System.

This module centralizes common functions used by both the web engine
(detector_engine.py) and the CLI standalone (shoplifting_detection.py)
to eliminate code duplication.
"""

from datetime import datetime
from typing import Dict, List, Set, Tuple

import cv2
import numpy as np

# ==============================================================================
# Color Configurations (BGR format for OpenCV)
# ==============================================================================
COLOR_SHOPLIFTER_RED = (0, 0, 255)       # High-light RED for thief / shoplifting person
COLOR_ITEM_YELLOW = (0, 215, 255)        # Yellow-Orange for target item (phone, purse, bag)
COLOR_VICTIM_GREEN = (0, 255, 0)         # Green for normal person / victim
COLOR_ALERT_RED = (0, 0, 255)            # Red for alert badges
COLOR_HEADER = (0, 255, 255)             # Yellow for header text
COLOR_FOOTER = (0, 255, 255)             # Yellow for footer text
COLOR_BG_DARK = (15, 15, 15)             # Dark HUD background overlay

# Classes considered "target items" in general YOLO COCO model
TARGET_ITEM_CLASSES = [
    "cell phone", "handbag", "backpack", "suitcase",
    "purse", "wallet", "mouse", "laptop", "bottle", "cup", "book",
]


# ==============================================================================
# Detection Parsing
# ==============================================================================
def parse_detections(
    results,
    conf_threshold: float,
    model_names: dict,
) -> Tuple[List, List, List, bool]:
    """
    Parse YOLO detection results into categorized lists.

    Returns:
        persons: list of (x1, y1, x2, y2, conf, "Person")
        target_items: list of (x1, y1, x2, y2, conf, class_name)
        custom_shoplifter_boxes: list of (x1, y1, x2, y2, conf, "Shoplifter")
        is_custom_model: True if model has exactly 2 classes (custom shoplifting model)
    """
    persons: List = []
    target_items: List = []
    custom_shoplifter_boxes: List = []

    is_custom_model = len(model_names) == 2

    if not results or len(results[0].boxes) == 0:
        return persons, target_items, custom_shoplifter_boxes, is_custom_model

    xyxy = results[0].boxes.xyxy.cpu().numpy().astype(int)
    confs = results[0].boxes.conf.cpu().numpy()
    classes = results[0].boxes.cls.cpu().numpy().astype(int)

    for (x1, y1, x2, y2), conf, cls_id in zip(xyxy, confs, classes):
        if conf < conf_threshold:
            continue
        cname = model_names.get(cls_id, str(cls_id)).lower()

        if is_custom_model:
            if cls_id == 1 or "shoplift" in cname:
                custom_shoplifter_boxes.append((x1, y1, x2, y2, conf, "Shoplifter"))
            else:
                persons.append((x1, y1, x2, y2, conf, "Person"))
        else:
            if cname == "person":
                persons.append((x1, y1, x2, y2, conf, "Person"))
            elif cname in TARGET_ITEM_CLASSES:
                target_items.append((x1, y1, x2, y2, conf, cname))

    return persons, target_items, custom_shoplifter_boxes, is_custom_model


# ==============================================================================
# Proximity Analysis
# ==============================================================================
def analyze_proximity(
    persons: List,
    proximity_ratio: float,
) -> Tuple[bool, List, List]:
    """
    Perform O(n^2) multi-person proximity analysis.

    Returns:
        theft_detected: True if any pair is interacting
        thief_boxes: persons flagged as alerts
        victim_boxes: persons flagged as normal
    """
    if len(persons) < 2:
        return False, [], list(persons)

    max_gap = max(40, int(200 * proximity_ratio))
    alert_indices: Set[int] = set()

    for i in range(len(persons)):
        p1_box = persons[i][:4]
        for j in range(i + 1, len(persons)):
            p2_box = persons[j][:4]

            # Overlaps
            ox = max(0, min(p1_box[2], p2_box[2]) - max(p1_box[0], p2_box[0]))
            oy = max(0, min(p1_box[3], p2_box[3]) - max(p1_box[1], p2_box[1]))

            # Gaps
            gx = max(0, max(p1_box[0], p2_box[0]) - min(p1_box[2], p2_box[2]))
            gy = max(0, max(p1_box[1], p2_box[1]) - min(p1_box[3], p2_box[3]))

            is_interacting = False

            # Condition 1: Direct 2D Body Overlap
            if ox > 0 and (oy > 0 or gy < 30):
                is_interacting = True
            # Condition 2: Close Proximity Approach
            elif gx < max_gap and gy < int(max_gap * 0.8):
                is_interacting = True

            if is_interacting:
                alert_indices.add(i)

    if len(alert_indices) > 0:
        thief_boxes = []
        victim_boxes = []
        for idx, p in enumerate(persons):
            if idx in alert_indices:
                thief_boxes.append((p[0], p[1], p[2], p[3], p[4], "Alert"))
            else:
                victim_boxes.append((p[0], p[1], p[2], p[3], p[4], "Person"))
        return True, thief_boxes, victim_boxes

    return False, [], list(persons)


# ==============================================================================
# Drawing Functions
# ==============================================================================
def draw_thief_red_box(
    frame: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    conf: float,
    label: str,
) -> None:
    """Draw high-visibility RED bounding box for the thief / shoplifting person."""
    # Thick High-Light RED Box
    cv2.rectangle(frame, (x1, y1), (x2, y2), COLOR_SHOPLIFTER_RED, 3)

    # Corner Accent Highlights
    corner_len = min(28, int((x2 - x1) / 4), int((y2 - y1) / 4))
    cv2.line(frame, (x1, y1), (x1 + corner_len, y1), (0, 0, 255), 5)
    cv2.line(frame, (x1, y1), (x1, y1 + corner_len), (0, 0, 255), 5)
    cv2.line(frame, (x2, y1), (x2 - corner_len, y1), (0, 0, 255), 5)
    cv2.line(frame, (x2, y1), (x2, y1 + corner_len), (0, 0, 255), 5)
    cv2.line(frame, (x1, y2), (x1 + corner_len, y2), (0, 0, 255), 5)
    cv2.line(frame, (x1, y2), (x1, y2 - corner_len), (0, 0, 255), 5)
    cv2.line(frame, (x2, y2), (x2 - corner_len, y2), (0, 0, 255), 5)
    cv2.line(frame, (x2, y2), (x2, y2 - corner_len), (0, 0, 255), 5)

    # White & Red Alert Indicator Dot
    center_x = int((x1 + x2) / 2)
    cv2.circle(frame, (center_x, y1), 8, (255, 255, 255), -1)
    cv2.circle(frame, (center_x, y1), 6, COLOR_ALERT_RED, -1)

    # High-Contrast RED Label Badge
    badge_text = f"{label} ({conf * 100:.1f}%)"
    (tw, th), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    badge_y1 = max(0, y1 - th - 12)
    cv2.rectangle(frame, (x1, badge_y1), (x1 + tw + 14, y1), COLOR_SHOPLIFTER_RED, -1)
    cv2.rectangle(frame, (x1, badge_y1), (x1 + tw + 14, y1), (255, 255, 255), 1)
    cv2.putText(
        frame, badge_text, (x1 + 6, y1 - 6),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA,
    )


def draw_normal_box(
    frame: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    conf: float,
    label: str,
) -> None:
    """Draw normal person / victim bounding box in green."""
    cv2.rectangle(frame, (x1, y1), (x2, y2), COLOR_VICTIM_GREEN, 2)
    text = f"{label}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    badge_y1 = max(0, y1 - th - 8)
    cv2.rectangle(frame, (x1, badge_y1), (x1 + tw + 8, y1), COLOR_VICTIM_GREEN, -1)
    cv2.putText(
        frame, text, (x1 + 4, y1 - 4),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA,
    )


def draw_item_box(
    frame: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    conf: float,
    label: str,
) -> None:
    """Draw target item bounding box in yellow-orange."""
    cv2.rectangle(frame, (x1, y1), (x2, y2), COLOR_ITEM_YELLOW, 2)
    item_text = f"{label} {conf * 100:.0f}%"
    (tw, th), _ = cv2.getTextSize(item_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 8, y1), COLOR_ITEM_YELLOW, -1)
    cv2.putText(
        frame, item_text, (x1 + 4, y1 - 4),
        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA,
    )


def draw_hud(
    frame: np.ndarray,
    status: str,
    fps: float,
    frame_count: int,
    device,
    extra_footer: str = "",
) -> None:
    """Draw top surveillance header and bottom status HUD."""
    h, w = frame.shape[:2]

    # Top Bar Background
    cv2.rectangle(frame, (0, 0), (w, 36), COLOR_BG_DARK, -1)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(
        frame, f"AI CCTV Surveillance | Live Feed | {ts}",
        (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_HEADER, 1, cv2.LINE_AA,
    )

    # Status text with dynamic color
    if "ALERT" in status:
        cv2.rectangle(frame, (8, 40), (w - 8, 72), (0, 0, 120), -1)
        cv2.rectangle(frame, (8, 40), (w - 8, 72), COLOR_SHOPLIFTER_RED, 2)
        cv2.putText(
            frame, f"STATUS: {status}", (15, 63),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA,
        )
    else:
        cv2.putText(
            frame, f"STATUS: {status}", (10, 58),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_VICTIM_GREEN, 2, cv2.LINE_AA,
        )

    # Bottom Bar Background
    cv2.rectangle(frame, (0, h - 30), (w, h), COLOR_BG_DARK, -1)
    footer = f"Frame: {frame_count} | FPS: {fps:.1f} | Device: {device}"
    if extra_footer:
        footer += f" | {extra_footer}"
    cv2.putText(
        frame, footer, (10, h - 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.48, COLOR_FOOTER, 1, cv2.LINE_AA,
    )


# ==============================================================================
# FPS Smoothing
# ==============================================================================
def compute_smooth_fps(prev_fps: float, dt: float, alpha: float = 0.1) -> float:
    """
    Compute exponentially smoothed FPS value.

    Args:
        prev_fps: Previous smoothed FPS
        dt: Time delta between frames (seconds)
        alpha: Smoothing factor (0.1 = smooth, 0.5 = responsive)

    Returns:
        Smoothed FPS value
    """
    if dt <= 0:
        return prev_fps
    instant_fps = 1.0 / dt
    return prev_fps * (1.0 - alpha) + instant_fps * alpha
