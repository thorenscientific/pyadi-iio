# Copyright (C) 2022-2024 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

import argparse
import sys
import tkinter as tk
from time import sleep
from tkinter import ttk

import libm2k  # type: ignore
import matplotlib.pyplot as plt  # type: ignore
import numpy as np  # type: ignore
import serial.tools.list_ports  # type: ignore
from matplotlib.widgets import Button, RadioButtons, TextBox  # type: ignore
from scipy import signal  # type: ignore
from sine_gen import *

from adi import ad4080  # type: ignore


def scan_com_ports():
    """Scan for available COM ports without opening them"""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in sorted(ports)]


def scan_m2k_devices():
    """Scan for available M2K devices"""
    try:
        contexts = libm2k.getAllContexts()
        return contexts if contexts else []
    except:
        return []


class DeviceSelectionDialog:
    def __init__(self):
        self.result = None
        self.root = tk.Tk()
        self.root.title("Select Devices")
        self.root.geometry("400x200")

        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill="both", expand=True)

        row = 0

        # AD4080 COM Port selection
        ttk.Label(main_frame, text="AD4080 COM Port:", font=("", 10)).grid(
            row=row, column=0, sticky="w", padx=5, pady=10
        )

        available_ports = scan_com_ports()
        if available_ports:
            self.com_port = tk.StringVar(
                value="COM12" if "COM12" in available_ports else available_ports[0]
            )
            ttk.Combobox(
                main_frame,
                textvariable=self.com_port,
                values=available_ports,
                width=25,
                state="readonly",
            ).grid(row=row, column=1, sticky="w", padx=5)
        else:
            self.com_port = tk.StringVar(value="COM12")
            ttk.Entry(main_frame, textvariable=self.com_port, width=27).grid(
                row=row, column=1, sticky="w", padx=5
            )
        row += 1

        # M2K URI selection
        ttk.Label(main_frame, text="M2K URI:", font=("", 10)).grid(
            row=row, column=0, sticky="w", padx=5, pady=10
        )

        available_m2k = scan_m2k_devices()
        if available_m2k:
            self.m2k_uri = tk.StringVar(value=available_m2k[0])
            ttk.Combobox(
                main_frame,
                textvariable=self.m2k_uri,
                values=available_m2k,
                width=25,
                state="readonly",
            ).grid(row=row, column=1, sticky="w", padx=5)
        else:
            self.m2k_uri = tk.StringVar(value="ip:192.168.2.1")
            ttk.Entry(main_frame, textvariable=self.m2k_uri, width=27).grid(
                row=row, column=1, sticky="w", padx=5
            )
        row += 1

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=20)

        ttk.Button(button_frame, text="Connect", command=self.on_ok, width=12).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Cancel", command=self.on_cancel, width=12).pack(
            side="left", padx=5
        )

    def on_ok(self):
        self.result = {
            "com_port": self.com_port.get(),
            "m2k_uri": self.m2k_uri.get(),
        }
        self.root.quit()
        self.root.destroy()

    def on_cancel(self):
        self.root.quit()
        self.root.destroy()

    def show(self):
        self.root.mainloop()
        return self.result


# Show device selection dialog
device_dialog = DeviceSelectionDialog()
selected_devices = device_dialog.show()

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

my_uri = f"serial:{selected_devices['com_port']},230400"
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


print("Collecting initial data sample")

plt.figure(1)
plt.clf()
data = my_adc.rx()

plt.plot(data, label="channel0")
plt.xlabel("Data Point")
plt.ylabel("ADC counts")
plt.legend(
    bbox_to_anchor=(0.0, 1.02, 1.0, 0.102),
    loc="lower left",
    ncol=4,
    mode="expand",
    borderaxespad=0.0,
)

