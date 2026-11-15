#!/usr/bin/env python3
"""EdgeConnect Virtual (EC-V) launcher for vrnetlab / containerlab.

Day-0 is delivered the way HPE documents it for KVM: a CloudInit ISO carrying
`spcustom.yml`, which ECOS reads on the first boot of a clean disk
("Deployment Guide: EdgeConnect-Virtual in a KVM Host using CloudInit").
ECOS applies the file itself and reboots itself, so this launcher never logs
in to the serial console and never types a credential into it.

Environment (all optional):

    ECOS_REGISTRATION_KEY   account key      } both needed to register with
    ECOS_ACCOUNT_NAME       account name     } the Cloud Portal
    ECOS_SITE_TAG           appliance tag Orchestrator shows on discovery
    ECOS_ADMIN_PASSWORD     replaces the default admin password
    ECOS_PORTAL_HOSTNAME    non-default Cloud Portal host
    ECOS_ROUTER_MODE        inline router mode, default "true"
    ECOS_NIC_MAP            default mgmt0:eth0,wan0:eth1,lan0:eth2,wan1:eth3,
                            lan1:eth4,lan2:eth6   (eth5 is left as ha)
    ECOS_READY_STABLE_SECS  seconds HTTPS must stay up before "healthy" (60)
    ECOS_BOOT_TIMEOUT_SECS  seconds before the node is reported stuck (1200)

Disk:

    /disk (bind mount)      if present, the VM overlay disk lives there instead
                            of in the container's writable layer
    ECOS_DISK_CACHE         QEMU cache mode, default "unsafe" (no host fsync:
                            fast, and a lab disk is disposable)
    ECOS_DISK_IF            "ide" (default, known to boot) or "virtio"

Sizing uses vrnetlab's generic QEMU_SMP / QEMU_MEMORY. ECOS_VCPU / ECOS_RAM
are still honoured as defaults so existing topologies keep working.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import signal
import socket
import ssl
import subprocess
import sys
import time
from types import FrameType

import vrnetlab

LOG = logging.getLogger("ecos")

CLOUDINIT_DIR = "/cloudinit"
CLOUDINIT_FILE = os.path.join(CLOUDINIT_DIR, "spcustom.yml")  # name is fixed by ECOS
CLOUDINIT_ISO = "/spcustom.iso"

DEFAULT_NIC_MAP = "mgmt0:eth0,wan0:eth1,lan0:eth2,wan1:eth3,lan1:eth4,lan2:eth6"
DEFAULT_VCPU = 4        # 1 vCPU / 4 GB loses the Orchestrator heartbeat
DEFAULT_RAM_MB = 16384

DISK_DIR = "/disk"                 # optional bind mount for the overlay
OWNER_TOKEN = "/.ecos-disk-owner"  # lives in the container layer on purpose
DISK_CACHE_MODES = ("unsafe", "writeback", "none", "writethrough", "directsync")
DISK_INTERFACES = ("ide", "virtio")

HTTPS_PROBE_INTERVAL = 5.0
HTTPS_PROBE_TIMEOUT = 3.0

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
_KEY_RE = re.compile(r"^[A-Za-z0-9+/=_-]+$")
_NIC_RE = re.compile(r"^[a-z]+[0-9]+$")


class ConfigError(ValueError):
    """An environment value cannot be written into spcustom.yml safely."""


def handle_sigchld(_sig: int, _frame: FrameType | None) -> None:
    os.waitpid(-1, os.WNOHANG)


def handle_sigterm(_sig: int, _frame: FrameType | None) -> None:
    sys.exit(0)


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not an integer") from exc
    if value <= 0:
        raise ConfigError(f"{name}={raw!r} must be positive")
    return value


def find_disk_image(directory: str = "/") -> str:
    """Return the base qcow2, never the overlay vrnetlab creates next to it.

    A plain "first *.qcow2" match can pick `<name>-overlay.qcow2` after a
    container restart and stack an overlay on an overlay.
    """
    candidates = sorted(
        e for e in os.listdir(directory)
        if e.endswith(".qcow2")
        and not e.endswith("-overlay.qcow2")
        and not e.startswith("clab-")
    )
    if not candidates:
        raise FileNotFoundError(f"no base .qcow2 image in {directory}")
    return os.path.join(directory, candidates[0])


def env_choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = os.getenv(name, "").strip().lower() or default
    if value not in allowed:
        raise ConfigError(f"{name}={value!r} must be one of {', '.join(allowed)}")
    return value


def prepare_disk_dir(base_image: str, disk_dir: str = DISK_DIR,
                     token_file: str = OWNER_TOKEN) -> str:
    """Return the path vrnetlab should treat as the base image.

    vrnetlab writes the overlay next to the base image. Presenting the base
    through a symlink in `disk_dir` therefore lands the overlay on the bind
    mount, off the container's writable layer.

    A bind mount outlives the container, and ECOS reads spcustom.yml only on
    the first boot of a clean disk. An overlay left by a previous deploy would
    boot with the old NIC MAC pinning and ignore the new day-0, so it is
    discarded unless it belongs to this container. Ownership is a random token
    kept in the container layer: a restart keeps it, a redeploy does not.
    """
    if not os.path.isdir(disk_dir):
        return base_image
    marker = os.path.join(disk_dir, ".owner")
    mine = theirs = None
    if os.path.exists(token_file):
        with open(token_file) as fh:
            mine = fh.read().strip()
    if os.path.exists(marker):
        with open(marker) as fh:
            theirs = fh.read().strip()
    if mine is None or mine != theirs:
        for entry in os.listdir(disk_dir):
            if entry.endswith(".qcow2"):
                LOG.info("discarding disk from an earlier deploy: %s", entry)
                os.remove(os.path.join(disk_dir, entry))
        mine = secrets.token_hex(16)
        for path in (token_file, marker):
            with open(path, "w") as fh:
                fh.write(mine + "\n")
    link = os.path.join(disk_dir, os.path.basename(base_image))
    if not os.path.islink(link):
        os.symlink(base_image, link)
    return link


def tune_drive_args(qemu_args: list[str], cache: str) -> list[str]:
    """Add cache/discard options to the overlay `-drive` vrnetlab generated.

    detect-zeroes=unmap keeps zero-filled writes from growing the qcow2, which
    matters for an appliance that formats a 30 GB disk on first boot.
    """
    out = list(qemu_args)
    for i, arg in enumerate(out):
        if i and out[i - 1] == "-drive" and "-overlay." in arg and "cache=" not in arg:
            out[i] = f"{arg},cache={cache},discard=unmap,detect-zeroes=unmap"
            return out
    raise RuntimeError("overlay -drive argument not found in the qemu command line")


def _check(name: str, value: str, pattern: re.Pattern[str]) -> str:
    if not pattern.match(value):
        raise ConfigError(f"{name} has characters that are not allowed: {value!r}")
    return value


def _check_plain_scalar(name: str, value: str) -> str:
    """Accept only text that survives as an unquoted YAML value.

    The guide writes config_vars unquoted, and what parses the file inside
    ECOS is undocumented, so do not rely on YAML quoting or escapes.
    """
    bad = (
        value != value.strip()
        or not value.isprintable()
        or ": " in value
        or " #" in value
        or "_$" in value
        or value[0] in "!&*-?|>'\"%@`#{}[],:"
    )
    if bad:
        raise ConfigError(f"{name} cannot be written as a plain YAML value: {value!r}")
    return value


def _check_cli_word(name: str, value: str) -> str:
    """A single CLI argument inside a `cli:a;b;c` task in a quoted YAML string."""
    if not value.isprintable() or any(c in value for c in " ;\"'\\") or "_$" in value:
        raise ConfigError(
            f"{name} must not contain spaces, semicolons, quotes, backslashes or '_$'"
        )
    return value


def parse_nic_map(raw: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in raw.split(","):
        ecos_if, sep, eth = item.strip().partition(":")
        if not sep or not _NIC_RE.match(ecos_if) or not _NIC_RE.match(eth):
            raise ConfigError(f"ECOS_NIC_MAP entry {item!r} is not <ecos-if>:<ethN>")
        pairs.append((ecos_if, eth))
    return pairs


def render_spcustom(hostname: str, env: dict[str, str]) -> str:
    """Build spcustom.yml. Layout follows Appendix 1/2 of the deployment guide."""
    _check("hostname", hostname, _NAME_RE)
    key = env.get("ECOS_REGISTRATION_KEY", "").strip()
    account = env.get("ECOS_ACCOUNT_NAME", "").strip()
    site_tag = env.get("ECOS_SITE_TAG", "").strip() or "containerlab"
    password = env.get("ECOS_ADMIN_PASSWORD", "").strip()
    portal = env.get("ECOS_PORTAL_HOSTNAME", "").strip()
    router_mode = env.get("ECOS_ROUTER_MODE", "true").strip().lower() != "false"
    nic_map = parse_nic_map(env.get("ECOS_NIC_MAP", "").strip() or DEFAULT_NIC_MAP)

    if bool(key) != bool(account):
        raise ConfigError(
            "set both ECOS_REGISTRATION_KEY and ECOS_ACCOUNT_NAME, or neither"
        )

    config_vars = [("HOSTNAME", hostname)]
    pre = ['"configdb:/system/hostname,hostname,_$HOSTNAME$"']
    if key:
        config_vars += [
            ("ACCNAME", _check_plain_scalar("ECOS_ACCOUNT_NAME", account)),
            ("ACCKEY", _check("ECOS_REGISTRATION_KEY", key, _KEY_RE)),
            ("SYS_TAG", _check("ECOS_SITE_TAG", site_tag, _NAME_RE)),
        ]
        base = "configdb:/cn/tunneld/portal/config/registration"
        pre += [
            f'"{base}/account,string,_$ACCNAME$"',
            f'"{base}/key,string,_$ACCKEY$"',
            f'"{base}/site,string,_$SYS_TAG$"',
        ]
    if router_mode:
        config_vars.append(("ILRM", "true"))
        pre.append('"configdb:/cn/tunneld/system/config/routing_inline,bool,_$ILRM$"')

    # MAC pinning only takes effect after the reboot at the end, which is why
    # the guide ends every example with one.
    post = [f'"cli:en;conf t;interface {a} mac address {b}"' for a, b in nic_map]
    if password:
        word = _check_cli_word("ECOS_ADMIN_PASSWORD", password)
        post.append(f'"cli:en;conf t;username admin password {word}"')
    if portal:
        word = _check_cli_word("ECOS_PORTAL_HOSTNAME", portal)
        post.append(f'"cli:en;conf t;portal hostname {word}"')
    post.append('"cli:en;conf t;write memory;reboot noconfirm"')

    lines = ["silverpeak_vxoa_init:", "  config_vars:"]
    lines += [f"    {k}: {v}" for k, v in config_vars]
    lines.append("  pre_mgmtd_tasks:")
    lines += [f"    - {t}" for t in pre]
    lines.append("  post_mgmtd_tasks:")
    lines += [f"    - {t}" for t in post]
    return "\n".join(lines) + "\n"


def build_cloudinit_iso(content: str) -> None:
    os.makedirs(CLOUDINIT_DIR, mode=0o700, exist_ok=True)
    # Holds the registration key and admin password: owner-only.
    fd = os.open(CLOUDINIT_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
    try:
        subprocess.run(
            ["genisoimage", "-quiet", "-R", "-o", CLOUDINIT_ISO, CLOUDINIT_FILE],
            check=True, capture_output=True, text=True, timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"genisoimage failed: {exc.stderr.strip()}") from exc
    os.chmod(CLOUDINIT_ISO, 0o600)


def https_alive(host: str = "127.0.0.1", port: int = 443) -> bool:
    """True only if the appliance completes a TLS handshake.

    A bare TCP connect proves nothing: QEMU's hostfwd socket accepts while the
    guest is down or rebooting. The handshake has to come from ECOS itself.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # Liveness probe of the appliance's self-signed cert over the container's
    # own loopback. Nothing is sent, so there is nothing to protect.
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=HTTPS_PROBE_TIMEOUT) as raw:
            with ctx.wrap_socket(raw):
                return True
    except (OSError, ssl.SSLError):
        return False


