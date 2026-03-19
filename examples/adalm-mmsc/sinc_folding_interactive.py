# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD
# Author: Ioan Dragomir (ioan.dragomir@analog.com)

import argparse
import sys
import time
import tkinter as tk
from threading import Thread
from tkinter import messagebox, ttk

import genalyzer as gn  # type: ignore
import libm2k  # type: ignore
import numpy as np  # type: ignore
import serial.tools.list_ports  # type: ignore
import workshop

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
    description="Interactive sinc folding demo: M2K generates noise, AD4080 records it."
)
parser.add_argument(
    "-m",
    "--m2k_uri",
    default=selected_devices["m2k_uri"],
    help="LibIIO context URI of the ADALM2000",
)
parser.add_argument(
    "-a",
    "--ad4080_uri",
    default=f"serial:{selected_devices['com_port']},230400",
    help="LibIIO context URI of the EVAL-AD4080ARDZ",
)

# AD4080 configuration
parser.add_argument(
    "-d",
    "--decimation",
    default="256",
    choices=[
        "2",
        "4",
        "8",
        "16",
        "32",
        "64",
        "128",
        "256",
        "512",
        "1024",
        "2048",
        "4096",
        "8192",
    ],
    help="AD4080 decimation ratio (default 256).",
)
parser.add_argument(
    "-f",
    "--filter-type",
    default="sinc1",
    choices=["sinc1", "sinc5", "sinc5+pf1"],
    help="AD4080 filter type (default sinc1).",
)

# Signal generation
parser.add_argument(
    "-w",
    "--noise-width",
    type=int,
    default=10000,
    help="Noise band width in Hz (default 10000).",
)
parser.add_argument(
    "-n",
    "--nsd",
    type=float,
    default=1000.0,
    help="Noise spectral density in ÂµV/âHz (default: 1000 = 1 mV/âHz). "
    "RMS = NSD \u00d7 \u221a(noise_width). M2K peak \u00b15 V is enforced automatically.",
)

args = vars(parser.parse_args())

m2k_uri = args["m2k_uri"]
ad4080_uri = args["ad4080_uri"]
decimation = int(args["decimation"])
print(
    f"ADALM2000: {m2k_uri}  AD4080: {ad4080_uri}  decimation={decimation}  filter={args['filter_type']}  noise_width={args['noise_width']}"
)

fs_pre = 40e6
fs_in = fs_pre / decimation
fs_out = 750000

# M2K analog output is Â±5 V peak (10 V p-p); do not exceed this.
M2K_PEAK_V = 5.0
_nsd = args["nsd"] * 1e-6  # muV/sqrtHz -> V/sqrtHz
# At startup, check if the NSD would exceed M2K limits with the default noise width.
# RMS = NSD \u00d7 \u221a(noise_width); peak \u2248 3\u00d7 RMS (3\u03c3 Gaussian)
_rms_at_default = _nsd * np.sqrt(args["noise_width"])
if _rms_at_default * 3 > M2K_PEAK_V:
    _max_nsd = M2K_PEAK_V / (3.0 * np.sqrt(args["noise_width"]))
    print(
        f"WARNING: NSD {_nsd:.2e} V/\u221aHz with width {args['noise_width']} Hz gives "
        f"RMS={_rms_at_default:.3f} V (peak \u2248{_rms_at_default*3:.2f} V), "
        f"exceeding M2K \u00b1{M2K_PEAK_V} V. Clamping NSD to {_max_nsd:.2e} V/\u221aHz."
    )
    _nsd = _max_nsd

# FFT parameters
window = gn.Window.BLACKMAN_HARRIS
nfft = 512  # Points per FFT
navg = 4  # Number of FFT averages
npts = navg * nfft  # Receive buffer size (max 16384)