print("\nFigure 1: Initial Data Sample")
print(" > Close the figure window to proceed with frequency sweep\n")
plt.show()


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
    start_hz, stop_hz, step_hz, osr, filt, amplitude, offset, phase, settle_time
):
    """Run a frequency sweep and return processed results for plotting."""

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

        sleep(settle_time)

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

        # Save last acquisition for time-domain and spectrum plots
        last_sample_indices = sample_indices
        last_time_domain_voltage = voltage

        effective_sample_rate = sampling_frequency / osr
        frequency_axis, power_spectrum = signal.periodogram(
            ac, effective_sample_rate, window="flattop", scaling="spectrum"
        )
        last_frequency_axis = frequency_axis
        last_spectrum_abs = np.sqrt(power_spectrum)

    sweep_response_db = 20 * np.log10(np.array(sweep_rms_values) / np.sqrt(4.0))
    return (
        sweep_frequencies_hz,
        sweep_response_db,
        last_sample_indices,
        last_time_domain_voltage,
        last_frequency_axis,
        last_spectrum_abs,
    )


# Set up interactive GUI for sweep and plots
# Figure 2: time-domain and spectrum (with controls)
fig, (ax_td, ax_spec) = plt.subplots(2, 1, figsize=(6, 6))
# Leave space at the bottom for all controls and stretch plots horizontally
fig.subplots_adjust(left=0.08, right=0.98, bottom=0.28, top=0.95, hspace=0.5)

ax_td.set_title("AD4080 Time Domain Data (Last Acquisition)")
ax_td.set_xlabel("Data Point")
ax_td.set_ylabel("Voltage (V)")
(td_line,) = ax_td.plot([], [], label="time domain")
ax_td.legend(loc="upper right")

ax_spec.set_title("AD4080 Spectrum (Volts absolute)")
ax_spec.set_xlabel("frequency [Hz]")
ax_spec.set_ylabel("Voltage (V)")
(spec_line,) = ax_spec.semilogy([], [])
ax_spec.set_ylim([1e-6, 4])

# Widget axes (placed along the bottom of Figure 2)
# Shift all controls to the right to better use horizontal space
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

# Figure 3: frequency-response plot in a separate window
fig_resp, ax_resp = plt.subplots(1, 1, num=3, figsize=(8, 4))
ax_resp.set_title(
    f"AD4080 Filter Frequency Response ({args['filter'].upper()}, OSR={args['osr']})"
)
ax_resp.set_xlabel("frequency [Hz]")
ax_resp.set_ylabel("response (dB)")
ax_resp.grid(True)


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

    # Clear previous response curves
    ax_resp.cla()

    last_sample_indices = None
    last_time_domain_voltage = None
    last_frequency_axis = None
    last_spectrum_abs = None

    # Run a sweep and plot a curve for each OSR
    for osr in osr_values:
        (
            sweep_frequencies_hz,
            sweep_response_db,
            last_sample_indices,
            last_time_domain_voltage,
            last_frequency_axis,
            last_spectrum_abs,
        ) = run_sweep(
            start_hz,
            stop_hz,
            step_hz,
            osr,
            filt,
            args["amplitude"],
            args["offset"],
            args["phase"],
            args["settle_time"],
        )

        ax_resp.semilogx(
            sweep_frequencies_hz,
            sweep_response_db,
            linestyle="dashed",
            marker="o",
            ms=2,
            label=f"OSR={osr}",
        )

    # Update time-domain and spectrum plots using the last sweep
    if last_sample_indices is not None and last_time_domain_voltage is not None:
        td_line.set_data(last_sample_indices, last_time_domain_voltage)
        ax_td.relim()
        ax_td.autoscale_view()

    if last_frequency_axis is not None and last_spectrum_abs is not None:
        spec_line.set_data(last_frequency_axis, last_spectrum_abs)
        ax_spec.relim()
        ax_spec.autoscale_view()
        ax_spec.set_ylim([1e-6, 4])

    ax_resp.set_xlabel("frequency [Hz]")
    ax_resp.set_ylabel("response (dB)")
    ax_resp.grid(True)
    ax_resp.legend(title="OSR")

    osr_label = ",".join(str(o) for o in osr_values)
    ax_resp.set_title(
        f"AD4080 Filter Frequency Response ({filt.upper()}, OSR={osr_label})"
    )

    # Redraw both figures so all plots update together
    fig.canvas.draw_idle()
    fig_resp.canvas.draw_idle()


btn_run.on_clicked(on_run)

print("Close the window to exit and clean up.\n")

plt.show()


print("All measurements complete. Cleaning up.")


siggen.stop()
libm2k.contextClose(ctx)
del my_adc
