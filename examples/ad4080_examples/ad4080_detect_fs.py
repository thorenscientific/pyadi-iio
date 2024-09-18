# Copyright (C) 2022 Analog Devices, Inc.
#
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#     - Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     - Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in
#       the documentation and/or other materials provided with the
#       distribution.
#     - Neither the name of Analog Devices, Inc. nor the names of its
#       contributors may be used to endorse or promote products derived
#       from this software without specific prior written permission.
#     - The use of this software may or may not infringe the patent rights
#       of one or more patent holders.  This license does not release you
#       from the requirement that you obtain separate licenses from these
#       patent holders to use this software.
#     - Use of the software either in source or binary form, must be run
#       on or directly connected to an Analog Devices Inc. component.
#
# THIS SOFTWARE IS PROVIDED BY ANALOG DEVICES "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, NON-INFRINGEMENT, MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED.
#
# IN NO EVENT SHALL ANALOG DEVICES BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, INTELLECTUAL PROPERTY
# RIGHTS, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
# BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF
# THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import sys

import matplotlib.pyplot as plt
import numpy as np
from adi import ad4080

# ToDo - Arg-Parsify
# Optionally pass URI as command line argument,
# else use default ip:analog.local
my_uri = sys.argv[1] if len(sys.argv) >= 2 else "serial:COM6,230400,8n1n"
print("uri: " + str(my_uri))

my_adc = ad4080(uri=my_uri, device_name="ad4080")

print("Sampling frequency from IIO Context: ", my_adc.sampling_frequency)
# print("Test mode: ", my_adc.test_mode)
print("Scale: ", my_adc.scale)

test_freq = 100000 # Consider making this a command line parameter

print("Apply an input sinewave with a frequency of ", test_freq, " Hz.")
print("This script will calculate the sample rate.")

my_adc.rx_buffer_size=(8192)
# Collect data
data = my_adc.rx()


# Create figure to plot results
fig, (ax1, ax2) = plt.subplots(nrows=2)
fig.set_figheight(6)
fig.set_figwidth(12)
fig.tight_layout()


# Set-up FFT Plot
ax1.set_title("Time Domain")
x = data
ax1.set_ylim([min(data) * 1.1, max(data) * 1.1])
line1, = ax1.plot(x, label="time domain")
ax1.legend()

# Set-up transmittance plot
ax2.set_title("FFT, calculated Fs = ")

line2, = ax2.plot(x[:len(x)//2], label="freq. domain")
ax2.legend()

while True:

    # Collect data
    data = my_adc.rx()
    
    ax1.set_ylim([min(data) * 1.1, max(data) * 1.1])
    line1.set_ydata(data)
    
    data_win = (data - np.average(data)) * np.blackman(len(data))
    mag_spec = 20 * np.log10(np.abs(np.fft.fft(data_win)/len(data_win)))[:len(data_win)//2]
    
    max_bin = np.argmax(mag_spec)
    fs = 100000.0 * len(data) / max_bin
    fs = int(np.around(fs/10, decimals=0)*10) # Round to nearest 10 Hz
    print("Peak found in bin ", max_bin)
    print("Assuming input freq. of 100 kHz, this is a sample rate of ", fs )
    
    ax2.set_ylim([min(mag_spec) * 1.1, max(mag_spec) * 1.1])
    line2.set_ydata(mag_spec)
    ax2.set_title("FFT, calculated Fs = %i" %fs)
    
    
    plt.pause(2)

    # Exit loop and close M2K Context
    if not plt.fignum_exists(1):
        del my_adc
        sys.exit()
