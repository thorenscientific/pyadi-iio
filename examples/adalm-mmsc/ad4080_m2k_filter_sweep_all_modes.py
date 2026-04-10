# Copyright (C) 2022-2024 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

import argparse
import sys
from time import sleep

import libm2k
import matplotlib.pyplot as plt
from matplotlib.widgets import Button, RadioButtons
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
    default="usb:1.38.5",
    help="LibIIO context URI of the ADALM2000",
)
# parser.add_argument('-a', '--ad4080_uri', default='serial:/dev/ttyACM0,230400,8n1',
parser.add_argument(
    "-u",
    "--ad4080_uri",
    default="serial:COM13,230400",
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

print("Setting filter to SINC1, decimation 128")
my_adc.oversampling_ratio = 128
my_adc.filter_type = "sinc1"
# my_adc.filter_type = "sinc5"
# my_adc.filter_type = "sinc5+pf1"

my_adc.rx_buffer_size = 4096
print("Verifying...")
print("Oversampling Ratio: ", my_adc.oversampling_ratio)
print("filter_sel: ", my_adc.filter_type)


# Collect initial data sample for Figure 1 with filter selection and start button
fig1, ax1 = plt.subplots(num=1, figsize=(8, 4))
# Use most of the width for the graph and leave space at the bottom for controls
fig1.subplots_adjust(left=0.10, right=0.98, bottom=0.30)
data = my_adc.rx()

ax1.plot(range(0, len(data)), data, label="channel0")
ax1.set_xlabel("Data Point")
ax1.set_ylabel("ADC counts")
ax1.legend(
    bbox_to_anchor=(0.0, 1.02, 1.0, 0.102),
    loc="lower left",
    ncol=4,
    mode="expand",
    borderaxespad=0.0,
)

# Filter selection radio buttons
filter_options = ["sinc1", "sinc5", "sinc5+pf1"]
current_filter = my_adc.filter_type
if current_filter in filter_options:
    default_index = filter_options.index(current_filter)
else:
    default_index = 0

ax_filter = fig1.add_axes([0.10, 0.08, 0.35, 0.10])
rb_filter = RadioButtons(ax_filter, filter_options, active=default_index)
ax_filter.set_title("Filter")

# Start sweep button
ax_start_btn = fig1.add_axes([0.55, 0.08, 0.30, 0.10])
btn_start = Button(
    ax_start_btn,
    "Start sweep",
    color="lightgreen",
    hovercolor="green",
)


vref = 5.0


def start_sweep(event):
    """Callback for the 'Start sweep' button: choose filter and run sweeps."""

    global my_adc

    selected_filter = rb_filter.value_selected
    print(f"Starting sweep with filter {selected_filter}")
    my_adc.filter_type = selected_filter

    # Set up m2k
    ctx = libm2k.m2kOpen()
    if ctx is None:
        print(f"Failed to open M2K at URI: {m2k_uri}")
        return
    ctx.calibrateADC()
    ctx.calibrateDAC()

    siggen = ctx.getAnalogOut()

    # Figure 2: combined window for time domain, spectrum, and all OSR responses
    fig2, (ax_td, ax_spec, ax_all) = plt.subplots(3, 1, num=2, figsize=(8, 8))
    fig2.subplots_adjust(hspace=0.5)

    ax_td.set_title("AD4020 Time Domain Data")
    ax_td.set_xlabel("Data Point")
    ax_td.set_ylabel("Voltage (V)")

    ax_spec.set_title("AD4020 Spectrum (Volts absolute)")
    ax_spec.set_xlabel("frequency [Hz]")
    ax_spec.set_ylabel("Voltage (V)")

    ax_all.set_title("All Oversampling Ratios")
    ax_all.set_xlabel("frequency [Hz]")
    ax_all.set_ylabel("response (dB)")

    # Now that the results window exists, close the initial Figure 1
    plt.close(fig1)

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

        # Update combined figure: response vs frequency for this OSR
        ax_all.semilogx(fs, amps_db, linestyle="dashed", marker="o", ms=2, label=f"OSR={oversample_ratio}")

        f_axis, Pxx_spec = signal.periodogram(
            ac, 40000000.0, window="flattop", scaling="spectrum"
        )
        Pxx_abs = np.sqrt(Pxx_spec)

        # Time-domain and spectrum plots
        ax_td.plot(x, voltage)
        ax_spec.semilogy(f_axis, Pxx_abs)
        ax_spec.set_ylim([1e-6, 4])

    ax_all.legend(title="OSR")

    siggen.stop()
    libm2k.contextClose(ctx)
    print("All measurements complete. Cleaning up.")

    fig2.show()


btn_start.on_clicked(start_sweep)
plt.show()
