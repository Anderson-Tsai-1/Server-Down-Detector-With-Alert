# Server Down Detector With Alert (Only for Linux)
I wanted a system to give me a notification when my servers when down. I opted for an actual call because I will not miss a phone call.
Lets start off with why I made this. I made this because I accidentally brought down my cluster of servers twice. Once was my APC backup battery failed, and another was when accidentally brought down my APC unbeknownst to me. I had conceived of this ages ago but didn't follow through. It was on the 2nd time I accidentally brought down the cluster did I began my work on this on May 6 2025. 

# How It Works
You need
1. A Linux node to be monitored
2. A VM in the cloud (I used a Oracle machine)
3. Tailscale
4. Use systemd-networkd.service for your networking
5. An SBC like an Rasberry PI (RPI)
6. Twilio Account
7. Access to the internet (Duh)
8. (Optional) APC UPS Backup Battery

The cloud VM has a python3 flask web server. It essentially is the brain for this alert system and needs to be running 24/7. I chose to use an Oracle free VM because it almost never it only goes down except for server migration and dangerous weather. Both of which you will receive emails ahead of time from Oracle. Every second, the nodes you want to be monitored sends a post request to the cloud VM's web server. If the node does not send a post request for 20 seconds, the node is considered to have failed. If a certain number of nodes have failed in 1 hour, an alert call will be placed. 
When a node shuts down, it sends a post request to a local machine (the SBC) as a proxy using socat, which is then redirected to the cloud VM web server. This is how the server knows this is not an unscheduled shutdown. The program assumes that the SBC and the nodes you are watching over are on the same local network.

The optional feature is the battery reporting. Since I operate a Proxmox cluster, this part may vary for you. I attached my APC UPS Backup battery to my SBC running the proxy. The SBC using apcupsd sends the status of the battery to the cloud VM every 5 seconds. When the power goes out and the backup battery is used the battery, the cloud VM receives this change in battery status, shuts down a list of Proxmox nodes using Proxmox API, then sends out an emergency call. 
There is 3 different calls, all with slightly different information: if the internet goes out, if the power goes out, and one in general.

There are 3 different calls you can recive based on the situation: General Node Failure, Power Outage, and Internet Outage. Currently, you are not alerted when you have less than 1 Proxy online.

The special part was how I got the nodes to send out a POST request on shutdown. I exited the systemctl systemd-networkd.service file directly and an ExecStop command. Weirdly enough, the tailscale network adapter would shut down before the LAN adapter shut down, resulting in the need for the local proxies. 

For me, I use this for my Proxmox cluster and have a LXC run the scripts, but it should work on other types of Linux machines.

Planned Features:
1. Ability to call multiple numbers
2. Add automatic messages for less urgent reminders such as X server is back online
3. Send call when less than 1 Proxy is online

# How to Set it UP!

## Set Up
1. Make a Twilio Account, get your number, tokens, etc
2. Make a Tailscale account
3. Make Oracle account and the VM (This will be monitoring server)
4. Set up the SBC (Will be used as the proxy server)
5. Install Tailscale on the SBC, monitoring server, and the sever you want to be monitored
 `apt install npm`

6. Install npm on the SBC, monitoring server, and the sever you want to be monitored
`apt install npm`
7. Install pm2 on all machines
`npm install pm2 -g`

## Installation

Note: These python files are meant to be run perpetually and start on start up. To do this, do:
1. `pm2 start filename.py`
2. `pm2 save`

When I say run the file, I am refering to this process

ALSO I kinda forgot the libraries I used, so just keep on doing pip install XXX til it works 🫠


### Monitoring Server
1. Install `ThatOneE2Sentry.py` onto the monitoring server
2. Edit `ip_index` in `ThatOneE2Sentry.py`
3. Every server you want to monitor along with all proxy servers you need to list it as `"Tailscale IP":"Host Name",` copy it as many times as you need
4. Run the file

### Individual Node
1. Install `checkup.py` onto the node
2. Edit `checkup.py` and replace 'serverip' with the actual IP
3. Run the file
4. `sudo nano /usr/lib/systemd/system/systemd-networkd.service`
5. Add `ExecStop=/usr/bin/curl -X POST (LOCALIPPROXYSERVER1):5000/shutdown LOCALIPPROXYSERVER2:5100/shutdown -H "Content-Type: application/json" -d "{\"node_name\": \"(NODENAME)\"}"`
It is required you use the local IPs of the proxy server (I tried using the Tailscale IPs but the Tailscale adapter shuts down first)
In the example above, you can add more and more proxy servers for redundancy
ONLY CHANGE THE PARTS IN (CAPSLOCK) 

6. Reboot

### Proxy Server
Note: You can use any linux locally networked linux device (Example: Octoprint PI) as long as the port is not taken
1. Install `proxycheckup.py` onto the node
2. Edit `proxycheckup.py` and replace 'serverip' with the actual IP
3. Run the file
4. Make systemctl file, start and enable
```
[Unit]
Description=Socat TCP Proxy from port 5000 to MONITORINGSERVER:5000
After=network.target

[Service]
ExecStart=/usr/bin/socat TCP-LISTEN:5000,fork,reuseaddr TCP:MONITORINGSERVER:5000/shutdown
Restart=always
RestartSec=5
User=nobody
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Optional Battery Monitor
Keep in mind you need a unit that will show up with `apcupsd` and have a serial connection with the device
1. Install `batterycheck.py` onto the node
2. Edit `batterycheck.py` and replace 'serverip' with the actual IP
3. Run the file

### Setup .env
1. I honestly forgot how I got the Twilio tokens, ask GPT or youtube.
2. FROM_NUMBER is your Twilio number
3. TO_NUMBER is the number you want to call. Keep in mind you need to do some verification meaning you can only call that number unless you show your goverment ID but dont quote me
4. NAME is what you want the program to refer to you as. IE: Hello NAME... when it calls you
5. THRESHHOLD is how many nodes do you want to fail before you recive a call
6. PROXMOX is the username you use to log into proxmox IE: `root@pam`
7. PROXMOX_TOKEN_NAME is `root@pam!TOKENNAME`. TOKENNAME is the TOKEN ID when creating an API token
8. PROXMOX_TOKEN_VALUE is the proxmox API token secret. Datacenter > Permissions > API Tokens > Secret
   
