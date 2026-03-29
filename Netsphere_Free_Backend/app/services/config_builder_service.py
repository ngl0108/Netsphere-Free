from typing import List, Dict, Any
from jinja2 import Environment, FileSystemLoader
import os
from app.core.config import settings

class ConfigBuilderService:
    """
    Service to convert abstract JSON configuration blocks into vendor-specific CLI commands.
    Supports: Cisco IOS, Juniper JunOS, Dasan NOS, Ubiquoss.
    """
    
    TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "config")
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), trim_blocks=True, lstrip_blocks=True)

    @staticmethod
    def generate_config(vendor: str, blocks: List[Dict[str, Any]]) -> str:
        """
        Generates CLI configuration for the specified vendor.
        
        Args:
            vendor: 'cisco_ios', 'juniper_junos', 'dasan', 'ubiquoss', etc.
            blocks: List of configuration objects (e.g. {'type': 'vlan', 'id': 10, 'name': 'Sales'})
            
        Returns:
            Generated CLI string.
        """
        vendor_map = {
            'cisco_ios': 'cisco_ios.j2',
            'cisco_xe': 'cisco_ios.j2',
            'cisco_nxos': 'cisco_ios.j2', # Basic compat
            'juniper_junos': 'juniper.j2',
            'dasan': 'dasan.j2',
            'dasan_nos': 'dasan.j2',
            'ubiquoss': 'ubiquoss.j2',
            'ubiquoss_l2': 'ubiquoss.j2',
            'ubiquoss_l3': 'ubiquoss.j2',
            'soltech_switch': 'cisco_ios.j2',
            'coreedge_switch': 'cisco_ios.j2',
            'nst_switch': 'cisco_ios.j2',
        }
        
        template_name = vendor_map.get(vendor.lower())
        if not template_name:
            # Fallback to Cisco IOS as generic
            template_name = 'cisco_ios.j2'
            
        try:
            template = ConfigBuilderService.env.get_template(template_name)
            return template.render(blocks=blocks)
        except Exception as e:
            return f"! Error generating config: {str(e)}"

    @staticmethod
    def validate_blocks(blocks: List[Dict[str, Any]]) -> List[str]:
        """
        Basic validation of configuration blocks structure.
        Returns list of error messages (empty if valid).
        """
        errors = []
        for idx, block in enumerate(blocks):
            b_type = block.get("type")
            if not b_type:
                errors.append(f"Block #{idx}: Missing 'type'")
                continue
                
            if b_type == "vlan":
                if not block.get("id"): errors.append(f"Block #{idx} (VLAN): Missing 'id'")
            elif b_type == "interface":
                if not block.get("name"): errors.append(f"Block #{idx} (Interface): Missing 'name'")
                
        return errors
