# Copyright (C) 2022-2024 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

import sys
import libm2k
from sine_gen import *
from time import sleep

from scipy import signal

import matplotlib.pyplot as plt
import numpy as np
from adi import ad4080

# Optionally pass URI as command line argument,
# else use default ip:analog.local
my_uri = sys.argv[1] if len(sys.argv) >= 2 else "ip:analog.local"

my_uri = "serial:COM6,230400,8n1n"

print("uri: " + str(my_uri))

my_adc = ad4080(uri=my_uri, device_name="ad4080")

# Fix this later - appears there's some things in flux...
# print("Sampling frequency: ", my_adc.sampling_frequency)

sampling_frequency = 40000000.0 # hack for now

print("sinc_dec_rate_available: ", my_adc.sinc_dec_rate_available)
print("filter_sel_available: ", my_adc.filter_sel_available)

print("Setting filter to SINC5, decimation 128")
my_adc.sinc_dec_rate = 128
# my_adc.filter_sel = "sinc5_plus_compensation"
my_adc.filter_sel = "sinc5"
print("Verifying...")
print("sinc_dec_rate: ", my_adc.sinc_dec_rate)
print("filter_sel: ", my_adc.filter_sel)



print("Scale: ", my_adc.scale)

print(dir(my_adc))

plt.figure(1)
plt.clf()
# Collect data
data = my_adc.rx()



plt.plot(range(0, len(data)), data, label="channel0")
plt.xlabel("Data Point")
plt.ylabel("ADC counts")
plt.legend(
    bbox_to_anchor=(0.0, 1.02, 1.0, 0.102),
    loc="lower left",
    ncol=4,
    mode="expand",
    borderaxespad=0.0,
)

plt.show()


# Set up m2k

ctx=libm2k.m2kOpen()
ctx.calibrateADC()
ctx.calibrateDAC()

siggen=ctx.getAnalogOut()


fs = []
amps = []
vref = 5.0

for f in range(10000, 1000000, 20000): # Sweep 3kHz to 300kHz in 1kHz steps

    #call buffer generator, returns sample rate and buffer
    samp0,buffer0 = sine_buffer_generator(0,f,0.5,1.5,180)
    samp1,buffer1 = sine_buffer_generator(1,f,0.5,1.5,0)
    
    siggen.enableChannel(0, True)
    siggen.enableChannel(1, True)
    
    siggen.setSampleRate(0, samp0)
    siggen.setSampleRate(1, samp1)
    
    siggen.push([buffer0,buffer1])
    
    sleep(0.25)
    
    #print("Sample Rate: ", my_adc.sampling_frequency)
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
    


amps_db = 20*np.log10(amps/np.sqrt(4.0)) # 4V is p-p amplitude

plt.figure(2)
plt.clf()
plt.title("AD4020 Time Domain Data")
plt.plot(x, voltage)
plt.xlabel("Data Point")
plt.ylabel("Voltage (V)")
plt.show()

f, Pxx_spec = signal.periodogram(
    ac, 40000000.0, window="flattop", scaling="spectrum"
)
Pxx_abs = np.sqrt(Pxx_spec)

plt.figure(3)
plt.clf()
plt.title("AD4020 Spectrum (Volts absolute)")
plt.semilogy(f, Pxx_abs)
plt.ylim([1e-6, 4])
plt.xlabel("frequency [Hz]")
plt.ylabel("Voltage (V)")
plt.draw()
plt.pause(0.05)

plt.figure(4)
plt.title("input filter freq. response")
plt.semilogx(fs, amps_db, linestyle="dashed", marker="o", ms=2)
#plt.ylim([1e-6, 4])
plt.xlabel("frequency [Hz]")
plt.ylabel("response (dB)")
plt.draw()

siggen.stop()
libm2k.contextClose(ctx)
del my_adc 
