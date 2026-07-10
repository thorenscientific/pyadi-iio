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
        ("max", 319, 81600, 1000, 1, 5, "VPWR"),
        ("min", 319, 81600, 1000, 1, 5, "VPWR"),
        ("max", 0, 26, 1, 1, 5, "SENSE"),
        ("min", 0, 26, 1, 1, 5, "SENSE"),
        ("max", 0, 2088960, 100000, 1, 5, "Power"),
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
