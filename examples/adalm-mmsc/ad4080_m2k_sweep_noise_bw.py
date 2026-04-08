# Copyright (C) 2026 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

import re
import sys
from time import sleep

import libm2k  # type: ignore
import matplotlib.pyplot as plt  # type: ignore
import numpy as np  # type: ignore
from matplotlib.widgets import Button, RadioButtons, TextBox  # type: ignore
from mmsc_utils import DeviceSelectionDialog, build_ad4080_uri
from scipy import signal  # type: ignore
from workshop import time_points_from_freq  # type: ignore

from adi import ad4080  # type: ignore

# Show device selection dialog before anything else
selected_devices = DeviceSelectionDialog(include_m2k=True).show()

if selected_devices is None:
    print("Connection cancelled by user")
    sys.exit(0)


my_uri = build_ad4080_uri(selected_devices["com_port"])
m2k_uri = selected_devices["m2k_uri"]
print(f"AD4080: {my_uri}  M2K: {m2k_uri}")


my_adc = None
ax_noise = None  # Persistent noise plot axes (embedded in control window)
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


def run_noise_sweep(
    oversample_ratio, filter_type, freq_start=0, freq_stop=99000, freq_step=1000
):
    """Configure ADC and run the noise bandwidth sweep, then plot results."""
    global my_adc, ax_noise
    assert ax_noise is not None, "ax_noise not yet initialised"

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

    siggen_sr = 7500000  # 7.5 MHz
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

    sweep_freqs, sweep_amps = [], []
    vref = 5.0
    noise_bin_amplitude = 1000e-6  # V amplitude per frequency bin

    if hasattr(my_adc, "channel") and len(my_adc.channel) > 0:
        _v_per_code = my_adc.channel[0].scale / 1e6
    else:
        _v_per_code = 2.0 * vref / (2 ** 20)
    print(f"[Scaling] {_v_per_code:.4e} V/LSB  (FSR={_v_per_code * 2**20:.3f} V p-p)")

    print(f"[Sweep] start={freq_start} Hz, stop={freq_stop} Hz, step={freq_step} Hz")
    for f in range(freq_start, freq_stop + 1, freq_step):
        noiseband = np.zeros(n)
        maxbin = int(2 * f / bin_width)
        noiseband[0:maxbin] = np.ones(maxbin)
        noiseband *= noise_bin_amplitude
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

        sweep_freqs.append(f)
        sweep_amps.append(rms)

    f_arr = np.array(sweep_freqs, dtype=float)
    amps_arr = np.array(sweep_amps)

    plt.rcParams.update({"font.size": 7})
    ax_noise.cla()

    f_pos = f_arr[1:]  # skip f=0
    df = float(f_pos[1] - f_pos[0]) if len(f_pos) > 1 else 1000.0

    # Rectangular-noise basis: flat input PSD integrated through the selected sinc filter
    white_integrated = np.sqrt(np.cumsum(np.ones_like(f_pos)) * df)  # rectangular input
    sincN_integrated = np.sqrt(
        np.cumsum(np.sinc(f_pos / fnotch) ** (2 * sinc_order)) * df
    )  # output: flat PSD × |H(f)|² with H(f)=sinc^N
    # Raw (non-integrated) filter magnitude responses
    sinc1_response = np.abs(np.sinc(f_pos / fnotch))  # |sinc(f/fnotch)|
    sinc2_response = np.abs(np.sinc(f_pos / fnotch)) ** 2  # |sinc(f/fnotch)|²

    a_pos = amps_arr[1:]
    mid_idx = len(f_pos) // 2

    def _scale_mid(ref):
        return ref * (a_pos[mid_idx] / ref[mid_idx]) if ref[mid_idx] > 0 else ref

    title = (
        f"Total Integrated Noise — OSR={my_adc.oversampling_ratio}, "
        f"{filter_type.upper()}, notch={fnotch/1e3:.1f} kHz"
    )
    ax_noise.set_title(title, fontsize=9)
    ax_noise.plot(
        f_pos,
        a_pos,
        linestyle="solid",
        color="k",
        linewidth=2,
        marker="o",
        ms=2,
        label="Measured integrated noise",
    )
    ax_noise.plot(
        f_pos,
        _scale_mid(white_integrated),
        linestyle="--",
        color="gray",
        label="Rectangular input (flat PSD)",
    )
    ax_noise.plot(
        f_pos,
        _scale_mid(sincN_integrated),
        linestyle="--",
        color="r",
        label=f"Rectangular input × sinc{sinc_order}",
    )

    # Raw filter responses on a secondary y-axis (different scale)
    ax_filt = ax_noise.twinx()
    ax_filt.plot(
        f_pos,
        sinc1_response,
        linestyle="-.",
        color="steelblue",
        linewidth=1.5,
        label="Sinc filter response",
    )
    ax_filt.plot(
        f_pos,
        sinc2_response,
        linestyle="-.",
        color="darkorange",
        linewidth=1.5,
        label="Sinc² filter response",
    )
    ax_filt.set_ylabel("Filter magnitude", fontsize=7)
    ax_filt.set_ylim([-0.05, 1.05])  # type: ignore

    ax_noise.axvline(
        x=fnotch,
        color="r",
        linestyle=":",
        linewidth=1,
        alpha=0.6,
        label=f"Notch {fnotch/1e3:.1f} kHz",
    )
    # Combine legends from both axes
    lines1, labels1 = ax_noise.get_legend_handles_labels()
    lines2, labels2 = ax_filt.get_legend_handles_labels()
    ax_noise.legend(lines1 + lines2, labels1 + labels2, fontsize=7, loc="center right")
    ax_noise.set_ylabel("Integrated noise (V rms)")
    ax_noise.grid(True, which="both", alpha=0.3)

    fig_ctrl.canvas.draw_idle()

    # Clean up M2K after the sweep completes
    siggen.stop()
    libm2k.contextClose(my_m2k)


