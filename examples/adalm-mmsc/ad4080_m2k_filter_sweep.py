# Copyright (C) 2026 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD


import argparse
import sys

import libm2k  # type: ignore
import matplotlib.pyplot as plt  # type: ignore
import numpy as np  # type: ignore
from matplotlib.widgets import Button, RadioButtons, TextBox  # type: ignore
from mmsc_utils import DeviceSelectionDialog, build_ad4080_uri
from scipy import signal  # type: ignore
from sine_gen import sine_buffer_generator

from adi import ad4080  # type: ignore

# Show device selection dialog
selected_devices = DeviceSelectionDialog(include_m2k=True).show()

if selected_devices is None:
    print("Connection cancelled by user")
    sys.exit(0)

parser = argparse.ArgumentParser(
    description="Frequency sweep: Generate signals with M2K, measure with AD4080, analyze frequency response.",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Example usage:
  python ad4080_m2k_filter_sweep.py --start 50000 --stop 500000 --step 10000 --osr 64
    python ad4080_m2k_filter_sweep.py --filter sinc5+pf1 --amplitude 1.5
    """,
)
# Frequency sweep parameters
parser.add_argument(
    "--start",
    type=int,
    default=10000,
    help="Sweep start frequency in Hz (default: 10000)",
)
parser.add_argument(
    "--stop",
    type=int,
    default=1000000,
    help="Sweep stop frequency in Hz (default: 1000000)",
)
parser.add_argument(
    "--step",
    type=int,
    default=20000,
    help="Frequency step size in Hz (default: 20000)",
)

# AD4080 configuration
parser.add_argument(
    "--osr", type=int, default=1024, help="Oversampling ratio (default: 1024)",
)
parser.add_argument(
    "--filter",
    type=str,
    default="sinc5",
    help="Filter type: sinc1, sinc5, or sinc5+pf1 (default: sinc5)",
)

# M2K signal generation parameters
parser.add_argument(
    "--amplitude",
    type=float,
    default=2.0,
    help="Signal amplitude in volts (default: 2.0)",
)
parser.add_argument(
    "--offset",
    type=float,
    default=2.5,
    help="Signal DC offset in volts (default: 2.5)",
)
parser.add_argument(
    "--phase",
    type=float,
    default=180,
    help="Phase offset between channels in degrees (default: 180)",
)

# Timing
parser.add_argument(
    "--settle_time",
    type=float,
    default=0.25,
    help="Settling time between frequency changes in seconds (default: 0.25)",
)

# Front-end sample rate (set by board rotary switch)
parser.add_argument(
    "--frontend_fs",
    type=float,
    default=40000000.0,
    help="Front-end sample rate in Hz (matches rotary switch setting, default: 40000000.0)",
)

args = vars(parser.parse_args())

my_uri = build_ad4080_uri(selected_devices["com_port"])
m2k_uri = selected_devices["m2k_uri"]

print(f"AD4080 uri: {my_uri}")

my_adc = ad4080(uri=my_uri, device_name="ad4080")

# Use user-provided front-end sample rate (set via board rotary switch)
sampling_frequency = args["frontend_fs"]
print(f"Front-end sample rate (Hz): {sampling_frequency}")
print("oversampling_ratio_available:", my_adc.oversampling_ratio_available)
print("filter_type_available:", my_adc.filter_type_available)

print(f"\nSetting filter to {args['filter'].upper()}, OSR={args['osr']}")
my_adc.oversampling_ratio = args["osr"]
my_adc.filter_type = args["filter"]
print("Readback filter type:", my_adc.filter_type)
print("Readback OSR:", my_adc.oversampling_ratio)


# # Commented out: initial data sample graph ---
# print("Collecting initial data sample")
#
# plt.figure(1)
# plt.clf()
# data = my_adc.rx()
#
# plt.plot(data, label="channel0")
# plt.xlabel("Data Point")
# plt.ylabel("ADC counts")
# plt.legend(
#     bbox_to_anchor=(0.0, 1.02, 1.0, 0.102),
#     loc="lower left",
#     ncol=4,
#     mode="expand",
#     borderaxespad=0.0,
# )
#
# print("\nFigure 1: Initial Data Sample")
# print(" > Close the figure window to proceed with frequency sweep\n")
# plt.show()


# Set up m2k
print("Setting up M2K signal generator")

ctx = libm2k.m2kOpen(m2k_uri)
if ctx is None:
    print(f"Failed to open M2K at URI: {m2k_uri}")
    sys.exit(1)

ctx.calibrateADC()
ctx.calibrateDAC()

siggen = ctx.getAnalogOut()

vref = 5.0


def run_sweep(
    start_hz,
    stop_hz,
    step_hz,
    osr,
    filt,
    amplitude,
    offset,
    phase,
    settle_time,
    my_adc,
    siggen,
    sampling_frequency,
    vref,
    ax,
    fig,
    label=None,
):
    """Run a frequency sweep, plotting results incrementally as data is acquired."""

    my_adc.oversampling_ratio = osr
    my_adc.filter_type = filt

    sweep_frequencies_hz = []
    sweep_rms_values = []

    frequency_range = range(start_hz, stop_hz, step_hz)
    total_sweep_points = len(frequency_range)
    print(
        f"\nStarting frequency sweep: {total_sweep_points} points from {start_hz/1000:.1f} kHz to {stop_hz/1000:.1f} kHz"
    )
    print(f"Step size: {step_hz/1000:.1f} kHz\n")
    print("=" * 60)

    # Create an empty line to update incrementally
    (line,) = ax.semilogx([], [], linestyle="dashed", marker="o", ms=2, label=label,)
    ax.legend(title="OSR")

    last_sample_indices = None
    last_time_domain_voltage = None
    last_frequency_axis = None
    last_spectrum_abs = None

    for i, input_frequency_hz in enumerate(frequency_range, 1):
        # Generate sine buffers for the current input frequency
        samp0, buffer0 = sine_buffer_generator(
            0, input_frequency_hz, amplitude, offset, phase
        )
        samp1, buffer1 = sine_buffer_generator(
            1, input_frequency_hz, amplitude, offset, 0
        )

        siggen.enableChannel(0, True)
        siggen.enableChannel(1, True)

        siggen.setSampleRate(0, samp0)
        siggen.setSampleRate(1, samp1)

        siggen.push([buffer0, buffer1])

        # Use plt.pause instead of sleep to allow the GUI to update
        plt.pause(settle_time)

        print(
            f"[{i}/{total_sweep_points}] Measuring at {input_frequency_hz/1000:.1f} kHz..."
        )

        data = my_adc.rx()
        data = my_adc.rx()

        sample_indices = np.arange(0, len(data))
        voltage = data * 2.0 * vref / (2 ** 20)
        dc = np.average(voltage)
        ac = voltage - dc
        rms_value = np.std(ac)

        sweep_frequencies_hz.append(input_frequency_hz)
        sweep_rms_values.append(rms_value)

        # Update plot incrementally
        sweep_response_db = 20 * np.log10(np.array(sweep_rms_values) / amplitude)
        line.set_data(sweep_frequencies_hz, sweep_response_db)
        ax.relim()
        ax.autoscale_view()
        fig.canvas.draw_idle()

        # Save last acquisition for time-domain and spectrum plots
        last_sample_indices = sample_indices
        last_time_domain_voltage = voltage

        effective_sample_rate = sampling_frequency / osr
        frequency_axis, power_spectrum = signal.periodogram(
            ac, effective_sample_rate, window="flattop", scaling="spectrum"
        )
        last_frequency_axis = frequency_axis
        last_spectrum_abs = np.sqrt(power_spectrum)

    return (
        last_sample_indices,
        last_time_domain_voltage,
        last_frequency_axis,
        last_spectrum_abs,
    )


# Set up interactive GUI for sweep and plots
fig, ax_resp = plt.subplots(1, 1, figsize=(12, 6))
fig.subplots_adjust(left=0.10, right=0.95, bottom=0.28, top=0.95)

ax_resp.set_title(
    f"AD4080 Filter Frequency Response ({args['filter'].upper()}, OSR={args['osr']})"
)
ax_resp.set_xlabel("frequency [Hz]")
ax_resp.set_ylabel("response (dB)")
ax_resp.grid(True)

# # Commented out: time-domain and spectrum plots ---
# fig_td, (ax_td, ax_spec) = plt.subplots(2, 1, figsize=(6, 6))
# fig_td.subplots_adjust(left=0.08, right=0.98, bottom=0.10, top=0.95, hspace=0.5)
# ax_td.set_title("AD4080 Time Domain Data (Last Acquisition)")
# ax_td.set_xlabel("Data Point")
# ax_td.set_ylabel("Voltage (V)")
# (td_line,) = ax_td.plot([], [], label="time domain")
# ax_td.legend(loc="upper right")
# ax_spec.set_title("AD4080 Spectrum (Volts absolute)")
# ax_spec.set_xlabel("frequency [Hz]")
# ax_spec.set_ylabel("Voltage (V)")
# (spec_line,) = ax_spec.semilogy([], [])
# ax_spec.set_ylim([1e-6, 4])

# Widget axes
ax_start = fig.add_axes([0.235, 0.17, 0.10, 0.05])
ax_stop = fig.add_axes([0.40, 0.17, 0.10, 0.05])
ax_step = fig.add_axes([0.58, 0.17, 0.10, 0.05])
ax_osr = fig.add_axes([0.72, 0.17, 0.06, 0.05])
ax_filt = fig.add_axes([0.20, 0.03, 0.30, 0.09])
ax_run = fig.add_axes([0.53, 0.03, 0.28, 0.09])

tb_start = TextBox(ax_start, "Start (Hz)", initial=str(args["start"]))
tb_start.label.set_x(-0.05)  # type: ignore
tb_stop = TextBox(ax_stop, "Stop (Hz)", initial=str(args["stop"]))
tb_stop.label.set_x(-0.05)  # type: ignore
tb_step = TextBox(ax_step, "Step (Hz)", initial=str(args["step"]))
tb_step.label.set_x(-0.05)  # type: ignore
tb_osr = TextBox(ax_osr, "OSR", initial=str(args["osr"]))
tb_osr.label.set_x(-0.07)  # type: ignore

filter_options = ["sinc1", "sinc5", "sinc5+pf1"]
default_filter = args["filter"] if args["filter"] in filter_options else "sinc5"
rb_filt = RadioButtons(ax_filt, filter_options, active=filter_options.index(default_filter))  # type: ignore

# Valid OSR values
# Get the list of valid OSR values from the device
try:
    osr_available_raw = my_adc.oversampling_ratio_available
    osr_valid_values = []

    # Convert whatever format we got into a list of integers
    if isinstance(osr_available_raw, str):
        # If it's a string, split it and convert each part to an integer
        osr_valid_values = [
            int(x) for x in str(osr_available_raw).replace(",", " ").split() if x
        ]
    else:
        # If it's already a list/array, convert each item to an integer
        osr_valid_values = [int(x) for x in osr_available_raw if x]

    if not osr_valid_values:
        raise ValueError("No valid OSR values found")

except Exception:
    # If we can't get the values from the device, use these defaults
    osr_valid_values = [32, 64, 128, 256]

print("OSR valid values:", osr_valid_values)

btn_run = Button(ax_run, "Run sweep", color="lightgreen", hovercolor="green",)


def _parse_int_sanitized(label, text):
    """Parse a numeric TextBox entry, allowing decimals but returning an int."""
    try:
        return int(float(text))
    except ValueError:
        print(f"Invalid {label}: '{text}' (expected a number)")
        return None


def _parse_osr_values(osr_text, osr_valid_values):
    """Parse a comma-separated OSR list and snap to nearest valid values.

    Returns a de-duplicated list of integers or None on error.
    """

    text = osr_text.strip().replace(" ", "")
    if not text:
        print("No OSR values provided")
        return None

    tokens = [t for t in text.split(",") if t]
    try:
        requested_osr_values = [int(float(t)) for t in tokens]
    except ValueError:
        print("Invalid OSR list. Use comma-separated numbers, e.g. 32,64,128")
        return None

    snapped = []
    for value in requested_osr_values:
        nearest = min(osr_valid_values, key=lambda v: abs(v - value))
        snapped.append(nearest)
        if nearest != value:
            print(f"Requested OSR {value} -> using nearest valid {nearest}")

    osr_values = []
    for v in snapped:
        if v not in osr_values:
            osr_values.append(v)

    return osr_values


def on_run(event):
    # Sanitize frequency inputs: accept decimals but convert to integers
    start_hz = _parse_int_sanitized("start frequency", tb_start.text)
    stop_hz = _parse_int_sanitized("stop frequency", tb_stop.text)
    step_hz = _parse_int_sanitized("step size", tb_step.text)

    if start_hz is None or stop_hz is None or step_hz is None:
        return

    # Parse and validate OSR selection from the textbox
    osr_values = _parse_osr_values(tb_osr.text, osr_valid_values)
    if not osr_values:
        return

    if step_hz <= 0 or stop_hz <= start_hz:
        print("Invalid sweep range or step size")
        return

    filt = rb_filt.value_selected

    # Clear previous response curves and set up axes
    ax_resp.cla()
    ax_resp.set_xlabel("frequency [Hz]")
    ax_resp.set_ylabel("response (dB)")
    ax_resp.grid(True)

    osr_label = ",".join(str(o) for o in osr_values)
    ax_resp.set_title(
        f"AD4080 Filter Frequency Response ({filt.upper()}, OSR={osr_label})"
    )

    # Run a sweep and plot a curve for each OSR
    for osr in osr_values:
        run_sweep(
            start_hz,
            stop_hz,
            step_hz,
            osr,
            filt,
            args["amplitude"],
            args["offset"],
            args["phase"],
            args["settle_time"],
            my_adc,
            siggen,
            sampling_frequency,
            vref,
            ax_resp,
            fig,
            label=f"OSR={osr}",
        )

    fig.canvas.draw_idle()


btn_run.on_clicked(on_run)


def on_close(event):
    print("All measurements complete. Cleaning up.")
    siggen.stop()
    libm2k.contextClose(ctx)


fig.canvas.mpl_connect("close_event", on_close)

print("Close the window to exit and clean up.\n")

plt.show()
