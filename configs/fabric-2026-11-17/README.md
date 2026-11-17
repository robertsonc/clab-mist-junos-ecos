# Greek fabric switch configs, 2026-11-17

Live pull from all 24 vJunos switches (TH / TR / MA: bd, co, di, ac × 2) plus the
Mist `additional_config_cmds` of each border. Pulled by `ops/2026-11/pull_configs.py`
(run on t430-srv-03) and redacted by `ops/2026-11/redact_configs.py`.

| File | Content |
|---|---|
| `<switch>.conf` | `show configuration` — the committed config as-is, Mist groups (`top`, …) unexpanded |
| `<switch>.set` | `show configuration \| display inheritance no-comments \| display set` — flattened, groups applied |
| `<border>-additional-cli.set` | Mist device-level additional CLI on each `bd-01/02` (EC peering, VRF type-5 export policy, etc.) |
| `site-<SITE>-additional-cli.set` | Mist site-level additional CLI, applied to every switch at that site (mgmt VRF, DNS, idle timeout) |

Border additional CLI is structurally identical on TH-bd-01/02 and TR-bd-01/02 (only
addresses/ASNs differ). Differences:

- **MA-bd-01**: `evpn_export_type5_corp_vrf term 01_default` (0.0.0.0/0 to type-5) is commented out.
- **MA-bd-01 / MA-bd-02**: one extra `firewall family any filter … term tag… then accept` term, left over from the GBP test.

Redacted: password/key hashes (`$9$`, `$6$`), SSH public keys, BGP authentication keys,
RADIUS secrets, Mist outbound-ssh secret and device-id, UUIDs. The only MAC left is the
anycast virtual gateway MAC (00:00:5e:…). Unredacted originals are kept outside the repo in
`~/labs/backups/greek-fabric-configs-unredacted/fabric-2026-11-17/`.
