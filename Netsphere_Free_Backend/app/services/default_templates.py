"""
Default Configuration Templates for NetSphere

This module provides built-in templates for common configurations.
Templates are seeded into the database on first run.
"""

import logging

logger = logging.getLogger(__name__)

# =============================================================================
# CISCO IOS / IOS-XE Default Templates
# =============================================================================

CISCO_BASE_TEMPLATE = """! ========================================
! NetSphere - Cisco IOS Base Configuration
! ========================================

! --- Hostname & Domain ---
hostname {{ hostname }}
ip domain-name {{ domain_name | default('netmanager.local') }}

! --- Management Interface ---
interface {{ mgmt_interface | default('Vlan1') }}
 description Management Interface
 ip address {{ management_ip }} {{ subnet_mask | default('255.255.255.0') }}
 no shutdown

! --- Default Gateway ---
ip default-gateway {{ default_gateway }}

! --- Enable SSH ---
crypto key generate rsa modulus 2048
ip ssh version 2
ip ssh time-out 60
ip ssh authentication-retries 3

line vty 0 15
 transport input ssh
 login local
 exec-timeout 15 0

! --- Local User ---
username {{ ssh_username | default('admin') }} privilege 15 secret {{ ssh_password }}

! --- Console Settings ---
line console 0
 exec-timeout 15 0
 logging synchronous

! --- Disable HTTP Server ---
no ip http server
no ip http secure-server

! --- Banner ---
banner motd ^
************************************************************
*  UNAUTHORIZED ACCESS TO THIS DEVICE IS PROHIBITED        *
*  Managed by NetSphere - {{ company | default('IT Team') }}
************************************************************
^
"""

CISCO_SNMP_TEMPLATE = """! ========================================
! NetSphere - Cisco SNMP Configuration
! ========================================

! --- SNMP Community (Read-Only) ---
snmp-server community {{ snmp_community | default('public') }} RO

! --- SNMP Location & Contact ---
snmp-server location {{ location | default('Data Center') }}
snmp-server contact {{ contact | default('noc@company.com') }}

! --- SNMP Trap Destination ---
snmp-server host {{ snmp_server }} version 2c {{ snmp_community | default('public') }}
snmp-server trap-source {{ mgmt_interface | default('Vlan10') }}

! --- Enable Common Traps ---
snmp-server enable traps snmp authentication linkdown linkup coldstart warmstart
snmp-server enable traps config
snmp-server enable traps entity
snmp-server enable traps cpu threshold
snmp-server enable traps syslog
snmp-server enable traps envmon
"""

CISCO_LOGGING_TEMPLATE = """! ========================================
! NetSphere - Cisco Logging Configuration
! ========================================

! --- Logging Buffer ---
logging buffered 65536 informational

! --- Syslog Server ---
logging host {{ syslog_server }}
logging source-interface {{ mgmt_interface | default('Vlan10') }}
logging trap informational

! --- Timestamps ---
service timestamps debug datetime msec localtime show-timezone
service timestamps log datetime msec localtime show-timezone

! --- Archive Logging ---
archive
 log config
  logging enable
  logging size 200
  notify syslog contenttype plaintext
  hidekeys
"""

CISCO_NTP_TEMPLATE = """! ========================================
! NetSphere - Cisco NTP Configuration
! ========================================

! --- Timezone ---
clock timezone {{ timezone | default('KST') }} {{ timezone_offset | default('9') }}

! --- NTP Servers ---
ntp server {{ ntp_server_1 | default('time.google.com') }} prefer
ntp server {{ ntp_server_2 | default('time.cloudflare.com') }}

! --- NTP Source Interface ---
ntp source {{ mgmt_interface | default('Vlan10') }}
"""


# =============================================================================
# JUNIPER JUNOS Default Templates
# =============================================================================

JUNIPER_BASE_TEMPLATE = """# ========================================
# NetSphere - Juniper JunOS Base Configuration
# ========================================

system {
    host-name {{ hostname }};
    domain-name {{ domain_name | default('netmanager.local') }};
    
    root-authentication {
        encrypted-password "{{ root_password_hash }}";
    }
    
    login {
        user {{ ssh_username | default('admin') }} {
            class super-user;
            authentication {
                encrypted-password "{{ ssh_password_hash }}";
            }
        }
    }
    
    services {
        ssh {
            protocol-version v2;
        }
        netconf {
            ssh;
        }
    }
    
    syslog {
        host {{ syslog_server }} {
            any notice;
            authorization info;
        }
        file messages {
            any notice;
            authorization info;
        }
    }
    
    ntp {
        server {{ ntp_server_1 | default('time.google.com') }};
        server {{ ntp_server_2 | default('time.cloudflare.com') }};
    }
}
"""

JUNIPER_SNMP_TEMPLATE = """# ========================================
# NetSphere - Juniper SNMP Configuration
# ========================================

snmp {
    location "{{ location | default('Data Center') }}";
    contact "{{ contact | default('noc@company.com') }}";
    
    community {{ snmp_community | default('public') }} {
        authorization read-only;
    }
    
    trap-group netmanager-traps {
        version v2;
        targets {
            {{ snmp_server }};
        }
    }
    
    trap-options {
        source-address {{ management_ip }};
    }
}
"""


# =============================================================================
# ARISTA EOS Default Templates
# =============================================================================

