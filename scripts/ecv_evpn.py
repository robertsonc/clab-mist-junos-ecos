#!/usr/bin/env python3
"""EVPN peering from the EC-Vs to the Mist border leaves - EC side ONLY.

The Mist side is already built and is NOT touched here. Every value below is
copied from what Mist pushes to the borders (GET .../devices/{id}/config_cmd),
so this script makes the ECs match the borders, never the other way round:

    protocols bgp group ec_sdwan  type external, multihop ttl 2,
                                  family evpn signaling, local-address <lo0>,
                                  local-as <border asn>,
                                  neighbor 198.19.<idx>.<1|2> peer-as <EC asn>
    routing-options static        198.19.<idx>.<n>/32 via the EC's lan /31
    <vrf> evpn interconnect       vrf-target target:65000:100<1|2|3>
    <vrf> ip-prefix-routes vni    corp 11384125 / guest 11581948 / iot 16751755

What changes on each EC:

  1. Static /32s to both border loopbacks, in the Default segment. Without
     them the multihop session has no route to its peer: the ECs only know
     their connected /31s, and nothing else advertises 10.254.x to them.
  2. Default segment (0): ASN -> the site EC ASN Mist expects, and the old
     IPv4 neighbors (10.<idx>.x.1, AS 645xx - nothing on the borders answers
     them) are replaced by two EVPN neighbors at the border loopbacks.
  3. CORP/GUEST/IOT segments (3/6/7): BGP on, same ASN, and import/export
     route-target equal to the border's interconnect vrf-target.

     The route-target goes in TWO maps, as the GUI writes it:
       Default segment  route_target {"<seg>": {self: <seg>, import, export}}
       the segment      route_target {"0":     {self: 0,     import, export}}
     The segment's own map is keyed "0"; keyed by its own id it is a 400.
     Without it the segment shows no RT.
     remote_as_path_advertise is on for all three, so routes shared over the
     SD-WAN keep their AS path (IoT was arriving at the borders with only the
     EC's ASN).
  4. Both EVPN neighbors export through ec0<N>_to_campus (ecv-01 -> ec01,
     ecv-02 -> ec02). The maps live in Orchestrator's Default Template Group:
     they permit SD-WAN-learned and local routes, MED 100 / 200 so the campus
     prefers ecv-01 like the SD-WAN side does (metric 91 / 92), and deny routes
     learned from the borders so one border's routes are not reflected to the
     other.

The segment -> VNI map (/vxlan/segVniMap) already matches the borders' type-5
VNIs on all six, so it is checked, not written.

    python3 scripts/ecv_evpn.py                       # dry run, all six
    python3 scripts/ecv_evpn.py --name TH-ecv-01      # dry run, one
    python3 scripts/ecv_evpn.py --name TH-ecv-01 --yes
    python3 scripts/ecv_evpn.py --verify              # read back, change nothing

Before-state of each EC is saved under configs/ecv-evpn-<date>/ on --yes.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orch_api  # noqa: E402

# site -> (index, EC ASN, [(bd-01 lo0, asn), (bd-02 lo0, asn)])
# EC ASN is the `peer-as` in each site's Mist ec_sdwan group. Border lo0/ASN
# are the Mist underlay router-id / local-as.
SITES = {
    "TH": (5, 64532, [("10.254.100.1", 65100), ("10.254.100.2", 65101)]),
    "TR": (6, 64533, [("10.254.101.2", 65201), ("10.254.101.1", 65200)]),
    "MA": (7, 64534, [("10.254.102.2", 65301), ("10.254.102.1", 65300)]),
}

# EC segment id -> (name, Mist VRF interconnect route-target, type-5 VNI)
SEGMENTS = {
    3: ("CORP", "65000:1001", 11384125),
    6: ("GUEST", "65000:1003", 11581948),
    7: ("IOT", "65000:1002", 16751755),
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ec_plan(hostname):
    """Intended config for one EC, derived from the same addressing as
    gen_ecv_preconfigs.py: ecv-0N lan0 -> bd-01, lan1 -> bd-02."""
    prefix, num = hostname.split("-ecv-")
    num = int(num)
    idx, asn, borders = SITES[prefix]
    base = (num - 1) * 2
    loopback = "198.19.%d.%d" % (idx, num)
    peers = []
    for i, (lo, basn) in enumerate(borders):
        peers.append({"ip": lo, "asn": basn, "lan": "lan%d" % i,
                      "nhop": "10.%d.%d.1" % (idx, base + i),
                      "border": "%s-vjunos-bd-%02d" % (prefix, i + 1)})
    return {"asn": asn, "rtr_id": loopback, "peers": peers,
            "rtmap_out": "ec%02d_to_campus" % num}


def rest(env, ne, method, url, body=None):
    r = orch_api.call(env, method, "appliance/rest?nePk=%s&url=%s" % (ne, url), body)
    if isinstance(r, dict) and ("_http_error" in r or "_error" in r):
        raise SystemExit("%s %s on %s failed: %s" % (method, url, ne, r))
    return r


def neighbor(p, rtmap_out):
    return {"self": p["ip"], "remote_as": p["asn"], "enable": True,
            "evpn": True, "directly_connected": False, "lcl_interface": "lo0",
            "type": "Branch", "next_hop_self": False, "as_override": False,
            "bfd_desired": False, "store_received_routes": True,
            "password": "", "ka": 30, "hold": 90,
            "rtmap_inbound": "default_rtmap_bgp_inbound_br",
            "rtmap_outbound": rtmap_out}


def check(env, ne, plan):
    """List of human-readable differences between the EC and the plan."""
    diffs = []
    bgp = rest(env, ne, "GET", "/bgp/config/vrfs/all/system")
    seg0 = bgp.get("0", {})
    if seg0.get("asn") != plan["asn"] or seg0.get("rtr_id") != plan["rtr_id"] \
            or not seg0.get("enable"):
        diffs.append("seg 0: asn=%s rtr_id=%s enable=%s"
                     % (seg0.get("asn"), seg0.get("rtr_id"), seg0.get("enable")))
    nbrs = seg0.get("neighbor", {})
    want = {p["ip"]: p for p in plan["peers"]}
    for ip in sorted(set(nbrs) - set(want)):
        diffs.append("seg 0: stale neighbor %s (AS %s)" % (ip, nbrs[ip].get("remote_as")))
    for ip, p in want.items():
        n = nbrs.get(ip)
        if not n:
            diffs.append("seg 0: missing EVPN neighbor %s (%s)" % (ip, p["border"]))
        elif (n.get("remote_as"), n.get("evpn"), n.get("lcl_interface"), n.get("rtmap_outbound")) \
                != (p["asn"], True, "lo0", plan["rtmap_out"]):
            diffs.append("seg 0: neighbor %s as=%s evpn=%s lcl=%s out=%s"
                         % (ip, n.get("remote_as"), n.get("evpn"), n.get("lcl_interface"),
                            n.get("rtmap_outbound")))
    for sid, (name, rt, _vni) in SEGMENTS.items():
        s = bgp.get(str(sid), {})
        got = seg0.get("route_target", {}).get(str(sid), {})
        own = s.get("route_target", {}).get("0", {})
        if (s.get("asn"), s.get("enable"), got.get("import"), got.get("export"),
                own.get("import"), own.get("export"), s.get("remote_as_path_advertise")) \
                != (plan["asn"], True, rt, rt, rt, rt, True):
            diffs.append("seg %d %s: asn=%s enable=%s rt seg0=%s/%s own=%s/%s as_path_adv=%s"
                         % (sid, name, s.get("asn"), s.get("enable"),
                            got.get("import"), got.get("export"),
                            own.get("import"), own.get("export"),
                            s.get("remote_as_path_advertise")))
    vni = rest(env, ne, "GET", "/vxlan/segVniMap")
    for sid, (name, _rt, want_vni) in SEGMENTS.items():
        if vni.get(str(sid), {}).get("vni") != want_vni:
            diffs.append("seg %d %s: VNI %s, borders use %s (NOT auto-fixed)"
                         % (sid, name, vni.get(str(sid), {}).get("vni"), want_vni))
    routes = rest(env, ne, "GET", "/subnets3/all/vrfs/0")
    have = {(e["state"]["prefix"], e["state"]["nextHop"])
            for e in routes["subnets"]["entries"]}
    for p in plan["peers"]:
        if (p["ip"] + "/32", p["nhop"]) not in have:
            diffs.append("route: missing %s/32 via %s %s" % (p["ip"], p["nhop"], p["lan"]))
    return diffs


def apply(env, ne, hostname, plan, outdir):
    before = {u: rest(env, ne, "GET", u) for u in
              ("/bgp/config/vrfs/all/system", "/vxlan/segVniMap", "/subnets3/all/vrfs/0")}
    with open(os.path.join(outdir, "%s-before.json" % hostname), "w") as fh:
        json.dump(before, fh, indent=1)

    # 1. Reachability to the border loopbacks first, so the session can form
    #    as soon as the neighbor exists. addMultiple adds; it never removes.
    routes = {"%s/32" % p["ip"]: {"nhop": {p["nhop"]: {"interface": {p["lan"]: {
        "metric": 50, "dir": "ANY",
        "comment": "%s lo0 - EVPN peer" % p["border"]}}}}} for p in plan["peers"]}
    rest(env, ne, "POST", "/subnets3/configured/addMultiple", routes)

    # 2. Default segment: ASN + router-id, then replace the neighbor set.
    seg0 = before["/bgp/config/vrfs/all/system"]["0"]
    rest(env, ne, "POST", "/bgp/config/vrfs/0/system", {
        "asn": plan["asn"], "enable": True, "rtr_id": plan["rtr_id"],
        "graceful_restart_en": seg0.get("graceful_restart_en", False),
        "log_nbr_msgs": seg0.get("log_nbr_msgs", True),
        "max_restart_time": seg0.get("max_restart_time", 120),
        "stale_path_time": seg0.get("stale_path_time", 150),
        "remote_as_path_advertise": seg0.get("remote_as_path_advertise", False),
        "route_target": dict(seg0.get("route_target", {}), **{
            str(sid): {"self": sid, "import": rt, "export": rt}
            for sid, (_n, rt, _v) in SEGMENTS.items()})})
    rest(env, ne, "POST", "/bgp/config/vrfs/0/neighbor",
         {p["ip"]: neighbor(p, plan["rtmap_out"]) for p in plan["peers"]})
    # The passthrough refuses DELETE (403), so stale neighbors go via the
    # POST-shaped deleteMultiple, which acts on the Default segment.
    stale = sorted(set(rest(env, ne, "GET", "/bgp/config/vrfs/0/neighbor"))
                   - {p["ip"] for p in plan["peers"]})
    if stale:
        rest(env, ne, "POST", "/bgp/config/neighbor/deleteMultiple", stale)

    # 3. VRF segments: BGP on, plus the segment's own route-target (keyed "0").
    for sid, (_n, rt, _v) in SEGMENTS.items():
        cur = before["/bgp/config/vrfs/all/system"].get(str(sid), {})
        rest(env, ne, "POST", "/bgp/config/vrfs/%d/system" % sid, {
            "asn": plan["asn"], "enable": True, "rtr_id": plan["rtr_id"],
            "graceful_restart_en": cur.get("graceful_restart_en", False),
            "log_nbr_msgs": cur.get("log_nbr_msgs", True),
            "max_restart_time": cur.get("max_restart_time", 120),
            "stale_path_time": cur.get("stale_path_time", 150),
            "remote_as_path_advertise": True,
            "route_target": {"0": {"self": 0, "import": rt, "export": rt}}})


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", action="append",
                    help="EC hostname; repeatable. Default: all six")
    ap.add_argument("--yes", action="store_true", help="apply (default is dry run)")
    ap.add_argument("--verify", action="store_true", help="read back only")
    args = ap.parse_args()

    names = args.name or sorted(orch_api.ALLOWED_HOSTNAMES)
    bad = set(names) - orch_api.ALLOWED_HOSTNAMES
    if bad:
        raise SystemExit("refusing non-fabric appliances: %s" % ", ".join(sorted(bad)))

    env = orch_api.load_env()
    nepk = {a["hostName"]: a["nePk"] for a in orch_api.call(env, "GET", "appliance")
            if a.get("hostName") in orch_api.ALLOWED_HOSTNAMES}
    outdir = os.path.join(ROOT, "configs", "ecv-evpn-%s" % datetime.date.today())

    drift = 0
    for h in names:
        if h not in nepk:
            print("%-10s not in Orchestrator" % h)
            drift += 1
            continue
        plan = ec_plan(h)
        diffs = check(env, nepk[h], plan)
        print("%-10s %s  asn %d  peers %s" % (h, nepk[h], plan["asn"], ", ".join(
            "%s/AS%d via %s" % (p["ip"], p["asn"], p["lan"]) for p in plan["peers"])))
        for d in diffs:
            print("    - " + d)
        if not diffs:
            print("    ok")
            continue
        if args.verify or not args.yes:
            drift += 1
            continue
        os.makedirs(outdir, exist_ok=True)
        apply(env, nepk[h], h, plan, outdir)
        after = check(env, nepk[h], plan)
        print("    applied; %s" % ("ok" if not after else "STILL DIFFERS:"))
        for d in after:
            print("    ! " + d)
        drift += bool(after)
    if not args.yes and not args.verify and drift:
        print("\ndry run - re-run with --yes to apply")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
