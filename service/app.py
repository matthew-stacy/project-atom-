import math
import threading

import cv2
import mediapipe as mp
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile

MODEL = "pose/models/pose_landmarker_lite.task"
SHOULDER, ELBOW, WRIST = 12, 14, 16

app = FastAPI(title="Project ATOM pose service")

# Load the model once when the server starts, not on every request
options = mp.tasks.vision.PoseLandmarkerOptions(
    base_options=mp.tasks.BaseOptions(model_asset_path=MODEL),
    running_mode=mp.tasks.vision.RunningMode.IMAGE,
    num_poses=1,
)
landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
lock = threading.Lock()  # the model handles one image at a time


def angle_at(a, b, c):
    ang = math.degrees(
        math.atan2(c.y - b.y, c.x - b.x) - math.atan2(a.y - b.y, a.x - b.x)
    )
    ang = abs(ang)
    return 360 - ang if ang > 180 else ang


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict")
def predict(file: UploadFile = File(...)):
    data = np.frombuffer(file.file.read(), dtype=np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not read image")

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    with lock:
        result = landmarker.detect(image)

    if not result.pose_landmarks:
        return {"person_detected": False}

    lm = result.pose_landmarks[0]
    s, e, w = lm[SHOULDER], lm[ELBOW], lm[WRIST]
    visibility = min(s.visibility, e.visibility, w.visibility)

    return {
        "person_detected": True,
        "arm_visible": visibility > 0.5,
        "elbow_angle": round(angle_at(s, e, w), 1),
        "visibility": round(visibility, 2),
    }
