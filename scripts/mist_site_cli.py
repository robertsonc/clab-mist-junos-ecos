"""The DNS/VRF lines Mist must push to every switch in this fabric.

Single source of truth for mist_site_create.py (which writes them into each
site's settings in Mist) and push_dns_fix.py (which applies them on-box to
bootstrap a switch Mist cannot reach yet). Stdlib only - no paramiko.

WHY THEY LIVE IN MIST
Mist's config push replaces the whole config with what Mist intends, deleting
anything it does not manage, in whatever group it sits. On-box copies survive
only until the next push. On 2026-09-19 MARATHON lost them this way two minutes
after being fixed. As site-setting additional_config_cmds, Mist pushes them
itself. See README "Mist must own the config".
"""

# oc-term.ac2.mist.com is an AWS ELB. Pinned because outbound-ssh's reconnect
# path resolves via inet.0, which is dead on vrnetlab. Refresh from
# `getent hosts oc-term.ac2.mist.com` if Mist moves it.
OC_TERM = "oc-term.ac2.mist.com"
OC_TERM_IPS = ["3.218.167.152", "98.94.119.178", "44.218.238.151"]

MGMT_VRF = "mgmt_junos"

SITE_CLI = [
    "set system management-instance",
    "set system services outbound-ssh routing-instance %s" % MGMT_VRF,
    "set system name-server 8.8.8.8 routing-instance %s" % MGMT_VRF,
    "set system name-server 8.8.4.4 routing-instance %s" % MGMT_VRF,
] + [
    "set system static-host-mapping %s inet %s" % (OC_TERM, ip)
    for ip in OC_TERM_IPS
]

# A site-level additional_config_cmds list REPLACES the template's rather than
# appending to it, so the template's own lines must be carried into the site.
TEMPLATE_NAME = "main-template"


def merged(template_cmds):
    """Template lines first (as Mist would render them), then ours, no dupes."""
    out = []
    for line in list(template_cmds or []) + SITE_CLI:
        if line not in out:
            out.append(line)
    return out


def missing(site_cmds):
    """SITE_CLI lines absent from a site's current additional_config_cmds."""
    have = set(site_cmds or [])
    return [line for line in SITE_CLI if line not in have]