class ECOS_vm(vrnetlab.VM):
    """One EC-V. Day-0 comes from the CloudInit ISO, not the console."""

    def __init__(self, hostname: str, username: str, password: str, conn_mode: str):
        super().__init__(
            username,
            password,
            disk_image=prepare_disk_dir(find_disk_image()),
            ram=env_int("ECOS_RAM", DEFAULT_RAM_MB),
            smp=str(env_int("ECOS_VCPU", DEFAULT_VCPU)),
            driveif=env_choice("ECOS_DISK_IF", "ide", DISK_INTERFACES),
        )
        self.qemu_args = tune_drive_args(
            self.qemu_args, env_choice("ECOS_DISK_CACHE", "unsafe", DISK_CACHE_MODES)
        )
        self.hostname = hostname
        self.conn_mode = conn_mode
        self.num_nics = 7  # eth1..eth7: wan0 lan0 wan1 lan1 ha lan2 + spare
        self.nic_type = "virtio-net-pci"

        self.ready_stable = env_int("ECOS_READY_STABLE_SECS", 60)
        self.boot_timeout = env_int("ECOS_BOOT_TIMEOUT_SECS", 1200)
        self._login_re = re.escape(hostname).encode() + rb"[^\r\n]* login:"
        self._spin_started: float | None = None
        self._last_probe = 0.0
        self._https_since: float | None = None
        self._last_console = 0.0
        self._login_seen = False
        self._hostname_seen = False
        self._last_stuck_log = 0.0

        build_cloudinit_iso(render_spcustom(hostname, dict(os.environ)))
        # Same wiring as the guide's "IDE cdrom". An IDE disk is index 0.
        self.qemu_args.extend(
            ["-drive", f"if=ide,index=1,media=cdrom,readonly=on,file={CLOUDINIT_ISO}"]
        )

    def bootstrap_spin(self) -> None:
        """Watch the boot; mark the node running only once it is stable.

        ECOS reboots at least once on its own while applying spcustom.yml, so
        the first sign of life is not readiness. Because nothing is typed at
        the console, declaring "ready" early cannot corrupt day-0 - ECOS
        finishes regardless - but it is still held back until HTTPS has
        stayed up for ECOS_READY_STABLE_SECS.
        """
        now = time.monotonic()
        if self._spin_started is None:
            self._spin_started = self._last_console = now

        ridx, _match, res = self.tn.expect([self._login_re, rb"login:"], 1)
        if res:
            self._last_console = now
        if ridx == 0 and not self._hostname_seen:
            self._hostname_seen = True
            self.logger.info("console shows hostname %s: spcustom.yml was read", self.hostname)
        if ridx >= 0:
            self._login_seen = True

        if self.mgmt_passthrough:
            # No hostfwd to probe; fall back to a quiet console at a login prompt.
            ready = self._login_seen and now - self._last_console >= self.ready_stable
        else:
            if now - self._last_probe >= HTTPS_PROBE_INTERVAL:
                self._last_probe = now
                if https_alive():
                    if self._https_since is None:
                        self.logger.info("HTTPS is up; waiting %ss for it to stay up",
                                         self.ready_stable)
                        self._https_since = now
                elif self._https_since is not None:
                    self.logger.info("HTTPS went away (reboot); waiting again")
                    self._https_since = None
            ready = (self._https_since is not None
                     and now - self._https_since >= self.ready_stable)

        if ready:
            if not self._hostname_seen:
                self.logger.warning(
                    "ready, but hostname %s never appeared on the serial console - "
                    "confirm spcustom.yml was applied (show running-config)",
                    self.hostname,
                )
            self.logger.info("EC-V ready after %.0fs", now - self._spin_started)
            self.tn.close()  # free the serial console for `telnet <node> 5000`
            self.running = True
            return

        # Never report healthy on a timeout: a node that is not up should look it.
        if (now - self._spin_started > self.boot_timeout
                and now - self._last_stuck_log > 60):
            self._last_stuck_log = now
            self.logger.error(
                "not ready after %.0fs (login prompt seen: %s, https up: %s)",
                now - self._spin_started, self._login_seen, self._https_since is not None,
            )


class ECOS(vrnetlab.VR):
    def __init__(self, hostname: str, username: str, password: str, conn_mode: str):
        super().__init__(username, password)
        self.vms = [ECOS_vm(hostname, username, password, conn_mode)]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="EdgeConnect EC-V vrnetlab launcher")
    parser.add_argument("--hostname", default="ecos")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--connection-mode", default="tc")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s: %(module)-10s %(levelname)-8s %(message)s",
        level=logging.DEBUG if args.trace else logging.INFO,
    )
    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGCHLD, handle_sigchld)

    vrnetlab.boot_delay()
    try:
        vr = ECOS(args.hostname, args.username, args.password, args.connection_mode)
    except (ConfigError, FileNotFoundError, RuntimeError) as exc:
        LOG.error("cannot start EC-V: %s", exc)
        return 1
    vr.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
