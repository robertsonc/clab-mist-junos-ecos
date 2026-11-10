# October 2026 change scripts

One-off scripts behind the Oct 2026 changes, run from the repo root (they import
`scripts/mist_api.py`, `scripts/orch_api.py`, `scripts/junos.py`). Each wrote a
before-copy under `configs/<change>-<date>/` (serials, MACs, PSKs and emails
redacted in git).

| Script | Change |
|---|---|
| `nac_rollout.py`, `nac_pull.py`, `nac_check.sh`, `s1radius.py` | Mist NAC MAB on the CORP VMs (GBP 10001/10002) |
| `mist_borders.py`, `pull.py` | EC-facing border config copied to TROY / MARATHON |
| `subshare.py`, `seg_routes.py`, `corpdef.py` | EC segment route sharing and CORP default route |
| `wanzone.py` | EC wan0/wan1 into the WAN zone |
| `cli.py`, `ec.py`, `mapchk.py`, `vxchk.py` | Orchestrator CLI and check helpers |
| `vrrpchk.py` | Fabric-wide VRRP check (none configured) |
| `recover_ma_ac.sh` | Recover MA-ac-01/02 after a hung vJunos reboot (run as root on t430) |
