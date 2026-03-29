import sys
import json
import re

# GuestShell Execution
try:
    import cli
except ImportError:
    print("CLI module not found. Are you in GuestShell?")
    # In case of running locally for test
    class MockCLI:
        def execute(self, cmd): return "Processor board ID TEST_SERIAL_12345"
        def configure(self, cmds): print("Configuring: {}".format(cmds))
    cli = MockCLI()

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError
except ImportError:
    # Python 2 fallback
    from urllib2 import Request, urlopen, URLError

SERVER_IP = "{{ server_ip }}"
SERVER_PORT = "{{ server_port }}"
BASE_URL = "http://{}:{}".format(SERVER_IP, SERVER_PORT)

def get_serial():
    try:
        output = cli.execute("show version")
        match = re.search(r"Processor board ID (\S+)", output)
        if match:
            return match.group(1)
        # Fallback for some platforms
        match = re.search(r"Board ID (\S+)", output)
        if match:
            return match.group(1)
    except Exception as e:
        print("Error getting serial: {}".format(e))
    except Exception as e:
        print("Error getting serial: {}".format(e))
    return "UNKNOWN"

def get_uplink_info():
    """
    Parse CDP neighbors to identify uplink device and port.
    Returns dict with name, port, ip.
    """
    info = {}
    try:
        output = cli.execute("show cdp neighbors detail")
        
        # 1. Device ID (Hostname)
        match_dev = re.search(r"Device ID: (\S+)", output)
        if match_dev: info['name'] = match_dev.group(1)
        
        # 2. IP Address
        match_ip = re.search(r"IP address: (\S+)", output)
        if match_ip: info['ip'] = match_ip.group(1)
        
        # 3. Port ID (Remote Port) - pattern varies
        # Interface: GigabitEthernet0/0,  Port ID (outgoing port): GigabitEthernet1/0/5
        match_port = re.search(r"Port ID \(outgoing port\): (\S+)", output)
        if match_port: info['port'] = match_port.group(1)
            
        print(">>> Detected Uplink: {}".format(info))
    except Exception as e:
        print(">>> Failed to get uplink info: {}".format(e))
    return info

def main():
    print(">>> Starting ZTP Boot Script...")
    serial = get_serial()
    print(">>> Device Serial: {}".format(serial))
    
    # Register / Check Config
    url = "{}/api/v1/ztp/register".format(BASE_URL)
    
    # [RMA] capture uplink info
    uplink = get_uplink_info()
    
    payload = {
        "serial_number": serial, 
        "model": "CiscoIOS",
        "uplink_info": uplink
    }
    data = json.dumps(payload).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    
    try:
        req = Request(url, data=data, headers=headers)
        response = urlopen(req)
        resp_data = json.loads(response.read().decode('utf-8'))
        
        action = resp_data.get('action')
        print(">>> ZTP Action Received: {}".format(action))

        if action == 'configure':
            print(">>> Received Configuration. Applying...")
            config_content = resp_data.get('config_content', '')
            if config_content:
                config_lines = config_content.split('\n')
                # Apply Config
                cli.configure(config_lines)
                cli.execute("write memory")
                print(">>> Configuration Applied Successfully!")
            else:
                print(">>> Config content is empty.")
        elif action == 'wait':
            print(">>> Device registered. Waiting for administrator approval.")
        else:
            print(">>> Unknown action.")
            
    except Exception as e:
        print(">>> ZTP Failed (Server Connection Failed): {}".format(e))

if __name__ == "__main__":
    main()
