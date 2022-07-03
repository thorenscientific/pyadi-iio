# Copyright (C) 2021 Analog Devices, Inc.
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

import adi


class CN0575:
    """ CN0575 class, exposing onboard temperature sensor, pushbutton,
    and LED. Also reads the platform CPU's temperature, which under
    most operating conditions should be higher than the onboard sensor.
    """

    def __init__(
        self, uri=None, verbose=False,
    ):

        self.gpios = adi.one_bit_adc_dac(uri)
        self.lm75 = adi.lm75(uri)
        self.cpu_thermal = adi.cpu_thermal(uri)
        self.gpios.gpio_ext_led = 0  # turn off LED
        self.gpios.gpio_ext_btn  # dummy read

    @property
    def button(self):
        """Read button state."""
        return self.gpios.gpio_ext_btn

    @property
    def led(self):
        """Read LED state."""
        return self.gpios.gpio_ext_led

    @led.setter
    def led(self, value):
        """Set LED state"""
        self.gpios.gpio_ext_led = value

    @property
    def onboard_adt75(self):
        """Read onboard ADT75 temperature."""
        return self.lm75.to_degrees(self.lm75.input)

    @property
    def rpi_cpu_temp(self):
        """Read CPU temperature state."""
        return self.cpu_thermal.to_degrees(self.cpu_thermal.input)
