import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
import time
""" This is the CN0566 directory and files created inside it. For now sdr pll and beamformer class are inside 
    3 different python files and CN0566 directory has it's own __init__.py file. Later merge them to single or change
    according to pyadi requirements."""

# Instantiate all the Devices
rpi_ip = "ip:phaser.local"  # IP address of the Raspberry Pi
sdr_ip = "ip:pluto.local" # "192.168.2.1"  # IP address of the Transreceiver Block

try:
    x = my_sdr.uri
    print("Pluto already connected")
except NameError:
    print("Pluto not connected...")
    from adi import ad9361
    my_sdr = ad9361(uri=sdr_ip)

time.sleep(0.5)

try:
    x = my_cn0566.uri
    print("cn0566 already connected")
except NameError:
    print("cn0566 not open...")
    from adi.cn0566 import CN0566
    my_cn0566 = CN0566(uri=rpi_ip, rx_dev=my_sdr)
    
    
""" Configure SDR parameters.
    Current freq plan is Sig Freq = 10.492 GHz, antenna element spacing = 0.015m, Freq of pll is 12/2 GHz
    this is mixed down using mixer to get 10.492 - 6 = 4.492GHz which is freq of sdr.
    This frequency plan can be updated any time in example code
    e.g:- my_cn0566.frequency = 9000000000 etc"""
# configure sdr/pluto according to above-mentioned freq plan
# my_sdr._ctrl.debug_attrs["adi,frequency-division-duplex-mode-enable"].value = "1"
# my_sdr._ctrl.debug_attrs["adi,ensm-enable-txnrx-control-enable"].value = "0"  # Disable pin control so spi can move the states
# my_sdr._ctrl.debug_attrs["initialize"].value = "1"
my_sdr.rx_enabled_channels = [0, 1]  # enable Rx1 (voltage0) and Rx2 (voltage1)
my_sdr.gain_control_mode_chan1 = 'manual'  # We must be in manual gain control mode (otherwise we won't see
my_sdr.rx_hardwaregain_chan1 = 20
my_sdr._rxadc.set_kernel_buffers_count(1) # Super important - don't want to have to flush stale buffers
rx = my_sdr._ctrl.find_channel('voltage0')
rx.attrs['quadrature_tracking_en'].value = '1'  # set to '1' to enable quadrature tracking
my_sdr.sample_rate = int(30000000)  # Sampling rate
my_sdr.rx_buffer_size = int(4 * 256)
my_sdr.rx_rf_bandwidth = int(10e6)
# We must be in manual gain control mode (otherwise we won't see the peaks and nulls!)
my_sdr.gain_control_mode_chan0 = 'manual'
my_sdr.gain_control_mode_chan1 = 'manual'
my_sdr.rx_hardwaregain_chan0 = 20
my_sdr.rx_hardwaregain_chan1 = 20



my_sdr.rx_lo = int(2.2e9)  # 4495000000  # Recieve Freq
my_sdr.tx_lo = int(2.2e9)

my_sdr.filter="LTE20_MHz.ftr"
rx_buffer_size = int(4 * 256)
my_sdr.rx_buffer_size = rx_buffer_size

my_sdr.tx_cyclic_buffer = True
my_sdr.tx_buffer_size = int(2**16)

my_sdr.tx_hardwaregain_chan0 = int(-6) # this is a negative number between 0 and -88
my_sdr.tx_hardwaregain_chan1 = int(-6) # Make sure the Tx channels are attenuated (or off) and their freq is far away from Rx

#my_sdr.dds_enabled = [1, 1, 1, 1] #DDS generator enable state
#my_sdr.dds_frequencies = [0.1e6, 0.1e6, 0.1e6, 0.1e6] #Frequencies of DDSs in Hz
#my_sdr.dds_scales = [1, 1, 0, 0] #Scale of DDS signal generators Ranges [0,1]
my_sdr.dds_single_tone(int(2e6), 0.9, 1) # sdr.dds_single_tone(tone_freq_hz, tone_scale_0to1, tx_channel)

""" Configure CN0566 parameters.
    ADF4159 and ADAR1000 array attributes are exposed directly, although normally
    accessed through other methods."""

# By default device_mode is "rx"
my_cn0566.configure(device_mode="rx")  # Configure adar in mentioned mode and also sets gain of all channel to 127

# HB100 measured frequency - 10492000000


# my_cn0566.SignalFreq = 10600000000 # Make this automatic in the future.
my_cn0566.SignalFreq = 10.497e9


# my_cn0566.frequency = (10492000000 + 2000000000) // 4 #6247500000//2



# Onboard source w/ external Vivaldi
my_cn0566.frequency = (int(my_cn0566.SignalFreq) + my_sdr.rx_lo) // 4




my_cn0566.freq_dev_step = 5690
my_cn0566.freq_dev_range = 0
my_cn0566.freq_dev_time = 0
my_cn0566.powerdown = 0
my_cn0566.ramp_mode = "disabled"


