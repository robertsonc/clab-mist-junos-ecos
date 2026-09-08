"""Minimal Junos-over-SSH driver for the mist-ec-fabric lab."""
import time
import paramiko


def connect(host, user="admin", password="admin@123", timeout=20):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username=user, password=password, timeout=timeout,
              look_for_keys=False, allow_agent=False)
    return c


def shell(c, idle=1.0, total=90):
    sh = c.invoke_shell(width=250, height=1000)
    sh.settimeout(total)
    time.sleep(2)
    _drain(sh)
    return sh


def _drain(sh, wait=1.0):
    out = ""
    end = time.time() + wait
    while time.time() < end:
        if sh.recv_ready():
            out += sh.recv(65535).decode(errors="replace")
            end = time.time() + wait
        else:
            time.sleep(0.1)
    return out


def send(sh, cmd, wait=1.5):
    sh.send(cmd + "\n")
    return _drain(sh, wait)


def cli(host, cmds, user="admin", password="admin@123"):
    """Run operational-mode commands, return combined output."""
    c = connect(host, user, password)
    try:
        sh = shell(c)
        out = send(sh, "set cli screen-length 0", 1.0)
        out += send(sh, "set cli screen-width 0", 1.0)
        for cmd in cmds:
            out += send(sh, cmd, 3.0)
        return out
    finally:
        c.close()


def connect_kbd(host, user, password, timeout=20):
    """Connect using keyboard-interactive (EC-V / ECOS)."""
    t = paramiko.Transport((host, 22))
    t.connect()
    def handler(title, instructions, prompt_list):
        return [password for _ in prompt_list]
    t.auth_interactive(user, handler)
    return t


def ecos_cli(host, cmds, user="admin", password="admin"):
    t = connect_kbd(host, user, password)
    try:
        ch = t.open_session()
        ch.get_pty(width=250, height=1000)
        ch.invoke_shell()
        time.sleep(3)
        out = ""
        if ch.recv_ready():
            out += ch.recv(65535).decode(errors="replace")
        for cmd in cmds:
            ch.send(cmd + "\n")
            end = time.time() + 4
            while time.time() < end:
                if ch.recv_ready():
                    out += ch.recv(65535).decode(errors="replace")
                    end = time.time() + 1.5
                else:
                    time.sleep(0.1)
        return out
    finally:
        t.close()
