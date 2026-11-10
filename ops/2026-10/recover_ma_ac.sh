#!/bin/bash
# Recover MA-vjunos-ac-01 / ac-02 after a hung `request system reboot`
# (guest stuck on "128.0.0.1: No route to host"). Run on t430-srv-03 as root:
#   sudo bash recover_ma_ac.sh
# Procedure from mist_and_ec_fabric/HANDOFF.md: restore init.conf, restart the
# container (fresh qemu => fresh emulated PFE; overlay disk + Mist config survive),
# rebuild the clab veths, re-mirror tc on the peers, re-address the VMs.
set -eux
P=clab-greek-marathon
IMG=vrnetlab/juniper_vjunos-switch:26.2R1.7

[ -f /tmp/init.conf ] || { cid=$(docker create $IMG); docker cp "$cid:/init.conf" /tmp/init.conf; docker rm "$cid"; }

for n in MA-vjunos-ac-01 MA-vjunos-ac-02; do
  docker stop -t 5 $P-$n
  docker cp /tmp/init.conf $P-$n:/init.conf
  docker start $P-$n
done

# ge-0/0/N == ethN+1
veth() { containerlab tools veth create -m 9500 -a $P-$1 -b $P-$2; }
veth MA-vjunos-ac-01:eth1 MA-vjunos-di-01:eth4
veth MA-vjunos-ac-01:eth2 MA-vjunos-di-02:eth4
veth MA-vjunos-ac-01:eth3 MA-vm-01:eth1
veth MA-vjunos-ac-01:eth4 MA-vm-03:eth1          # hot-added 10-05, not in the topology file
veth MA-vjunos-ac-02:eth1 MA-vjunos-di-01:eth5
veth MA-vjunos-ac-02:eth2 MA-vjunos-di-02:eth5
veth MA-vjunos-ac-02:eth3 MA-vm-02:eth1

# re-point the vrnetlab peers' tc mirrors at the new veths
remirror() { docker exec $P-$1 sh -c "
  tc qdisc del dev eth$2 clsact 2>/dev/null; tc qdisc del dev tap$2 clsact 2>/dev/null
  ip link set tap$2 up; ip link set tap$2 mtu 65000
  tc qdisc add dev eth$2 clsact
  tc filter add dev eth$2 ingress flower action mirred egress redirect dev tap$2
  tc qdisc add dev tap$2 clsact
  tc filter add dev tap$2 ingress flower action mirred egress redirect dev eth$2"; }
remirror MA-vjunos-di-01 4; remirror MA-vjunos-di-02 4
remirror MA-vjunos-di-01 5; remirror MA-vjunos-di-02 5

# VM addressing (topology exec: only runs at deploy) + traffic generator
# The new veth has a new MAC; put the original back or Mist NAC (usermacs) misclassifies the VM.
vm() { docker exec $P-$1 bash -c "ip link set eth1 down; ip link set eth1 address $4; ip link set eth1 up; ip addr add $2/24 dev eth1; ip route replace 10.0.0.0/8 via $3 dev eth1"
       docker exec -d $P-$1 sh -c "nohup /usr/local/bin/vm_trafgen.sh >/dev/null 2>&1"; }
vm MA-vm-01 10.7.10.11 10.7.10.1 aa:c1:ab:de:7d:d4
vm MA-vm-02 10.7.10.12 10.7.10.1 aa:c1:ab:f5:a5:0d
vm MA-vm-03 10.7.12.11 10.7.12.1 $(docker exec $P-MA-vm-03 cat /sys/class/net/eth1/address)  # no usermac; keeps current
echo done - the vJunos guests take ~10-15 min to boot
