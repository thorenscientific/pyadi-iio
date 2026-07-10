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

# Collect channels by type.
# _channel_voltage_enable and _channel_voltage_fault both inherit _channel_voltage,
# so isinstance(_channel_voltage) catches all three. Check the subtype when
# printing to conditionally show enable/fault.
# _channel_voltage_alarm is separate (no ADC input, comparator-only).
# Channels are accessible by label: my_ltc4284.VPWR, my_ltc4284.ISENSE, etc.
# Differential channels use underscore: my_ltc4284.ADIN2_ADIN1, etc.
# Energy channel is suppressed in the current LTC4284 kernel driver.
voltage_alarm_channels = []
voltage_channels = []
current_channels = []
power_channels = []

for attr in dir(my_ltc4284):
    obj = getattr(my_ltc4284, attr)
    if isinstance(obj, adi.ltc4284._channel_voltage):
        voltage_channels.append(obj)
    elif isinstance(obj, adi.ltc4284._channel_voltage_alarm):
        voltage_alarm_channels.append(obj)
    elif isinstance(obj, adi.ltc4284._channel_current):
        current_channels.append(obj)
    elif isinstance(obj, adi.ltc4284._channel_power):
        power_channels.append(obj)

print("\n--- Voltage Alarm Channels (comparator-only, no ADC input) ---")
for ch in voltage_alarm_channels:
    print(f"\n  {ch.label} (iio channel {ch.name})")
    print(f"    crit_alarm:  {ch.crit_alarm}")
    print(f"    lcrit_alarm: {ch.lcrit_alarm}")

print("\n--- Voltage Channels ---")
for ch in voltage_channels:
    print(f"\n  {ch.label} (iio channel {ch.name})")
    if isinstance(ch, adi.ltc4284._channel_voltage_enable):
        enabled = ch.enable
        print(f"    enable:    {enabled}")
        if enabled:
            print(f"    input:     {ch.input} mV")
            print(f"    highest:   {ch.highest} mV")
            print(f"    lowest:    {ch.lowest} mV")
        else:
            print(f"    input/highest/lowest: (channel disabled)")
    else:
        print(f"    input:     {ch.input} mV")
        print(f"    highest:   {ch.highest} mV")
        print(f"    lowest:    {ch.lowest} mV")
    print(f"    max:       {ch.max} mV")
    print(f"    min:       {ch.min} mV")
    print(f"    max_alarm: {ch.max_alarm}")
    print(f"    min_alarm: {ch.min_alarm}")
    if isinstance(ch, adi.ltc4284._channel_voltage_fault):
        print(f"    fault:     {ch.fault}")

print("\n--- Current Channels ---")
for ch in current_channels:
    print(f"\n  {ch.label} (iio channel {ch.name})")
    print(f"    input:      {ch.input} mA")
    print(f"    highest:    {ch.highest} mA")
    print(f"    lowest:     {ch.lowest} mA")
    print(f"    max:        {ch.max} mA")
    print(f"    min:        {ch.min} mA")
    print(f"    max_alarm:  {ch.max_alarm}")
    print(f"    min_alarm:  {ch.min_alarm}")
    print(f"    crit_alarm: {ch.crit_alarm}")

print("\n--- Power Channel ---")
for ch in power_channels:
    print(f"\n  {ch.label} (iio channel {ch.name})")
    print(f"    input:         {ch.input} uW")
    print(f"    input_highest: {ch.input_highest} uW")
    print(f"    input_lowest:  {ch.input_lowest} uW")
    print(f"    max:           {ch.max} uW")
    print(f"    min:           {ch.min} uW")
    print(f"    max_alarm:     {ch.max_alarm}")
    print(f"    min_alarm:     {ch.min_alarm}")

# Energy channel suppressed in current LTC4284 kernel driver — not exposed here.

# del my_ltc4284
