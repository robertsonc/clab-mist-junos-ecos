# usage: gbp_check.sh <mgmt-ip> [mac]
ssh -o BatchMode=yes t430-srv-03 "cd ~/labs/greek-fabric && .venv/bin/python -c \"
import sys; sys.path.insert(0,'scripts'); import junos
print(junos.cli('$1', ['show configuration forwarding-options evpn-vxlan', 'show system commit | match \\\"^ *0 \\\"', 'show system uptime | match booted', 'show ethernet-switching table ${2:-aa:c1:ab:de:7d:d4} detail | match \\\"MAC address|GBP|gbp|Tag|tag\\\"', 'show dot1x interface ge-0/0/2.0 | match ge-']))
\"" 2>&1 | grep -vE 'screen-|^$|^admin@'
