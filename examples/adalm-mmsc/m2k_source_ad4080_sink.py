# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

import argparse
from sys import exit

import genalyzer as gn
import libm2k
import numpy as np
import workshop

import adi

parser = argparse.ArgumentParser(
    description="Generate a noisy signal on the M2K, record it using the AD4080ARDZ, and do a Fourier analysis."
)
parser.add_argument(
    "-m",
    "--m2k_uri",
    default="ip:m2k.local",
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

# 0. Configuration
fs_out = 7500000  # Generated waveform sample rate
fs_in = 40000000  # Received waveform sample rate. AD4080 fixed at 40Msps

# Tone parameters
fsr = 2.0  # Full-scale range in Volts
fund_freq = 100000.0  # Hz

# This is a list of the amplitudes (in dBfs) of the fundamental (first element)
# and harmonics. You can add more harmonics to the list, but we'll start
# out with just the 2nd, 3rd, and 4th.
harm_dbfs = [-3.0, -23.0, -20.0, -20.0]

# These are lists of the frequencies (Hz) and amplitudes (in dBfs) of
# interfering tones or "noise tones". Genalyzer will interpret them as not
# harmonically related and add them to the total noise.
noise_freqs = [150000.0, 250000.0, 350000.0, 450000.0]
noise_dbfs = [-40, -60, -70, -50]

# FFT parameters
window = gn.Window.BLACKMAN_HARRIS  # FFT window
npts = 16384  # Receive buffer size
navg = 2  # No. of fft averages
nfft = npts // navg  # No. of points per FFT

# 1. Connect to M2K and AD4080
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

# Connect to AD4080
my_ad4080 = adi.ad4080(args["ad4080_uri"])
if my_ad4080 is None:
    print("Connection Error: No AD4080 device available/connected to your PC.")
    exit(1)

# Initialize ADC
my_ad4080.rx_buffer_size = npts
my_ad4080.filter_type = "none"
print(f"Sampling frequency: {my_ad4080.sampling_frequency}")
# print(f'Available sampling frequencies: {my_ad4080.sampling_frequency_available}') # not in ad4080 class yet
assert my_ad4080.sampling_frequency == fs_in  # Check 40Msps assumption

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

# 4. Receive one buffer of samples
data_in_raw = my_ad4080.rx()

# Convert ADC codes to Volts
data_in = data_in_raw * my_ad4080.channel[0].scale / 1e6  # Scale is in microvolts/code

# 5. Analyze recorded waveform
workshop.fourier_analysis(
    data_in, fundamental=fund_freq, sampling_rate=fs_in, window=window
)


# del my_ad4080
