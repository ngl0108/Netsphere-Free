import sys
import os
import sqlite3

# Add project root to path
sys.path.append(os.getcwd())

from app.services.snmp_service import SnmpManager

def debug_snmp():
    print("--- SNMP Raw Octet Debug ---")
    conn = sqlite3.connect('netmanager.db')
    c = conn.cursor()
    c.execute("SELECT id, ip_address, snmp_community FROM devices WHERE status='online'")
    devices = c.fetchall()
    conn.close()

    if not devices:
        print("No online devices found in DB.")
        return

    for dev in devices:
        dev_id, ip, community = dev
        print(f"\n[Device {dev_id}] IP: {ip}, Community: {community}")
        
        try:
            mgr = SnmpManager(ip, community)
            
            # 1. Test Status
            status = mgr.check_status()
            print(f"  > Status Check: {status.get('status')} (Uptime: {status.get('uptime')})")
            
            # 2. Test Octets
            octets = mgr.get_total_octets()
            print(f"  > Total Octets: {octets}")
            
            # 3. Test Interface Count (To see if walk works)
            ifaces = mgr.get_interface_statuses()
            print(f"  > Interfaces Found: {len(ifaces)}")
            
        except Exception as e:
            print(f"  > Error: {e}")

if __name__ == "__main__":
    debug_snmp()
