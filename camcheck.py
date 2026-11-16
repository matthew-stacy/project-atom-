import time
import cv2

for i in range(3):
    cap = cv2.VideoCapture(i)
    time.sleep(1.0)               # let the camera start up
    for _ in range(15):           # throw away warm-up frames
        cap.read()
    ok, frame = cap.read()
    print(i, ok, None if frame is None else frame.shape, cap.get(cv2.CAP_PROP_FPS))
    cap.release()
