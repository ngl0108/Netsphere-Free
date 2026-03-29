import socket
import struct
import threading
import time
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class DHCPServer(threading.Thread):
    """
    Lightweight DHCP Server for ZTP Lab Environments.
    - Binds to UDP 67.
    - Issues IPs from a predefined pool.
    - Provides Option 67 (Bootfile Name).
    """
    def __init__(self, server_ip="192.168.1.2", start_ip="192.168.1.100", subnet_mask="255.255.255.0", router="192.168.1.1", dns="8.8.8.8", boot_file_url="http://192.168.1.2:8000/api/v1/ztp/boot"):
        super().__init__()
        self.server_ip = server_ip
        self.offer_ip = start_ip # Simple implementation: always offers same IP or increment
        self.subnet_mask = subnet_mask
        self.router = router
        self.dns = dns
        self.boot_file = boot_file_url
        self.sock = None
        self.running = False
        self.daemon = True
        self.mac_map = {}

    def run(self):
        self.running = True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.sock.bind(('', 67))
            logger.info("DHCP server listening bind=0.0.0.0:67 boot_file=%s", self.boot_file)
        except PermissionError:
            logger.error("DHCP failed to bind port 67 (admin privileges required)")
            return
        except Exception as e:
            logger.exception("DHCP failed to start")
            return

        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
                self.handle_dhcp(data)
            except Exception as e:
                if self.running:
                    logger.warning("DHCP loop error=%s", e)

    def handle_dhcp(self, pkt):
        # Basic parsing (Ethernet/IP/UDP headers are stripped by recvfrom, this is DHCP payload)
        # However, recvfrom on raw socket might behave differently, but for DGRAM socket we get UDP payload.
        
        # RFC 2131: op(1), htype(1), hlen(1), hops(1), xid(4), secs(2), flags(2), ciaddr(4), yiaddr(4), siaddr(4), giaddr(4), chaddr(16), sname(64), file(128), options(var)
        if len(pkt) < 240: return
        
        op, htype, hlen, hops = struct.unpack('!BBBB', pkt[0:4])
        xid = pkt[4:8]
        flags = pkt[10:12]
        ciaddr = pkt[12:16]
        chaddr = pkt[28:44] # Client MAC is in first 6 bytes
        cookie = pkt[236:240]
        
        if op != 1: return # Not a Boot Request
        
        # Parse Options
        options = pkt[240:]
        msg_type = 0
        
        i = 0
        while i < len(options):
            opt = options[i]
            if opt == 255: break # End
            if opt == 0: 
                i+=1
                continue
            length = options[i+1]
            if opt == 53: # DHCP Message Type
                msg_type = options[i+2]
            i += 2 + length

        # Message Type: 1=Discover, 3=Request
        if msg_type == 1: # Discover -> Offer
            self.send_reply(xid, chaddr, flags, 2) # 2=Offer
        elif msg_type == 3: # Request -> Ack
            self.send_reply(xid, chaddr, flags, 5) # 5=Ack

    def send_reply(self, xid, chaddr, flags, msg_type):
        # Build DHCP Packet
        op = 2 # Boot Reply
        htype = 1 # Ethernet
        hlen = 6
        hops = 0
        
        yiaddr = socket.inet_aton(self.offer_ip) # Your IP (Client IP)
        siaddr = socket.inet_aton(self.server_ip) # Next Server IP
        giaddr = b'\x00\x00\x00\x00'
        
        packet = struct.pack('!BBBB', op, htype, hlen, hops)
        packet += xid
        packet += b'\x00\x00' # secs
        packet += flags # Broadcast flag from request
        packet += b'\x00\x00\x00\x00' # ciaddr
        packet += yiaddr
        packet += siaddr # siaddr (Next Server / TFTP Server IP)
        packet += giaddr
        packet += chaddr
        packet += b'\x00' * 192 # sname(64) + file(128) - We use Option 67 instead of file field for URL
        packet += b'\x63\x82\x53\x63' # Magic Cookie

        # Options
        packet += b'\x35\x01' + struct.pack('B', msg_type) # Option 53: Msg Type
        packet += b'\x36\x04' + socket.inet_aton(self.server_ip) # Option 54: Server ID
        packet += b'\x01\x04' + socket.inet_aton(self.subnet_mask) # Option 1: Subnet Mask
        packet += b'\x03\x04' + socket.inet_aton(self.router) # Option 3: Gateway
        packet += b'\x06\x04' + socket.inet_aton(self.dns) # Option 6: DNS
        packet += b'\x33\x04' + struct.pack('!I', 3600) # Option 51: Lease Time
        
        # Option 67: Bootfile Name (URL for GuestShell ZTP)
        # Modern Cisco ZTP supports HTTP URL here
        boot_url = self.boot_file.encode('ascii')
        packet += b'\x43' + struct.pack('B', len(boot_url)) + boot_url
        
        packet += b'\xff' # End Option
        
        # Send Broadcast
        dest = ('255.255.255.255', 68)
        try:
            self.sock.sendto(packet, dest)
            type_str = "Offer" if msg_type == 2 else "Ack"
            client_mac = ':'.join('%02x' % b for b in chaddr[:6])
            logger.info("DHCP sent type=%s client_mac=%s offer_ip=%s boot_file=%s", type_str, client_mac, self.offer_ip, self.boot_file)
        except Exception as e:
            logger.warning("DHCP send error=%s", e)

# Global Instance
ztp_dhcp = None

def start_dhcp_server_if_enabled():
    global ztp_dhcp
    # Hardcoded for Lab Test - In Prod, load from settings/DB
    ztp_dhcp = DHCPServer()
    ztp_dhcp.start()
