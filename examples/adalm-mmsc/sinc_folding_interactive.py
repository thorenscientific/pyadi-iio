# Copyright (C) 2025 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD
# Author: Ioan Dragomir (ioan.dragomir@analog.com)

import genalyzer as gn
from threading import Thread
import libm2k
import adi
import numpy as np
import workshop
import argparse
import time

parser = argparse.ArgumentParser(
    description='Generate a band of noise (whose frequency is adjustable by a GUI slider) on the M2K, record it using the AD4080ARDZ, comparing it to the theoretical sinc1 response, taking into account frequency folding.')
# parser.add_argument('-m', '--m2k_uri', default='ip:m2k.local',
parser.add_argument('-m', '--m2k_uri', default='ip:m2k.local',
    help='LibIIO context URI of the ADALM2000')
#parser.add_argument('-a', '--ad4080_uri', default='serial:/dev/ttyACM0,230400,8n1',
parser.add_argument('-a', '--ad4080_uri', default='serial:COM51,230400',
    help='LibIIO context URI of the VAL-AD4080ARDZ')
parser.add_argument('-d', '--decimation', default='256',
    choices=[2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 1024],
    help='AD4080 digital filter (sinc1) decimation.')
args = vars(parser.parse_args())

# 0. Configuration
m2k_uri = args['m2k_uri']
ad4080_uri = args['ad4080_uri']
decimation = int(args['decimation'])

print("ADALM2000 URI: ", m2k_uri)
print("Decimation: ", decimation)
print("AD4880 URI: ", ad4080_uri)

      

fs_pre = 40e6                # Pre-digital filter sample rate, AD4080ARDZ fixed at 40Msps
fs_in  = fs_pre / decimation # Actual data rate we receive after AD4080 filtering
fs_out = 750000              # Generated waveform sample rate (up to 75 Msps)

# FFT parameters
window = gn.Window.BLACKMAN_HARRIS  # FFT window
nfft = 512          # no. of points per FFT
navg = 4            # No. of fft averages
npts = navg * nfft  # Receive buffer size - maximum for this board is 16384

class IIOThread(Thread):
    # Variables used for inter-thread communication
    selected_center_frequency = fs_in + 5000       # Frequency set by slider
    received_center_frequency = None               # Frequency for the currently displayed waveform (will lag behind the slider by up to 2 iterations

    data_in = np.zeros(npts)         # Properly scaled waveform, sent from iio_thread to the GUI
    fft_db = np.zeros(nfft // 2 + 1) # FFT of data_in, sent from iio_thread to the GUI

    running = True # Set to False to stop the iio thread

    status_msg = None
    last_status_time = time.time()

    def status(self, msg):
        now = time.time()
        delta = now - self.last_status_time
        self.last_status_time = now
        print(f'[{now: 8.3f}] (+{delta: 5.3f}) {msg}')
        self.status_msg = f'{msg} (+{delta: 5.3f})'

    def run(self):        
        self.status('Initializing')
        
        # Connect to M2K and AD4080 and initialize them
        print("Connecting to ADALM2000...")
        my_m2k = libm2k.m2kOpen(m2k_uri)# (args['m2k_uri'])
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
        print("Connecting to ADALM-MMSC...")
        my_ad4080 = adi.ad4080(args['ad4080_uri'])
        if my_ad4080 is None:
            print("Connection Error: No AD4080 device available/connected to your PC.")
            exit(1)

        # Initialize ADC
        my_ad4080.rx_buffer_size = npts
        print(f'Sampling frequency: {my_ad4080.sampling_frequency}')
#        print(f'Available sampling frequencies: {my_ad4080.sampling_frequency_available}')
#        assert my_ad4080.sampling_frequency == fs_pre # Check 40Msps assumption

        my_ad4080.filter_type = 'sinc1'
        print("Verifying filter: ", my_ad4080.filter_type)
        my_ad4080.oversampling_ratio = decimation
        print("Verifying oversampling ratio: ", my_ad4080.oversampling_ratio)
        

        transmitting_center_frequency = None # Frequency that is being transmitted by the m2k. Will lag behind the slider frequency

        while self.running:
            # If running for the first time or after a slider change, regenerate waveform
            if transmitting_center_frequency != self.selected_center_frequency:
                # Generate waveform
                self.status(f"Generating new waveform with center frequency = {self.selected_center_frequency} Hz")
                waveform = workshop.generate_noise_band(self.selected_center_frequency, 10000, fs_out)
                print(waveform)
                print("Length of waveform: ", len(waveform))

                print(f"RMS of transmitted signal: {np.std(waveform):.3f} V")

                # Send it to the m2k
                aout.push([waveform])

                transmitting_center_frequency = self.selected_center_frequency

            # Receive one buffer from the AD4080 and process it
            self.status("Receiving")
            din_raw = my_ad4080.rx()
            self.received_center_frequency = transmitting_center_frequency

            # Scale to Volts
            scale = my_ad4080.channel[0].scale
            print("Scale: ", scale)
            print("max before scaling: ", np.max(din_raw))
            din = din_raw * scale / 1e3 # scale is in uV
            print("max after scaling: ", np.max(din))

            # Remove DC component
            din -= np.average(din)

            print(f"RMS of received signal: {np.std(din):.5f} V")

            # Send processed data to the UI thread
            self.data_in = din

            # Compute FFT
            code_fmt = gn.CodeFormat.TWOS_COMPLEMENT
            rfft_scale = gn.RfftScale.NATIVE
#            fft_cplx = gn.rfft(np.array(din), navg, nfft, window, code_fmt, rfft_scale)
            fft_cplx = gn.rfft((din), navg, nfft, window, code_fmt, rfft_scale)
            self.fft_db = gn.db(fft_cplx) # FIXME: White noise offset depending on nfft

            print(f'{np.max(self.fft_db)=}') 
        
        print('IIO Thread finished')

th = IIOThread()
th.start()

# Hiding the UI implementation in workshop.py to keep this script clean
workshop.interactive_sinc_folding_ui(fs_in, npts, nfft, th)

# Stop iio thread as well
th.running = False
th.join()
