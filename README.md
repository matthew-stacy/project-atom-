# project-atom-

The Goal
The Metrics (p50/95 latency, FPS, late commands)
Date: November 13, 2026


# Project ATOM

A robotics project built around the Feetech/Waveshare ST3215 serial bus servo.

## Hardware
- ST3215 serial bus servo
- Waveshare Bus Servo Adapter
- External power supply for the servo
- Custom servo bracket (designed in Fusion)

## Setup
1. Clone the repo and create a virtual environment:
   python3 -m venv .venv
   source .venv/bin/activate
2. Install dependencies:
   pip install -r requirements.txt
3. Set your serial port in servo/ping.py and run:
   python servo/ping.py

## Status
## Status
- [x] Servo bracket designed in Fusion
- [x] Python SDK installed and servo communication confirmed
- [x] Read servo position
- [x] Move servo to target positions
- [x] Standalone pose tracker (elbow angle + FPS)
- [x] FastAPI service with /predict endpoint
- [x] Map elbow angle to servo position (live mimic)

Updated upstream
## Demo 
https://github.com/user-attachments/assets/81588a6f-7149-407d-b17c-d6eff19aa8b2


## Results

### Baseline (2-minute run, 1797 cycles)
| Stage | p50 ms | p95 ms |
|---|---|---|
| Capture | 21.9 | 26.5 |
| Encode | 0.8 | 0.9 |
| Network | 2.9 | 3.0 |
| Inference | 20.4 | 20.9 |
| Servo write | 0.5 | 0.5 |
| Display | 20.0 | 20.3 |
| **End-to-end** | **66.3** | **71.4** |

- ~15 FPS, 0.1% of cycles over 100 ms, 0 service errors
- Bottleneck: camera wait + preview rendering (~63% of the cycle), not inference
- Raw data: [`results/baseline_run.csv`](results/baseline_run.csv) · Summary: [`results/baseline_summary.txt`](results/baseline_summary.txt)
