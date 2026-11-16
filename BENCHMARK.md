# Project ATOM — Benchmark Record

How the latency numbers in the README were produced, and what is and isn't confirmed.
⚠️ = not confirmed.

## Runs

| Run | Raw log (copy in `results/`) | Cycles | Settings |
|---|---|---|---|
| Baseline | `logs/run_20261114_091510.csv` → `results/baseline_run.csv` | 1797 | blocking `cap.read()` in main loop, preview every frame |
| Threaded | `logs/run_threaded_20261114_095113.csv` → `results/threaded_run.csv` | 2759 | background camera thread, `PREVIEW_EVERY = 1` |
| Optimized | `logs/run_threaded_preview3_20261114_095747.csv` → `results/optimized_run.csv` | 3593 | background camera thread, `PREVIEW_EVERY = 3` |

- All runs: Nov 14 2026, `RUN_SECONDS = 120`, `DRY_RUN = False` (servo live), one ST3215 (ID 1).
- Only one variable changes between runs: baseline → threaded (capture thread), threaded → optimized (preview frequency).
- `results/*.csv` are byte-identical copies of the logs above.
- `logs/run_20261114_091349.csv` and `logs/run_20261114_091400.csv` are aborted runs, not used.
- Summaries: `results/baseline_summary.txt`, `results/optimized_summary.txt`, `results/comparison.txt`.

## How to reproduce

1. Start the pose service from the repo root:
   `./run_service.sh`
   (runs `uvicorn service.app:app --host 127.0.0.1 --port 8000`, 1 worker)
   ⚠️ The Nov 14 runs predate this script; the exact command used then wasn't recorded.
   It was almost certainly the same, based on `loop.py` (`API_URL = http://127.0.0.1:8000/predict`).
2. Set the run constants at the top of `loop.py` (`RUN_LABEL`, `RUN_SECONDS`, `PREVIEW_EVERY`, `DRY_RUN`), then:
   `python loop.py`
3. Summarize or compare:
   `python analyze.py <run.csv>` · `python analyze.py <A.csv> <B.csv>`

## Code version

- Results committed at `2b0d610` (HEAD on Nov 14).
- ⚠️ Each run happened before its code was committed:
  - Baseline ran 09:15; timing code committed 09:22 in `0c91728`.
  - Threaded runs ran 09:51 / 09:57; code committed 10:01 in `c7aa891` (HEAD `loop.py` has `RUN_LABEL = "threaded_preview3"`, matching the optimized run).
  - So the exact code per run is very likely, not proven.

## Model

- MediaPipe Pose Landmarker **Lite**, float16, version 1
- Source: https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
- SHA-256: `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a` (verified against the official download)
- Path: `pose/models/pose_landmarker_lite.task` (gitignored — download it from the URL above)
- `RunningMode.IMAGE`, `num_poses = 1`; elbow angle from landmarks 12 / 14 / 16 (right shoulder, elbow, wrist)
- Delegate: CPU — MediaPipe's default; ⚠️ not set explicitly in code

## Runtime

- Python 3.15.2 (Homebrew), `.venv`
- mediapipe 1.2.3 · opencv-python 5.0.0.93 · fastapi 0.162.7 · uvicorn 0.54.0 · numpy 2.5.4 · requests 2.34.2 · feetech-servo-sdk 1.0.0
- Client (`loop.py`) and service on the same machine over 127.0.0.1

## Device

- MacBook Pro, Apple M1 Max (10-core CPU, 24-core GPU), 64 GB RAM
- macOS 27.0.1 (build 26A434)
- Plugged in during all runs
- Servo: Waveshare bus servo adapter at `/dev/cu.usbmodem5B910308701`, 1,000,000 baud

## Camera

- Built-in FaceTime HD Camera, OpenCV index 0, AVFoundation backend
- Native: 1920×1080 @ 30 FPS (⚠️ measured Nov 16 with `camcheck.py`, not logged during the runs; same camera and code)
- Each frame resized to 640 px wide (aspect preserved → 640×360) and JPEG-encoded at quality 80 before `/predict`
- Continuity Camera (iPhone) can take index 0 — keep it off when benchmarking

## Timers (`time.perf_counter`)

| Field | Starts | Stops | Notes |
|---|---|---|---|
| `capture_ms` | before getting a frame | frame returned | Baseline: blocking `cap.read()`. Threaded: waiting for a newer frame from the thread. Not the same quantity across runs. |
| `encode_ms` | before resize | after `cv2.imencode` | |
| `request_ms` | before `session.post` | after `response.json()` | |
| `inference_ms` | server, before `landmarker.detect` (inside lock) | after `detect` | rounded to 0.1 ms |
| `network_ms` | = `request_ms − inference_ms` | | Not pure network: includes upload, server JPEG decode, BGR→RGB, FastAPI + JSON overhead |
| `servo_ms` | before `write2ByteTxRx` | status packet received | Command round-trip, not motion. Only on cycles where a command was sent (deadband 8) |
| `frame_age_ms` | when the camera thread's `cap.read()` returned | after the servo step | Threaded runs only. Not sensor exposure and not physical motion; also recorded on cycles with no servo write. README "Camera → servo" = this field |
| `display_ms` | before preview | after `waitKey` | 0 on cycles without preview |
| `total_ms` | start of cycle | before CSV write | Excludes CSV write and printing; includes first-cycle warm-up (~300 ms) |

- FPS = cycles ÷ (last timestamp + last `total_ms` − first timestamp)
- Percentiles via `numpy.percentile` over all cycles, warm-up included

## Known gaps / next fixes

- [ ] Record the service launch command in a script
- [ ] Log camera index, resolution and FPS at startup in `loop.py`
- [ ] Set the MediaPipe delegate explicitly
- [ ] Rename `network_ms` → `overhead_ms` (or time server decode separately)
- [ ] Drop the first N warm-up cycles from percentiles
- [ ] Commit code before each benchmark run and log the commit hash in the CSV