fig_ctrl, ax_noise = plt.subplots(1, 1, num=1, figsize=(12, 6))
fig_ctrl.subplots_adjust(left=0.10, right=0.95, bottom=0.28, top=0.95)

ax_noise.set_ylabel("Integrated noise (V rms)")
ax_noise.grid(True, which="both", alpha=0.3)
ax_noise.text(
    0.5,
    0.5,
    "Run a sweep to see results",
    transform=ax_noise.transAxes,
    ha="center",
    va="center",
    color="gray",
    fontsize=10,
    style="italic",
)

# Filter options
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

fig_ctrl.text(0.53, 0.24, "Noise BW Sweep Setup", ha="center", fontsize=10)

ax_fstart = fig_ctrl.add_axes([0.235, 0.17, 0.10, 0.05])
tb_fstart = TextBox(ax_fstart, "Start (Hz)", initial="0")
tb_fstart.label.set_x(-0.05)  # type: ignore

ax_fstop = fig_ctrl.add_axes([0.40, 0.17, 0.10, 0.05])
tb_fstop = TextBox(ax_fstop, "Stop (Hz)", initial="99000")
tb_fstop.label.set_x(-0.05)  # type: ignore

ax_fstep = fig_ctrl.add_axes([0.58, 0.17, 0.10, 0.05])
tb_fstep = TextBox(ax_fstep, "Step (Hz)", initial="1000")
tb_fstep.label.set_x(-0.05)  # type: ignore

ax_osr = fig_ctrl.add_axes([0.72, 0.17, 0.06, 0.05])
tb_osr = TextBox(ax_osr, "OSR", initial="1024")
tb_osr.label.set_x(-0.07)  # type: ignore

ax_filter = fig_ctrl.add_axes([0.20, 0.03, 0.30, 0.09])
rb_filter = RadioButtons(ax_filter, filter_options, active=default_idx)  # type: ignore
ax_filter.set_title("Filter")

ax_start = fig_ctrl.add_axes([0.53, 0.03, 0.28, 0.09])
btn_start = Button(ax_start, "Start sweep", color="lightgreen", hovercolor="green")


def _parse_int(label, text):
    try:
        return int(float(text))
    except ValueError:
        print(f"Invalid {label}: '{text}' (expected a number)")
        return None


def on_start(event):
    osr = _parse_int("OSR", tb_osr.text)
    fstart = _parse_int("Start freq", tb_fstart.text)
    fstop = _parse_int("Stop freq", tb_fstop.text)
    fstep = _parse_int("Step freq", tb_fstep.text)
    if osr is None or fstart is None or fstop is None or fstep is None:
        return
    if fstep <= 0:
        print("Step (Hz) must be > 0")
        return
    if fstart > fstop:
        print("Start (Hz) must be <= Stop (Hz)")
        return

    filt = rb_filter.value_selected
    print(
        f"Starting noise BW sweep with OSR={osr}, filter={filt}, "
        f"start={fstart} Hz, stop={fstop} Hz, step={fstep} Hz"
    )

    run_noise_sweep(osr, filt, freq_start=fstart, freq_stop=fstop, freq_step=fstep)


btn_start.on_clicked(on_start)

# Start the GUI event loop and keep all windows open until user closes them
plt.show(block=True)
