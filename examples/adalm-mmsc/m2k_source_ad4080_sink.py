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


import tkinter as tk
from sys import exit
from tkinter import messagebox, ttk

import genalyzer as gn  # type: ignore
import libm2k  # type: ignore
import matplotlib.pyplot as plt  # type: ignore
import numpy as np  # type: ignore
import serial.tools.list_ports  # type: ignore
import workshop # type: ignore
import adi  # type: ignore

def scan_com_ports():
    """Scan for available COM ports without opening them"""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in sorted(ports)]


def scan_m2k_devices():
    """Scan for available M2K devices"""
    try:
        contexts = libm2k.getAllContexts()
        return contexts if contexts else []
    except Exception:
        return []


class ConfigDialog:
    def __init__(self):
        self.result = None
        self.root = tk.Tk()
        self.root.title("M2K + AD4080 Signal Generator")
        self.root.geometry("400x240")

        # Main frame
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill="both", expand=True)

        self.create_form(main_frame)

        # Buttons at bottom
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=10, column=0, columnspan=2, pady=20)

        ttk.Button(button_frame, text="Run Test", command=self.on_ok, width=12).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Cancel", command=self.on_cancel, width=12).pack(
            side="left", padx=5
        )

    def create_form(self, parent):
        row = 0

        # Frequency
        ttk.Label(parent, text="Fundamental Frequency (Hz):").grid(
            row=row, column=0, sticky="w", padx=5, pady=8
        )
        self.freq = tk.StringVar(value="100000")
        ttk.Entry(parent, textvariable=self.freq, width=20).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        # Amplitude
        ttk.Label(parent, text="Amplitude (dBFS):").grid(
            row=row, column=0, sticky="w", padx=5, pady=8
        )
        self.amplitude = tk.StringVar(value="-3")
        ttk.Entry(parent, textvariable=self.amplitude, width=20).grid(
            row=row, column=1, sticky="w"
        )
        row += 1

        ttk.Separator(parent, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=15
        )
        row += 1

        # Connection URIs
        ttk.Label(parent, text="AD4080 COM Port:").grid(
            row=row, column=0, sticky="w", padx=5, pady=8
        )

        # Scan for available COM ports
        available_ports = scan_com_ports()

        if available_ports:
            # Use combobox if ports are found
            self.ad4080_port = tk.StringVar(
                value=available_ports[0] if "COM12" not in available_ports else "COM12"
            )
            ttk.Combobox(
                parent,
                textvariable=self.ad4080_port,
                values=available_ports,
                width=18,
                state="readonly",
            ).grid(row=row, column=1, sticky="w")
        else:
            # Fallback to text entry if no ports found
            self.ad4080_port = tk.StringVar(value="COM12")
            ttk.Entry(parent, textvariable=self.ad4080_port, width=20).grid(
                row=row, column=1, sticky="w"
            )
        row += 1

        ttk.Label(parent, text="M2K URI:").grid(
            row=row, column=0, sticky="w", padx=5, pady=8
        )

        # Scan for available M2K devices
        available_m2k = scan_m2k_devices()

        if available_m2k:
            self.m2k_uri = tk.StringVar(value=available_m2k[0])
            ttk.Combobox(
                parent,
                textvariable=self.m2k_uri,
                values=available_m2k,
                width=23,
                state="readonly",
            ).grid(row=row, column=1, sticky="w")
        else:
            self.m2k_uri = tk.StringVar(value="ip:192.168.2.1")
            ttk.Entry(parent, textvariable=self.m2k_uri, width=25).grid(
                row=row, column=1, sticky="w"
            )
        row += 1

    def on_ok(self):
        try:
            # Validate inputs
            freq = float(self.freq.get())
            if freq <= 0:
                raise ValueError("Frequency must be positive")

            amplitude = float(self.amplitude.get())

            # Build result dictionary with default harmonics and noise
            self.result = {
                "fund_freq": freq,
                "amplitude": amplitude,
                "ad4080_uri": f"serial:{self.ad4080_port.get()},230400",
                "m2k_uri": self.m2k_uri.get(),
                "harmonics": f"{amplitude},-23,-20,-20",  # Default harmonics pattern
                "noise_freqs": "150000,250000,350000,450000",  # Default noise frequencies
                "noise_dbfs": "-40,-60,-70,-50",  # Default noise amplitudes
                "buffer_size": 16384,  # Default buffer size
                "navg": 2,  # Default averages
                "fs_out": 7500000.0,  # Default M2K sample rate
            }
            self.root.quit()
            self.root.destroy()
        except Exception as e:
            messagebox.showerror(
                "Invalid Input", f"Error: {str(e)}\nPlease check your inputs."
            )

    def on_cancel(self):
        self.root.quit()
        self.root.destroy()

    def show(self):
        self.root.mainloop()
        return self.result


# Show GUI configuration dialog
config = ConfigDialog()
gui_config = config.show()

if gui_config is None:
    print("Configuration cancelled by user")
    exit(0)

