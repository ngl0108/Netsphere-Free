from app.drivers.generic_driver import GenericDriver
from app.drivers.manager import DriverManager


def test_driver_manager_maps_domestic_cisco_like_to_generic_cisco_ios():
    driver = DriverManager.get_driver("domestic_cisco_like", "10.0.0.5", "admin", "pw", 22, None)
    assert isinstance(driver, GenericDriver)
    assert driver.device_type == "cisco_ios"
