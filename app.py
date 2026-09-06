import os
import shutil
import uuid
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from detector_engine import ShopliftingDetectionEngine

# Load environment variables from .env
load_dotenv()

# Create directories
os.makedirs("uploads", exist_ok=True)
os.makedirs("outputs", exist_ok=True)
os.makedirs("outputs/snapshots", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
os.makedirs("static/snapshots", exist_ok=True)
os.makedirs("templates", exist_ok=True)

app = FastAPI(title="AI Shoplifting & Theft Detection System", version="2.0.0")

# CORS: read from env or default to permissive for dev
_allowed_origins = os.getenv("SENTINEL_ALLOWED_ORIGINS", "")
if _allowed_origins:
    origins = [o.strip() for o in _allowed_origins.split(",") if o.strip()]
else:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Shared detection engine
engine = ShopliftingDetectionEngine(weights_path="yolo11n.pt")
LATEST_OUTPUT_FILE = "outputs/latest_recording.avi"

# API key for optional authentication
API_KEY = os.getenv("SENTINEL_API_KEY", "")


# Optional API key authentication middleware
@app.middleware("http")
async def api_key_auth_middleware(request: Request, call_next):
    """If SENTINEL_API_KEY is set, require X-API-Key header on /api/* routes."""
    if API_KEY and request.url.path.startswith("/api/"):
        provided_key = request.headers.get("X-API-Key", "")
        if provided_key != API_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
    response = await call_next(request)
    return response


@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = os.path.join("templates", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h2>Web App is Initializing...</h2>")


@app.get("/presentation", response_class=HTMLResponse)
async def get_presentation():
    pres_path = os.path.join("templates", "presentation.html")
    if os.path.exists(pres_path):
        with open(pres_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h2>Presentation Deck Not Found</h2>")


@app.get("/api/demos")
async def get_demos():
    """List available sample demo videos."""
    demos = []
    sample_files = ["demo.mp4", "demo1.mp4", "demo2.mp4", "demo3.mp4"]
    for f in sample_files:
        if os.path.exists(f):
            size_mb = round(os.path.getsize(f) / (1024 * 1024), 2)
            demos.append({"name": f, "size_mb": size_mb, "path": f})
    return {"demos": demos}


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """Handle custom video uploads."""
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in [".mp4", ".avi", ".mov", ".mkv", ".webm"]:
        raise HTTPException(status_code=400, detail="Unsupported video format. Please upload MP4, AVI, MOV, or MKV.")

    unique_filename = f"upload_{uuid.uuid4().hex[:8]}{file_ext}"
    dest_path = os.path.join("uploads", unique_filename)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    size_mb = round(os.path.getsize(dest_path) / (1024 * 1024), 2)
    return {
        "success": True,
        "filename": file.filename,
        "path": dest_path,
        "size_mb": size_mb,
    }


@app.get("/api/stream")
async def video_stream(
    source: str = Query("demo3.mp4", description="Video path or webcam index"),
    conf: float = Query(0.25, ge=0.1, le=0.9),
    proximity: float = Query(0.45, ge=0.1, le=1.2),
):
    """Stream live annotated video feed."""
    global LATEST_OUTPUT_FILE

    # Stop any currently running stream before starting a new one
    engine.stop_stream()

    LATEST_OUTPUT_FILE = os.path.join("outputs", f"recording_{uuid.uuid4().hex[:6]}.avi")

    return StreamingResponse(
        engine.process_and_stream(
            video_source=source,
            output_save_path=LATEST_OUTPUT_FILE,
            conf_threshold=conf,
            proximity_ratio=proximity,
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/stop")
async def stop_stream():
    """Stop the currently running stream gracefully."""
    engine.stop_stream()
    return {"status": "stopped"}


@app.get("/api/telemetry")
async def get_telemetry():
    """Fetch real-time detection telemetry and incident log."""
    return engine.telemetry


@app.get("/api/download")
async def download_output():
    """Download the latest annotated recording."""
    global LATEST_OUTPUT_FILE
    if os.path.exists(LATEST_OUTPUT_FILE):
        return FileResponse(
            LATEST_OUTPUT_FILE,
            media_type="video/x-msvideo",
            filename=os.path.basename(LATEST_OUTPUT_FILE),
        )
    elif os.path.exists("shoplifting_output.avi"):
        return FileResponse(
            "shoplifting_output.avi",
            media_type="video/x-msvideo",
            filename="shoplifting_output.avi",
        )
    raise HTTPException(status_code=404, detail="No recorded output available yet.")


@app.get("/api/snapshots")
async def get_snapshots():
    """List all persisted crime scene snapshots, newest first."""
    snapshots = []
    snap_dir = os.path.join("static", "snapshots")
    if os.path.exists(snap_dir):
        files = [f for f in os.listdir(snap_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(snap_dir, x)), reverse=True)

        for f in files:
            full_path = os.path.join(snap_dir, f)
            mtime = os.path.getmtime(full_path)
            time_str = datetime.fromtimestamp(mtime).strftime("%H:%M:%S")
            frame_num = 0
            if "_f" in f:
                try:
                    parts = f.split("_f")[1].split("_")
                    frame_num = int(parts[0])
                except Exception:
                    frame_num = 0

            snapshots.append({
                "url": f"/static/snapshots/{f}",
                "filename": f,
                "frame": frame_num,
                "timestamp": time_str,
                "confidence": "Alert",
            })
    return {"snapshots": snapshots}


@app.post("/api/snapshots/clear")
async def clear_snapshots():
    """Clear all saved crime scene snapshots from disk."""
    snap_dir = os.path.join("static", "snapshots")
    count = 0
    if os.path.exists(snap_dir):
        for f in os.listdir(snap_dir):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                try:
                    os.remove(os.path.join(snap_dir, f))
                    count += 1
                except Exception:
                    pass
    return {"status": "cleared", "count": count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
