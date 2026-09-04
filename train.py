"""
Train a custom YOLOv8 model on the FYP-Shoplift dataset.

Usage:
    python train.py
    python train.py --epochs 200 --batch 32
    python train.py --resume
"""

import argparse
from ultralytics import YOLO


def parse_args():
    parser = argparse.ArgumentParser(description="Train YOLOv8 Shoplifting Detector")
    parser.add_argument(
        "--model", type=str, default="yolov8n.yaml",
        help="YOLO model config (yolov8n.yaml, yolov8s.yaml, etc.)",
    )
    parser.add_argument(
        "--data", type=str, default="FYP-Shoplift-1/data.yaml",
        help="Path to dataset YAML config",
    )
    parser.add_argument("--epochs", type=int, default=100, help="Number of training epochs")
    parser.add_argument("--batch", type=int, default=16, help="Batch size (-1 for auto)")
    parser.add_argument("--imgsz", type=int, default=640, help="Input image size")
    parser.add_argument("--project", type=str, default="runs/train", help="Output project directory")
    parser.add_argument("--name", type=str, default="shoplift_detector", help="Run name")
    parser.add_argument("--resume", action="store_true", help="Resume training from last checkpoint")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.resume:
        # Resume from the last checkpoint
        model = YOLO(f"{args.project}/{args.name}/weights/last.pt")
        results = model.train(resume=True)
    else:
        model = YOLO(args.model)
        results = model.train(
            data=args.data,
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            project=args.project,
            name=args.name,
            exist_ok=True,
            patience=20,          # early stopping patience
            save=True,           # save checkpoints
            save_period=10,      # save every N epochs
            pretrained=True,     # use pretrained weights
            optimizer="auto",
            lr0=0.01,
            lrf=0.01,
            momentum=0.937,
            weight_decay=0.0005,
            warmup_epochs=3.0,
            warmup_momentum=0.8,
            warmup_bias_lr=0.1,
            box=7.5,
            cls=0.5,
            dfl=1.5,
            amp=True,            # mixed precision for faster training
        )

    print("\n[INFO] Training complete.")
    print(f"[INFO] Best model saved at: {args.project}/{args.name}/weights/best.pt")
    print(f"[INFO] Use this model with: python app.py or python shoplifting_detection.py --weights {args.project}/{args.name}/weights/best.pt")
