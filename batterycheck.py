import subprocess
import requests
import time

URL = "http://serverip:5000/battery"

def get_apc_status():
    try:
        result = subprocess.run(['apcaccess'], capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print("Error running apcaccess:", e)
        return None

def send_apc_status(status):
    headers = {'Content-Type': 'text/plain'}
    try:
        response = requests.post(URL, data=status, headers=headers)
        print(f"Sent battery status | HTTP {response.status_code}, {status}")
    except requests.RequestException as e:
        print("Error sending POST request:", e)

def main():
    while True:
        status = get_apc_status()
        if status:
            send_apc_status(status)
        time.sleep(5)

if __name__ == "__main__":
    main()
