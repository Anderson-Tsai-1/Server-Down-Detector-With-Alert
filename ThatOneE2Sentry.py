import requests
import urllib3
from flask import Flask, request
from threading import Thread, Lock
import time
import logging
import os
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import subprocess


ip_index = {
    "69.69.69.69":"Name",
}


# You shouldnt need to edit below this line.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

battery_info = {
    "load_percent": None,
    "battery_percent": None,
    "time_remaining": None,
    "last_updated": None,
    "last_status": "ONLINE",
    "status_change_time": None
}

load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
from_number = os.getenv("FROM_NUMBER")
to_number = os.getenv("TO_NUMBER")
name = os.getenv("NAME")
proxmox = os.getenv("PROXMOX")

client = Client(account_sid, auth_token)

alert_sent = False



#user = 'root@pam'
def shutdown_nodes(node_names, host='Tree0', user=proxmox, verify_ssl=False, timeout=10, total_timeout=30):
    token_name = os.getenv("PROXMOX_TOKEN_NAME")
    token_value = os.getenv("PROXMOX_TOKEN_VALUE")

    print(f"[INFO] Starting shutdown process for nodes: {', '.join(node_names)}")

    if not token_name or not token_value:
        print("[ERROR] PROXMOX_TOKEN_NAME or PROXMOX_TOKEN_VALUE not set")
        return {}

    valid_nodes = node_names
    results = {}

    def shutdown_node(node_name):
        try:
            curl_cmd = [
                "curl", "-X", "POST",
                "-H", f"Authorization: PVEAPIToken={user}!{token_name}={token_value}",
                "-H", "Content-Type: application/x-www-form-urlencoded",
                "--data", "command=shutdown",
                "--insecure",
                f"https://{host}:8006/api2/json/nodes/{node_name}/status"
            ]
            print(f"[INFO] Sending shutdown command for node: {node_name} with curl")
            result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=timeout)
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode == 0 and '"data":' in stdout:
                print(f"[INFO] Shutdown command sent successfully for {node_name}. Response: {stdout}")
                return node_name, stdout
            else:
                print(f"[ERROR] Failed to send shutdown command for {node_name}. Return code: {result.returncode}, Error: {stderr}, Output: {stdout}")
                return node_name, f"Error: curl failed with code {result.returncode}, stderr: {stderr}"
        except subprocess.TimeoutExpired:
            print(f"[ERROR] Shutdown task for {node_name} timed out after {timeout} seconds")
            return node_name, f"Error: Timeout after {timeout} seconds"
        except Exception as e:
            print(f"[ERROR] Failed to send shutdown command for {node_name}: {e}")
            return node_name, f"Error: {str(e)}"

    if not valid_nodes:
        print("[ERROR] No valid nodes to shut down")
        return {}

    print(f"[INFO] Initiating concurrent shutdowns for {len(valid_nodes)} valid nodes")
    with ThreadPoolExecutor(max_workers=len(valid_nodes)) as executor:
        futures = {executor.submit(shutdown_node, node): node for node in valid_nodes}
        try:
            for future in as_completed(futures, timeout=total_timeout):
                node_name = futures[future]
                try:
                    node_name, result = future.result(timeout=timeout)
                    results[node_name] = (node_name, result)
                    print(f"[INFO] Shutdown task completed for {node_name}: {result}")
                except TimeoutError:
                    print(f"[ERROR] Shutdown task for {node_name} timed out after {timeout} seconds")
                    results[node_name] = (node_name, f"Error: Timeout after {timeout} seconds")
                except Exception as e:
                    print(f"[ERROR] Shutdown task for {node_name} failed: {e}")
                    results[node_name] = (node_name, f"Error: {str(e)}")
        except TimeoutError as e:
            print(f"[ERROR] Total timeout of {total_timeout} seconds reached, {len(futures)} tasks unfinished: {e}")
            for future in futures:
                if future.done():
                    try:
                        node_name, result = future.result(timeout=0)
                        results[node_name] = (node_name, result)
                        print(f"[INFO] Shutdown task completed for {node_name}: {result}")
                    except Exception as e:
                        node_name = futures[future]
                        print(f"[ERROR] Failed to retrieve result for {node_name}: {e}")
                        results[node_name] = (node_name, f"Error: {str(e)}")
                else:
                    node_name = futures[future]
                    future.cancel()
                    print(f"[WARNING] Cancelled shutdown task for {node_name} due to total timeout")
                    results[node_name] = (node_name, "Error: Cancelled due to total timeout")

        executor._threads.clear()
        executor.shutdown(wait=False)
        print("[INFO] ThreadPoolExecutor shut down")

    print(f"[INFO] All shutdown tasks processed. Results: {results}")
    return results

