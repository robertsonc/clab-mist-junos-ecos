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

.venv/bin/python scripts/mist_site_create.py --yes      # create sites + DNS/VRF CLI (BEFORE claiming)
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

The working fix points the resolver at a **public** address reachable *through the
VRF*, rather than the QEMU SLIRP forwarder at `10.0.0.3` that is only reachable
from `inet.0`. These four go in configuration group `top` — the same group Mist
uses for Dedicated Management VRF — because Mist sets equivalent values itself,
so they survive when it rewrites that group:

```
set groups top system commit no-delta-synchronize
set groups top system services outbound-ssh routing-instance mgmt_junos
set groups top system management-instance
set groups top system name-server 8.8.8.8 routing-instance mgmt_junos
set apply-groups top
```

Note this **keeps** `management-instance`. Deleting it also works, but it fights
Mist once the switch is adopted and Dedicated Management VRF is enabled.

### …and neither are the static host mappings

The name-server line above gets the **first** resolution done, so a switch adopts
fine and looks completely healthy. But outbound-ssh's *reconnect* path calls
`getaddrinfo()` — libc, reading `/var/etc/resolv.conf`, a file with no
routing-instance annotation. That query leaves via `inet.0`, which has no routes
here. So the first connection works and every reconnection fails:

```
outbound_ssh_connect_to_server: (mist) Connecting to server: oc-term.ac2.mist.com:2200
outbound_ssh_populate_address_info: (mist) getaddrinfo() failed for:
    oc-term.ac2.mist.com: error 8 (Name does not resolve)
```

This is latent until something drops a session — then that switch retries every
60s forever and never returns. It took out all 23 adopted switches at once when
their sessions dropped together, hours after everything looked green.

`oc-term.ac2.mist.com` is an AWS ELB with several addresses, pinned to remove DNS
from the reconnect path entirely:

```
set groups greek-dns system static-host-mapping oc-term.ac2.mist.com inet 3.218.167.152
set groups greek-dns system static-host-mapping oc-term.ac2.mist.com inet 98.94.119.178
set groups greek-dns system static-host-mapping oc-term.ac2.mist.com inet 44.218.238.151
set apply-groups greek-dns
```

These are bootstrap only: the durable copy lives in Mist. See "Mist must own the config" below.

If Mist ever moves that endpoint, refresh these from `getent hosts oc-term.ac2.mist.com`.

All of it is applied by `scripts/push_dns_fix.py`.

### Mist must own the config — nothing on the switch survives a push

This is the one that cost the most time: every earlier fix held for days and
then quietly vanished.

**Mist's config push replaces the whole config with what Mist intends.** Anything
Mist does not itself manage is deleted, whichever group it lives in. It first
went unnoticed as "Mist rewrites `top`", so the mappings were moved into our own
group `greek-dns`. That did not help, because Mist deleted `greek-dns` and its
`apply-groups` line as well, together with the `mgmt_junos` bindings in `top`.

Timeline of the 2026-09-19 MARATHON outage, from `show system commit` and
`show system rollback compare` on the switches:

1. 09-17 01:15 — `main-template` edited. TROY and THERMOPYLAE, connected, get the push.
2. MARATHON is down at the time (the previous outage), so its push stays pending.
3. 09-19 ~01:37 — `push_dns_fix.py` restores MARATHON and it reconnects.
4. Two minutes later Mist delivers the pending push, wiping everything
   `push_dns_fix.py` had just added. 7/8 go dark; MA-bd-01 survived only because
   its fix was re-run *after* its Mist push.
5. TROY and THERMOPYLAE look fine purely because Mist had nothing pending for
   them. Their next push, from any template, site or device edit, would have
   killed them the same way.

Because the outage only shows up on the switch's *next* session drop, it looks
unrelated to whatever caused it.

**The fix is to put the lines in Mist.** Since 2026-09-22 the three sites
carry them as site-setting `additional_config_cmds`. Mist then pushes them into
`system` on every push, so a push restores them instead of deleting them:

