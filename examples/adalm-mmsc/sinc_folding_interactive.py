# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD
# Author: Ioan Dragomir (ioan.dragomir@analog.com)

import argparse
import sys
import time
from threading import Thread

import genalyzer as gn # type: ignore
import libm2k # type: ignore
import numpy as np # type: ignore
import workshop

import adi # type: ignore

parser = argparse.ArgumentParser(
    description="Interactive sinc folding demo: M2K generates noise, AD4080 records it."
)
parser.add_argument("-m", "--m2k_uri",    default="ip:192.168.2.1",     help="LibIIO context URI of the ADALM2000")
parser.add_argument("-a", "--ad4080_uri", default="serial:COM13,230400", help="LibIIO context URI of the EVAL-AD4080ARDZ")
parser.add_argument("-d", "--decimation", default="256",
    choices=["2","4","8","16","32","64","128","256","512","1024","2048","4096","8192"],
    help="AD4080 decimation ratio (default 256).")
parser.add_argument("-f", "--filter-type", default="sinc1",
    choices=["sinc1", "sinc5", "sinc5+pf1"],
    help="AD4080 filter type (default sinc1).")
parser.add_argument("-w", "--noise-width", type=int, default=10000,
    help="Noise band width in Hz (default 10000).")
args = vars(parser.parse_args())

m2k_uri    = args["m2k_uri"]
ad4080_uri = args["ad4080_uri"]
decimation = int(args["decimation"])
print(f"ADALM2000: {m2k_uri}  AD4080: {ad4080_uri}  decimation={decimation}  filter={args['filter_type']}  noise_width={args['noise_width']}")


fs_pre = 40e6  # Pre-digital filter sample rate, AD4080ARDZ fixed at 40Msps
fs_in = fs_pre / decimation  # Actual data rate we receive after AD4080 filtering
fs_out = 750000  # Generated waveform sample rate (up to 75 Msps)

# FFT parameters
window = gn.Window.BLACKMAN_HARRIS  # FFT window
nfft = 512  # no. of points per FFT
navg = 4  # No. of fft averages
npts = navg * nfft  # Receive buffer size - maximum for this board is 16384


class IIOThread(Thread):
    selected_center_frequency = fs_in + 5000
    selected_filter_type      = args["filter_type"]
    selected_noise_width      = args["noise_width"]
    filter_options            = ["sinc1", "sinc5", "sinc5+pf1"]
    received_center_frequency = None
    data_in                   = np.zeros(npts)
    fft_db                    = np.zeros(nfft // 2 + 1)
    running                   = True
    status_msg                = None
    last_status_time          = time.time()

    def status(self, msg):
        now = time.time()
        delta = now - self.last_status_time
        self.last_status_time = now
        print(f"[{now: 8.3f}] (+{delta: 5.3f}) {msg}")
        self.status_msg = f"{msg} (+{delta: 5.3f})"

    def run(self):
        self.status("Initializing")

        # Connect to M2K and AD4080 and initialize them
        print("Connecting to ADALM2000...")
        my_m2k = libm2k.m2kOpen(m2k_uri)
        if my_m2k is None:
            print(
                "Connection Error: No ADALM2000 device available/connected to your PC."
            )
            sys.exit(1)
        # Initialize DAC channel 0
        aout = my_m2k.getAnalogOut()
        aout.reset()
        my_m2k.calibrateDAC()
        aout.setSampleRate(0, fs_out)
        aout.enableChannel(0, True)
        aout.enableChannel(1, True)
        aout.setCyclic(True)  # Send buffer repeatedly, not just once

        # Connect to AD4080
        print("Connecting to ADALM-MMSC...")
        my_ad4080 = adi.ad4080(args["ad4080_uri"])
        if my_ad4080 is None:
            print("Connection Error: No AD4080 device available/connected to your PC.")
            sys.exit(1)

        # Initialize ADC
        my_ad4080.rx_buffer_size     = npts
        my_ad4080.filter_type        = self.selected_filter_type
        my_ad4080.oversampling_ratio = decimation
        print(f"Filter: {my_ad4080.filter_type}  OSR: {my_ad4080.oversampling_ratio}")

        transmitting_center_frequency = None
        transmitting_filter_type      = None
        transmitting_noise_width      = None

        while self.running:
            if transmitting_filter_type != self.selected_filter_type:
                my_ad4080.filter_type    = self.selected_filter_type
                transmitting_filter_type = self.selected_filter_type
                self.status(f"Filter set to {transmitting_filter_type}")

            if (transmitting_center_frequency != self.selected_center_frequency
                    or transmitting_noise_width != self.selected_noise_width):
                self.status(f"Generating waveform at {self.selected_center_frequency} Hz, width={self.selected_noise_width} Hz")
                waveform = workshop.generate_noise_band(
                    self.selected_center_frequency, self.selected_noise_width, fs_out
                )
                aout.push([waveform, waveform * -1.0])
                transmitting_center_frequency = self.selected_center_frequency
                transmitting_noise_width      = self.selected_noise_width

            self.status("Receiving")
            try:
                din_raw = my_ad4080.rx()
            except OSError as e:
                if e.errno == 138:  # timed out — serial link stalled, retry
                    self.status("rx() timeout, retrying...")
                    continue
                raise
            self.received_center_frequency = transmitting_center_frequency

            din  = din_raw * my_ad4080.channel[0].scale / 1e3  # µV/code → V
            din -= np.average(din)
            self.data_in = din

            fft_cplx = gn.rfft(din, navg, nfft, window,
                                gn.CodeFormat.TWOS_COMPLEMENT, gn.RfftScale.NATIVE)
            self.fft_db = gn.db(fft_cplx)

        print("IIO Thread finished")
        libm2k.contextClose(my_m2k)
        del my_ad4080


th = IIOThread()
th.start()

# Hiding the UI implementation in workshop.py to keep this script clean
workshop.interactive_sinc_folding_ui(fs_in, npts, nfft, th)

# Stop iio thread as well
th.running = False
th.join()
