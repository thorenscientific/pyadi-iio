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

import sys
import tkinter as tk
from tkinter import ttk

import matplotlib.pyplot as plt  # type: ignore
import numpy as np  # type: ignore
import serial.tools.list_ports  # type: ignore
from matplotlib.widgets import Button, TextBox  # type: ignore

from adi import ad4080  # type: ignore


def scan_com_ports():
    """Scan for available COM ports without opening them"""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in sorted(ports)]


class PortSelectionDialog:
    def __init__(self):
        self.result = None
        self.root = tk.Tk()
        self.root.title("Select AD4080 COM Port")
        self.root.geometry("350x150")

        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill="both", expand=True)

        # COM Port selection
        ttk.Label(main_frame, text="AD4080 COM Port:", font=("", 10)).grid(
            row=0, column=0, sticky="w", padx=5, pady=10
        )

        # Scan for available COM ports
        available_ports = scan_com_ports()

        if available_ports:
            self.com_port = tk.StringVar(
                value="COM12" if "COM12" in available_ports else available_ports[0]
            )
            ttk.Combobox(
                main_frame,
                textvariable=self.com_port,
                values=available_ports,
                width=20,
                state="readonly",
            ).grid(row=0, column=1, sticky="w", padx=5)
        else:
            self.com_port = tk.StringVar(value="COM12")
            ttk.Entry(main_frame, textvariable=self.com_port, width=22).grid(
                row=0, column=1, sticky="w", padx=5
            )

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, columnspan=2, pady=20)

        ttk.Button(button_frame, text="Connect", command=self.on_ok, width=12).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Cancel", command=self.on_cancel, width=12).pack(
            side="left", padx=5
        )

    def on_ok(self):
        self.result = self.com_port.get()
        self.root.quit()
        self.root.destroy()

    def on_cancel(self):
        self.root.quit()
        self.root.destroy()

    def show(self):
        self.root.mainloop()
        return self.result


# Show port selection dialog
port_dialog = PortSelectionDialog()
selected_port = port_dialog.show()

if selected_port is None:
    print("Connection cancelled by user")
    sys.exit(0)

my_uri = f"serial:{selected_port},230400"
input_frequency = 100000  # Default input frequency in Hz (100 kHz)

print("AD4080 uri: " + str(my_uri))

my_adc = ad4080(uri=my_uri, device_name="ad4080")

print("Sampling frequency from IIO Context: ", my_adc.sampling_frequency)

# Configure AD4080 for accurate measurement
print("Oversampling ratio: ", my_adc.oversampling_ratio)
print("Filter type: ", my_adc.filter_type)
print(f"Expected output sample rate: {my_adc.sampling_frequency} Hz\n")

# Set default frequency - user can change via GUI text box
print(f"Default input frequency: {input_frequency/1000:.1f} kHz\n")

# Fixed buffer size set to maximum
buffer_size = 16384
print(f"Buffer size: {buffer_size} samples (maximum)")
print(f"Frequency resolution: {my_adc.sampling_frequency / buffer_size:.2f} Hz/bin\n")

my_adc.rx_buffer_size = buffer_size
data = my_adc.rx()

# Create figure with more vertical spacing
fig = plt.figure(figsize=(12, 8))
gs = fig.add_gridspec(4, 4, height_ratios=[3, 3, 0.4, 0.4], hspace=0.6)

ax1 = fig.add_subplot(gs[0, :])
ax2 = fig.add_subplot(gs[1, :])

# Set-up time domain plot
ax1.set_title("Time Domain")
# Add margin around min/max for better visibility
margin = (max(data) - min(data)) * 0.2
ax1.set_ylim([min(data) - margin, max(data) + margin])  # type: ignore
(line1,) = ax1.plot(data, label="time domain")
ax1.set_xlabel("Sample")
ax1.set_ylabel("ADC Code")
ax1.grid(True)
ax1.legend()

# Set-up transmittance plot
ax2.set_title("FFT, calculated Fs = ")