```
set system login idle-timeout 60                          # copied from main-template:
delete system login idle-timeout                          #   site-level additional_config_cmds
set groups top system login class <*> idle-timeout 60     #   REPLACES the template's list
set system management-instance
set system services outbound-ssh routing-instance mgmt_junos
set system name-server 8.8.8.8 routing-instance mgmt_junos
set system name-server 8.8.4.4 routing-instance mgmt_junos
set system static-host-mapping oc-term.ac2.mist.com inet 3.218.167.152
set system static-host-mapping oc-term.ac2.mist.com inet 98.94.119.178
set system static-host-mapping oc-term.ac2.mist.com inet 44.218.238.151
```

Consequences:

* **Rebuilding a site in Mist:** `mist_site_create.py` writes the lines when it
  creates a site, so run it *before* claiming. On existing sites it checks them,
  exits 1 on drift, and repairs with `--fix-cli --yes`. The lines themselves
  live in `scripts/mist_site_cli.py`, shared with `push_dns_fix.py`.
* **Editing `main-template`'s Additional CLI:** the three sites do not inherit it,
  because the site-level list overrides it. Copy the change into each site too.
* **`push_dns_fix.py` is bootstrap only**, for switches Mist cannot reach yet
  (first adoption, or a node that dropped before Mist had the lines). Mist
  deletes its `greek-dns` group on the first push, which is expected.
* To see what Mist will push, read
  `GET /sites/{site}/devices/{device}/config_cmd`. If the static host mappings
  are not in it, the next push removes them.

### Verify the effective config, not a group

`push_dns_fix.py --verify-only` reads `show configuration system | display
inheritance`, i.e. what is actually in effect, and requires all three mappings plus
the `mgmt_junos` bindings, along with an ESTABLISHED session to port 2200. An
earlier version checked for `apply-groups greek-dns`. That check was wrong both
before (the group could be present and empty) and after the move into Mist (the
group is absent on every healthy switch). Run it periodically, not only after a change, alongside a `mist_site_create.py` dry run
for the Mist side.

### Debugging this

Evidence lives in **`/var/log/outbound-ssh.log`** — the traceoptions file Mist
configures. `/var/log/messages` contains none of it, which makes the switch look
silent rather than failing.

Do **not** trust these as tests, they fail on perfectly healthy switches because
both query via the dead `inet.0`:

* `ping <host> routing-instance mgmt_junos`
* `show host <host>`

The only signal that means anything is an ESTABLISHED connection to port 2200,
which is what `push_dns_fix.py --verify-only` reports as `mist-session`.

### Renaming

On adoption Mist overwrites the device hostname with its MAC, so the portal
becomes a wall of hex. `mist_rename.py` recovers the mapping by asking each switch
what MAC Mist gave it — Mist rewrites the local config to
`outbound-ssh client mist device-id <org-uuid>.<mac>`, so the box carries its own
join key. Chassis MAC and `fxp0` MAC are both unrelated to what Mist displays.

`--site` is required and has no "all": an unscoped run against an org-wide API key
is how you touch devices you did not mean to.

## EC-V onboarding (preconfigs + approval)

`scripts/ecv_onboard.py` is self-contained (stdlib only) and does the whole
sequence. It deliberately does **not** depend on the external EC_SD-WAN_Expert
repo — that tool was used to discover this API, but redeploying this lab on
another host should not require it.

```bash
python3 scripts/gen_ecv_preconfigs.py       # generate the six YAMLs
python3 scripts/ecv_onboard.py validate     # check against Orchestrator, no writes
python3 scripts/ecv_onboard.py push         # create/update, validates each first
python3 scripts/ecv_onboard.py approve      # approve discovered EC-Vs
python3 scripts/ecv_onboard.py apply        # only needed if approve happened first
python3 scripts/ecv_onboard.py status --detail
```

**Order matters.** `autoApply` only fires when the appliance is discovered or
approved *while a matching preconfig already exists*. Push the preconfigs
**before** approving. If you approve first, nothing binds and you need the
explicit `apply` step.

