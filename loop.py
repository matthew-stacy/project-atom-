import csv
import hashlib
import json
import os
import platform
import subprocess
import threading
import time
from datetime import datetime

import cv2
import requests
import scservo_sdk as scs

# --- Run settings ---
RUN_LABEL = "clean_baseline"   # goes in the log filename
RUN_SECONDS = 120        # stop automatically (0 = run until q / Ctrl + C)
SHOW_PREVIEW = True      # False = no video window (stop with Ctrl + C)
PREVIEW_EVERY = 3        # draw the window every N cycles
DRY_RUN = False          # must be False to measure servo writes
LOG_DIR = "logs"
CAMERA_INDEX = 0 # 0 = FaceTime HD (keep Continuity Camera off)
MODEL_PATH = "pose/models/pose_landmarker_lite.task" # must match service/app.py


# --- Service ---
API_URL = "http://127.0.0.1:8000/predict"

# --- Servo connection ---
PORT = "/dev/cu.usbmodem5B910308701"
BAUD = 1000000
SERVO_ID = 1

# ST3215 memory addresses
TORQUE_ENABLE = 40
ACCELERATION = 41
GOAL_POSITION = 42
GOAL_SPEED = 46

SPEED = 1500
ACCEL = 50

# --- Mapping: your measured elbow range -> servo range ---
ARM_BENT = 37.0
ARM_STRAIGHT = 180.0
SERVO_MIN = 1024
SERVO_MAX = 3072
INVERT = False

# --- Smoothing ---
SMOOTHING = 0.3
DEADBAND = 8

FIELDS = [
    "cycle", "timestamp", "frame_id", "skipped_frames",
    "capture_ms", "encode_ms", "request_ms", "inference_ms", "network_ms",
    "servo_ms", "frame_age_ms", "display_ms", "total_ms",
    "arm_visible", "angle", "target", "sent", "error",
]


class CameraThread:
    """Reads the camera nonstop in the background and keeps only the newest frame."""

    def __init__(self, index=0):
        self.cap = cv2.VideoCapture(index)
        self.cond = threading.Condition()
        self.frame = None
        self.frame_id = 0
        self.frame_time = 0.0
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            captured_at = time.perf_counter()
            with self.cond:
                self.frame = frame
                self.frame_id += 1
                self.frame_time = captured_at
                self.cond.notify_all()

    def read_new(self, last_id, timeout=3.0):
        """Wait for a frame newer than last_id, then return it."""
        with self.cond:
            got_new = self.cond.wait_for(
                lambda: self.frame_id > last_id or not self.running, timeout=timeout
            )
            if not got_new or self.frame is None:
                return None, last_id, None
            return self.frame, self.frame_id, self.frame_time

    def stop(self):
        self.running = False
        with self.cond:
            self.cond.notify_all()
        self.thread.join(timeout=1.0)
        self.cap.release()


def ms_since(start):
    return (time.perf_counter() - start) * 1000


def clamp(value, low, high):
    return max(low, min(high, value))


def angle_to_position(angle):
    t = (angle - ARM_BENT) / (ARM_STRAIGHT - ARM_BENT)
    t = clamp(t, 0.0, 1.0)
    if INVERT:
        t = 1.0 - t
    position = SERVO_MIN + t * (SERVO_MAX - SERVO_MIN)
    return int(clamp(round(position), SERVO_MIN, SERVO_MAX))


# --- Servo setup ---
port = packet = None
if not DRY_RUN:
    port = scs.PortHandler(PORT)
    packet = scs.PacketHandler(0)
    if not (port.openPort() and port.setBaudRate(BAUD)):
        print("Couldn't open the servo port")
        raise SystemExit
    packet.write1ByteTxRx(port, SERVO_ID, ACCELERATION, ACCEL)
    packet.write2ByteTxRx(port, SERVO_ID, GOAL_SPEED, SPEED)
    packet.write1ByteTxRx(port, SERVO_ID, TORQUE_ENABLE, 1)

# --- Log file ---
os.makedirs(LOG_DIR, exist_ok=True)
log_path = os.path.join(LOG_DIR, f"run_{RUN_LABEL}_{datetime.now():%Y%m%d_%H%M%S}.csv")
log_file = open(log_path, "w", newline="")
writer = csv.DictWriter(log_file, fieldnames=FIELDS)
writer.writeheader()

session = requests.Session()
camera = CameraThread(CAMERA_INDEX)

# --- Run metadata: saved next to the CSV so every run records how it was made ---
REPO = os.path.dirname(os.path.abspath(__file__))


def git_commit():
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True
        ).strip()
        dirty = subprocess.call(["git", "diff", "--quiet", "HEAD"], cwd=REPO) != 0
        return commit + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


