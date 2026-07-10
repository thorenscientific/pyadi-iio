import pytest

import adi

hardware = "ltc4284"
classname = "adi.ltc4284"

#########################################
@pytest.mark.iio_hardware(hardware)
@pytest.mark.parametrize("classname", [(classname)])
@pytest.mark.parametrize(
    "attr, start, stop, step, tol, repeats, sub_channel",
    [
        # VPWR: supply rail voltage thresholds, mV. Full hardware range.
        ("max", 319, 81600, 1000, 500, 5, "VPWR"),
        ("min", 319, 81600, 1000, 500, 5, "VPWR"),
        # ISENSE: primary sense current thresholds, mA. Range for eval board rsense.
        ("max", 0, 26, 1, 1, 5, "ISENSE"),
        ("min", 0, 26, 1, 1, 5, "ISENSE"),
        # Power: computed load power thresholds, uW.
        ("max", 0, 2088960, 100000, 1, 5, "Power"),
        ("min", 0, 2088960, 100000, 1, 5, "Power"),
    ],
)
def test_ltc4284_attr(
    test_attribute_single_value,
    iio_uri,
    classname,
    attr,
    start,
    stop,
    step,
    tol,
    repeats,
    sub_channel,
):
    test_attribute_single_value(
        iio_uri, classname, attr, start, stop, step, tol, repeats, sub_channel
    )
