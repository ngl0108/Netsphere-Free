from app.services.auto_discovery_scheduler import _parse_bool, _parse_int


def test_parse_bool():
    assert _parse_bool("true") is True
    assert _parse_bool("1") is True
    assert _parse_bool("yes") is True
    assert _parse_bool("on") is True
    assert _parse_bool("false") is False
    assert _parse_bool("0") is False
    assert _parse_bool("", default=True) is True


def test_parse_int():
    assert _parse_int("10", 1) == 10
    assert _parse_int("  20 ", 1) == 20
    assert _parse_int("nope", 7) == 7