### A preconfig that is too small is worse than none

The first version of these preconfigs carried only `applianceInfo` and four
interfaces. It validated cleanly, applied without error, and produced an
appliance at `state=Normal` that carried no traffic whatsoever — because with
no `businessIntentOverlays` there are **no overlay tunnels**, and with no
`segmentBgpSystems` the site's prefixes are never learned. Nothing looks wrong
until you check `GET /deployment?nePk=X` and find only `mgmt0`.

A complete preconfig needs all of:

| Section | Without it |
|---|---|
| `applianceInfo.group` | appliance lands ungrouped |
| `templateGroups` | no template application |
| `businessIntentOverlays` | **no overlay tunnels — the fabric never forms** |
| `ecLicensing` | no bandwidth tier |
| `deploymentInfo` | no data-plane interfaces |
| `segmentBgpSystems` | LAN prefixes never learned |
| `loopbackInterface` | no stable router-id |
| `segmentLocalRoutes` | no default route out |

### Silent-failure checks

`taskstatus=0`, `completionstatus=False`, `nepk=None`, `result=[]` on a preconfig
means it never bound to an appliance — it was never applied, regardless of how
healthy the appliance looks. That is the check that catches this.

A preconfig is staged **before** the appliance registers and matched by hostname
tag, so the EC-V self-configures on first contact. Stage them while the lab is
still booting and the appliances land fully built.

### API notes that each cost a failed request

**The schema is self-documenting — do not guess it.**
`GET /gms/appliance/preconfiguration/default` returns a ~3600-line YAML template
with inline comments for every field. `ecv_onboard.py template` saves it.

**Validate before pushing.** `POST /gms/appliance/preconfiguration/validate`
names the exact offending field (`YAML invalid, Unrecognized field: "hostname"`).
That error loop is how the schema was mapped. Top-level keys are only
`applianceInfo`, `deploymentInfo`, `templateGroups` and the other documented
sections — **not** `deployment`, `modeIfs`, `sysConfig`, `interfaces`, `hostname`.

**DHCP WAN interfaces** need `addressingMode: dhcpv4` with `ipAddressMask` and
`nextHop` left empty. `ipAddressMask: dhcp` is rejected.

**The field is `behindNat`**, lowercase "at" — the template's own comments spell
it `behindNAT`, and the comments are wrong.

**`interfaceLabel` is a label NAME** that must already exist in Orchestrator
(`GET /gms/interfaceLabels`), not a numeric id. Ours: wan `INET1`/`INET2`, lan `Data`.

**Updating a preconfig uses `preconfigId`, not `id`** — `PUT ...?id=` returns 400.

**Apply is multi-stage and reboots the appliance.** Watch it with
`GET /gms/appliance/preconfiguration/apply?preconfigId=X`, which returns a
per-section list. Order: Appliance Info -> Zones/labels/Segments -> license ->
deployment (interfaces) -> **reboot** -> template -> overlays -> routes -> BGP ->
loopback. The top-level `completionstatus` stays `False` until the last section
lands, and `GET /deployment` returns nothing at all mid-reboot — normal, not a
failure.

**Approval requires an empty JSON body.** This one is genuinely obscure:

```
POST /appliance/discovered/approve?id=<id>            -> HTTP 500
POST /appliance/discovered/approve?id=<id>  body {}   -> HTTP 200 "22.NE"
```

Same URL, same headers. Without a body it returns "There was an internal server
error", which reads like an Orchestrator fault rather than a malformed request.
On success it returns the new nePk. The `id` comes from
`GET /appliance/discovered` — not the serial, not the nePk.

**After a `containerlab destroy` + redeploy**, appliances re-register with new
serials and `discovered` accumulates ghosts. Approving one creates an appliance
that can never connect. `ecv_onboard.py approve` refuses when it sees duplicate
hostnames and prints their discovery times so you can tell live from stale.

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
