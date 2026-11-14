import time

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
ARM_BENT = 37.0        # degrees, fully bent
ARM_STRAIGHT = 180.0   # degrees, straight
SERVO_MIN = 1024       # safety limit (90 deg)
SERVO_MAX = 3072       # safety limit (270 deg)
INVERT = False         # set True if the servo moves the wrong way

# --- Smoothing ---
SMOOTHING = 0.3        # 0-1: lower = smoother but slower to react
DEADBAND = 8           # ignore changes smaller than this many steps

DRY_RUN = False         # True = print only, servo does not move


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

session = requests.Session()
cap = cv2.VideoCapture(0)
smoothed = None
last_sent = None

print("DRY RUN - servo will not move" if DRY_RUN else "LIVE - servo will move")
print("Press q in the video window (or Ctrl + C here) to stop.")

try:
    while True:
        loop_start = time.perf_counter()

        # 1. Capture a frame
        ok, frame = cap.read()
        if not ok:
            print("Camera read failed")
            break

        # 2. Send it to /predict (shrunk and compressed so it's fast)
        width = 640
        height = int(frame.shape[0] * width / frame.shape[1])
        small = cv2.resize(frame, (width, height))
        _, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])

        data = None
        try:
            response = session.post(
                API_URL,
                files={"file": ("frame.jpg", jpg.tobytes(), "image/jpeg")},
                timeout=1.0,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as err:
            status = f"Service error: {err.__class__.__name__}"

        # 3. Map the angle to a servo position and 4. send the command
        if data and data.get("arm_visible"):
            angle = data["elbow_angle"]
            if smoothed is None:
                smoothed = angle
            else:
                smoothed = SMOOTHING * angle + (1 - SMOOTHING) * smoothed
            target = angle_to_position(smoothed)

            if last_sent is None or abs(target - last_sent) >= DEADBAND:
                if not DRY_RUN:
                    packet.write2ByteTxRx(port, SERVO_ID, GOAL_POSITION, target)
                last_sent = target

            status = (
                f"angle {angle:5.1f} | smooth {smoothed:5.1f} | pos {target} "
                f"| infer {data['inference_ms']} ms"
            )
        elif data:
            status = "Arm not visible - holding position"

        loop_ms = (time.perf_counter() - loop_start) * 1000
        line = f"{status} | loop {loop_ms:.0f} ms"
        print(line)

        display = cv2.flip(frame, 1)
        cv2.putText(display, line, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.imshow("Project ATOM - loop", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

except KeyboardInterrupt:
    pass
finally:
    cap.release()
    cv2.destroyAllWindows()
    if not DRY_RUN:
        packet.write1ByteTxRx(port, SERVO_ID, TORQUE_ENABLE, 0)
        port.closePort()
    print("Stopped.")

