# Copyright (C) 2026 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

from adi.attribute import attribute
from adi.context_manager import context_manager


class ltc4284(context_manager, attribute):
    """LTC4284 Single Hot Swap Controller

    Channels are created dynamically at init time, keyed by the driver label.
    Differential channel labels have hyphens replaced with underscores.
    Energy channels (no label in the driver) use the IIO channel ID as the key.

    Example channel access::

        dev = adi.ltc4284(uri="ip:analog.local")
        dev.VPWR.input           # Supply rail voltage, mV
        dev.ISENSE.input         # Load current, mA
        dev.Power.input          # Load power, uW
        dev.VADI1.input          # ADC general-purpose input, mV
        dev.ADIN2_ADIN1.input    # Differential input (if enabled), mV
        # Energy channel not exposed — suppressed in current LTC4284 kernel driver
        dev.DRNS.fault           # FET fault status
        dev.VIN.crit_alarm       # Input over-voltage alarm

    Parameters
    ----------
    uri: type=string
        Context URI. Default: Empty (auto-scan)
    device_index: type=integer
        Device index in contexts with multiple LTC4284 devices. Default: 0
    """

    _device_name = "ltc4284"

    def __init__(self, uri="", device_index=0):
        context_manager.__init__(self, uri, self._device_name)

        self._ctrl = None
        index = 0
        for device in self._ctx.devices:
            if device.name == "ltc4284":
                if index == device_index:
                    self._ctrl = device
                    break
                else:
                    index += 1

        if self._ctrl is None:
            raise Exception("LTC4284 device not found in context")

        # Sanitize hyphens in differential channel labels (e.g. ADIN2-ADIN1)
        # so the resulting attribute name is a valid Python identifier.
        # Energy channels are suppressed: the kernel driver exposes a partial
        # energy1 channel (enable only) for LTC4284 but the 64-bit accumulated
        # reading is not accessible via IIO. Skip them entirely for now.
        for ch in self._ctrl.channels:
            ch_id = ch._id
            label = ch.attrs["label"].value if "label" in ch.attrs else ch_id
            label = label.replace("-", "_")

            if ch_id.startswith("energy"):
                continue
            elif ch_id.startswith("power"):
                setattr(self, label, self._channel_power(self._ctrl, ch_id))
            elif ch_id.startswith("curr"):
                setattr(self, label, self._channel_current(self._ctrl, ch_id))
            elif ch_id.startswith("in"):
                # VIN: comparator alarm outputs only, no ADC.
                # DRNS: full ADC + enable + FET fault.
                # VADI/VADIO/DRAIN/differentials: full ADC + enable.
                # VPWR: full ADC, no enable (always-on supply rail measurement).
                if "lcrit_alarm" in ch.attrs and "input" not in ch.attrs:
                    setattr(self, label, self._channel_voltage_alarm(self._ctrl, ch_id))
                elif "fault" in ch.attrs:
                    setattr(self, label, self._channel_voltage_fault(self._ctrl, ch_id))
                elif "enable" in ch.attrs:
                    setattr(self, label, self._channel_voltage_enable(self._ctrl, ch_id))
                else:
                    setattr(self, label, self._channel_voltage(self._ctrl, ch_id))

    class _channel_base(attribute):
        """Base for labeled channels that support reset_history."""

        def __init__(self, ctrl, channel_name):
            self.name = channel_name
            self._ctrl = ctrl

        @property
        def label(self):
            """Human-readable channel label from the driver"""
            return self._get_iio_attr_str(self.name, "label", False)

        @property
        def reset_history(self):
            raise AttributeError("reset_history is write-only")

        @reset_history.setter
        def reset_history(self, value):
            if value != 1:
                raise ValueError("reset_history accepts only 1")
            self._set_iio_attr(self.name, "reset_history", False, value)

    class _channel_voltage_alarm(_channel_base):
        """VIN — comparator-based alarm monitor, no ADC measurement.

        Values in millivolts (mV).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

        @property
        def crit_alarm(self):
            """Critical over-voltage alarm"""
            return self._get_iio_attr(self.name, "crit_alarm", False)

        @property
        def lcrit_alarm(self):
            """Critical under-voltage alarm"""
            return self._get_iio_attr(self.name, "lcrit_alarm", False)

    class _channel_voltage(_channel_base):
        """VPWR — always-on supply rail voltage. Input/history/thresholds, no enable.

        Values in millivolts (mV).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

        @property
        def input(self):
            """Current voltage measurement"""
            return self._get_iio_attr(self.name, "input", False)

        @property
        def highest(self):
            """Peak high recorded since last reset_history"""
            return self._get_iio_attr(self.name, "highest", False)

        @property
        def lowest(self):
            """Peak low recorded since last reset_history"""
            return self._get_iio_attr(self.name, "lowest", False)

        @property
        def max(self):
            """Over-voltage warning threshold"""
            return self._get_iio_attr(self.name, "max", False)

        @max.setter
        def max(self, value):
            self._set_iio_attr(self.name, "max", False, value)

        @property
        def min(self):
            """Under-voltage warning threshold"""
            return self._get_iio_attr(self.name, "min", False)

        @min.setter
        def min(self, value):
            self._set_iio_attr(self.name, "min", False, value)

        @property
        def max_alarm(self):
            """Over-voltage warning alarm status"""
            return self._get_iio_attr(self.name, "max_alarm", False)

        @property
        def min_alarm(self):
            """Under-voltage warning alarm status"""
            return self._get_iio_attr(self.name, "min_alarm", False)

    class _channel_voltage_enable(_channel_voltage):
        """ADC voltage channel with enable: VADI1-4, VADIO1-4, DRAIN, differential pairs.

        Values in millivolts (mV).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

        @property
        def enable(self):
            """ADC channel enable"""
            return self._get_iio_attr(self.name, "enable", False)

        @enable.setter
        def enable(self, value):
            self._set_iio_attr(self.name, "enable", False, value)

    class _channel_voltage_fault(_channel_voltage_enable):
        """DRNS — drain-to-source voltage, adds FET fault detection.

        Values in millivolts (mV).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

        @property
        def fault(self):
            """FET fault status"""
            return self._get_iio_attr(self.name, "fault", False)

    class _channel_current(_channel_base):
        """Current sense channel: ISENSE, ISENSE1, ISENSE2.

        Values in milliamps (mA).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

        @property
        def input(self):
            """Current measurement"""
            return self._get_iio_attr(self.name, "input", False)

        @property
        def highest(self):
            """Peak high recorded since last reset_history"""
            return self._get_iio_attr(self.name, "highest", False)

        @property
        def lowest(self):
            """Peak low recorded since last reset_history"""
            return self._get_iio_attr(self.name, "lowest", False)

        @property
        def max(self):
            """Over-current warning threshold"""
            return self._get_iio_attr(self.name, "max", False)

        @max.setter
        def max(self, value):
            self._set_iio_attr(self.name, "max", False, value)

        @property
        def min(self):
            """Under-current warning threshold"""
            return self._get_iio_attr(self.name, "min", False)

        @min.setter
        def min(self, value):
            self._set_iio_attr(self.name, "min", False, value)

        @property
        def max_alarm(self):
            """Over-current warning alarm status"""
            return self._get_iio_attr(self.name, "max_alarm", False)

        @property
        def min_alarm(self):
            """Under-current warning alarm status"""
            return self._get_iio_attr(self.name, "min_alarm", False)

        @property
        def crit_alarm(self):
            """Critical over-current alarm status"""
            return self._get_iio_attr(self.name, "crit_alarm", False)

    class _channel_power(_channel_base):
        """Power channel (power1): computed load power.

        Uses input_highest/input_lowest naming per HWMON power convention.
        Values in microwatts (uW).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

        @property
        def input(self):
            """Current power measurement"""
            return self._get_iio_attr(self.name, "input", False)

        @property
        def input_highest(self):
            """Peak high power recorded since last reset_history"""
            return self._get_iio_attr(self.name, "input_highest", False)

        @property
        def input_lowest(self):
            """Peak low power recorded since last reset_history"""
            return self._get_iio_attr(self.name, "input_lowest", False)

        @property
        def max(self):
            """Over-power warning threshold"""
            return self._get_iio_attr(self.name, "max", False)

        @max.setter
        def max(self, value):
            self._set_iio_attr(self.name, "max", False, value)

        @property
        def min(self):
            """Under-power warning threshold"""
            return self._get_iio_attr(self.name, "min", False)

        @min.setter
        def min(self, value):
            self._set_iio_attr(self.name, "min", False, value)

        @property
        def max_alarm(self):
            """Over-power warning alarm status"""
            return self._get_iio_attr(self.name, "max_alarm", False)

        @property
        def min_alarm(self):
            """Under-power warning alarm status"""
            return self._get_iio_attr(self.name, "min_alarm", False)

    # _channel_energy is not implemented: the LTC4284 kernel driver suppresses
    # the energy channel. energy1 appears in IIO with enable only, and the
    # 64-bit accumulated reading (energy64_1_input) is not bridged to IIO.
    # Re-add when the driver properly exposes the full energy interface.
