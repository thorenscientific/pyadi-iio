# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

"""
ADALM-LSMSPG Production Test Script.

Connections: Four jumper-shunts placed between channels 4-5 and 6-7 on both
P2 and P5

The rest of the tests are just using the onboard circuits.

ToDo: Clean up GPIO test, make that a bit more elegant.
ToDo: Set LM75 hysteresis so the LED blinks, prompt user
ToDo: Basic analog test on NPN and PNP transistor circuits, no need for a
full curve trace, rather pick a place in the middle and do a quick and dirty
beta test.

"""

import argparse
import adi

# Optionally pass URI as command line argument, else use analog.local
# (URI stands for "Uniform Resource Identifier")
# NOTE - when running directly on the Raspberry Pi, you CAN use "local",
# but you must run as root (sudo) because we are writing as well as reading

parser = argparse.ArgumentParser(description="ADALM-LSMSPG Production Test Script")
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
my_ad5593r = adi.ad5592r(uri=my_uri)
my_gpios = adi.one_bit_adc_dac(uri=my_uri)
my_lm75 = adi.lm75(uri=my_uri)


print("\nChecking temperature channel...")
print("Temperature raw: " + str(my_lm75.input))
print(
    "Temperature in deg. Celsius: " + str(my_lm75.to_degrees(my_lm75.input))
)

print("\nUpdate interval: " + str(my_lm75.update_interval))


print("\nMax threshold: " + str(my_lm75.to_degrees(my_lm75.max)))
print("Max hysteresis: " + str(my_lm75.to_degrees(my_lm75.max_hyst)))

print("\nSetting max threshold, hyst. to 30C, 25C...\n")

my_lm75.max = my_lm75.to_millidegrees(30.0)
my_lm75.max_hyst = my_lm75.to_millidegrees(25.0)

print("New thresholds:")
print("Max: " + str(my_lm75.to_degrees(my_lm75.max)))
print("Max hysteresis: " + str(my_lm75.to_degrees(my_lm75.max_hyst)))

# Set outputs...
print("Setting GPIO outputs to initial state...")
my_gpios.gpio_ad5592r_gpo_ch_5 = 0
my_gpios.gpio_ad5592r_gpo_ch_7 = 1

my_gpios.gpio_ad5593r_gpo_ch_5 = 0
my_gpios.gpio_ad5593r_gpo_ch_7 = 1

# Read inputs...
if my_gpios.gpio_ad5592r_gpi_ch_4 == 0:
    print("WooHoo on 5592 ch 4-5!")
else:
    print("D'oh! 5592 ch 4-5! fails :(")

if my_gpios.gpio_ad5592r_gpi_ch_6 == 1:
    print("WooHoo on 5592 ch 6-7!")
else:
    print("D'oh! 5592 ch 6-7! fails :(")

if my_gpios.gpio_ad5593r_gpi_ch_4 == 0:
    print("WooHoo on 5593 ch 4-5!")
else:
    print("D'oh! 5592 ch 4-5! fails :(")

if my_gpios.gpio_ad5593r_gpi_ch_6 == 1:
    print("WooHoo on 5593 ch 6-7!")
else:
    print("D'oh! 5592 ch 6-7! fails :(")

# Set outputs the other way...
print("Setting GPIO outputs to opposite state...")
my_gpios.gpio_ad5592r_gpo_ch_5 = 1
my_gpios.gpio_ad5592r_gpo_ch_7 = 0

my_gpios.gpio_ad5593r_gpo_ch_5 = 1
my_gpios.gpio_ad5593r_gpo_ch_7 = 0

# Read inputs...
if my_gpios.gpio_ad5592r_gpi_ch_4 == 1:
    print("WooHoo on 5592 ch 4-5!")
else:
    print("D'oh! 5592 ch 4-5! fails :(")

if my_gpios.gpio_ad5592r_gpi_ch_6 == 0:
    print("WooHoo on 5592 ch 5-6!")
else:
    print("D'oh! 5592 ch 5-6! fails :(")

if my_gpios.gpio_ad5593r_gpi_ch_4 == 1:
    print("WooHoo on 5593 ch 4-5!")
else:
    print("D'oh! 5593 ch 4-5! fails :(")

if my_gpios.gpio_ad5593r_gpi_ch_6 == 0:
    print("WooHoo on 5592 ch 5-6!")
else:
    print("D'oh! 5592 ch 5-6! fails :(")
    






"""
# Define a few constants, according to curve tracer circuit
Rsense = 47.0  # 47 Ohms
Rbase = 47.0e3  # 47 kOhms
Vbe = 0.7  # Volts (An approximation, of course...)

# Symbolically associate net names with AD5592r channels...
# NOW are things getting intuitive? :)
Vbdrive = my_ad5592r.voltage0_dac
Vcsense = my_ad5592r.voltage1_adc
Vcdrive = my_ad5592r.voltage2_dac
Vcdrive_meas = my_ad5592r.voltage2_adc

mV_per_lsb = Vcdrive.scale  # Makes things a bit more intuitive below.
# Scale is identical for all channels of the AD5592r,
# not necessarily the case for other devices.

Vbdrive.raw = 500.0 / float(mV_per_lsb)
Vcdrive.raw = 500.0 / float(mV_per_lsb)

## Curve Tracer code!!

curves = []  # Empty list for curvces
vcs_index = 0  # curves[x][vcs_index] Extract collector voltages
ics_index = 1  # curves[x][ics_index] Extract collector currents

for vb in range(499, 2500, 500):  # Sweep base voltage from 499 mV to 2.5V in 5 steps
    Vbdrive.raw = vb / float(mV_per_lsb)  # Set base voltage
    ib = ((Vbdrive.raw * mV_per_lsb / 1000) - Vbe) / Rbase  # Calculate base current
    vcs = []  # Empty list for collector voltages
    ics = []  # Empty list for collector currents
    print("Base Drive: ", Vbdrive.raw * mV_per_lsb / 1000, " Volts, ", ib * 1e6, " uA")
    for vcv in range(
        0, 2500, 50
    ):  # Sweep collector drive voltage from 0 to 2.5V in 50 mV steps
        Vcdrive.raw = vcv / float(mV_per_lsb)  # Set collector drive voltage
        ic = (
            (Vcdrive_meas.raw - Vcsense.raw) * mV_per_lsb / Rsense
        )  # Measure collector current
        vc = Vcsense.raw * mV_per_lsb / 1000.0  # Remember - actual collector voltage is
        vcs.append(vc)  # a bit less due to sense resistor
        ics.append(ic)  # Add measurements to lists
        print("coll voltage: ", vc, "  coll curre: ", ic)  # Print for fun
    curves.append([vcs, ics])  # vcs, ics, will be index 0, 1, respectively

plt.figure(1)  # Create new figure
plt.title("Fred in the Shed Curve Tracer: Prototype 0.1")
plt.xlabel("Collector Voltage (V)")
plt.ylabel("Collector Current (mA)")
plt.tight_layout()  # A bit of formatting
for curve in range(0, len(curves)):  # Iterate through curves
    # plot() method arguments are X values, y values, with optional parameters after.
    plt.plot(curves[curve][vcs_index], curves[curve][ics_index])
plt.show()  # Self-explanatory :)
"""