ARISTA_BASE_TEMPLATE = """! ========================================
! NetSphere - Arista EOS Base Configuration
! ========================================

! --- Hostname ---
hostname {{ hostname }}
dns domain {{ domain_name | default('netmanager.local') }}

! --- Management Interface ---
interface Management1
   description Management Interface
   ip address {{ management_ip }}/{{ prefix_length | default('24') }}
   no shutdown

! --- Default Route ---
ip route 0.0.0.0/0 {{ default_gateway }}

! --- Enable eAPI (for NAPALM) ---
management api http-commands
   no shutdown
   protocol https

! --- Local User ---
username {{ ssh_username | default('admin') }} privilege 15 role network-admin secret {{ ssh_password }}

! --- SSH Settings ---
management ssh
   idle-timeout 15

! --- Banner ---
banner motd
************************************************************
*  UNAUTHORIZED ACCESS TO THIS DEVICE IS PROHIBITED        *
*  Managed by NetSphere - {{ company | default('IT Team') }}
************************************************************
EOF
"""

ARISTA_SNMP_TEMPLATE = """! ========================================
! NetSphere - Arista SNMP Configuration
! ========================================

! --- SNMP Community ---
snmp-server community {{ snmp_community | default('public') }} ro

! --- SNMP Location & Contact ---
snmp-server location {{ location | default('Data Center') }}
snmp-server contact {{ contact | default('noc@company.com') }}

! --- SNMP Trap Host ---
snmp-server host {{ snmp_server }} version 2c {{ snmp_community | default('public') }}

! --- Enable Traps ---
snmp-server enable traps
"""

ARISTA_LOGGING_TEMPLATE = """! ========================================
! NetSphere - Arista Logging Configuration
! ========================================

! --- Logging Buffer ---
logging buffered 65536 informational

! --- Syslog Server ---
logging host {{ syslog_server }}
logging source-interface Management1
logging trap informational

! --- Timestamps ---
logging format timestamp traditional
"""


# =============================================================================
# Template Registry (for seeding)
# =============================================================================

DEFAULT_TEMPLATES = [
    # Cisco Templates
    {
        "name": "[Cisco] Base Configuration",
        "category": "Day-0",
        "content": CISCO_BASE_TEMPLATE,
        "version": "1.0",
        "author": "NetSphere",
        "tags": "cisco,ios,base,day0,ztp"
    },
    {
        "name": "[Cisco] SNMP Configuration",
        "category": "Monitoring",
        "content": CISCO_SNMP_TEMPLATE,
        "version": "1.0",
        "author": "NetSphere",
        "tags": "cisco,ios,snmp,monitoring"
    },
    {
        "name": "[Cisco] Logging Configuration",
        "category": "Monitoring",
        "content": CISCO_LOGGING_TEMPLATE,
        "version": "1.0",
        "author": "NetSphere",
        "tags": "cisco,ios,syslog,logging"
    },
    {
        "name": "[Cisco] NTP Configuration",
        "category": "Global",
        "content": CISCO_NTP_TEMPLATE,
        "version": "1.0",
        "author": "NetSphere",
        "tags": "cisco,ios,ntp,time"
    },
    # Juniper Templates
    {
        "name": "[Juniper] Base Configuration",
        "category": "Day-0",
        "content": JUNIPER_BASE_TEMPLATE,
        "version": "1.0",
        "author": "NetSphere",
        "tags": "juniper,junos,base,day0"
    },
    {
        "name": "[Juniper] SNMP Configuration",
        "category": "Monitoring",
        "content": JUNIPER_SNMP_TEMPLATE,
        "version": "1.0",
        "author": "NetSphere",
        "tags": "juniper,junos,snmp,monitoring"
    },
    # Arista Templates
    {
        "name": "[Arista] Base Configuration",
        "category": "Day-0",
        "content": ARISTA_BASE_TEMPLATE,
        "version": "1.0",
        "author": "NetSphere",
        "tags": "arista,eos,base,day0"
    },
    {
        "name": "[Arista] SNMP Configuration",
        "category": "Monitoring",
        "content": ARISTA_SNMP_TEMPLATE,
        "version": "1.0",
        "author": "NetSphere",
        "tags": "arista,eos,snmp,monitoring"
    },
    {
        "name": "[Arista] Logging Configuration",
        "category": "Monitoring",
        "content": ARISTA_LOGGING_TEMPLATE,
        "version": "1.0",
        "author": "NetSphere",
        "tags": "arista,eos,syslog,logging"
    },
]


def seed_default_templates(db_session):
    """
    Seed default templates into the database if they don't exist.
    Call this function during application startup.
    """
    from app.models.device import ConfigTemplate
    
    created_count = 0
    for tpl in DEFAULT_TEMPLATES:
        # Check if template already exists
        existing = db_session.query(ConfigTemplate).filter(
            ConfigTemplate.name == tpl["name"]
        ).first()
        
        if not existing:
            new_template = ConfigTemplate(
                name=tpl["name"],
                category=tpl["category"],
                content=tpl["content"],
                version=tpl["version"],
                author=tpl["author"],
                tags=tpl["tags"]
            )
            db_session.add(new_template)
            created_count += 1
    
    if created_count > 0:
        db_session.commit()
        logger.info("Created default configuration templates count=%s", created_count)
    
    return created_count
