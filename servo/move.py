import time
import scservo_sdk as scs

PORT = "/dev/cu.usbmodem5B910308701"
BAUD = 1000000
SERVO_ID = 1

# ST3215 memory addresses
TORQUE_ENABLE = 40
ACCELERATION = 41
GOAL_POSITION = 42
GOAL_SPEED = 46
PRESENT_POSITION = 56

SPEED = 800
ACCEL = 30
TOLERANCE = 10     # "close enough" in steps
TIMEOUT = 5        # seconds before giving up on a move

TARGETS = [2048, 1024, 3072, 2048]

port = scs.PortHandler(PORT)
packet = scs.PacketHandler(0)


def read_position():
    position, result, error = packet.read2ByteTxRx(port, SERVO_ID, PRESENT_POSITION)
    return position if result == scs.COMM_SUCCESS else None


def move_to(target):
    packet.write2ByteTxRx(port, SERVO_ID, GOAL_POSITION, target)
    start = time.time()
    while time.time() - start < TIMEOUT:
        position = read_position()
        if position is not None and abs(position - target) <= TOLERANCE:
            return position, time.time() - start
        time.sleep(0.05)
    return read_position(), None


if not (port.openPort() and port.setBaudRate(BAUD)):
    print("Couldn't open the port")
    raise SystemExit

try:
    packet.write1ByteTxRx(port, SERVO_ID, ACCELERATION, ACCEL)
    packet.write2ByteTxRx(port, SERVO_ID, GOAL_SPEED, SPEED)
    packet.write1ByteTxRx(port, SERVO_ID, TORQUE_ENABLE, 1)

    for target in TARGETS:
        print(f"Moving to {target} ({target * 360 / 4096:.0f}°)")
        position, seconds = move_to(target)
        if seconds is None:
            print(f"  Timed out at {position}")
        else:
            print(f"  Arrived at {position} ({position * 360 / 4096:.1f}°) in {seconds:.2f}s")
        time.sleep(0.5)

    print("Done.")
finally:
    packet.write1ByteTxRx(port, SERVO_ID, TORQUE_ENABLE, 0)
    port.closePort()
