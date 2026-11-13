import scservo_sdk as scs

PORT = "/dev/cu.usbmodem5B910308701"
BAUD = 1000000
SERVO_ID = 1

port = scs.PortHandler(PORT)
packet = scs.PacketHandler(0)

if port.openPort() and port.setBaudRate(BAUD):
    model, result, error = packet.ping(port, SERVO_ID)
    if result == scs.COMM_SUCCESS:
        print(f"Servo {SERVO_ID} found, model number {model}")
    else:
        print("No response:", packet.getTxRxResult(result))
    port.closePort()
else:
    print("Couldn't open the port")
