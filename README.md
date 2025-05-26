# Server Down Detector With Alert
I wanted a system to give me a notification when my servers when down. I opted for an actual call because I will not miss a phone call.
Lets start off with why I made this. I made this because I accidentally brought down my cluster of servers twice. Once was my APC backup battery failed, and another was when accidentally brought down my APC unbeknownst to me. I had conceived of this ages ago but didn't follow through. It was on the 2nd time I accidentally brought down the cluster did I began my work on this on May 6 2025. 

# How It Works
You need
1. A Linux node to be monitored
2. A VM in the cloud (I used a Oracle machine)
3. Tailscale
4. Use systemd-networkd.service for your networking
5. An SBC like an RPI
6. Twilio Account
7. Access to the internet (Duh)
8. (Optional) APC UPS Backup Battery

The cloud VM has a web server. It essentially is the brain for this alert system and needs to be running 24/7. I chose to use an Oracle free VM because it almost never it only goes down except for server migration and dangerous weather. Both of which you will receive emails ahead of time from Oracle. Every second, the node you want to be monitored sends a post to the cloud VM's web server. If the node does not send a post request for 20 seconds, the node is considered to have failed. If a certain number of nodes have failed in 1 hour, an alert call will be placed. 
When a node shuts down, it sends a post request to a local machine (the SBC) as a proxy using socat, which is then redirected to the cloud VM web server. This is how the server knows this is not an unscheduled shutdown. 
The optional feature is the battery reporting. Since I operate a Proxmox cluster, this part may vary for you. I attached my APC UPS Backup battery to my SBC running the proxy. The SBC using apcupsd sends the status of the battery to the cloud VM every 5 seconds. When the power goes out and the backup battery is used the battery, the cloud VM receives this change in battery status, shuts down a list of Proxmox nodes using Proxmox API, then sends out an emergency call. 
There is 3 different calls all with slightly different information if the internet goes out, if the power goes out, and one in general.

The special part was how I got the nodes to send out a POST request on shutdown. I exited the systemctl systemd-networkd.service file directly and an ExecStop command. Weirdly enough, the tailscale network adapter would shut down before the LAN adapter shut down, resulting in the need for the local proxies. 
