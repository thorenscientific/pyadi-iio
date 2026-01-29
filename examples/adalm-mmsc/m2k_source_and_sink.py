# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD
# Author: Ioan Dragomir (ioan.dragomir@analog.com)

import argparse
from time import sleep

import genalyzer as gn
import libm2k
import numpy as np
import workshop

parser = argparse.ArgumentParser(
    description="Generate a noisy signal on the M2K, record it using the AD4080ARDZ, and do a Fourier analysis."
)
parser.add_argument(
    "-m",
    "--m2k-uri",
    default="ip:m2k.local",
    help="LibIIO context URI of the ADALM2000",
)
args = vars(parser.parse_args())

# 0. Configuration

# Input and output will be done at different sampling frequencies
# Need to make sure we're not mixing these up later!
fs_in = 100000
fs_out = 750000

# Tone parameters
fsr = 2.0  # Full-scale range in Volts
fund_freq = 10000.0  # Hz

# This is a list of the amplitudes (in dBfs) of the fundamental (first element)
# and harmonics. You can add more harmonics to the list, but we'll start
# out with just the 2nd, 3rd, and 4th.
harm_dbfs = [-3.0, -23.0, -20.0, -20.0]

# These are lists of the frequencies (Hz) and amplitudes (in dBfs) of
# interfering tones or "noise tones". Genalyzer will interpret them as not
# harmonically related and add them to the total noise.
noise_freqs = [15000.0, 25000.0, 35000.0, 45000.0]
noise_dbfs = [-40, -60, -70, -50]

# FFT parameters
window = gn.Window.BLACKMAN_HARRIS  # FFT window
navg = 2  # No. of fft averages
nfft = 1024 * 64  # FFT order
npts = navg * nfft  # Receive buffer size

# 1. Connect to M2K
my_m2k = libm2k.m2kOpen(args["m2k_uri"])
if my_m2k is None:
    print("Connection Error: No ADALM2000 device available/connected to your PC.")
    exit(1)

# Initialize DAC channel 0
aout = my_m2k.getAnalogOut()
aout.reset()
my_m2k.calibrateDAC()
aout.setSampleRate(0, fs_out)
aout.enableChannel(0, True)
aout.setCyclic(True)  # Send buffer repeatedly, not just once

# Initialize ADC channel 0
ain = my_m2k.getAnalogIn()
my_m2k.reset()
my_m2k.calibrateADC()
ain.setSampleRate(fs_in)
ain.enableChannel(0, True)
ain.setRange(0, -10, 10)

# 2. Generate waveform containing both the wanted signal and some noise

# Convert dBfs to amplitudes for both harmonics and noise
harm_ampl = [(fsr / 2) * 10 ** (x / 20) for x in harm_dbfs]
noise_ampl = [(fsr / 2) * 10 ** (x / 20) for x in noise_dbfs]

# Nudge fundamental to the closest coherent bin
fund_freq = gn.coherent(nfft, fs_out, fund_freq)

# Build up the signal from the fundamental, harmonics, and noise tones
awf = np.zeros(npts)

for harmonic in range(len(harm_dbfs)):
    freq = fund_freq * (harmonic + 1)
    print(f"Frequency: {freq} ({harm_dbfs[harmonic]} dBfs)")

    awf += gn.cos(npts, fs_out, harm_ampl[harmonic], freq, 0, 0, 0)

for tone in range(len(noise_freqs)):
    freq = noise_freqs[tone]
    freq = gn.coherent(nfft, fs_out, noise_freqs[tone])

    print(f"Noise Frequency: {freq} ({noise_dbfs[tone]} dBfs)")
    awf += gn.cos(npts, fs_out, noise_ampl[tone], freq, 0, 0, 0)

# 3. Transmit generated waveform
aout.push([awf])  # Would be [awf0, awf1] if sending data to multiple channels

sleep(0.5)

# 4. Receive one buffer of samples
data_in = ain.getSamples(npts)[0]

# 5. Analyze recorded waveform
workshop.fourier_analysis(
    data_in,
    fundamental=fund_freq,
    sampling_rate=fs_in,
    window=window,
    ssb_fund=200,
    ssb_rest=200,
)
