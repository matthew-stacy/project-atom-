import math
import time
import cv2
import mediapipe as mp

MODEL = "pose/models/pose_landmarker_lite.task"

# MediaPipe landmark numbers for your RIGHT arm
SHOULDER, ELBOW, WRIST = 12, 14, 16

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
RunningMode = mp.tasks.vision.RunningMode


def angle_at(a, b, c):
    """Angle at point b (degrees) formed by points a-b-c."""
    ang = math.degrees(
        math.atan2(c.y - b.y, c.x - b.x) - math.atan2(a.y - b.y, a.x - b.x)
    )
    ang = abs(ang)
    return 360 - ang if ang > 180 else ang


options = PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL),
    running_mode=RunningMode.VIDEO,
    num_poses=1,
)

cap = cv2.VideoCapture(0)
start = time.time()
last = time.time()

with PoseLandmarker.create_from_options(options) as landmarker:
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = int((time.time() - start) * 1000)
        result = landmarker.detect_for_video(image, timestamp_ms)

        text = "No person detected"
        if result.pose_landmarks:
            lm = result.pose_landmarks[0]
            s, e, wr = lm[SHOULDER], lm[ELBOW], lm[WRIST]

            if min(s.visibility, e.visibility, wr.visibility) > 0.5:
                points = [(int(p.x * w), int(p.y * h)) for p in (s, e, wr)]
                cv2.line(frame, points[0], points[1], (0, 255, 0), 4)
                cv2.line(frame, points[1], points[2], (0, 255, 0), 4)
                for p in points:
                    cv2.circle(frame, p, 8, (0, 0, 255), -1)
                text = f"Elbow angle: {angle_at(s, e, wr):.0f} deg"
            else:
                text = "Right arm not fully visible"

        # Mirror the picture so it feels like a mirror, then add the text
        frame = cv2.flip(frame, 1)

        now = time.time()
        fps = 1 / (now - last)
        last = now

        cv2.putText(frame, f"{text}  |  {fps:.0f} FPS", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        print(f"{text} | {fps:.0f} FPS")
        cv2.imshow("Project ATOM - pose", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

cap.release()
cv2.destroyAllWindows()
