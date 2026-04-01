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

import re
import sys
import tkinter as tk
from time import sleep
from tkinter import ttk

import libm2k  # type: ignore
import serial.tools.list_ports  # type: ignore
import matplotlib.pyplot as plt  # type: ignore
import numpy as np  # type: ignore
from matplotlib.widgets import Button, RadioButtons, TextBox  # type: ignore
from scipy import signal  # type: ignore
from workshop import time_points_from_freq # type: ignore

from adi import ad4080  # type: ignore

def scan_com_ports():
    """Scan for available COM ports without opening them."""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in sorted(ports)]


def scan_m2k_devices():
    """Scan for available M2K devices via libm2k."""
    try:
        contexts = libm2k.getAllContexts()
        return contexts if contexts else []
    except Exception:
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
                value="COM13" if "COM13" in available_ports else available_ports[0]
            )
            ttk.Combobox(
                main_frame,
                textvariable=self.com_port,
                values=available_ports,
                width=25,
                state="readonly",
            ).grid(row=row, column=1, sticky="w", padx=5)
        else:
            self.com_port = tk.StringVar(value="COM13")
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


# Show device selection dialog before anything else
_device_dialog = DeviceSelectionDialog()
_selected_devices = _device_dialog.show()

if _selected_devices is None:
    print("Connection cancelled by user")
    sys.exit(0)


my_uri = f"serial:{_selected_devices['com_port']},230400"
m2k_uri = _selected_devices["m2k_uri"]
print(f"AD4080: {my_uri}  M2K: {m2k_uri}")


my_adc = None
results_fig = None  # Figure 2: time-domain + spectrum
noise_fig = None  # Figure 3: integrated noise + NSD
try:
    my_adc = ad4080(uri=my_uri, device_name="ad4080")
    try:
        my_adc._ctx.set_timeout(10000)  # ms; avoids serial read timeouts
    except Exception:
        pass

    my_adc.rx_buffer_size = 4096
    sampling_frequency = 40000000.0  # AD4080 fixed at 40 MSPS

    print("oversampling_ratio_available: ", my_adc.oversampling_ratio_available)
    print("filter_type_available: ", my_adc.filter_type_available)
except Exception as e:
    print("Failed to open AD4080:", e)
    sampling_frequency = 40000000.0