class IIOThread(Thread):
    selected_center_frequency = fs_in + 5000
    selected_filter_type = args["filter_type"]
    selected_noise_width = args["noise_width"]
    selected_nsd = _nsd  # V/\u221aHz; RMS = nsd * sqrt(noise_width)
    _m2k_peak_v = M2K_PEAK_V
    filter_options = ["sinc1", "sinc5", "sinc5+pf1"]
    received_center_frequency = None
    data_in = np.zeros(npts)
    fft_db = np.zeros(nfft // 2 + 1)
    running = True
    status_msg = None
    last_status_time = time.time()

    def status(self, msg):
        now = time.time()
        delta = now - self.last_status_time
        self.last_status_time = now
        print(f"[{now: 8.3f}] (+{delta: 5.3f}) {msg}")
        self.status_msg = f"{msg} (+{delta: 5.3f})"

    def run(self):
        self.status("Initializing")

        print("Connecting to ADALM2000...")
        my_m2k = libm2k.m2kOpen(m2k_uri)
        if my_m2k is None:
            print(
                "Connection Error: No ADALM2000 device available/connected to your PC."
            )
            sys.exit(1)

        aout = my_m2k.getAnalogOut()
        aout.reset()
        my_m2k.calibrateDAC()
        aout.setSampleRate(0, fs_out)
        aout.enableChannel(0, True)
        aout.enableChannel(1, True)
        aout.setCyclic(True)

        print("Connecting to ADALM-MMSC...")
        my_ad4080 = adi.ad4080(args["ad4080_uri"])
        if my_ad4080 is None:
            print("Connection Error: No AD4080 device available/connected to your PC.")
            sys.exit(1)

        # Initialize ADC
        my_ad4080.rx_buffer_size = npts
        my_ad4080.filter_type = self.selected_filter_type
        my_ad4080.oversampling_ratio = decimation
        print(f"Filter: {my_ad4080.filter_type}  OSR: {my_ad4080.oversampling_ratio}")
        transmitting_center_frequency = None
        transmitting_filter_type = None
        transmitting_noise_width = None

        while self.running:
            if transmitting_filter_type != self.selected_filter_type:
                my_ad4080.filter_type = self.selected_filter_type
                transmitting_filter_type = self.selected_filter_type
                self.status(f"Filter set to {transmitting_filter_type}")

            if (
                transmitting_center_frequency != self.selected_center_frequency
                or transmitting_noise_width != self.selected_noise_width
            ):
                self.status(
                    f"Generating waveform at {self.selected_center_frequency} Hz, width={self.selected_noise_width} Hz"
                )
                waveform = workshop.generate_noise_band(
                    self.selected_center_frequency, self.selected_noise_width, fs_out
                )
                # generate_noise_band returns 1 V RMS normalised; scale by NSD \u00d7 \u221aBW
                amplitude = self.selected_nsd * np.sqrt(self.selected_noise_width)
                waveform *= amplitude
                peak_v = np.max(np.abs(waveform))
                self.status(
                    f"Pushing: NSD={self.selected_nsd:.2e} V/\u221aHz  RMS={np.std(waveform):.3f} V  peak={peak_v:.3f} V  (M2K limit \u00b1{M2K_PEAK_V} V)"
                )
                if peak_v > M2K_PEAK_V:
                    self.status(
                        f"WARNING: peak {peak_v:.3f} V exceeds M2K Â±{M2K_PEAK_V} V â output will clip!"
                    )
                aout.push([waveform, waveform * -1.0])
                transmitting_center_frequency = self.selected_center_frequency
                transmitting_noise_width = self.selected_noise_width

            self.status("Receiving")
            try:
                din_raw = my_ad4080.rx()
            except OSError as e:
                if e.errno == 138:  # timed out â serial link stalled, retry
                    self.status("rx() timeout, retrying...")
                    continue
                raise
            self.received_center_frequency = transmitting_center_frequency

            din = din_raw * my_ad4080.channel[0].scale / 1e3  # ÂµV/code â V
            din -= np.average(din)
            self.data_in = din

            fft_cplx = gn.rfft(
                din,
                navg,
                nfft,
                window,
                gn.CodeFormat.TWOS_COMPLEMENT,
                gn.RfftScale.NATIVE,
            )
            self.fft_db = gn.db(fft_cplx)

        print("IIO Thread finished")
        libm2k.contextClose(my_m2k)
        del my_ad4080


th = IIOThread()
th.start()

workshop.interactive_sinc_folding_ui(fs_in, npts, nfft, th)

th.running = False
th.join()
