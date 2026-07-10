# Copyright (C) 2026 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

import argparse

import adi

parser = argparse.ArgumentParser(description="LTC4284 Example Script")
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

my_ltc4284 = adi.ltc4284(uri=my_uri)

# Collect channels by type. Because _channel_voltage_crit inherits from
# _channel_voltage (and likewise for current), isinstance catches both the
# base and crit subtypes in a single pass. The subtype check below then
# prints the extra attributes only where they exist.
# Channels are accessible by label: my_ltc4284.VPWR, my_ltc4284.SENSE, etc.
voltage_channels = []
current_channels = []
power_channels = []
energy_channels = []

for attr in dir(my_ltc4284):
    obj = getattr(my_ltc4284, attr)
    if isinstance(obj, adi.ltc4284._channel_voltage):
        voltage_channels.append(obj)
    elif isinstance(obj, adi.ltc4284._channel_current):
        current_channels.append(obj)
    elif isinstance(obj, adi.ltc4284._channel_power):
        power_channels.append(obj)
    elif isinstance(obj, adi.ltc4284._channel_energy):
        energy_channels.append(obj)

print("\n--- Voltage Channels ---")
for ch in voltage_channels:
    print(f"\n  {ch.label} (iio channel {ch.name})")
    print(f"    input:   {ch.input} mV")
    print(f"    highest: {ch.highest} mV")
    print(f"    lowest:  {ch.lowest} mV")
    print(f"    max:     {ch.max} mV")
    print(f"    min:     {ch.min} mV")
    if isinstance(ch, adi.ltc4284._channel_voltage_crit):
        print(f"    crit_alarm:  {ch.crit_alarm}")
        print(f"    lcrit_alarm: {ch.lcrit_alarm}")

print("\n--- Current Channels ---")
for ch in current_channels:
    print(f"\n  {ch.label} (iio channel {ch.name})")
    print(f"    input:   {ch.input} mA")
    print(f"    highest: {ch.highest} mA")
    print(f"    lowest:  {ch.lowest} mA")
    if isinstance(ch, adi.ltc4284._channel_current_crit):
        print(f"    max:        {ch.max} mA")
        print(f"    min:        {ch.min} mA")
        print(f"    crit_alarm: {ch.crit_alarm}")

print("\n--- Power Channel ---")
for ch in power_channels:
    print(f"\n  {ch.label} (iio channel {ch.name})")
    print(f"    input:         {ch.input} uW")
    print(f"    input_highest: {ch.input_highest} uW")
    print(f"    input_lowest:  {ch.input_lowest} uW")
    print(f"    max:           {ch.max} uW")

print("\n--- Energy Channel ---")
for ch in energy_channels:
    print(f"\n  {ch.label} (iio channel {ch.name})")
    print(f"    input: {ch.input} uJ")

# del my_ltc4284
