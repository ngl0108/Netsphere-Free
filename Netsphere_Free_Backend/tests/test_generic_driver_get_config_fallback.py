from app.drivers.generic_driver import GenericDriver


class FakeConn:
    def __init__(self, outputs):
        self.outputs = outputs

    def send_command(self, cmd, **kwargs):
        v = self.outputs.get(cmd)
        if isinstance(v, Exception):
            raise v
        return v


def test_generic_get_config_picks_longest_non_error_output():
    d = GenericDriver("h", "u", "p", device_type="cisco_ios")
    d.connection = FakeConn(
        {
            "show running-config": "% Invalid input detected at '^' marker.",
            "show running": "!\nhostname SW1\ninterface Gi1/0/1\n description test\n!\n",
            "show config": "",
            "show configuration": "unknown command",
            "display current-configuration": "",
        }
    )
    out = d.get_config("running")
    assert "hostname SW1" in out


def test_generic_get_config_huawei_uses_display_current_configuration_candidates():
    d = GenericDriver("h", "u", "p", device_type="huawei")
    d.connection = FakeConn(
        {
            "display current-configuration": "sysname HW1\ninterface GigabitEthernet0/0/1\n",
            "display saved-configuration": "",
            "display configuration": "",
        }
    )
    out = d.get_config("running")
    assert "sysname HW1" in out
