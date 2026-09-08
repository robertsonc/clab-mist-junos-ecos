# clab-mist-junos-ecos — Greek fabric

A three-site containerlab fabric of Juniper vJunos switches and Aruba EdgeConnect
(EC-V) SD-WAN appliances, adopted into Mist and Orchestrator.

    THERMOPYLAE    TROY    MARATHON

All three run on a **single host** and peer with each other over two local
software backbones. Each site is 8 vJunos switches in four tiers, an EC-V HA
pair, and two test hosts — 12 nodes per site, 36 in total.

## Topology

Per site, every tier dual-homed to the one above:

    ecv-01  ecv-02        SD-WAN HA pair
       \      /
    bd-01 -- bd-02        BORDER  (EC-V handoff + peer link)
      |  \  /  |
    co-01    co-02        CORE
      |  \  /  |
    di-01    di-02        DIST
      |  \  /  |
    ac-01    ac-02        ACCESS
      |        |
    vm-01    vm-02        hosts

Sites are stitched at the transport layer. Each runs its own `isp-a` (Internet)
and `isp-b` (MPLS) router, attached to the host bridges `br-isp-a` / `br-isp-b`.
Because all three sites share one host, that stitch never leaves the box: the
bridges have **no physical members** and there are no inter-host links.

    isp-a eth3 -> br-isp-a <- isp-a eth3   (the other two sites)
    isp-b eth3 -> br-isp-b <- isp-b eth3   (the other two sites)

## Addressing

| Site | Prefix | Lab name | Idx | Management | Host subnet | Backbone |
|---|---|---|---|---|---|---|
| THERMOPYLAE | `TH` | `greek-thermopylae` | 5 | `172.30.44.0/24` | `10.5.10.0/24` | `.5` |
| TROY | `TR` | `greek-troy` | 6 | `172.30.45.0/24` | `10.6.10.0/24` | `.6` |
| MARATHON | `MA` | `greek-marathon` | 7 | `172.30.46.0/24` | `10.7.10.0/24` | `.7` |

Backbones are `192.168.100.0/24` (ISP-A) and `10.100.0.0/24` (ISP-B); each site
takes its index in both.

The site index is load-bearing. Tooling derives the site from the **second octet**
of the host subnet `10.<site>.10.0/24`, and the management subnet must equal
`172.30.4<index-1>`. Those two have to agree — 5/6/7 is the range where they do.

Three things must stay unique per site or containerlab refuses to deploy, since
all three share one host:

* `name:` — two labs cannot share a name on one host
* `mgmt.network` — one Docker network cannot hold three subnets, so it is derived
  from the lab name rather than hardcoded
* bridge-side veth names — `th-ispa` / `tr-ispa` / `ma-ispa`

## Host requirements

Measured with all three sites up and healthy:

| | Three sites | Notes |
|---|---|---|
| RAM | ~184 GB | ~60 GB per site once booted and holding |
| CPU | ~67 load | oversubscribed on 56 threads; fine at idle, slow during boot |
| Disk | ~16 GB initially | grows toward ~88 GB per site as EC-V layers fill |

`/dev/kvm` is required. Put container storage on its own volume — the EC-V
writable layers reach 37–39 GB **each**, and with Docker's containerd snapshotter
that lands in `/var/lib/containerd`, not `/var/lib/docker`.

The bridges must exist before deploy. They are owned by `lab-transport.sh`,
installed as `lab-transport.service`; containerlab attaches to them and does not
create them.

## Generating and deploying

Topologies are generated — edit the generator, not the YAML:

```bash
python3 gen_greek_topology.py          # writes the three .clab.yml + dnsmasq configs
```

Deploy **sequentially**, not in parallel — 30 VMs booting at once will contend:

```bash
sudo containerlab deploy -t greek-fabric-thermopylae.clab.yml
sudo containerlab deploy -t greek-fabric-troy.clab.yml
sudo containerlab deploy -t greek-fabric-marathon.clab.yml
```

A site reaches all-healthy in roughly four minutes.

## Mist adoption