# 0. Configuration
fs_out = gui_config["fs_out"]
fs_in = 40_000_000


def _parse_csv_floats(s: str):
    if not s or not s.strip():
        return []
    return [float(x) for x in s.split(",") if x.strip()]


# Tone parameters
fsr = 2.0
fund_freq = gui_config["fund_freq"]

harm_dbfs = _parse_csv_floats(gui_config["harmonics"])
noise_freqs = _parse_csv_floats(gui_config["noise_freqs"])
noise_dbfs = _parse_csv_floats(gui_config["noise_dbfs"])

if len(noise_freqs) != len(noise_dbfs):
    raise ValueError("noise-freqs and noise-dbfs must have the same length")

# FFT parameters
window = gn.Window.BLACKMAN_HARRIS
npts = gui_config["buffer_size"]
navg = gui_config["navg"]
nfft = npts // navg

# 1. Connect to M2K and AD4080
my_m2k = libm2k.m2kOpen(gui_config["m2k_uri"])

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
my_ad4080 = adi.ad4080(gui_config["ad4080_uri"])
if my_ad4080 is None:
    print("Connection Error: No AD4080 device available/connected to your PC.")
    exit(1)

# Initialize ADC
my_ad4080.rx_buffer_size = npts
my_ad4080.filter_type = "none"
print(f"Sampling frequency: {my_ad4080.sampling_frequency}")
assert my_ad4080.sampling_frequency == fs_in

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
    freq = gn.coherent(nfft, fs_out, noise_freqs[tone])

    print(f"Noise Frequency: {freq} ({noise_dbfs[tone]} dBfs)")
    awf += gn.cos(npts, fs_out, noise_ampl[tone], freq, 0, 0, 0)

# 3. Transmit generated waveform
print(f"\nM2K Waveform stats:")
print(f"  Min: {np.min(awf):.6f} V")
print(f"  Max: {np.max(awf):.6f} V")
print(f"  Peak-to-Peak: {np.ptp(awf):.6f} V")
print(f"  RMS: {np.sqrt(np.mean(awf**2)):.6f} V")
print(f"  Sample rate: {aout.getSampleRate(0)} Hz")
print(f"  Channel enabled: {aout.isChannelEnabled(0)}")
print(f"  Cyclic mode: {aout.getCyclic(0)}")

aout.push([awf])  # Would be [awf0, awf1] if sending data to multiple channels

# 4. Receive one buffer of samples
data_in_raw = my_ad4080.rx()

print(f"\nAD4080 received data stats:")
print(
    f"  Raw ADC codes - Min: {np.min(data_in_raw)}, Max: {np.max(data_in_raw)}, Range: {np.ptp(data_in_raw)}"
)
raw_scale = float(my_ad4080.channel[0].scale)
print(f"  Reported scale factor: {raw_scale} (driver units unknown)")

# Interpret the reported scale in likely units and choose the most plausible one.
# Many IIO drivers use mV/code, but some use V/code or uV/code.
scale_candidates = {
    "V/code": raw_scale,
    "mV/code": raw_scale / 1e3,
    "uV/code": raw_scale / 1e6,
}

target_vpp = max(np.ptp(awf), 1e-12)  # DAC waveform p-p in Volts
best_unit = "uV/code"
best_v_per_code = scale_candidates[best_unit]
best_score = float("inf")

for unit_name, v_per_code in scale_candidates.items():
    measured_vpp = np.ptp(data_in_raw * v_per_code)
    score = abs(np.log10(max(measured_vpp, 1e-12) / target_vpp))
    if score < best_score:
        best_score = score
        best_unit = unit_name
        best_v_per_code = v_per_code

data_in = data_in_raw * best_v_per_code

print(f"  Inferred scale interpretation: {best_unit}")
print(f"  Using {best_v_per_code:.6e} V/code")
print(
    f"  Converted to Volts - Min: {np.min(data_in):.6f} V, Max: {np.max(data_in):.6f} V, Peak-to-Peak: {np.ptp(data_in):.6f} V"
)
print(f"  M2K output waveform peak-to-peak: {np.ptp(awf):.6f} V")
print(f"  Script assumes FSR: {fsr} V (±{fsr/2} V)")

ratio = np.ptp(data_in) / target_vpp
if ratio < 0.1 or ratio > 10:
    print(
        "  WARNING: ADC amplitude is far from DAC amplitude. Check analog attenuation/gain path and ADC input mode."
    )

# Normalize waveform so that full-scale corresponds to 0 dBFS for genalyzer
# This matches the assumption in workshop.fourier_analysis (fund_ampl = 10**(-3/20))
data_fs = data_in / (fsr / 2.0)

del my_ad4080
del my_m2k

# 5. Analyze recorded waveform
workshop.fourier_analysis(
    data_fs, fundamental=fund_freq, sampling_rate=fs_in, window=window
)

# Keep figures open until manually closed
plt.show(block=True)
