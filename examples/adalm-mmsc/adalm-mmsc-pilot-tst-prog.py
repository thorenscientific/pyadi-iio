# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD



import libm2k
import adi
from sys import exit
import numpy as np
import genalyzer as gn
import workshop
import argparse

parser = argparse.ArgumentParser(
    description='Generate a noisy signal on the M2K, record it using the AD4080ARDZ, and do a Fourier analysis.')
parser.add_argument('-m', '--m2k_uri', default='ip:m2k.local',
    help='LibIIO context URI of the ADALM2000')
# parser.add_argument('-a', '--ad4080_uri', default='serial:/dev/ttyACM0,230400,8n1',
parser.add_argument('-a', '--ad4080_uri', default='serial:COM49,230400',
    help='LibIIO context URI of the EVAL-AD4080ARDZ')
args = vars(parser.parse_args())

# 0. Configuration
fs_out = 7500000  # Generated waveform sample rate
fs_in  = 40000000 # Received waveform sample rate. AD4080 fixed at 40Msps

# Tone parameters
fsr = 2.0             # Full-scale range in Volts
fund_freq = 100000.0  # Hz


# FFT parameters
window = gn.Window.BLACKMAN_HARRIS  # FFT window
npts = 16384        # Receive buffer size
navg = 2            # No. of fft averages
nfft = npts // navg # No. of points per FFT

# 1. Connect to M2K and AD4080
my_m2k = libm2k.m2kOpen(args['m2k_uri'])
if my_m2k is None:
    print("Connection Error: No ADALM2000 device available/connected to your PC.")
    exit(1)

# Initialize DAC channel 0
aout = my_m2k.getAnalogOut()
aout.reset()
my_m2k.calibrateDAC()
aout.setSampleRate(0, fs_out)
aout.enableChannel(0, True)
aout.setCyclic(True) # Send buffer repeatedly, not just once

# Connect to AD4080
my_ad4080 = adi.ad4080(args['ad4080_uri'])
if my_ad4080 is None:
    print("Connection Error: No AD4080 device available/connected to your PC.")
    exit(1)

# Initialize ADC
my_ad4080.rx_buffer_size = npts
my_ad4080.filter_type = 'none'
print(f'Sampling frequency: {my_ad4080.sampling_frequency}')
# print(f'Available sampling frequencies: {my_ad4080.sampling_frequency_available}') # not in ad4080 class yet
assert my_ad4080.sampling_frequency == fs_in # Check 40Msps assumption


# Nudge fundamental to the closest coherent bin
fund_freq = gn.coherent(nfft, fs_out, fund_freq)

# Build up the signal from the fundamental, harmonics, and noise tones

awf = gn.cos(npts, fs_out, fsr, fund_freq, 0, 0, 0)

# 3. Transmit generated waveform
aout.push([awf]) # Would be [awf0, awf1] if sending data to multiple channels

# 4. Receive one buffer of samples
data_in_raw = my_ad4080.rx()

# Convert ADC codes to Volts
data_in = data_in_raw * my_ad4080.channel[0].scale / 1e3 # Scale is in millivolts/code

# 5. Analyze recorded waveform
fft_results = workshop.fourier_analysis(data_in, fundamental = fund_freq, sampling_rate = fs_in, window = window)

failed_tests = []

if (- 5.0 < fft_results['A:mag_dbfs'] < -2.0) is False:
    failed_tests.append("Failed full-scale amplitude")
if (55.0 < fft_results['snr'] < 70.0) is False:
    failed_tests.append("Failed SNR")
if (55.0 < fft_results['sinad'] < 70.0) is False:
    failed_tests.append("Failed SINAD")

if len(failed_tests) == 0:
    print("WooHoo, board passes!")
else:
    print("D'oh! Board fails these test(s)")
    print(failed_tests)


del my_ad4080