def send_alert(failed, online, power, proxies):
    failed_str = ", ".join(f"{node}" for node in sorted(failed))
    failed_summary = f"{len(failed)} nodes failed in the past hour. The nodes that have failed are: {failed_str}."

    battery_status = (
        f"The battery load is {battery_info['load_percent']} and has "
        f"{battery_info['battery_percent']} capacity left, which is {battery_info['time_remaining']} remaining. "
        f"Recorded {time_since_last_update()}."
    )

    online_str = ", ".join(f"{node}" for node in sorted(online))
    online_summary = f"There are {len(online)} online nodes. The online nodes are: {online_str}. There are {len(proxies)} online proxies."

    
    if power:
        main_message = (f"Greetings, {name}. A Power Outage is in effect. {battery_status} {online_summary}")
        repeat_message = (f" Again... A Power Outage is in effect. {battery_status} Goodbye.")
    elif online:
        main_message = (f"Greetings, {name}. {failed_summary} {online_summary} {battery_status} ")
        repeat_message = (f" Again... {failed_summary} {online_summary} {battery_status} Goodbye.")
    else:
        main_message = (f"Greetings, {name}. It is likely the internet went out. {failed_summary} {battery_status}")
        repeat_message = (f" Again... {failed_summary} {battery_status} Goodbye.")

    say_string = main_message + repeat_message

    print(f"[INFO] Preparing to send emergency call with message: {say_string}")

    response = VoiceResponse()
    response.say(say_string, voice='alice')

    try:
        print("[INFO] Initiating Twilio call")
        call = client.calls.create(
            twiml=str(response),
            to=to_number,
            from_=from_number,
            machine_detection='Enable'
        )
        print(f"[INFO] Call initiated successfully. SID: {call.sid}")
    except Exception as e:
        print(f"[ERROR] Failed to send Twilio call: {e}")

    return say_string

app = Flask(__name__)
hosts = {}
failed_hosts = {}
proxynodes = {}
failed_proxynodes = {}
lock = Lock()

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

def load_ip_index_from_env(prefix="NODE_"):
    ip_map = {}
    for key, value in os.environ.items():
        if key.startswith(prefix):
            name = key[len(prefix):]
            ip_map[value] = name
    return ip_map

def get_node_name(ip):
    return ip_index.get(ip, ip)


@app.route('/checkup', methods=['POST'])
def checkup():
    client_ip = request.remote_addr
    node_name = get_node_name(client_ip)
    now = time.time()

    with lock:
        if node_name not in hosts:
            #print(f"[INFO] New node detected: {node_name}")
            hosts[node_name] = {'last_seen': now, 'supposed_state': 1, 'current_state': 1}
        else:
            #print(f"[INFO] Updating last seen for node: {node_name}")
            hosts[node_name]['last_seen'] = now
            hosts[node_name]['supposed_state'] = 1
            hosts[node_name]['current_state'] = 1

        if node_name in failed_hosts:
            print(f"[INFO] {node_name} recovered from failure")
            del failed_hosts[node_name]

    return '', 200


@app.route('/proxycheckup', methods=['POST'])
def proxycheckup():
    client_ip = request.remote_addr
    node_name = get_node_name(client_ip)
    now = time.time()

    with lock:
        if node_name not in proxynodes:
            #print(f"[INFO] New proxy node detected: {node_name}")
            proxynodes[node_name] = {'last_seen': now, 'supposed_state': 1, 'current_state': 1}
        else:
            #print(f"[INFO] Updating last seen for proxy node: {node_name}")
            proxynodes[node_name]['last_seen'] = now
            proxynodes[node_name]['supposed_state'] = 1
            proxynodes[node_name]['current_state'] = 1

        if node_name in failed_proxynodes:
            print(f"[INFO] {node_name} recovered from failure in proxy nodes")
            del failed_proxynodes[node_name]

    return '', 200



@app.route('/shutdown', methods=['POST'])
def shutdown():
    data = request.get_json()
    if not data or 'node_name' not in data:
        return 'Missing node_name in request', 400

    node_name = data['node_name']
    ip_addr = request.remote_addr
    proxyname = get_node_name(ip_addr)

    with lock:
        if node_name in hosts:
            print(f"[SHUTDOWN] {node_name} ({proxyname}) shutting down gracefully")
            del hosts[node_name]
        else:
            print(f"[SHUTDOWN] Shutdown received from {node_name} ({proxyname})")

    return '', 200


