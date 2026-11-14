import csv
import os
import time
from datetime import datetime

import cv2
import requests
import scservo_sdk as scs

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

DRY_RUN = False        # must be False to measure servo writes
RUN_SECONDS = 120      # stop automatically after this long (0 = run until q)
LOG_DIR = "logs"

FIELDS = [
    "cycle", "timestamp",
    "capture_ms", "encode_ms", "request_ms", "inference_ms", "network_ms",
    "servo_ms", "display_ms", "total_ms",
    "arm_visible", "angle", "target", "sent", "error",
]


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
log_path = os.path.join(LOG_DIR, f"run_{datetime.now():%Y%m%d_%H%M%S}.csv")
log_file = open(log_path, "w", newline="")
writer = csv.DictWriter(log_file, fieldnames=FIELDS)
writer.writeheader()

session = requests.Session()
cap = cv2.VideoCapture(0)
smoothed = None
last_sent = None
cycle = 0

print("DRY RUN - servo will not move" if DRY_RUN else "LIVE - servo will move")
print(f"Logging to {log_path}")
if RUN_SECONDS:
    print(f"Running for {RUN_SECONDS} seconds. Press q to stop early.")

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

        # 1. Capture
        t = time.perf_counter()
        ok, frame = cap.read()
        row["capture_ms"] = round(ms_since(t), 2)
        if not ok:
            print("Camera read failed")
            break

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

        # 5. Display
        t = time.perf_counter()
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
    cap.release()
    cv2.destroyAllWindows()
    if not DRY_RUN:
        packet.write1ByteTxRx(port, SERVO_ID, TORQUE_ENABLE, 0)
        port.closePort()
    print(f"Stopped. Logged {cycle} cycles to {log_path}")