(line2,) = ax2.plot(data[: len(data) // 2], label="freq. domain")
ax2.set_xlabel("Frequency Bin")
ax2.set_ylabel("Magnitude (dB)")
ax2.legend()

# Create label for frequency input
ax_freq_label = fig.add_subplot(gs[2, 0])
ax_freq_label.text(
    0.0, 0.5, "Input Frequency (kHz):", va="center", ha="left", fontsize=10
)
ax_freq_label.axis("off")

# Create frequency input text box (moved to the right)
ax_freq = fig.add_subplot(gs[2, 1])
freq_textbox = TextBox(
    ax_freq, "", initial=str(input_frequency / 1000), textalignment="left"
)
# Move text box slightly closer to the label
pos = ax_freq.get_position()
ax_freq.set_position([pos.x0 - 0.06, pos.y0, pos.width, pos.height])

# Create control buttons
ax_start = fig.add_subplot(gs[3, 0:2])
ax_stop = fig.add_subplot(gs[3, 2])
ax_single = fig.add_subplot(gs[3, 3])

btn_start = Button(ax_start, "Start", color="lightgreen", hovercolor="green")
btn_stop = Button(ax_stop, "Stop", color="salmon", hovercolor="red")
btn_single = Button(ax_single, "Single Shot", color="lightblue", hovercolor="blue")

# Adjust button positions to move them higher
for ax_btn in [ax_start, ax_stop, ax_single]:
    pos = ax_btn.get_position()
    ax_btn.set_position([pos.x0, pos.y0 + 0.05, pos.width, pos.height])

# Control state
class AcquisitionState:
    def __init__(self):
        self.running = False
        self.single_shot = False


state = AcquisitionState()

# Frequency update callback with input sanitization
def update_frequency(text):
    global input_frequency
    try:
        # Convert kHz input to Hz, handling decimal inputs
        new_freq_khz = float(text)
        new_freq = int(new_freq_khz * 1000)

        # Validate reasonable frequency range
        if new_freq <= 0:
            print("\\n[Error: Frequency must be positive]")
            freq_textbox.set_val(
                str(input_frequency / 1000)
            )  # Reset to previous valid value
        elif new_freq < 1000:  # Less than 1 kHz
            print(
                f"\\n[Warning: Frequency very low ({new_freq_khz:.1f} kHz). Proceed with caution.]"
            )
            input_frequency = new_freq
            print(f"[Updated input frequency to {new_freq_khz:.1f} kHz]")
        elif new_freq > my_adc.sampling_frequency / 2:  # Above Nyquist
            print(
                f"\\n[Error: Frequency ({new_freq_khz:.1f} kHz) exceeds Nyquist limit ({my_adc.sampling_frequency/2000:.1f} kHz)]"
            )
            print("[Frequency should be less than half the sample rate]")
            freq_textbox.set_val(
                str(input_frequency / 1000)
            )  # Reset to previous valid value
        else:
            input_frequency = new_freq
            print(f"\\n[Updated input frequency to {new_freq_khz:.1f} kHz]")
    except ValueError:
        print(f"\n[Error: Invalid input '{text}' - please enter a number]")
        freq_textbox.set_val(
            str(input_frequency / 1000)
        )  # Reset to previous valid value
    except Exception as e:
        print(f"\n[Error: {e}]")
        freq_textbox.set_val(
            str(input_frequency / 1000)
        )  # Reset to previous valid value


freq_textbox.on_submit(update_frequency)

# Button callbacks
def start_acquisition(event):
    state.running = True
    state.single_shot = False
    print("\n[Started continuous acquisition]")


def stop_acquisition(event):
    state.running = False
    state.single_shot = False
    print("\n[Stopped acquisition]")


def single_shot_acquisition(event):
    state.single_shot = True
    state.running = False
    print("\n[Single shot acquisition]")


btn_start.on_clicked(start_acquisition)
btn_stop.on_clicked(stop_acquisition)
btn_single.on_clicked(single_shot_acquisition)


while True:
    # Only acquire data if running or single shot requested
    if state.running or state.single_shot:
        try:
            # Collect data
            data = my_adc.rx()

            # Update Y-axis limits with margin
            margin = (max(data) - min(data)) * 0.2
            ax1.set_ylim([min(data) - margin, max(data) + margin])  # type: ignore
            line1.set_ydata(data)

            windowed_data = (data - np.average(data)) * np.blackman(len(data))
            magnitude_spectrum = (
                20
                * np.log10(np.abs(np.fft.fft(windowed_data) / len(windowed_data)))[
                    : len(windowed_data) // 2
                ]
            )

            peak_bin = np.argmax(magnitude_spectrum)
            calculated_fs = input_frequency * len(data) / peak_bin
            calculated_fs = int(
                np.around(calculated_fs / 10, decimals=0) * 10
            )  # Round to nearest 10 Hz

            # Calculate error vs expected
            error_percent = (
                (calculated_fs - my_adc.sampling_frequency) / my_adc.sampling_frequency
            ) * 100

            print(f"Peak found in bin {peak_bin} out of {len(data)//2}")
            print(f"Calculated sample rate: {calculated_fs} Hz")
            print(f"Expected sample rate:   {my_adc.sampling_frequency} Hz")
            print(f"Error: {error_percent:+.2f}%\n")

            ax2.set_ylim([min(magnitude_spectrum) * 1.1, max(magnitude_spectrum) * 1.1])  # type: ignore
            line2.set_ydata(magnitude_spectrum)
            ax2.set_title("FFT, calculated Fs = %i" % calculated_fs)

            # Reset single shot flag
            if state.single_shot:
                state.single_shot = False
                print("[Single shot complete - stopped]")

        except Exception as e:
            print(f"Error during acquisition: {e}")
            state.running = False
            state.single_shot = False

    plt.pause(0.1)

    # Exit loop and close context
    if not plt.fignum_exists(fig.number):  # type: ignore
        del my_adc
        sys.exit()
