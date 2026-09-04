import os
from dotenv import load_dotenv
from roboflow import Roboflow

load_dotenv()

api_key = os.getenv("ROBOFLOW_API_KEY")
if not api_key:
    raise RuntimeError("ROBOFLOW_API_KEY not found in .env file")

rf = Roboflow(api_key=api_key)
project = rf.workspace("fastnuces-uakqb").project("fyp-shoplift")
version = project.version(1)
dataset = version.download("yolov11")
                