# Copyright (C) 2023 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

import sys
import time

import adi

test_raw1 = 16384  # Test raw DAC code
test_raw2 = 8192  # Test raw DAC code

toggle1 = 41210  # 1st toggle value
toggle2 = 21410  # 2nd toggle value

dither_raw_test = 8192  # dither raw value
dither_freq_test = 16384  # dither frequency
dither_phase_test = (
    1.5708  # dither phase. available options: 0, 1.5708, 3.14159, 4.71239
)

# indices of standard channels
# ch1 expected value = -3.9V
# ch2 expected value = 0V
# even number channel = 1.249V
# odd number channel = 0.624V
standard_channels = [1, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15]
toggle_channels = []# [2, 7]
dither_channels = []# [0, 3]

# Device initialization

my_uri="ip:analog.local"

try:
    myDAC = adi.ltc2688(uri=my_uri)

    for ch in myDAC.channel_names:
        ch_object = eval("myDAC." + str(ch))
        id_num = int(ch[7:])
        if id_num in toggle_channels:
            ch_object.raw0 = 0
            ch_object.raw1 = 0
            ch_object.toggle_en = 0
            if id_num == 7:
                print("Channel: " + str(ch) + " function: " + "sw toggle")
            else:
                print("Channel: " + str(ch) + " function: " + "hw toggle")
        elif id_num in dither_channels:
            ch_object.dither_en = 0
            if id_num == 3:
                ch_object.raw = 32768
            else:
                ch_object.raw = 0
            print("Channel: " + str(ch) + " function: " + "dither")
        else:
            ch_object.raw = 0
            print("Channel: " + str(ch) + " function: " + "standard")

except Exception as e:
    print(str(e))
    print("Failed to open LTC2688 device")
    sys.exit(0)



# Basic DAC output setting function
try:
    print("Basic DAC output configuration.")

    myDAC.voltage0.volt = 200
    myDAC.voltage1.volt = 100
    myDAC.voltage2.volt = 400
    myDAC.voltage3.volt = 300
    myDAC.voltage4.volt = 600
    myDAC.voltage5.volt = 500
    myDAC.voltage6.volt = 800
    myDAC.voltage7.volt = 700
    myDAC.voltage8.volt = 1000
    myDAC.voltage9.volt = 900
    myDAC.voltage10.volt = 1200
    myDAC.voltage11.volt = 1100
    myDAC.voltage12.volt = 1400
    myDAC.voltage13.volt = 1300
    myDAC.voltage14.volt = 1600
    myDAC.voltage15.volt = 1500

    



    time.sleep(1)

except Exception as e:
    print(str(e))
    print("Failed to write to LTC2688 DAC")
    sys.exit(0)





my_ad7124 = adi.ad7124(uri=my_uri)

my_ad7124.rx_destroy_buffer() # Just in case... this gives access to raw values.

for i in range(0,len(my_ad7124.channel)):
    my_ad7124.channel[i].sampling_frequency = 4800

time.sleep(0.1)


print(
    "Welcome to the ad7124 example script, where the local temperature is ",
    my_ad7124.temp(),
    " degrees C.",
)

print("Now reading out all raw channels...")

for i in range(0,len(my_ad7124.channel)):
    print("Channel ", i, ":  ", my_ad7124.channel[i].raw)

time.sleep(0.1)

my_ad7124.rx_destroy_buffer() # Just in case... this gives access to raw values.

for i in range(0,len(my_ad7124.channel)):
    my_ad7124.channel[i].sampling_frequency = 4800

time.sleep(0.1)



# del myDAC
# del my_ad7124