""" If you want to use previously calibrated values load_gain and load_phase values by passing path of previously
    stored values. If this is not done system will be working as uncalibrated system."""
my_cn0566.load_gain_cal('gain_cal_val.pkl')
my_cn0566.load_phase_cal('phase_cal_val.pkl')

""" This can be useful in Array size vs beam width experiment or beamtappering experiment. 
    Set the gain of outer channels to 0 and beam width will increase and so on."""
#my_beamformer.set_chan_gain(3, 120)  # set gain of Individual channel
#my_beamformer.set_all_gain(120)  # Set all gain to mentioned value, if not, set to 127 i.e. max gain

""" To set gain of all channels with different values."""

#gain_list = [127, 125, 122, 125, 119, 119, 121, 121]
gain_list = [127, 127, 127, 127, 127, 127, 127, 127]
for i in range(0, len(gain_list)):
    my_cn0566.set_chan_gain(i, gain_list[i])



""" Averages decide number of time samples are taken to plot and/or calibrate system. By default it is 1."""
my_cn0566.Averages = 8

""" This instantiate calibration routine and perform gain and phase calibration. Note gain calibration should be always
    done 1st as phase calibration depends on gain cal values if not it throws error"""
# print("Calibrating Gain...")
# my_cn0566.gain_calibration()   # Start Gain Calibration
# print("Calibrating Phase...")
# my_cn0566.phase_calibration()  # Start Phase Calibration
# print("Done calibration")

""" This can be used to change the angle of center lobe i.e if we want to concentrate main lobe/beam at 45 degress"""
# my_beamformer.set_beam_angle(45)

#my_cn0566.gcal = [127, 127, 127, 127, 127, 127, 127, 127]
#my_cn0566.gcal = [127, 121, 117, 119, 111, 115, 119, 119]


#my_cn0566.gcal = [100, 100, 100, 100, 100, 100, 100, 100]
#my_cn0566.gcal = [127, 126, 126, 126, 87, 89, 89, 92] # Cal values after some messing around w/ hardware

#my_cn0566.gcal = [100, 100, 100, 100, 0, 0, 0, 0] # This half looks okay...
#my_cn0566.gcal = [0, 0, 0, 100, 100, 0, 0, 0]
#my_cn0566.gcal = [0, 100, 100, 0, 0, 00, 00, 00] # This half looks a little off...

# for i in range(0, len(my_cn0566.gcal)):
#     my_cn0566.set_chan_gain(i, my_cn0566.gcal[i])

# asn = 0.0
# my_cn0566.pcal = [0, asn, 2.0*asn, 3.0*asn, 4.0*asn, 5.0*asn, 6.0*asn, 7.0*asn]

#my_cn0566.pcal =  [0, -25.3125, -61.875, -101.25, -137.8125, -146.25, -132.1875, -120.9375]

#my_cn0566.pcal = [0, -19.6875, 126.5625, 95.625, 56.25, 47.8125, 70.3125, 84.375]
    
for i in range(0, 8):
    #my_cn0566.set_chan_phase(i, my_cn0566.pcal[i])
    my_cn0566.set_chan_phase(i, 0.0)

#my_cn0566.phase_step_size = 2.8125

do_plot = True
while do_plot == True:
    start=time.time()
    my_cn0566.set_beam_phase_diff(0.0)
    time.sleep(0.25)
    data = my_sdr.rx()
    data = my_sdr.rx()
    ch0 = data[0]
    ch1 = data[1]
    f, Pxx_den0 = signal.periodogram(ch0[1:-1], 30000000, 'blackman', scaling='spectrum')
    f, Pxx_den1 = signal.periodogram(ch1[1:-1], 30000000, 'blackman', scaling='spectrum')
    
    plt.figure(1)
    plt.clf()
    plt.plot(np.real(ch0), color='red')
    plt.plot(np.imag(ch0), color='blue')
    plt.plot(np.real(ch1), color='green')
    plt.plot(np.imag(ch1), color='black')
    np.real
    plt.xlabel("data point")
    plt.ylabel("output code")
    plt.draw()
    
    plt.figure(2)
    plt.clf()
    plt.semilogy(f, Pxx_den0)
    plt.semilogy(f, Pxx_den1)
    plt.ylim([1e-5, 1e6])
    plt.xlabel("frequency [Hz]")
    plt.ylabel("PSD [V**2/Hz]")
    plt.draw()
    
    """ Plot the output based on experiment that you are performing"""
    print("Plotting...")
    
    
    
    plt.figure(3)
    plt.ion()
#    plt.show()
    gain, angle, delta, diff_error, beam_phase, xf, max_gain, PhaseValues = my_cn0566.calculate_plot()
    print("Sweeping took this many seconds: " + str(time.time()-start))
#    gain,  = my_cn0566.plot(plot_type="monopulse")
    plt.clf()
    plt.scatter(angle, gain, s=10)
    plt.scatter(angle, delta, s=10)
    plt.show()
    
    
    plt.pause(0.05)
    time.sleep(0.05)
    print("Total took this many seconds: " + str(time.time()-start))
