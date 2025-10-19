# Copyright (C) 2019-2026 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

from decimal import Decimal

import numpy as np

from adi.attribute import attribute
from adi.context_manager import context_manager
from adi.rx_tx import rx


class ad7124(rx, context_manager):
    """ AD7124 4/8 -Channel, Low Noise, Low Power, 24-Bit, Sigma-Delta ADC with PGA and Reference

    Analog input configuration (single-ended, differential, unipolar, bipolar) is set in
    the device tree. This class scans all channels and creates both:
        * a channel[] list attribute
        * individual channel attributes, for example:
            * my_ad7124.temp (temperature sensor)
            * my_ad7124.voltage0_voltage1 (differential input between inputs 0 and 1)

    The ad7124.enable_single_cycle device attribute defaults to 'Y', and ensures that when
    a single channel is enabled, output data is fully settled; intermediate, unsettled outputs
    from the digital filter are ignored. Setting to 'N' includes these unsettled samples,
    increasing the output data rate accordignly.

    Each channel has the following sub-attributes:
        voltageX_voltageY.raw:              Raw 12-bit ADC code. read only for ADC channels
        voltageX_voltageY.scale:            ADC scale, millivolts per lsb
        voltageX_voltageY.scale_available:  Available scales, corresponding to Vref*1, Vref*2
        voltageX_voltageY():                Returns ADC reading in millivolts (read only)

        voltageX_voltageY.filter_type_available: List available filter types
        voltageX_voltageY.filter_type:           set / get filter type
        voltageX_voltageY.sampling_frequency:  set / get sampling frequency.
                                               Available values are dependent on filter type,
                                               and overall sample rate dependent on all other
                                               channels.
        voltageX_voltageY.scale_available: List available scales
        voltageX_voltageY.scale:           set / get scale
        voltageX_voltageY.

    The temperature channel is the same, with these exceptions:
        temp.scale:                    Does not have a setter
        temp.scale_available           Does not apply (raises error)
        temp():                        Returns temperature in degrees Celsius\n

    """

    _complex_data = False
    channel = []  # type: ignore
    _device_name = ""

    def __repr__(self):
        retstr = f"""
ad5592r(uri="{self.uri}, device_name={self._device_name})"

{self.__doc__}
"""
        return retstr

    def __init__(self, uri="", device_index=0):

        context_manager.__init__(self, uri, self._device_name)

        compatible_parts = ["ad7124-8", "ad7124-4"]

        self._ctrl = None
        index = 0

        # Selecting the device_index-th device from the 7124 family as working device.
        for device in self._ctx.devices:
            if device.name in compatible_parts:
                if index == device_index:
                    self._ctrl = device
                    self._rxadc = device
                    break
                else:
                    index += 1

        self._rx_channel_names = [chan.id for chan in self._ctrl.channels]

        for name in self._rx_channel_names:
            if name == "temp":
                self.channel.append(self._temp_channel(self._ctrl, name))
                setattr(
                    self, name.replace("-", "_"), self._temp_channel(self._ctrl, name)
                )
            else:
                self.channel.append(self._channel(self._ctrl, name))
                setattr(self, name.replace("-", "_"), self._channel(self._ctrl, name))
        rx.__init__(self)

    @property
    def enable_single_cycle(self):
        """Sets single cycle mode (no latency, even with only one channel enabled)"""
        return self._get_iio_debug_attr_str("enable_single_cycle", self._ctrl)

    @enable_single_cycle.setter
    def enable_single_cycle(self, value):
        self._set_iio_debug_attr_str("enable_single_cycle", value, self._ctrl)

    class _channel(attribute):
        """AD7124 channel"""

        def __init__(self, ctrl, channel_name):
            self.name = channel_name
            self._ctrl = ctrl

        @property
        def raw(self):
            """AD7124 channel raw value"""
            return self._get_iio_attr(self.name, "raw", False)

        @property
        def filter_type_available(self):
            """Provides all available filter types for the selected channel"""
            return self._get_iio_attr_str(self.name, "filter_type_available", False)

        @property
        def filter_type(self):
            """AD7124 channel filter type"""
            return self._get_iio_attr_str(self.name, "filter_type", False)

        @filter_type.setter
        def filter_type(self, ftype):
            """Set filter type."""
            if ftype in self.filter_type_available:
                self._set_iio_attr(self.name, "filter_type", False, ftype)
            else:
                raise ValueError(
                    "Error: Filter type not supported \nUse one of: "
                    + str(self.filter_type_available)
                )

        @property
        def scale_available(self):
            """Provides all available scale(gain) settings for the selected channel"""
            return self._get_iio_attr(self.name, "scale_available", False)

        @property
        def scale(self):
            """AD7124 channel scale(gain)"""
            return float(self._get_iio_attr_str(self.name, "scale", False))

        @scale.setter
        def scale(self, value):
            self._set_iio_attr(self.name, "scale", False, str(Decimal(value).real))

        @property
        def offset(self):
            """AD7124 channel offset"""
            return self._get_iio_attr(self.name, "offset", False)

        # @offset.setter
        # def offset(self, value):
        #     self._set_iio_attr(self.name, "offset", False, value)

        @property
        def sampling_frequency(self):
            """Sets sampling frequency of the selected channel"""
            return self._get_iio_attr(self.name, "sampling_frequency", False)

        @sampling_frequency.setter
        def sampling_frequency(self, value):
            self._set_iio_attr(self.name, "sampling_frequency", False, value)

        @property
        def sys_calibration_mode_available(self):
            """Returns state of calibration mode"""
            return self._get_iio_attr_str(
                self.name, "sys_calibration_mode_available", False
            )

        @property
        def sys_calibration_mode(self):
            """Returns state of calibration mode"""
            return self._get_iio_attr_str(self.name, "sys_calibration_mode", False)

        @sys_calibration_mode.setter
        def sys_calibration_mode(self, calmode):
            """Set filter type."""
            if calmode in self.sys_calibration_mode_available:
                self._set_iio_attr(self.name, "sys_calibration_mode", False, calmode)
            else:
                raise ValueError(
                    "Error: This calibration mode not supported \nUse one of: "
                    + str(self.sys_calibration_mode_available)
                )

        @property
        def sys_calibration(self):
            """Returns state of calibration mode"""
            raise AttributeError(
                "sys_calibration is write only; write 1 to calibrate.\
                                  This is a self-clear bit"
            )

        @sys_calibration.setter
        def sys_calibration(self, cal):
            # accept any argument, 1 is the only valid value.
            self._set_iio_attr(self.name, "sys_calibration", False, 1)

        def __call__(self, mV=None):
            """Convenience function, get temperature in SI units (millivolts)"""
            return (self.raw + self.offset) * self.scale

    class _temp_channel(_channel):
        @property
        def scale_available(self):
            raise AttributeError("scale_available not applicable to temp channel")

        @property
        def scale(self):
            """AD7124 temperature scale, needs to be repeated here so we can override the setter"""
            return float(self._get_iio_attr_str(self.name, "scale", False))

        @scale.setter
        def scale(self, value):
            raise AttributeError("scale not applicable to temp channel")

        def __call__(self, mV=None):
            """Convenience function, get temperature in SI units (Degrees C)"""
            return ((self.raw + self.offset) * self.scale) / 1000
