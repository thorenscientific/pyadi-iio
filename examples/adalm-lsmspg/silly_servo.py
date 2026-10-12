# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

import argparse
import time

import matplotlib.pyplot as plt  # Matplotlib is a very common Python plotting routine.

import adi  # This is the main pyadi-iio module, contains everything

# Optionally pass URI as command line argument, else use analog.local
# (URI stands for "Uniform Resource Identifier")
# NOTE - when running directly on the Raspberry Pi, you CAN use "local",
# but you must run as root (sudo) because we are writing as well as reading

parser = argparse.ArgumentParser(
    description="AD5593r Curve Tracer, see docs for connections"
)
parser.add_argument(
    "-u",
    default=["ip:analog.local"],
    help="-u (arg) URI of target device's context, eg: 'ip:analog.local',\
    'ip:192.168.2.1',\
    'serial:COM4,115200,8n1n'",
    action="store",
    nargs="*",
)
args = parser.parse_args()
my_uri = args.u[0]

print("uri: " + str(my_uri))

# Instantiate and connect to our AD5592r
# while the "my_" prefix might sound a little childish, it's a reminder that
# it represents the physical chip that is in front of you.
my_ad5592r = adi.ad5592r(uri=my_uri)

motor_drive = my_ad5592r.voltage4_dac
position_fb = my_ad5592r.voltage5_adc
mV_per_lsb = motor_drive.scale

## Servo code!!
# Start with motor drive at midpoint
motor_drive.raw = int(1000 * 1.25 / float(mV_per_lsb))
md = int(1000 * 1.25 / float(mV_per_lsb)) # Shadow motor drive variable

#parameters
ki = 0.1
kp = 20.0
kd = 1.0

duration = 1.0 # seconds

def set_position(position, duration):
    start_time = time.time()
    error_int = 0.0
    error_old = 0.0
    while time.time() - start_time < duration:
        setpoint = position
        fb = position_fb()
        error = setpoint - fb
        error_int += error * ki
        error_d = (error - error_old) * kd
        
#        print("error: ", error)
        md = error * kp + error_int - error_d
        md_clamped = max(0, min(md, 4095))
#        print("motor drive: ", md_clamped)
        motor_drive.raw = md_clamped
        error_old = error # for calculating derivative
        print("Setpoint: ", setpoint, "FB: ", fb, "Error: ", error)
        time.sleep(0.05)

while True:
    for position in range(625, 1875, 200):
        print("setting position to : ", position)
        set_position(float(position), duration)
    

