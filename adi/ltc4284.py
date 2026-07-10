# Copyright (C) 2026 Analog Devices, Inc.
#
# SPDX short identifier: ADIBSD

from adi.attribute import attribute
from adi.context_manager import context_manager


class ltc4284(context_manager, attribute):
    """LTC4284 Single Hot Swap Controller

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

        # Dynamically create typed channel objects keyed on the driver label
        # (e.g. VPWR, SENSE, ADIN1) rather than the raw IIO channel ID
        # (in0, curr1). The channel object's internal self.name stays as the
        # IIO ID so libiio attr calls continue to work.
        # crit_alarm in ch.attrs is the data-driven discriminator for the
        # voltage (VPWR/in0) and current (SENSE/curr1) channels that carry
        # alarm flags and thresholds absent on the others.
        for ch in self._ctrl.channels:
            ch_id = ch._id
            label = ch.attrs["label"].value
            has_crit = "crit_alarm" in ch.attrs
            if ch_id.startswith("energy"):
                setattr(self, label, self._channel_energy(self._ctrl, ch_id))
            elif ch_id.startswith("power"):
                setattr(self, label, self._channel_power(self._ctrl, ch_id))
            elif ch_id.startswith("curr"):
                if has_crit:
                    setattr(self, label, self._channel_current_crit(self._ctrl, ch_id))
                else:
                    setattr(self, label, self._channel_current(self._ctrl, ch_id))
            elif ch_id.startswith("in"):
                if has_crit:
                    setattr(self, label, self._channel_voltage_crit(self._ctrl, ch_id))
                else:
                    setattr(self, label, self._channel_voltage(self._ctrl, ch_id))

    class _channel_base(attribute):
        """Base channel: input reading, label, and reset_history.

        reset_history() is write-only and requires elevated permissions.
        """

        def __init__(self, ctrl, channel_name):
            self.name = channel_name
            self._ctrl = ctrl

        @property
        def input(self):
            """Channel measurement in HWMON standard units (mV / mA / uW / uJ)"""
            return self._get_iio_attr(self.name, "input", False)

        @property
        def label(self):
            """Human-readable channel label from the driver"""
            return self._get_iio_attr_str(self.name, "label", False)

        @property
        def reset_history(self):
            """Write 1 to reset peak highest/lowest history. Requires elevated permissions."""
            raise AttributeError("reset_history is write-only")

        @reset_history.setter
        def reset_history(self, value):
            if value != 1:
                raise ValueError("reset_history accepts only 1")
            self._set_iio_attr(self.name, "reset_history", False, value)

    class _channel_voltage(_channel_base):
        """Standard voltage input channel (in*): ADIN1-4, ADIO1-4, paired variants.

        Values in millivolts (mV).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

        @property
        def highest(self):
            """Peak high value recorded since last reset_history()"""
            return self._get_iio_attr(self.name, "highest", False)

        @property
        def lowest(self):
            """Peak low value recorded since last reset_history()"""
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

    class _channel_voltage_crit(_channel_voltage):
        """Main power voltage channel (in0/VPWR).

        Adds critical alarm flags absent on other voltage channels.
        Values in millivolts (mV).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

        @property
        def crit_alarm(self):
            """Critical over-voltage alarm status"""
            return self._get_iio_attr(self.name, "crit_alarm", False)

        @property
        def lcrit_alarm(self):
            """Critical under-voltage alarm status"""
            return self._get_iio_attr(self.name, "lcrit_alarm", False)

    class _channel_current(_channel_base):
        """Standard current input channel (curr2/SENSE1, curr3/SENSE2).

        Values in milliamps (mA).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

        @property
        def highest(self):
            """Peak high value recorded since last reset_history()"""
            return self._get_iio_attr(self.name, "highest", False)

        @property
        def lowest(self):
            """Peak low value recorded since last reset_history()"""
            return self._get_iio_attr(self.name, "lowest", False)

    class _channel_current_crit(_channel_current):
        """Main sense current channel (curr1/SENSE).

        Adds over/under-current thresholds and critical alarm absent on
        SENSE1/SENSE2. Values in milliamps (mA).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

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
        def crit_alarm(self):
            """Critical over-current alarm status"""
            return self._get_iio_attr(self.name, "crit_alarm", False)

    class _channel_power(_channel_base):
        """Power input channel (power1): computed load power.

        Uses input_highest / input_lowest (driver naming differs from voltage/current).
        Values in microwatts (uW).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

        @property
        def input_highest(self):
            """Peak high power recorded since last reset_history()"""
            return self._get_iio_attr(self.name, "input_highest", False)

        @property
        def input_lowest(self):
            """Peak low power recorded since last reset_history()"""
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

    class _channel_energy(_channel_base):
        """Energy accumulator channel (energy1).

        No highest/lowest history. enable requires elevated permissions.
        Values in microjoules (uJ).
        """

        def __init__(self, ctrl, channel_name):
            super().__init__(ctrl, channel_name)

        @property
        def reset_history(self):
            raise AttributeError("reset_history is write-only")

        @reset_history.setter
        def reset_history(self, value):
            raise NotImplementedError("energy channel does not support reset_history")

        @property
        def enable(self):
            """Energy accumulator enable state"""
            return self._get_iio_attr(self.name, "enable", False)

        @enable.setter
        def enable(self, value):
            self._set_iio_attr(self.name, "enable", False, value)
