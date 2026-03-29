from app.drivers.base import NetworkDriver
from app.drivers.cisco.ios_driver import CiscoIOSDriver
from app.drivers.cisco.nxos_driver import CiscoNXOSDriver
from app.drivers.cisco.wlc_driver import CiscoWLCDriver
from app.drivers.juniper.junos_driver import JuniperJunOSDriver
from app.drivers.arista.eos_driver import AristaEOSDriver
from app.drivers.korea.dasan_driver import DasanDriver
from app.drivers.korea.ubiquoss_driver import UbiquossDriver
from app.drivers.korea.domestic_cisco_like_driver import CoreEdgeDriver, NSTDriver, SoltechDriver

from app.drivers.generic_driver import GenericDriver
import logging

logger = logging.getLogger(__name__)

class DriverManager:
    """
    Factory class to return the correct driver instance.
    Maps device types to appropriate driver implementations.
    """
    
    # Custom Driver Implementations (for advanced features like SWIM, ZTP)
    CUSTOM_DRIVERS = {
        'cisco_ios': CiscoIOSDriver,
        'cisco_xe': CiscoIOSDriver,
        'cisco_ios_xe': CiscoIOSDriver,
        'cisco_nxos': CiscoNXOSDriver,
        'cisco_wlc': CiscoWLCDriver,
        'juniper_junos': JuniperJunOSDriver,
        'juniper': JuniperJunOSDriver,
        'arista_eos': AristaEOSDriver,
        'arista': AristaEOSDriver,
        # Korean Vendors (Dedicated)
        'dasan_nos': DasanDriver,
        'dasan': DasanDriver,
        'ubiquoss_l2': UbiquossDriver,
        'ubiquoss_l3': UbiquossDriver,
        'ubiquoss': UbiquossDriver,
        'soltech_switch': SoltechDriver,
        'coreedge_switch': CoreEdgeDriver,
        'nst_switch': NSTDriver,
        'domestic_cisco_like': GenericDriver,
    }

    # Generic Driver Support (Netmiko based, basic SSH/Config)
    # These will use GenericDriver with the specified Netmiko device_type
    GENERIC_SUPPORT = [
        'huawei', 'huawei_vrp', 
        'hp_procurve', 'hp_comware', 
        'aruba_os', 
        'dell_os10', 'dell_force10',
        'nokia_sros', 'alcatel_aos',
        'extreme_exos', 'extreme_netiron', # Extreme
        'handream_sg', 'handream',         # Handream (still generic for now)
        'piolink_pas',                     # Piolink
        'soltech_switch',
        'coreedge_switch',
        'nst_switch',
        'domestic_cisco_like',
        'fortinet', 
        'paloalto_panos',
        'linux', 
        'linux_ahnlab',
        'linux_secui',
        'linux_wins',
        'linux_axgate',
        'linux_nexg',
        'linux_genians',
        'linux_monitorapp',
        'linux_aircuve',
        'linux_netman',
        'linux_mlsoft',
        'linux_sga',
        'linux_nixtech',
        'linux_trinitysoft',
        'f5_ltm', 
        'checkpoint_gaia'
    ]
    
    @staticmethod
    def get_driver(device_type: str, hostname: str, username: str, password: str, port: int = 22, secret: str = None) -> NetworkDriver:
        """
        Factory method to get the appropriate driver.
        """
        device_type_lower = device_type.lower().strip() if device_type else 'cisco_ios'
        
        # 1. Check Custom Drivers (Advanced + Domestic)
        if device_type_lower in DriverManager.CUSTOM_DRIVERS:
            driver_class = DriverManager.CUSTOM_DRIVERS[device_type_lower]
            return driver_class(hostname, username, password, port, secret)
            
        # 2. Check Generic Support (Basic)
        if device_type_lower in DriverManager.GENERIC_SUPPORT or \
           any(vendor in device_type_lower for vendor in ['handream', 'piolink', 'soltech', 'coreedge', 'nst', 'extreme', 'ahnlab', 'secui', 'wins', 'axgate', 'nexg', 'genians', 'monitorapp', 'aircuve', 'netman', 'mlsoft', 'sga', 'nixtech', 'trinitysoft']):
            
            # Map specific aliases to Netmiko types
            netmiko_type = device_type_lower
            
            # Map Handream/Piolink to cisco_ios if valid Netmiko driver doesn't exist
            if 'handream' in netmiko_type: netmiko_type = 'cisco_ios'
            elif 'piolink' in netmiko_type: netmiko_type = 'cisco_ios' 
            elif 'soltech' in netmiko_type: netmiko_type = 'cisco_ios'
            elif 'coreedge' in netmiko_type: netmiko_type = 'cisco_ios'
            elif 'nst' in netmiko_type: netmiko_type = 'cisco_ios'
            elif 'domestic_cisco_like' in netmiko_type: netmiko_type = 'cisco_ios'
            elif netmiko_type.startswith('linux_'): netmiko_type = 'linux'
            
            # Other Aliases
            elif netmiko_type == 'huawei_vrp': netmiko_type = 'huawei'
            elif netmiko_type == 'aruba_os': netmiko_type = 'hp_procurve' 
            
            return GenericDriver(hostname, username, password, port, secret, device_type=netmiko_type)

        # 3. Fallback Heuristics
        if device_type_lower.startswith('cisco'):
            logger.warning("DriverManager unknown cisco type=%s fallback=CiscoIOSDriver", device_type)
            return CiscoIOSDriver(hostname, username, password, port, secret)
        
        if device_type_lower.startswith('juniper'):
            return JuniperJunOSDriver(hostname, username, password, port, secret)
            
        if device_type_lower.startswith('arista'):
            return AristaEOSDriver(hostname, username, password, port, secret)
            
        # 4. Ultimate Fallback -> GenericDriver with passed type (Let Netmiko handle it)
        logger.warning("DriverManager unknown type=%s fallback=GenericDriver", device_type)
        return GenericDriver(hostname, username, password, port, secret, device_type=device_type_lower)
        
        # Strict error for completely unknown vendors
        raise ValueError(f"Unsupported device driver type: {device_type}. Supported: {list(DriverManager.DRIVER_MAP.keys())}")