@app.route('/battery', methods=['POST'])
def battery_status():
    try:
        status = request.data.decode('utf-8')
        #print(f"[INFO] Received battery status: {status}")
        lines = status.splitlines()
        data = {}

        for line in lines:
            if ':' not in line:
                continue
            key, value = map(str.strip, line.split(":", 1))
            data[key] = value

        with lock:
            battery_info['load_percent'] = data.get('LOADPCT')
            battery_info['battery_percent'] = data.get('BCHARGE')
            battery_info['time_remaining'] = data.get('TIMELEFT')
            new_status = data.get('STATUS', 'ONLINE')
            if battery_info['last_status'] != new_status:
                print(f"[INFO] Battery status changed from {battery_info['last_status']} to {new_status}")
                battery_info['last_status'] = new_status
                battery_info['status_change_time'] = time.time()
            battery_info['last_updated'] = time.time()

        #print("[INFO] Battery status updated successfully")
        return 'Battery status received', 200
    except Exception as e:
        print(f"[ERROR] Failed to handle /battery POST: {e}")
        return 'Internal server error', 500

def time_since_last_update():
    if battery_info['last_updated'] is None:
        return "unknown"
    elapsed = time.time() - battery_info['last_updated']
    if elapsed >= 3600:
        return f"{round(elapsed / 3600)} hour(s) ago."
    elif elapsed >= 60:
        return f"{round(elapsed / 60)} minute(s) ago."
    else:
        return f"{round(elapsed)} second(s) ago."

def monitor_hosts():
    global alert_sent
    while True:
        now = time.time()
        changed = False

        with lock:
            for node_name, info in list(failed_hosts.items()):
                if now - info.get('failed_time', 0) > 3600:
                    print(f"[INFO] Removing stale failed host: {node_name}")
                    del failed_hosts[node_name]
                    changed = True

            for node_name, info in list(hosts.items()):
                if now - info['last_seen'] > 10:
                    print(f"[WARNING] Node {node_name} timed out (last seen {round(now - info['last_seen'])}s ago)")
                    info['current_state'] = 0
                else:
                    info['current_state'] = 1

                if info['supposed_state'] == 1 and info['current_state'] == 0:
                    print(f"[WARNING] Node {node_name} marked as failed")
                    info['failed_time'] = now
                    failed_hosts[node_name] = info
                    del hosts[node_name]
                    changed = True

            if changed:
                print("[INFO] Host status changed, resetting alert_sent flag")
                alert_sent = False

            if len(failed_hosts) >= 2 and battery_info['last_status'] in ['ONLINE', 'ONLINE LOWBATT', 'COMMLOST', 'SHUTTING DOWN']:
                if not alert_sent and (now - max(info['failed_time'] for info in failed_hosts.values())) >= 10:
                    print(f"[INFO] Triggering alert for {len(failed_hosts)} failed hosts")
                    send_alert(list(failed_hosts.keys()), list(hosts.keys()), False , list(proxynodes.keys()))
                    with open("alert_log.txt", "a") as f:
                        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | Nodes Failed | {hosts} hosts online | {failed_hosts} hosts failed | Battery Status: {battery_info['last_status']} | {list(proxynodes.keys())} proxies online |\n")
                    failed_hosts.clear()
                    alert_sent = True

            if battery_info['last_status'] not in ['ONLINE', 'ONLINE LOWBATT', 'COMMLOST', 'SHUTTING DOWN'] and battery_info['status_change_time']:
                if now - battery_info['status_change_time'] > 5:
                    with open("alert_log.txt", "a") as f:
                        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | Battery Failed | {hosts} hosts online | {failed_hosts} hosts failed | Battery Status: {battery_info['last_status']} | {list(proxynodes.keys())} proxies online |\n")

                    print("[ACTION] Battery is not ONLINE for 5 seconds. Initiating shutdown of all nodes.")
                    try:
                        shutdown_results = shutdown_nodes(["steinsgate", "tree1", "tree2", "tree3", "tree4", "tree5", "tree0"])
                        print(f"[INFO] Shutdown results: {shutdown_results}")
                    except Exception as e:
                        print(f"[ERROR] Shutdown nodes failed: {e}")
                        shutdown_results = {}
                    alert_sent = True
                    print("[INFO] Waiting 30 seconds to allow nodes to shutdown")
                    hosts.clear()
                    failed_hosts.clear()
                    time.sleep(20)

                    failed_hosts.clear()
                    hosts.clear()
                    failed_hosts.clear()
                    time.sleep(10)
                    hosts.clear()
                    failed_hosts.clear()

                    print("[INFO] Sending power outage alert")
                    send_alert(list(failed_hosts.keys()), list(hosts.keys()), True, list(proxynodes.keys()))
                    battery_info['status_change_time'] = None

        print(f" [STATUS] {time.strftime('%Y-%m-%d %H:%M:%S')} | {len(hosts)} hosts online | {len(failed_hosts)} hosts failed | Battery {battery_info['last_status']} at {battery_info['battery_percent']}, last updated {time_since_last_update()} | {len(list(proxynodes.keys()))} proxies online ")
        time.sleep(5)

Thread(target=monitor_hosts, daemon=True).start()

if __name__ == '__main__':
    print("[INFO] Starting Flask application")
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=5000)