```bash
python3 -m venv .venv && .venv/bin/pip install paramiko
cp .env.example .env                       # fill in MIST_ORG_ID / MIST_API_KEY
# export the claim snippet from the portal as mist_claim_set.cfg

.venv/bin/python scripts/mist_site_create.py --yes      # create the three sites
.venv/bin/python scripts/push_mist.py --all             # claim all 24 switches
.venv/bin/python scripts/push_dns_fix.py --all          # REQUIRED - see below
.venv/bin/python scripts/push_dns_fix.py --all --verify-only   # confirm it landed

# adoption completes ~45s after the DNS fix; then:
.venv/bin/python scripts/mist_rename.py --site thermopylae --yes
.venv/bin/python scripts/mist_rename.py --site troy --yes
.venv/bin/python scripts/mist_rename.py --site marathon --yes
```

Run the `--verify-only` pass. A Junos commit that runs long returns nothing,
which older versions of `push_dns_fix.py` read as success - one switch silently
got no config while the script reported `commit=ok`, and the only symptom was
that node never adopting. The script now reads the config back and reports
`applied=` separately from `commit=`, but the verify pass is still the cheap way
to be sure before moving on to the renames.

`mist_rename.py` is safe to re-run: it prints `site=ok name=ok` for anything
already correct and only acts on what has changed. If a node shows
`not adopted yet (no device-id)`, re-run `push_dns_fix.py <ip>` for it and give
it a minute.

### The DNS fix is not optional

A stock vrnetlab vJunos node sets `system management-instance`, which binds `fxp0`
to the `mgmt_junos` VRF and leaves `inet.0` with **no default route at all**.

Binding outbound-ssh to the VRF is necessary but **not sufficient**:

```
set system services outbound-ssh routing-instance mgmt_junos
```

That fixes the SSH *transport*. Name resolution does not go through outbound-ssh —
the system resolver queries via `inet.0`, which is dead. So `oc-term.ac2.mist.com`
never resolves, outbound-ssh has nothing to dial, and adoption silently never
starts. The switch reports "claimed" and then sits there.

The working fix puts everything in configuration group `top` — the same group Mist
uses for Dedicated Management VRF — and points the resolver at a **public** address
reachable *through the VRF*, rather than the QEMU SLIRP forwarder at `10.0.0.3`
that is only reachable from `inet.0`:

```
set groups top system commit no-delta-synchronize
set groups top system services outbound-ssh routing-instance mgmt_junos
set groups top system management-instance
set groups top system name-server 8.8.8.8 routing-instance mgmt_junos
set apply-groups top
```

Applied via `scripts/push_dns_fix.py`. Adoption then completes in under a minute.

Note this **keeps** `management-instance`. Deleting it also works, but it fights
Mist once the switch is adopted and Dedicated Management VRF is enabled.

### Renaming

On adoption Mist overwrites the device hostname with its MAC, so the portal
becomes a wall of hex. `mist_rename.py` recovers the mapping by asking each switch
what MAC Mist gave it — Mist rewrites the local config to
`outbound-ssh client mist device-id <org-uuid>.<mac>`, so the box carries its own
join key. Chassis MAC and `fxp0` MAC are both unrelated to what Mist displays.

`--site` is required and has no "all": an unscoped run against an org-wide API key
is how you touch devices you did not mean to.

## EC-V sizing

Do not trim it. At the vrnetlab default of 1 vCPU / 4 GB the appliances lose their
management heartbeat and flap continuously in Orchestrator. 4 vCPU / 16 GB is
stable:

```yaml
env:
  ECOS_VCPU: "4"
  ECOS_RAM:  "16384"
```

This needs the patched `launch.py` — stock vrnetlab hardcodes `ram=4096` and never
passes `smp`, so older images ignore both variables silently.

vJunos sizing is **not** settable this way; it is hardcoded in vrnetlab's
`launch.py` (`ram=5120`, `smp=4`).

## Secrets

This repo is public. These are gitignored and must never be committed:

| File | Why |
|---|---|
| `.env` | Mist and Orchestrator API keys, EC-V registration key |
| `configs/ecos.env` | EC-V admin password and registration key |
| `mist_claim_set.cfg` | org device-id, outbound-ssh secret, password hash, SSH key |

Templates are provided as `.env.example` and `mist_claim_set.cfg.example`.
`JUNOS_USER` / `JUNOS_PASSWORD` default to vrnetlab's built-ins and are
overridable via the environment.
