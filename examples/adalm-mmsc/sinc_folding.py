# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD
# Author: Ioan Dragomir (ioan.dragomir@analog.com)

import argparse
from sys import exit

import genalyzer as gn
import libm2k
import matplotlib.pyplot as pl
import numpy as np
import workshop

import adi

parser = argparse.ArgumentParser(
    description="Generate wideband noise on the M2K, record it using the ADALM-MMSC, comparing it to the theoretical sinc1 response, taking into account frequency folding."
)
parser.add_argument(
    "-m",
    "--m2k_uri",
    default="ip:m2k.local",
    help="LibIIO context URI of the ADALM2000",
)
parser.add_argument(
    "-a",
    "--ad4080_uri",
    default="serial:COM51,230400,8n1",
    help="LibIIO context URI of the ADALM-MMSC",
)
parser.add_argument(
    "-d",
    "--decimation",
    default="256",
    choices=[2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 1024],
    help="AD4080 digital filter (sinc1) decimation",
)
args = vars(parser.parse_args())

# 0. Configuration
fs_pre = 40000000  # AD4080 fixed at 40Msps pre digital filtering
fs_out = 750000  # Generated waveform sample rate

plot_freq_range = (
    100000  # Plot all FFTs with the same frequency range for easy comparison
)

# FFT parameters
window = gn.Window.BLACKMAN_HARRIS  # FFT window
npts = 16384  # Receive buffer size - maximum for this board
navg = 1  # No. of fft averages
nfft = npts // navg  # No. of points per FFT

decimation = int(args["decimation"])
fs_in = fs_pre // decimation  # AD4080 output data rate

# 1. Connect to M2K and AD4080
m2k = libm2k.m2kOpen(args["m2k_uri"])
if m2k is None:
    print("Connection Error: No ADALM2000 device available/connected to your PC.")
    exit(1)

# Initialize DAC channel 0
aout = m2k.getAnalogOut()
aout.reset()
m2k.calibrateDAC()
aout.setSampleRate(0, fs_out)
aout.enableChannel(0, True)
aout.setCyclic(True)  # Send buffer repeatedly, not just once

# Connect to AD4080 and configure
ad4080 = adi.ad4080(args["ad4080_uri"])
if ad4080 is None:
    print("Connection Error: No AD4080 device available/connected to your PC.")
    exit(1)

ad4080.filter_type = "sinc1"
ad4080.oversampling_ratio = decimation
ad4080.rx_buffer_size = npts

print(f"Sampling frequency: {ad4080.sampling_frequency}")
# print(f'Available sampling frequencies: {ad4080.sampling_frequency_available}') # Not in ad4080 class yet
assert ad4080.sampling_frequency == fs_pre  # Check 40Msps assumption

# 2. Generate waveform with multiple noise bands
spectrum = np.array(
    # Formula ahead makes bands of noise arranged such that:
    # - there are a handful of bands from 0Hz to nyquist*2
    # - there is enough space between the bands to see the noise floor
    # - after folding, the aliased bands don't overlap
    # - FFT bins are 1Hz, so spectrum[x] corresponds to exactly x Hz
    [int((i // int(fs_in / 4 / (8 + 7 / 8))) % 8 == 0) for i in range(fs_in)]
    + [0 for i in range(fs_in, fs_out // 2)]
)

awf = workshop.time_points_from_freq(spectrum)
awf /= np.std(awf)  # Scale to 1V RMS

# Compute and plot generated signal FFT
fft_cplx = gn.rfft(
    awf.copy(),
    1,
    len(awf),
    gn.Window.BLACKMAN_HARRIS,
    gn.CodeFormat.TWOS_COMPLEMENT,
    gn.RfftScale.NATIVE,
)
fft_db = gn.db(fft_cplx)
freq_axis = gn.freq_axis(fs_out, gn.FreqAxisType.REAL, fs_out)

workshop.plot_waveform_and_fft("Generated", awf, fs_out, fft_db)

# 3. Transmit generated waveform
aout.push([awf])  # Would be [awf0, awf1] if sending data to multiple channels

# 4. Receive multiple buffers and average their FFTs
num_avg = 4
fft_average = np.zeros(nfft // 2 + 1)

for i in range(num_avg):
    # Read one buffer of samples and convert to volts
    data_in = ad4080.rx() * ad4080.scale / 1e6  # uV -> V

    # Remove DC component
    data_in = data_in - np.average(data_in)

    # Compute FFT
    fft_cplx = gn.rfft(
        np.array(data_in),
        navg,
        nfft,
        window,
        gn.CodeFormat.TWOS_COMPLEMENT,
        gn.RfftScale.NATIVE,
    )
    fft_average += gn.db(fft_cplx)

fft_average /= num_avg

# Display last received buffer and averaged spectrum, then overlay sinc1 response
# Replace this with anything else you want to do with the data!
workshop.plot_waveform_and_fft(f"Recorded ({decimation=})", data_in, fs_in, fft_average)
workshop.plot_sinc1_folded(decimation, fs_in)
pl.show()
