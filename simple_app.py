"""
Simple AI Shoplifting Detection Application
Allows the user to select any video file from their computer and runs real-time detection.
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from shoplifting_detection import ShopliftingDetector


def pick_video_and_run():
    # Hide root window while showing file dialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    file_path = filedialog.askopenfilename(
        title="Select Video for Shoplifting Detection",
        initialdir=os.getcwd(),
        filetypes=[
            ("Video Files", "*.mp4 *.avi *.mov *.mkv *.webm *.flv"),
            ("MP4 Files", "*.mp4"),
            ("AVI Files", "*.avi"),
            ("All Files", "*.*"),
        ],
    )

    root.destroy()

    if not file_path:
        print("[INFO] No file selected. Exiting.")
        sys.exit(0)

    print(f"\n[INFO] Selected Video: {file_path}")
    print("[INFO] Initializing Shoplifting Detection Engine...")
    print("[INFO] Press 'q' in the video window at any time to exit.\n")

    output_path = os.path.splitext(file_path)[0] + "_annotated.avi"

    detector = ShopliftingDetector(
        weights_path="yolov8n.pt",
        input_path=file_path,
        output_path=output_path,
        conf_threshold=0.25,
        proximity_ratio=0.45,
        show_video=True,
    )

    try:
        detector.process_video()
    finally:
        detector.cleanup()


def launch_gui_launcher():
    """Interactive GUI launcher with file selector, webcam button, and settings."""
    root = tk.Tk()
    root.title("Anti-Theft Tracker - Video Selection")
    root.geometry("520x420")
    root.resizable(False, False)
    root.configure(bg="#121826")

    # Keep on top at startup
    root.attributes("-topmost", True)

    selected_video = tk.StringVar(value="")

    # Styling
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TLabel", background="#121826", foreground="#e2e8f0", font=("Segoe UI", 10))
    style.configure("Header.TLabel", font=("Segoe UI", 15, "bold"), foreground="#60a5fa")

    # Header
    title_lbl = ttk.Label(root, text="🛡️ Anti-Theft Shoplifting Tracker", style="Header.TLabel")
    title_lbl.pack(pady=(18, 4))

    subtitle_lbl = ttk.Label(root, text="Select a video file to run real-time AI theft detection", font=("Segoe UI", 9), foreground="#94a3b8")
    subtitle_lbl.pack(pady=(0, 16))

    # File selection card
    card = tk.Frame(root, bg="#1e293b", padx=16, pady=16, relief=tk.FLAT)
    card.pack(fill=tk.X, padx=24, pady=8)

    path_entry = tk.Entry(card, textvariable=selected_video, font=("Segoe UI", 10), bg="#0f172a", fg="#f8fafc", insertbackground="#fff", relief=tk.FLAT)
    path_entry.pack(fill=tk.X, pady=(0, 10), ipady=4)

    def browse_file():
        path = filedialog.askopenfilename(
            parent=root,
            title="Choose a Video File",
            initialdir=os.getcwd(),
            filetypes=[
                ("Video Files", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            selected_video.set(path)

    btn_frame = tk.Frame(card, bg="#1e293b")
    btn_frame.pack(fill=tk.X)

    browse_btn = tk.Button(
        btn_frame,
        text="📁 Browse Computer...",
        font=("Segoe UI", 10, "bold"),
        bg="#3b82f6",
        fg="#ffffff",
        activebackground="#2563eb",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=12,
        pady=6,
        cursor="hand2",
        command=browse_file,
    )
    browse_btn.pack(side=tk.LEFT, padx=(0, 8))

    def set_webcam():
        selected_video.set("0")

    webcam_btn = tk.Button(
        btn_frame,
        text="📷 Use Webcam",
        font=("Segoe UI", 10),
        bg="#334155",
        fg="#e2e8f0",
        activebackground="#475569",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=12,
        pady=6,
        cursor="hand2",
        command=set_webcam,
    )
    webcam_btn.pack(side=tk.LEFT)

    # Demo files helper
    demo_frame = tk.Frame(root, bg="#121826")
    demo_frame.pack(fill=tk.X, padx=24, pady=(10, 5))

    demo_lbl = ttk.Label(demo_frame, text="Or quick-select sample footage:", font=("Segoe UI", 9))
    demo_lbl.pack(anchor=tk.W, pady=(0, 4))

    demos_sub = tk.Frame(demo_frame, bg="#121826")
    demos_sub.pack(fill=tk.X)

    for d in ["demo1.mp4", "demo2.mp4", "demo3.mp4"]:
        if os.path.exists(d):
            btn = tk.Button(
                demos_sub,
                text=d,
                font=("Segoe UI", 9),
                bg="#1e293b",
                fg="#38bdf8",
                relief=tk.FLAT,
                padx=8,
                pady=2,
                cursor="hand2",
                command=lambda name=d: selected_video.set(os.path.abspath(name)),
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))

    # Run detection
    def run_detection():
        video = selected_video.get().strip()
        if not video:
            messagebox.showwarning("No Video Selected", "Please browse and select a video file first.", parent=root)
            return

        root.withdraw()
        print(f"\n[INFO] Running detection on: {video}")
        output = "shoplifting_output.avi"
        detector = ShopliftingDetector(
            weights_path="yolov8n.pt",
            input_path=video,
            output_path=output,
            conf_threshold=0.25,
            proximity_ratio=0.45,
            show_video=True,
        )
        try:
            detector.process_video()
        finally:
            detector.cleanup()
            root.deiconify()

    start_btn = tk.Button(
        root,
        text="▶  START DETECTION",
        font=("Segoe UI", 12, "bold"),
        bg="#10b981",
        fg="#ffffff",
        activebackground="#059669",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        padx=16,
        pady=8,
        cursor="hand2",
        command=run_detection,
    )
    start_btn.pack(fill=tk.X, padx=24, pady=(20, 10))

    # Auto-open file picker dialog on launch if nothing selected
    root.after(200, browse_file)

    root.mainloop()


if __name__ == "__main__":
    launch_gui_launcher()