def run_noise_sweep(oversample_ratio, filter_type):
    """Configure ADC and run the noise bandwidth sweep, then plot results."""
    global my_adc, results_fig, noise_fig

    if my_adc is None:
        print("Cannot run sweep: AD4080 not available")
        return

    my_m2k = libm2k.m2kOpen(m2k_uri)
    if my_m2k is None:
        print("No M2K device found at:", m2k_uri)
        return

    sleep(0.1)
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
    siggen.setCyclic(True)  # ~35 ms buffer; loop it so ADC always sees a live signal

    my_adc.oversampling_ratio = int(oversample_ratio)
    my_adc.filter_type = filter_type

    print("Setting filter to", filter_type, "decimation", my_adc.oversampling_ratio)
    print("Verifying... read back filter type: ", my_adc.filter_type)

    fnotch = sampling_frequency / my_adc.oversampling_ratio
    print("SINC first notch at ", fnotch)

    _m = re.search(r"sinc(\d+)", filter_type.lower())
    sinc_order = int(_m.group(1)) if _m else 1
    print(f"[Filter] sinc_order={sinc_order}, filter_type='{filter_type}'")
    actual_filter = my_adc.filter_type
    if actual_filter.lower() != filter_type.lower():
        print(
            f"[Filter] WARNING: requested '{filter_type}' but ADC reports '{actual_filter}'"
        )

    fs, amps = [], []
    vref = 5.0
    en = 1000e-6

    if hasattr(my_adc, "channel") and len(my_adc.channel) > 0:
        _v_per_code = my_adc.channel[0].scale / 1e6
    else:
        _v_per_code = 2.0 * vref / (2 ** 20)
    print(f"[Scaling] {_v_per_code:.4e} V/LSB  (FSR={_v_per_code * 2**20:.3f} V p-p)")

    for f in range(0, 100000, 1000):  # Sweep 0 to 100 kHz in 1 kHz steps
        noiseband = np.zeros(n)
        maxbin = int(2 * f / bin_width)
        noiseband[0:maxbin] = np.ones(maxbin)
        noiseband *= en
        time_points = time_points_from_freq(noiseband, siggen_sr, True)
        buffer = [time_points, time_points * -1.0]

        siggen.push(buffer)

        sleep(0.25)

        print("Frequency: ", f, "bin: ", maxbin)

        data = my_adc.rx()
        data = my_adc.rx()

        x = np.arange(len(data))
        voltage = data * _v_per_code
        dc = np.average(voltage)
        ac = voltage - dc
        rms = np.std(ac)  # std == RMS for zero-mean signal

        fs.append(f)
        amps.append(rms)

    f_arr = np.array(fs, dtype=float)
    amps_arr = np.array(amps)

    # Close previous results windows before creating new ones
    for _fig in (results_fig, noise_fig):
        if _fig is not None:
            try:
                plt.close(_fig)
            except Exception:
                pass
    results_fig = None
    noise_fig = None

    plt.rcParams.update({"font.size": 7})

    fig, (ax_td, ax_spec) = plt.subplots(2, 1, num=2, figsize=(9, 6))
    fig.subplots_adjust(hspace=0.5)

    ax_td.set_title("AD4080 Time Domain Data (last sweep point)")
    ax_td.plot(x, voltage)
    ax_td.set_xlabel("Sample")
    ax_td.set_ylabel("Voltage (V)")
    ax_td.grid(True, alpha=0.4)

    f_axis, Pxx_spec = signal.periodogram(
        ac, sampling_frequency, window="flattop", scaling="spectrum"
    )
    Pxx_abs = np.sqrt(Pxx_spec)
    ax_spec.set_title("AD4080 Spectrum — Volts absolute (last sweep point)")
    ax_spec.semilogy(f_axis, Pxx_abs)
    ax_spec.set_ylim([1e-6, 4])
    ax_spec.set_xlabel("Frequency (Hz)")
    ax_spec.set_ylabel("Voltage (V)")
    ax_spec.grid(True, alpha=0.4)

    fig.show()
    results_fig = fig

    fig2, (ax_noise, ax_nsd) = plt.subplots(2, 1, num=3, figsize=(9, 7))
    fig2.subplots_adjust(hspace=0.5)

    f_pos = f_arr[1:]  # skip f=0
    df = float(f_pos[1] - f_pos[0]) if len(f_pos) > 1 else 1000.0

    # Rectangular-noise basis: flat input PSD integrated through the selected sinc filter
    white_integrated = np.sqrt(np.cumsum(np.ones_like(f_pos)) * df)  # rectangular input
    sincN_integrated = np.sqrt(
        np.cumsum(np.sinc(f_pos / fnotch) ** (2 * sinc_order)) * df
    )  # output: flat PSD × |H(f)|² with H(f)=sinc^N

    # Scale each reference curve to the measured midpoint for log-log comparison
    a_pos = amps_arr[1:]
    mid_idx = len(f_pos) // 2

    def _scale_mid(ref):
        return ref * (a_pos[mid_idx] / ref[mid_idx]) if ref[mid_idx] > 0 else ref

    title = (
        f"Total Integrated Noise — OSR={my_adc.oversampling_ratio}, "
        f"{filter_type.upper()}, notch={fnotch/1e3:.1f} kHz"
    )
    ax_noise.set_title(title, fontsize=9)
    ax_noise.loglog(
        f_pos,
        a_pos,
        linestyle="solid",
        color="k",
        linewidth=2,
        marker="o",
        ms=2,
        label="Measured integrated noise",
    )
    ax_noise.loglog(
        f_pos,
        _scale_mid(white_integrated),
        linestyle="--",
        color="gray",
        label="Rectangular input (flat PSD)",
    )
    ax_noise.loglog(
        f_pos,
        _scale_mid(sincN_integrated),
        linestyle="--",
        color="r",
        label=f"Rectangular input × sinc{sinc_order}",
    )
    ax_noise.axvline(
        x=fnotch,
        color="r",
        linestyle=":",
        linewidth=1,
        alpha=0.6,
        label=f"Notch {fnotch/1e3:.1f} kHz",
    )
    ax_noise.legend(fontsize=7, loc="lower right")
    ax_noise.set_xlabel("Noise BW, from DC to [Hz]")
    ax_noise.set_ylabel("Integrated noise (V rms)")
    ax_noise.grid(True, which="both", alpha=0.3)

    rms_sq = amps_arr ** 2
    rms_sq_diff = np.empty_like(rms_sq)
    rms_sq_diff[1:-1] = (rms_sq[2:] - rms_sq[:-2]) / 2.0  # central diff
    rms_sq_diff[0] = rms_sq_diff[1]
    rms_sq_diff[-1] = rms_sq_diff[-2]
    noise_density = np.sqrt(np.abs(rms_sq_diff) / df)

    # Rectangular-band basis NSD model: flat input NSD shaped by selected sinc response
    def _nsd_curve(order):  # |sinc(f/fnotch)|^N amplitude response
        return np.abs(np.sinc(f_arr / fnotch)) ** order

    def _nsd_scale(ref):  # median-scale model to measured data
        valid = (noise_density > 0) & (ref > 0)
        return ref * (
            np.nanmedian(noise_density[valid] / ref[valid]) if valid.any() else 1.0
        )

    ax_nsd.semilogy(
        f_arr,
        noise_density,
        linestyle="solid",
        color="k",
        linewidth=1.5,
        marker="o",
        ms=2,
        label="Measured NSD",
    )

    ax_nsd.semilogy(
        f_arr,

        _nsd_scale(_nsd_curve(sinc_order)),
        linestyle="--",
        color="r",
        linewidth=2.2,
        alpha=1.0,
        label=f"Rectangular input × {filter_type}",
    )

    ax_nsd.axvline(
        x=fnotch,
        color="r",
        linestyle=":",
        linewidth=1.2,
        alpha=0.8,
        label=f"Notch  {fnotch/1e3:.1f} kHz",
    )
    ax_nsd.axvline(
        x=fnotch / 2,
        color="orange",
        linestyle=":",
        linewidth=1.2,
        alpha=0.8,
        label=f"Nyquist  {fnotch/2e3:.1f} kHz",
    )
    ax_nsd.set_title(
        f"Incremental NSD — selected: {filter_type}, notch={fnotch/1e3:.1f} kHz\n"
        "Rectangular-basis check: measured (black) should overlap the red model",
        fontsize=9,
    )
    ax_nsd.set_xlabel("Frequency (Hz)")
    ax_nsd.set_ylabel("NSD (V/√Hz)")
    ax_nsd.legend(fontsize=7)
    ax_nsd.grid(True, which="both", alpha=0.3)

    fig2.show()
    noise_fig = fig2

    # Clean up M2K after the sweep completes
    siggen.stop()
    libm2k.contextClose(my_m2k)


