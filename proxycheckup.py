import requests
import time

time.sleep(10)
CHECKUP_URL = 'http://serverip:5000/proxycheckup'

def send_checkup():
    try:
        r = requests.post(CHECKUP_URL, timeout=1)
        print("Sent: I'm alive", r.status_code)
    except Exception as e:
        print(e)
while True:
    send_checkup()
    time.sleep(1)