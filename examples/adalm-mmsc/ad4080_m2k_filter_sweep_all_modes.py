# Copyright (C) 2022-2024 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

import argparse
import sys
from time import sleep

import libm2k
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from sine_gen import *

from adi import ad4080

# Optionally pass URI as command line argument,
# else use default ip:analog.local
parser = argparse.ArgumentParser(
    description="Generate a noisy signal on the M2K, record it using the AD4080ARDZ, and do a Fourier analysis."
)
parser.add_argument(
    "-m",
    "--m2k_uri",
    default="ip:192.168.2.1",
    help="LibIIO context URI of the ADALM2000",
)
# parser.add_argument('-a', '--ad4080_uri', default='serial:/dev/ttyACM0,230400,8n1',
parser.add_argument(
    "-u",
    "--ad4080_uri",
    default="serial:COM49,230400",
    help="LibIIO context URI of the EVAL-AD4080ARDZ",
)
args = vars(parser.parse_args())

my_uri = args["ad4080_uri"]

m2k_uri = args["m2k_uri"]

print("uri: " + str(my_uri))


my_adc = ad4080(uri=my_uri, device_name="ad4080")

# Fix this later - appears there's some things in flux...
# print("Sampling frequency: ", my_adc.sampling_frequency)

sampling_frequency = 40000000.0  # hack for now

print("oversampling_ratio_available: ", my_adc.oversampling_ratio_available)
print("filter_type_available: ", my_adc.filter_type_available)

print("Setting filter to SINC5, decimation 128")
my_adc.oversampling_ratio = 128
my_adc.filter_type = "sinc1"
# my_adc.filter_type = "sinc5"
# my_adc.filter_type = "sinc5+pf1"

my_adc.rx_buffer_size = 4096
print("Verifying...")
print("Oversampling Ratio: ", my_adc.oversampling_ratio)
print("filter_sel: ", my_adc.filter_type)


plt.figure(1)
plt.clf()
plt.figure(2)
plt.clf()
plt.figure(3)
plt.clf()
plt.figure(4)
plt.clf()


# Collect data
data = my_adc.rx()


plt.figure(1)
plt.plot(range(0, len(data)), data, label="channel0")
plt.xlabel("Data Point")
plt.ylabel("ADC counts")
plt.legend(
    bbox_to_anchor=(0.0, 1.02, 1.0, 0.102),
    loc="lower left",
    ncol=4,
    mode="expand",
    borderaxespad=0.0,
)

plt.show()


# Set up m2k

ctx = libm2k.m2kOpen(m2k_uri)
ctx.calibrateADC()
ctx.calibrateDAC()

siggen = ctx.getAnalogOut()


vref = 5.0

# for oversample_ratio in my_adc.oversampling_ratio_available:
for oversample_ratio in [1024, 512, 256]:
    my_adc.oversampling_ratio = int(oversample_ratio)
    print("Sweeping with oversampling ratio ", my_adc.oversampling_ratio)
    fs = []
    amps = []
    for f in np.linspace(4.0, 5.5, num=50):  # Sweep 3kHz to 300kHz in 1kHz steps
        f = int(10 ** f)  # logarithmic freqs

        # call buffer generator, returns sample rate and buffer
        samp0, buffer0 = sine_buffer_generator(0, f, 0.5, 1.5, 180)
        samp1, buffer1 = sine_buffer_generator(1, f, 0.5, 1.5, 0)

        siggen.enableChannel(0, True)
        siggen.enableChannel(1, True)

        siggen.setSampleRate(0, samp0)
        siggen.setSampleRate(1, samp1)

        siggen.push([buffer0, buffer1])

        sleep(0.25)

        # print("Sample Rate: ", my_adc.sampling_frequency)
        print("Frequency: ", f)

        data = my_adc.rx()
        data = my_adc.rx()

        x = np.arange(0, len(data))
        voltage = data * 2.0 * vref / (2 ** 20)
        dc = np.average(voltage)  # Extract DC component
        ac = voltage - dc  # Extract AC component
        rms = np.std(ac)

        fs.append(f)
        amps.append(rms)

    amps_db = 20 * np.log10(amps / np.sqrt(4.0))  # 4V is p-p amplitude

    plt.figure(4)
    filter_type = my_adc.filter_type
    plt.title(filter_type + " freq. response")
    plt.semilogx(fs, amps_db, linestyle="dashed", marker="o", ms=2)
    # plt.ylim([1e-6, 4])
    plt.xlabel("frequency [Hz]")
    plt.ylabel("response (dB)")
    plt.draw()

    plt.figure(2)
    # plt.clf()
    plt.title("AD4020 Time Domain Data")
    plt.plot(x, voltage)
    plt.xlabel("Data Point")
    plt.ylabel("Voltage (V)")
    plt.show()

    f, Pxx_spec = signal.periodogram(
        ac, 40000000.0, window="flattop", scaling="spectrum"
    )
    Pxx_abs = np.sqrt(Pxx_spec)

    plt.figure(3)
    # plt.clf()
    plt.title("AD4020 Spectrum (Volts absolute)")
    plt.semilogy(f, Pxx_abs)
    plt.ylim([1e-6, 4])
    plt.xlabel("frequency [Hz]")
    plt.ylabel("Voltage (V)")
    plt.draw()
    plt.pause(0.05)


siggen.stop()
libm2k.contextClose(ctx)
del my_adc
