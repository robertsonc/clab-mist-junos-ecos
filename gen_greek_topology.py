#!/usr/bin/env python3
"""Generate the THERMOPYLAE / TROY / MARATHON containerlab topologies.

SELF-CONTAINED FABRIC. All three sites run on ONE host (t430-srv-03) and peer
only with each other. This generator deliberately knows nothing about Sites
1/2/3 or the hosts they run on - it cannot emit or reference them, which is the
point: those sites are live and must not be disturbed by anything here.

    THERMOPYLAE -> greek-fabric-thermopylae.clab.yml
    TROY        -> greek-fabric-troy.clab.yml
    MARATHON    -> greek-fabric-marathon.clab.yml

containerlab cannot put three labs in one topology, so each site is its own
topology and they are stitched locally: every site runs its OWN isp-a and isp-b,
attached to the host bridges `br-isp-a` / `br-isp-b`. Because all three sites
share one host that stitch never leaves the box - those bridges have no physical
members and there are no inter-host links. Owned by lab-transport.service.

Three things MUST stay unique per site or containerlab refuses to deploy. All
three are latent bugs in the multi-host generator this was derived from, which
only ever ran one campus site per host:

  * `name:`                 - two labs cannot share a name on one host
  * `mgmt.network`          - one Docker network cannot hold three subnets, so
                              it is derived from the lab name, not hardcoded
  * bridge-side veth names  - th-ispa / tr-ispa / ma-ispa, from the prefix

Site indices are 5/6/7, not 1/2/3, because tooling derives the site number from
the SECOND OCTET of the host subnet 10.<site>.10.0/24 and the management subnet
follows 172.30.4<site-1>. Those two must agree, and 5/6/7 is the range where
they do without colliding with anything already allocated.

Per site, four switch tiers of two, plus an EC-V HA pair and two hosts:

    border  bd-01 bd-02      <- EC-V LAN handoff, border peer link
    core    co-01 co-02
    dist    di-01 di-02
    access  ac-01 ac-02      <- hosts

Run:  python3 gen_greek_topology.py
"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
TIER_ROLE = {"bd": "border", "co": "core", "di": "dist", "ac": "access"}

# Transport backbone joining every site, carried over the 10G links.
# A /24 rather than a /30 so a third site (and a fourth) just takes the next
# address instead of forcing a renumber.
ISPA_BB = "192.168.100"   # site1 .1, site2 .2, dc .3
ISPB_BB = "10.100.0"      # site1 .1, site2 .2, dc .3

# Campus sites are four tiers; the DC is border -> spine -> leaf, no core/dist.
CAMPUS_TIERS = ["bd", "co", "di", "ac"]
DC_TIERS = ["br", "sp", "lf"]

TIER_ROLE = {
    "bd": "border", "co": "core", "di": "dist", "ac": "access",
    "br": "border", "sp": "spine", "lf": "leaf",
}

SITES = {
    # Site index (the 5/6/7 below) is load-bearing: tooling reads the site from
    # the second octet of hostnet, and mgmt must equal 172.30.4<index-1>.
    "thermopylae": {
        "prefix": "TH",
        "labname": "greek-thermopylae",
        "host": "t430-srv-03",
        "tiers": CAMPUS_TIERS,
        "mgmt": "172.30.44",       # = 172.30.4(5-1)
        "ispa": (109, 110),        # /24 per local EC-V on ISP-A
        "ispb": (9, 10),           # /24 per local EC-V on ISP-B
        "bb": 5,                   # our address in each backbone /24
        "hostnet": "10.5.10",      # site index 5
    },
    "troy": {
        "prefix": "TR",
        "labname": "greek-troy",
        "host": "t430-srv-03",
        "tiers": CAMPUS_TIERS,
        "mgmt": "172.30.45",       # = 172.30.4(6-1)
        "ispa": (111, 112),
        "ispb": (11, 12),
        "bb": 6,
        "hostnet": "10.6.10",      # site index 6
    },
    "marathon": {
        "prefix": "MA",
        "labname": "greek-marathon",
        "host": "t430-srv-03",
        "tiers": CAMPUS_TIERS,
        "mgmt": "172.30.46",       # = 172.30.4(7-1)
        "ispa": (113, 114),
        "ispb": (13, 14),
        "bb": 7,
        "hostnet": "10.7.10",      # site index 7
    },
}

# Deterministic ordering for route generation and docs. These three are the
# WHOLE fabric - peers() walks this list, so nothing outside it can be emitted.
SITE_ORDER = ["thermopylae", "troy", "marathon"]


def tag(site):
    """Filename / config suffix for a site."""
    return site


def peers(site):
    """Every other site - used to build backbone routes."""
    return [k for k in SITE_ORDER if k != site]



def sw(site, tier, num):
    return "%s-vjunos-%s-%02d" % (SITES[site]["prefix"], tier, num)


def ecv(site, num):
    return "%s-ecv-%02d" % (SITES[site]["prefix"], num)


def vm(site, num):
    return "%s-vm-%02d" % (SITES[site]["prefix"], num)


def mgmt(site, offset):
    return "%s.%d" % (SITES[site]["mgmt"], offset)


def switch_ip(site, tier, num):
    return mgmt(site, 20 + SITES[site]["tiers"].index(tier) * 2 + num)


def ecv_ip(site, num):
    return mgmt(site, 28 + num)


def vm_ip(site, num):
    return mgmt(site, 30 + num)


def header(site):
    s = SITES[site]
    return '''\
# =============================================================================
# Mist + EdgeConnect Fabric Lab - {prefix}
# =============================================================================
#
# GENERATED by gen_greek_topology.py - edit the generator, not this file.
#
# Runs on: {host}
#
# One site of a THREE-SITE SELF-CONTAINED FABRIC. All three run on this one
# host, so the transport stitch never leaves the box: this site's isp-a and
# isp-b attach to the local bridges `br-isp-a` / `br-isp-b`, and the other two
# sites' isp routers hang off the same two bridges. One L2 domain per transport,
# entirely in software.
#
#   isp-a eth3 -> br-isp-a <- isp-a eth3  (the other two sites)
#   isp-b eth3 -> br-isp-b <- isp-b eth3  (the other two sites)
#
# Those bridges have NO physical members and there are no inter-host links. This
# fabric is isolated by design and reuses backbone addressing independently of
# any other lab, so do not add uplinks without renumbering first.
#
# The bridges must already exist. They are owned by /opt/lab/lab-transport.sh,
# installed as lab-transport.service - do not hand-build them, and do not
# expect netplan to have them.
#
#   ISP-A backbone {ispa_bb}.0/24   this site .{bb}
#   ISP-B backbone {ispb_bb}.0/24   this site .{bb}
#
# TOPOLOGY - {tierlist}, two switches per tier,
# every tier dual-homed to the one above:
#
#      ecv-01  ecv-02        SD-WAN HA pair
#         \\      /
#      bd-01 -- bd-02        BORDER  (EC-V handoff + peer link)
#        |  \\  /  |
#      co-01    co-02        CORE
#        |  \\  /  |
#      di-01    di-02        DIST
#        |  \\  /  |
#      ac-01    ac-02        ACCESS
#        |        |
#      vm-01    vm-02        hosts
#
# PORT MAP - uniform on every switch:
#   ge-0/0/0, ge-0/0/1   northbound to the tier above
#                        (on BORDERS these are free - border is the top tier -
#                         so the core downlinks land here instead)
#   ge-0/0/2             border peer link (borders) / host port (access)
#   ge-0/0/3, ge-0/0/4   southbound to the tier below
#                        (on BORDERS: the EC-V lan handoff)
#
#   bd-01: ge-0/0/0,1 -> co-01,co-02   ge-0/0/3 = ecv-01 lan0, ge-0/0/4 = ecv-02 lan0
#   bd-02: ge-0/0/0,1 -> co-01,co-02   ge-0/0/3 = ecv-01 lan1, ge-0/0/4 = ecv-02 lan1
#
# -----------------------------------------------------------------------------
# EC-V NIC MAPPING (vrnetlab aruba_ecos 9.6.3.0) - do not reorder
#   eth0 = mgmt0 | eth1 = wan0 | eth2 = lan0 | eth3 = wan1 | eth4 = lan1
#   eth5 = ha    | eth6 = lan2 (unused here)
# Pinned by the launch script with `interface <name> mac address ethN` + reload,
# so it is deterministic rather than PCI-enumeration luck.
# -----------------------------------------------------------------------------
#
# RESOURCES (this site): {nsw} vJunos x (5 GB, 4 vCPU) + 2 EC-V x (16 GB, 4 vCPU)
#   = ~{ram} GB / ~{vcpu} vCPU. Note a host may run more than one site.
#   vJunos sizing is hardcoded in vrnetlab's launch.py. EC-V sizing is env-driven
#   (ECOS_VCPU / ECOS_RAM below) after patching the ecos launch.py - 1 vCPU / 4 GB
#   starved the appliances and they flapped in Orchestrator.
#
# ADDRESSING
#   Management  {mgmt}.0/24
#     bd .21 .22 | co .23 .24 | di .25 .26 | ac .27 .28 | ecv .29 .30 | vm .31 .32
#     isp-a .10  | isp-b .11
#   ISP-A (Internet)  192.168.{a0}.0/24 (ecv-01), 192.168.{a1}.0/24 (ecv-02)
#   ISP-B (MPLS)      10.100.{b0}.0/24 (ecv-01),  10.100.{b1}.0/24 (ecv-02)
#   Hosts             {hostnet}.0/24  vm-01 .11, vm-02 .12, gw .1
# =============================================================================

name: {labname}

mgmt:
  network: clab-{labname}
  ipv4-subnet: {mgmt}.0/24

topology:
  kinds:
    juniper_vjunosswitch:
      image: vrnetlab/juniper_vjunos-switch:26.2R1.7
    generic_vm:
      image: vrnetlab/aruba_ecos:9.6.3.0_107217
    linux:
      image: ghcr.io/hellt/network-multitool:latest

  nodes:

    # =========================================================================
    # LOCAL STITCH - pre-existing host bridges shared by all three sites.
    # These must exist before deploy; containerlab attaches to them, it does
    # not create them.
    # =========================================================================
    br-isp-a:
      kind: bridge
    br-isp-b:
      kind: bridge

'''.format(prefix=s["prefix"], labname=s["labname"], host=s["host"],
           mgmt=s["mgmt"], bb=s["bb"], hostnet=s["hostnet"],
           nsw=len(s["tiers"]) * 2,
           ram=len(s["tiers"]) * 2 * 5 + 32,
           vcpu=len(s["tiers"]) * 2 * 4 + 8,
           tierlist=" -> ".join(TIER_ROLE[t] for t in s["tiers"]),
           ispa_bb=ISPA_BB, ispb_bb=ISPB_BB,
           a0=s["ispa"][0], a1=s["ispa"][1], b0=s["ispb"][0], b1=s["ispb"][1])


def isp_block(site, which):
    """isp-a (Internet) or isp-b (MPLS) for one site.

    eth1/eth2 face the two local EC-V WAN interfaces; eth3 is the backbone
    uplink to every other site via the host bridge. Routes to each peer's
    transport subnets point across the backbone; the default route still exits
    eth0, so Orchestrator registration and licensing keep working over NAT.

    All sites' isp-a routers share one L2 backbone (br-isp-a over the 10G), so
    peers are directly reachable - no transit through a third site.
    """
    cfg = SITES[site]
    if which == "a":
        name, ip, nets = "isp-a", 10, cfg["ispa"]
        bb, pfx, desc, key = ISPA_BB, "192.168.%d", "Internet", "ispa"
    else:
        name, ip, nets = "isp-b", 11, cfg["ispb"]
        bb, pfx, desc, key = ISPB_BB, "10.100.%d", "MPLS", "ispb"

    execs = [
        "sysctl -w net.ipv4.ip_forward=1",
        "ip addr add %s.1/24 dev eth1" % (pfx % nets[0]),
        "ip addr add %s.1/24 dev eth2" % (pfx % nets[1]),
        "ip addr add %s.%d/24 dev eth3" % (bb, cfg["bb"]),
        "ip link set eth1 up",
        "ip link set eth2 up",
        "ip link set eth3 up",
    ]
    for peer in peers(site):
        pc = SITES[peer]
        for n in pc[key]:
            execs.append("ip route replace %s.0/24 via %s.%d dev eth3"
                         % (pfx % n, bb, pc["bb"]))
    execs += [
        "iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE",
        "iptables -A FORWARD -i eth1 -j ACCEPT",
        "iptables -A FORWARD -i eth2 -j ACCEPT",
        "iptables -A FORWARD -i eth3 -j ACCEPT",
        "iptables -A FORWARD -i eth0 -m state --state RELATED,ESTABLISHED -j ACCEPT",
        "apk add --no-cache dnsmasq",
        "dnsmasq",
    ]
    lines = "\n".join("        - %s" % e for e in execs)
    return '''
    # ISP-{U} / {desc} transport for this site.
    # eth1/eth2 -> local EC-V WANs, eth3 -> backbone to the other sites.
    isp-{l}:
      kind: linux
      mgmt-ipv4: {mgmt}.{ip}
      binds:
        - configs/isp-{l}-{tag}-dnsmasq.conf:/etc/dnsmasq.conf:ro
      exec:
{lines}
'''.format(U=which.upper(), desc=desc, l=which, mgmt=cfg["mgmt"], ip=ip,
           tag=tag(site), lines=lines)


def switch_block(site, tier, num):
    return '''
    {name}:
      kind: juniper_vjunosswitch
      mgmt-ipv4: {ip}
      group: {role}
      labels:
        site: {tag}
        role: {role}
'''.format(name=sw(site, tier, num), ip=switch_ip(site, tier, num),
           role=TIER_ROLE[tier], tag=tag(site))


def ecv_block(site, num):
    cfg = SITES[site]
    return '''
    {name}:
      kind: generic_vm
      mgmt-ipv4: {ip}
      group: sdwan
      labels:
        site: {tag}
        role: sdwan
      # Credentials come from a file, not the deploying shell's environment -
      # `${{VAR}}` expansion silently yields junk if the vars aren't exported.
      env-files:
        - configs/ecos.env
      env:
        ECOS_SITE_TAG: {sitetag}
        # 1 vCPU / 4 GB (the old hardcoded default) starves a real EC-V - the
        # appliance flaps in Orchestrator because it loses its management
        # heartbeat. 4 vCPU / 16 GB is the normal allocation.
        # Requires the env-aware launch.py; older images ignore these silently.
        ECOS_VCPU: "4"
        ECOS_RAM: "16384"
'''.format(name=ecv(site, num), ip=ecv_ip(site, num), tag=tag(site),
           sitetag=cfg["prefix"] if site == "dc" else "Site%s" % site)


def vm_block(site, num):
    cfg = SITES[site]
    return '''
    {name}:
      kind: linux
      image: ubuntu:24.04
      mgmt-ipv4: {ip}
      cmd: sleep infinity
      group: host
      labels:
        site: {tag}
        role: host
      exec:
        - >-
          bash -c "apt-get update -qq
          && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq
          iproute2 iputils-ping traceroute tcpdump iperf3 curl >/dev/null 2>&1
          && ip addr add {hostnet}.1{num}/24 dev eth1
          && ip link set eth1 up
          && ip route replace 10.0.0.0/8 via {hostnet}.1 dev eth1"
'''.format(name=vm(site, num), ip=vm_ip(site, num), tag=tag(site),
           hostnet=cfg["hostnet"], num=num)


def links(site):
    """Fabric wiring for one site.

    Tier list varies: campus sites are bd -> co -> di -> ac, the DC is
    br -> sp -> lf. Everything else is identical, so walk the list in pairs.
    """
    cfg = SITES[site]
    tiers = cfg["tiers"]
    top, bottom = tiers[0], tiers[-1]
    out = []

    for upper, lower in zip(tiers, tiers[1:]):
        out.append("\n    # %s <-> %s (each %s dual-homes to both %s)"
                   % (upper, lower, lower, upper))
        for ln in (1, 2):
            for un in (1, 2):
                # The TOP tier has no northbound switch links, so its ge-0/0/0
                # and ge-0/0/1 are free and the downlinks land there - leaving
                # ge-0/0/3 and ge-0/0/4 for the EC-V handoff. Every lower tier
                # keeps 0/1 northbound and 3/4 southbound.
                upper_port = (ln - 1) if upper == top else (2 + ln)
                out.append('    - endpoints: ["%s:ge-0/0/%d", "%s:ge-0/0/%d"]'
                           % (sw(site, lower, ln), un - 1,
                              sw(site, upper, un), upper_port))

    out.append("\n    # %s peer link (ESI-LAG / MC-LAG ICL toward the EC-Vs)"
               % TIER_ROLE[top].capitalize())
    out.append('    - endpoints: ["%s:ge-0/0/2", "%s:ge-0/0/2"]'
               % (sw(site, top, 1), sw(site, top, 2)))

    # ecv-01 -> ge-0/0/3, ecv-02 -> ge-0/0/4 on BOTH top-tier switches. lan0
    # always faces -01 and lan1 always faces -02, so one config template covers
    # both appliances and the two LAN paths stay independent.
    out.append("\n    # EC-V LAN handoff: lan0 (eth2) -> %s-01, lan1 (eth4) -> %s-02"
               % (top, top))
    for en in (1, 2):
        out.append('    - endpoints: ["%s:eth2", "%s:ge-0/0/%d"]'
                   % (ecv(site, en), sw(site, top, 1), 2 + en))
        out.append('    - endpoints: ["%s:eth4", "%s:ge-0/0/%d"]'
                   % (ecv(site, en), sw(site, top, 2), 2 + en))

    out.append("\n    # EC-V HA link (eth5 = ha)")
    out.append('    - endpoints: ["%s:eth5", "%s:eth5"]' % (ecv(site, 1), ecv(site, 2)))

    out.append("\n    # Hosts -> %s layer" % TIER_ROLE[bottom])
    for hn in (1, 2):
        out.append('    - endpoints: ["%s:eth1", "%s:ge-0/0/2"]'
                   % (vm(site, hn), sw(site, bottom, hn)))

    out.append("\n    # EC-V WAN -> local ISP routers")
    for en in (1, 2):
        out.append('    - endpoints: ["%s:eth1", "isp-a:eth%d"]  # wan0'
                   % (ecv(site, en), en))
        out.append('    - endpoints: ["%s:eth3", "isp-b:eth%d"]  # wan1'
                   % (ecv(site, en), en))

    # Bridge-side interface names must be unique per HOST, and here all three
    # sites share this host's br-isp-a / br-isp-b - hence th-/tr-/ma- prefixes.
    tag = cfg["prefix"].lower()
    out.append("\n    # Backbone to the other two sites, via the local bridges.")
    out.append("    # The bridge-side interface name must be unique on the host.")
    out.append('    - endpoints: ["isp-a:eth3", "br-isp-a:%s-ispa"]' % tag)
    out.append('    - endpoints: ["isp-b:eth3", "br-isp-b:%s-ispb"]' % tag)
    return "\n".join(out)


def dnsmasq(site, which):
    cfg = SITES[site]
    nets = cfg["ispa"] if which == "a" else cfg["ispb"]
    pfx = "192.168.%d" if which == "a" else "10.100.%d"
    desc = "Internet / wan0" if which == "a" else "MPLS / wan1"
    body = ["# ISP-%s (%s) DHCP - %s ONLY."
            % (which.upper(), desc, cfg["prefix"]),
            "# GENERATED by gen_greek_topology.py - do not hand-edit.",
            "#",
            "# One /24 per EC-V so each appliance gets a distinct transport subnet.",
            "# Only this site's two EC-Vs are here; every other site runs its own",
            "# isp-%s." % which,
            ""]
    for i, n in enumerate(nets, start=1):
        net = pfx % n
        body += ["# %s %s" % (ecv(site, i), "wan0" if which == "a" else "wan1"),
                 "interface=eth%d" % i,
                 "dhcp-range=eth%d,%s.10,%s.50,255.255.255.0,24h" % (i, net, net),
                 "dhcp-option=eth%d,3,%s.1" % (i, net),
                 "dhcp-option=eth%d,6,8.8.8.8,8.8.4.4" % i,
                 ""]
    return "\n".join(body)


def build(site):
    cfg = SITES[site]
    parts = [header(site), isp_block(site, "a"), isp_block(site, "b")]
    parts.append("\n    # ====================================================="
                 "====================\n    # %s FABRIC\n    # ================="
                 "========================================================\n"
                 % cfg["prefix"])
    for tier in cfg["tiers"]:
        parts.append("\n    # --- %s ---" % TIER_ROLE[tier].upper())
        for num in (1, 2):
            parts.append(switch_block(site, tier, num))
    parts.append("\n    # --- EdgeConnect Virtual HA pair ---")
    for num in (1, 2):
        parts.append(ecv_block(site, num))
    parts.append("\n    # --- Ubuntu test hosts ---")
    for num in (1, 2):
        parts.append(vm_block(site, num))
    parts.append("\n  links:\n")
    parts.append(links(site))
    parts.append("\n")
    return "".join(parts)


def main():
    for site in SITE_ORDER:
        path = os.path.join(ROOT, "greek-fabric-%s.clab.yml" % tag(site))
        with open(path, "w") as fh:
            fh.write(build(site))
        print("wrote %s" % os.path.relpath(path, ROOT))
        for which in ("a", "b"):
            cpath = os.path.join(ROOT, "configs",
                                 "isp-%s-%s-dnsmasq.conf" % (which, tag(site)))
            with open(cpath, "w") as fh:
                fh.write(dnsmasq(site, which))
            print("wrote %s" % os.path.relpath(cpath, ROOT))


if __name__ == "__main__":
    main()
