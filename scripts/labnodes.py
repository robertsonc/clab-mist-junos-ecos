"""Switch inventory for the THERMOPYLAE / TROY / MARATHON fabric.

GENERATED from gen_greek_topology.py - keep in step with it, do not hand-edit.

SCOPING GUARANTEE: this file lists ONLY the three sites on t430-srv-03. Sites
1/2/3 live on other hosts and are deliberately absent, so the Mist tooling that
imports SWITCHES from here cannot target them even if run without --site. That
is the point - do not add them back.

All three sites share this host, so unlike the original multi-host lab every
management subnet below is reachable locally and one run can cover all three.
"""
import os

# (clab name, mgmt IP, site label as it appears in Mist)
SWITCHES = [
    ("TH-vjunos-bd-01", "172.30.44.21", "THERMOPYLAE"),
    ("TH-vjunos-bd-02", "172.30.44.22", "THERMOPYLAE"),
    ("TH-vjunos-co-01", "172.30.44.23", "THERMOPYLAE"),
    ("TH-vjunos-co-02", "172.30.44.24", "THERMOPYLAE"),
    ("TH-vjunos-di-01", "172.30.44.25", "THERMOPYLAE"),
    ("TH-vjunos-di-02", "172.30.44.26", "THERMOPYLAE"),
    ("TH-vjunos-ac-01", "172.30.44.27", "THERMOPYLAE"),
    ("TH-vjunos-ac-02", "172.30.44.28", "THERMOPYLAE"),
    ("TR-vjunos-bd-01", "172.30.45.21", "TROY"),
    ("TR-vjunos-bd-02", "172.30.45.22", "TROY"),
    ("TR-vjunos-co-01", "172.30.45.23", "TROY"),
    ("TR-vjunos-co-02", "172.30.45.24", "TROY"),
    ("TR-vjunos-di-01", "172.30.45.25", "TROY"),
    ("TR-vjunos-di-02", "172.30.45.26", "TROY"),
    ("TR-vjunos-ac-01", "172.30.45.27", "TROY"),
    ("TR-vjunos-ac-02", "172.30.45.28", "TROY"),
    ("MA-vjunos-bd-01", "172.30.46.21", "MARATHON"),
    ("MA-vjunos-bd-02", "172.30.46.22", "MARATHON"),
    ("MA-vjunos-co-01", "172.30.46.23", "MARATHON"),
    ("MA-vjunos-co-02", "172.30.46.24", "MARATHON"),
    ("MA-vjunos-di-01", "172.30.46.25", "MARATHON"),
    ("MA-vjunos-di-02", "172.30.46.26", "MARATHON"),
    ("MA-vjunos-ac-01", "172.30.46.27", "MARATHON"),
    ("MA-vjunos-ac-02", "172.30.46.28", "MARATHON"),
]

ECVS = [
    ("TH-ecv-01", "172.30.44.29", "THERMOPYLAE"),
    ("TH-ecv-02", "172.30.44.30", "THERMOPYLAE"),
    ("TR-ecv-01", "172.30.45.29", "TROY"),
    ("TR-ecv-02", "172.30.45.30", "TROY"),
    ("MA-ecv-01", "172.30.46.29", "MARATHON"),
    ("MA-ecv-02", "172.30.46.30", "MARATHON"),
]

# vrnetlab's built-in defaults. Overridable via the environment so this file
# stays committable to a public repo - set JUNOS_USER / JUNOS_PASSWORD if the
# nodes are built with anything else.
JUNOS_USER = os.environ.get("JUNOS_USER", "admin")
JUNOS_PASSWORD = os.environ.get("JUNOS_PASSWORD", "admin@123")

# vrnetlab wires mgmt as QEMU user-mode (SLIRP) networking:
#   net=10.0.0.0/24, host=10.0.0.2, dns=10.0.0.3, guest=10.0.0.15
# External resolvers are unreachable over it; .3 is the built-in forwarder.
MGMT_GW = "10.0.0.2"
MGMT_DNS = "10.0.0.3"

# vrnetlab's init.conf sets `system management-instance`, which binds fxp0 to
# this VRF. Junos does the binding itself - there is no interface assignment in
# init.conf and none is possible. Anything that must egress fxp0 has to be told
# to use this instance explicitly.
MGMT_VRF = "mgmt_junos"


def by_ip(ip):
    for name, addr, site in SWITCHES:
        if addr == ip:
            return name, addr, site
    return None