# Simple control window: choose OSR and filter, then start sweep

fig_ctrl, ax_ctrl = plt.subplots(num=1, figsize=(5, 3))
fig_ctrl.subplots_adjust(left=0.05, right=0.95, top=0.85, bottom=0.25)
ax_ctrl.axis("off")
ax_ctrl.set_title("Noise BW Sweep Setup")

# Filter selection radio buttons using available types (or sensible defaults)
if my_adc is not None:
    filter_tokens = str(my_adc.filter_type_available).split()
    filter_options = [f for f in filter_tokens if f != "none"] or [
        "sinc1",
        "sinc5",
        "sinc5+pf1",
    ]
    current_filter = my_adc.filter_type
else:
    filter_options = ["sinc1", "sinc5", "sinc5+pf1"]
    current_filter = "sinc1"

default_idx = (
    filter_options.index(current_filter) if current_filter in filter_options else 0
)

# Stack everything centered horizontally
ax_filter = fig_ctrl.add_axes([0.20, 0.60, 0.60, 0.18])
rb_filter = RadioButtons(ax_filter, filter_options, active=default_idx)  # type: ignore
ax_filter.set_title("Filter")

# OSR textbox in the middle
ax_osr = fig_ctrl.add_axes([0.30, 0.35, 0.40, 0.12])
tb_osr = TextBox(ax_osr, "OSR", initial="1024")

# Start sweep button at the bottom of the stack
ax_start = fig_ctrl.add_axes([0.30, 0.15, 0.40, 0.12])
btn_start = Button(ax_start, "Start sweep", color="lightgreen", hovercolor="green")


def _parse_int(label, text):
    try:
        return int(float(text))
    except ValueError:
        print(f"Invalid {label}: '{text}' (expected a number)")
        return None


def on_start(event):
    osr = _parse_int("OSR", tb_osr.text)
    if osr is None:
        return

    filt = rb_filter.value_selected
    print(f"Starting noise BW sweep with OSR={osr}, filter={filt}")

    run_noise_sweep(osr, filt)


btn_start.on_clicked(on_start)

# Start the GUI event loop and keep all windows open until user closes them
plt.show(block=True)