def file_sha256(path):
    h = hashlib.sha256()
    with open(os.path.join(REPO, path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


meta = {
    "run_label": RUN_LABEL,
    "started": datetime.now().isoformat(timespec="seconds"),
    "git_commit": git_commit(),
    "run_seconds": RUN_SECONDS,
    "preview_every": PREVIEW_EVERY if SHOW_PREVIEW else 0,
    "dry_run": DRY_RUN,
    "camera_index": CAMERA_INDEX,
    "camera_width": camera.cap.get(cv2.CAP_PROP_FRAME_WIDTH),
    "camera_height": camera.cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
    "camera_fps": camera.cap.get(cv2.CAP_PROP_FPS),
    "send_width": 640,
    "jpeg_quality": 80,
    "model_path": MODEL_PATH,
    "model_sha256": file_sha256(MODEL_PATH),
    "api_url": API_URL,
    "servo_id": SERVO_ID,
    "python": platform.python_version(),
    "opencv": cv2.__version__,
    "os": platform.platform(),
}
meta_path = log_path.replace(".csv", ".json")
with open(meta_path, "w") as f:
    json.dump(meta, f, indent=2)
print(f"Run settings saved to {meta_path}")
smoothed = None
last_sent = None
last_frame_id = 0
cycle = 0

print("DRY RUN - servo will not move" if DRY_RUN else "LIVE - servo will move")
print(f"Logging to {log_path}")
if RUN_SECONDS:
    print(f"Running for {RUN_SECONDS} seconds.")
print("Stop early with q in the video window, or Ctrl + C here.")

run_start = time.perf_counter()

try:
    while True:
        if RUN_SECONDS and time.perf_counter() - run_start >= RUN_SECONDS:
            break

        cycle += 1
        row = {field: "" for field in FIELDS}
        row["cycle"] = cycle
        row["timestamp"] = round(time.time(), 4)
        row["sent"] = 0
        status = ""
        cycle_start = time.perf_counter()

        # 1. Get the newest frame (the camera thread already captured it)
        t = time.perf_counter()
        frame, frame_id, frame_time = camera.read_new(last_frame_id)
        row["capture_ms"] = round(ms_since(t), 2)
        if frame is None:
            print("No new frame from camera")
            break
        row["frame_id"] = frame_id
        row["skipped_frames"] = frame_id - last_frame_id - 1 if last_frame_id else 0
        last_frame_id = frame_id

        # 2. Encode
        t = time.perf_counter()
        width = 640
        height = int(frame.shape[0] * width / frame.shape[1])
        small = cv2.resize(frame, (width, height))
        _, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
        row["encode_ms"] = round(ms_since(t), 2)

        # 3. Request: network + server inference
        data = None
        t = time.perf_counter()
        try:
            response = session.post(
                API_URL,
                files={"file": ("frame.jpg", jpg.tobytes(), "image/jpeg")},
                timeout=1.0,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as err:
            row["error"] = err.__class__.__name__
            status = f"Service error: {row['error']}"
        request_ms = ms_since(t)
        row["request_ms"] = round(request_ms, 2)

        if data:
            inference_ms = float(data.get("inference_ms", 0.0))
            row["inference_ms"] = inference_ms
            row["network_ms"] = round(request_ms - inference_ms, 2)

        # 4. Map angle and write to servo
        if data and data.get("arm_visible"):
            angle = data["elbow_angle"]
            if smoothed is None:
                smoothed = angle
            else:
                smoothed = SMOOTHING * angle + (1 - SMOOTHING) * smoothed
            target = angle_to_position(smoothed)

            row["arm_visible"] = 1
            row["angle"] = angle
            row["target"] = target

            if last_sent is None or abs(target - last_sent) >= DEADBAND:
                t = time.perf_counter()
                if not DRY_RUN:
                    packet.write2ByteTxRx(port, SERVO_ID, GOAL_POSITION, target)
                row["servo_ms"] = round(ms_since(t), 2)
                row["sent"] = 1
                last_sent = target

            status = f"angle {angle:5.1f} -> pos {target}"
        elif data:
            row["arm_visible"] = 0
            status = "Arm not visible - holding position"

        # Camera-to-motion latency: from when the frame was taken until now
        row["frame_age_ms"] = round((time.perf_counter() - frame_time) * 1000, 2)

        # 5. Display (optional, and only every PREVIEW_EVERY cycles)
        t = time.perf_counter()
        key = -1
        if SHOW_PREVIEW and cycle % PREVIEW_EVERY == 0:
            display = cv2.flip(frame, 1)
            cv2.putText(display, status, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow("Project ATOM - loop", display)
            key = cv2.waitKey(1) & 0xFF
        row["display_ms"] = round(ms_since(t), 2)

        row["total_ms"] = round(ms_since(cycle_start), 2)
        writer.writerow(row)

        # Print only every 20 cycles so printing doesn't slow the loop
        if cycle % 20 == 0:
            elapsed = time.perf_counter() - run_start
            print(f"[{elapsed:5.1f}s] cycle {cycle} | {status} | total {row['total_ms']:.0f} ms")

        if key == ord("q"):
            break

except KeyboardInterrupt:
    pass
finally:
    log_file.close()
    camera.stop()
    cv2.destroyAllWindows()
    if not DRY_RUN:
        packet.write1ByteTxRx(port, SERVO_ID, TORQUE_ENABLE, 0)
        port.closePort()
    print(f"Stopped. Logged {cycle} cycles to {log_path}")
