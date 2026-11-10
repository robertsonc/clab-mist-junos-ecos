#!/bin/bash
# Deploy the GBP test far end on t430-srv-03. Run as root:  sudo bash gbpt_up.sh
# Puts enp12s0f0 (-> EX4400 ge-0/0/7) and enp12s0f1 (-> EX4400 ge-0/0/6) into host
# bridges, then deploys gbpt.clab.yml. Touches nothing in the greek fabric.
set -eux
cd "$(dirname "$0")"
for pair in br-gbpt-up:enp12s0f0 br-gbpt-host:enp12s0f1; do
  br=${pair%%:*}; nic=${pair##*:}
  ip link show $br >/dev/null 2>&1 || ip link add $br type bridge stp_state 0
  ip link set $nic mtu 9000
  ip link set $br mtu 9000
  ip link set $nic master $br
  ip link set $nic up
  ip link set $br up
done
containerlab deploy -t gbpt.clab.yml --reconfigure
for v in gbpt-vj0 gbpt-h1; do ip link set $v mtu 9000 || true; done
echo "done - gbpt-vjunos takes ~10-15 min to boot"
