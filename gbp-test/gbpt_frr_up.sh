set -eux; cd "$(dirname "$0")"
docker rm -f clab-gbpt-gbpt-vjunos 2>/dev/null || true
containerlab deploy -t gbpt.clab.yml --reconfigure
for v in gbpt-fr1 gbpt-h1; do ip link set $v mtu 9000 || true; done
