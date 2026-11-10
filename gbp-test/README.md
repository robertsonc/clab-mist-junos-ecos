# VXLAN-GBP hardware test (EX4400)

Question: is the missing GBP tag in the greek fabric's VXLAN headers (G=0 on every
packet) a vJunos limitation? Answer: yes. A physical EX4400 with the same features
puts the tag in the header and on more EVPN routes than vJunos does.

## Setup

- EX4400 (house switch, not Mist-managed): `ex4400-gbpt.set`. MAC-based
  micro-segmentation filter tags `aa:c1:ab:77:00:01` with GBP 10001.
  `vxlan-gbp-profile` and `shared-tunnels` need a reboot.
- Far end on t430-srv-03: `gbpt.clab.yml` (FRR 10.2.1 + Linux VXLAN with `gbp`).
  Deploy with `sudo bash gbpt_frr_up.sh`.
- `gbpt-vjunos.*` / `gbpt_up.sh`: first attempt with a vJunos far end. It never
  finished booting on the loaded server; kept for reference.

## Results (2026-10-19)

Data plane, EX4400 -> FRR:

| Traffic | VNI | G bit | GBP id |
|---|---|---|---|
| Bridged, from the tagged host | 77001 | 1 | 10001 |
| Routed (type-5), from the tagged host | 77999 | 1 | 10001 |
| Any other MAC | 77001 | 0 | 0 |

GBP extended community (`0x0317`, value = tag) on routes for the tagged host:

| Route | EX4400 | vJunos (MA-ac-01) |
|---|---|---|
| Type 2 MAC only | 10001 | 10001 |
| Type 2 MAC+IP | 10001 | none |
| Type 5 /32 | 10001 | none |
| Type 5 /24 | none | none |

On vJunos the tag is control-plane only; every VXLAN packet goes out with G=0.

## tools/

Helpers used to drive the test. `exrun.py` runs CLI or scripts on the EX4400
via t430-srv-03; credentials come from `.env` over stdin and are never printed.
`vxgbp.py` decodes VXLAN flags and GBP id from a pcap. `gbp_*.py`, `hexchk.py`
and `q*.py` are the vJunos route-policy and host-originated experiments
(all negative).
