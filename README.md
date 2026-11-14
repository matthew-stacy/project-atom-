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
- [ ] Map elbow angle to servo position (live mimic)
