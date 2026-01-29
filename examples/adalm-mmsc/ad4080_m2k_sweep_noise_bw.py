# Copyright (C) 2022-2024 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

# A script to sweep a band of noise from DC to f, plotting total integrated noise as
# measured with np.std

import argparse
import sys
from time import sleep

import libm2k
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from sine_gen import *
from workshop import time_points_from_freq

from adi import ad4080

plt.ion()


# Optionally pass URI as command line argument,
# else use default ip:analog.local
my_uri = sys.argv[1] if len(sys.argv) >= 2 else "ip:analog.local"


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

print("m2k uri: " + str(m2k_uri))

# my_m2k=libm2k.m2kOpen(my_m2k_uri)
my_m2k = libm2k.m2kOpen()
sleep(0.1)

# Set up m2k

my_m2k.calibrateADC()
my_m2k.calibrateDAC()

siggen = my_m2k.getAnalogOut()

siggen_sr = 7500000  # 750 kHz
n = 2 ** 18
bin_width = siggen_sr / n

siggen.setSampleRate(0, siggen_sr)
siggen.setSampleRate(1, siggen_sr)
siggen.enableChannel(0, True)
siggen.enableChannel(1, True)


my_adc = ad4080(uri=my_uri, device_name="ad4080")
my_adc.rx_buffer_size = 4096

# Fix this later - appears there's some things in flux...
# print("Sampling frequency: ", my_adc.sampling_frequency)

sampling_frequency = 40000000.0  # hack for now

print("oversampling_ratio_available: ", my_adc.oversampling_ratio_available)
print("filter_type_available: ", my_adc.filter_type_available)


print("Setting filter to SINC5, decimation 128")
my_adc.oversampling_ratio = 1024
# my_adc.filter_sel = "sinc5_plus_compensation"
my_adc.filter_type = "sinc1"
print("Verifying... read back filter type: ", my_adc.filter_type)

print("sinc_dec_rate: ", my_adc.oversampling_ratio)
print("filter_sel: ", my_adc.filter_type)
fnotch = sampling_frequency / my_adc.oversampling_ratio
print("SINC first notch at ", fnotch)

fs = []
vref = 5.0
en = 1000e-6
amps = []

for f in range(0, 100000, 1000):  # Sweep 3kHz to 300kHz in 1kHz steps
    noiseband = np.zeros(n)
    maxbin = int(2 * f / bin_width)
    noiseband[0:maxbin] = np.ones(maxbin)
    noiseband *= en
    time_points = time_points_from_freq(noiseband, siggen_sr, True)
    buffer = [time_points, time_points * -1.0]

    siggen.push(buffer)

    sleep(0.25)

    # print("Sample Rate: ", my_adc.sampling_frequency)
    print("Frequency: ", f, "bin: ", maxbin)

    data = my_adc.rx()
    data = my_adc.rx()

    x = np.arange(0, len(data))
    voltage = data * 2.0 * vref / (2 ** 20)
    dc = np.average(voltage)  # Extract DC component
    ac = voltage - dc  # Extract AC component
    rms = np.std(ac) * 2.0

    fs.append(f)
    amps.append(rms)


amps_db = 20 * np.log10(amps / np.sqrt(4.0))  # 4V is p-p amplitude

plt.figure(2)
plt.clf()
plt.title("AD4020 Time Domain Data")
plt.plot(x, voltage)
plt.xlabel("Data Point")
plt.ylabel("Voltage (V)")
plt.show()

f, Pxx_spec = signal.periodogram(ac, 40000000.0, window="flattop", scaling="spectrum")
Pxx_abs = np.sqrt(Pxx_spec)

plt.figure(3)
plt.clf()
plt.title("AD4020 Spectrum (Volts absolute)")
plt.semilogy(f, Pxx_abs)
plt.ylim([1e-6, 4])
plt.xlabel("frequency [Hz]")
plt.ylabel("Voltage (V)")
plt.draw()
plt.pause(0.05)


sinc_resp = np.abs(np.sinc(np.array(fs) / fnotch) * 1.0)
sincsquared = sinc_resp * sinc_resp

plt.figure(4)
plt.title("Total Integrated Noise, 40 Msps, DF 1024")
# plt.semilogx(fs, amps_db, linestyle="dashed", marker="o", ms=2)
plt.plot(fs, amps, linestyle="solid", color="k", marker="o", ms=2, label="total noise")
plt.plot(
    fs,
    sinc_resp,
    linestyle="dashed",
    color="r",
    marker="o",
    ms=2,
    label="sinc response",
)
plt.plot(
    fs, sincsquared, linestyle="dashed", color="b", marker="o", ms=2, label="sinc^2"
)

# plt.ylim([1e-6, 4])
plt.legend()
plt.xlabel("Noise BW, from DC to [Hz]")
plt.ylabel("Noise (arb units for now)")
plt.draw()

# input("Press any key to continue...")

siggen.stop()

libm2k.contextClose(my_m2k)
del my_adc


# print("Scale: ", my_adc.scale)

# print(dir(my_adc))

# plt.figure(1)
# plt.clf()
# # Collect data
# data = my_adc.rx()


# plt.plot(range(0, len(data)), data, label="channel0")
# plt.xlabel("Data Point")
# plt.ylabel("ADC counts")
# plt.legend(
#     bbox_to_anchor=(0.0, 1.02, 1.0, 0.102),
#     loc="lower left",
#     ncol=4,
#     mode="expand",
#     borderaxespad=0.0,
# )

# plt.show()
