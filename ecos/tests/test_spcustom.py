"""Tests for the spcustom.yml renderer. No QEMU, no vrnetlab image needed."""
import os
import sys
import tempfile
import types
import unittest

# launch.py imports vrnetlab, which only exists inside the image.
stub = types.ModuleType("vrnetlab")
stub.VM = object
stub.VR = object
sys.modules.setdefault("vrnetlab", stub)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "docker"))

import launch  # noqa: E402

FULL = {
    "ECOS_REGISTRATION_KEY": "BpPQaQ7ySH0obdqIZLeTpGQtsaJXB3D3",
    "ECOS_ACCOUNT_NAME": "SP-SEWAN-Metered with Orchestrator SP/Atlantic Coast",
    "ECOS_SITE_TAG": "SiteBranch",
    "ECOS_ADMIN_PASSWORD": "S3cret!pw",
}


class RenderTests(unittest.TestCase):
    def test_full_matches_guide_layout(self):
        out = launch.render_spcustom("BR-ecv-01", FULL)
        self.assertTrue(out.startswith("silverpeak_vxoa_init:\n  config_vars:\n"))
        self.assertIn("    ACCNAME: SP-SEWAN-Metered with Orchestrator SP/Atlantic Coast\n", out)
        self.assertIn('    - "configdb:/system/hostname,hostname,_$HOSTNAME$"\n', out)
        self.assertIn(
            '    - "configdb:/cn/tunneld/portal/config/registration/key,string,_$ACCKEY$"\n', out)
        self.assertIn('    - "cli:en;conf t;interface wan1 mac address eth3"\n', out)
        self.assertIn('    - "cli:en;conf t;username admin password S3cret!pw"\n', out)
        self.assertTrue(out.endswith('    - "cli:en;conf t;write memory;reboot noconfirm"\n'))
        # pre tasks come before post tasks
        self.assertLess(out.index("pre_mgmtd_tasks"), out.index("post_mgmtd_tasks"))

    def test_unregistered_has_no_registration_tasks(self):
        out = launch.render_spcustom("ecv", {})
        self.assertNotIn("registration", out)
        self.assertNotIn("username admin", out)
        self.assertIn("routing_inline", out)

    def test_router_mode_off(self):
        self.assertNotIn("routing_inline",
                         launch.render_spcustom("ecv", {"ECOS_ROUTER_MODE": "false"}))

    def test_key_without_account_rejected(self):
        with self.assertRaises(launch.ConfigError):
            launch.render_spcustom("ecv", {"ECOS_REGISTRATION_KEY": "abc"})

    def test_injection_rejected(self):
        for field, value in [
            ("ECOS_ADMIN_PASSWORD", "pw;reboot"),
            ("ECOS_ADMIN_PASSWORD", 'pw"x'),
            ("ECOS_ADMIN_PASSWORD", "pw x"),
            ("ECOS_ACCOUNT_NAME", "acct\nfoo: bar"),
            ("ECOS_ACCOUNT_NAME", "acct: x"),
            ("ECOS_SITE_TAG", "tag with space"),
            ("ECOS_REGISTRATION_KEY", "key;x"),
            ("ECOS_PORTAL_HOSTNAME", "host;x"),
        ]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(launch.ConfigError):
                    launch.render_spcustom("ecv", {**FULL, field: value})

    def test_bad_hostname_rejected(self):
        with self.assertRaises(launch.ConfigError):
            launch.render_spcustom("bad host", {})

    def test_nic_map(self):
        self.assertEqual(launch.parse_nic_map("mgmt0:eth0, wan0:eth1"),
                         [("mgmt0", "eth0"), ("wan0", "eth1")])
        with self.assertRaises(launch.ConfigError):
            launch.parse_nic_map("wan0=eth1")


class DiskTests(unittest.TestCase):
    def test_drive_args_tuned(self):
        args = ["qemu", "-drive", "if=ide,file=/disk/ECV-1-overlay.qcow2", "-m", "4096"]
        out = launch.tune_drive_args(args, "unsafe")
        self.assertEqual(
            out[2],
            "if=ide,file=/disk/ECV-1-overlay.qcow2,cache=unsafe,discard=unmap,detect-zeroes=unmap")
        self.assertEqual(args[2], "if=ide,file=/disk/ECV-1-overlay.qcow2")  # input untouched

    def test_drive_args_missing_overlay(self):
        with self.assertRaises(RuntimeError):
            launch.tune_drive_args(["qemu", "-m", "4096"], "unsafe")

    def test_no_disk_dir_keeps_base(self):
        self.assertEqual(
            launch.prepare_disk_dir("/ECV-1.qcow2", "/nonexistent-dir", "/nonexistent-tok"),
            "/ECV-1.qcow2")

    def test_disk_dir_restart_keeps_overlay_redeploy_discards(self):
        with tempfile.TemporaryDirectory() as tmp:
            disk = os.path.join(tmp, "disk")
            os.mkdir(disk)
            token = os.path.join(tmp, "token")
            base = os.path.join(tmp, "ECV-1.qcow2")
            open(base, "w").close()

            link = launch.prepare_disk_dir(base, disk, token)
            self.assertEqual(os.path.realpath(link), os.path.realpath(base))
            overlay = os.path.join(disk, "ECV-1-overlay.qcow2")
            open(overlay, "w").close()

            launch.prepare_disk_dir(base, disk, token)      # container restart
            self.assertTrue(os.path.exists(overlay))

            os.remove(token)                                # new container
            launch.prepare_disk_dir(base, disk, token)
            self.assertFalse(os.path.exists(overlay))
            self.assertTrue(os.path.islink(link))

    def test_bad_cache_mode_rejected(self):
        os.environ["ECOS_DISK_CACHE"] = "bogus"
        try:
            with self.assertRaises(launch.ConfigError):
                launch.env_choice("ECOS_DISK_CACHE", "unsafe", launch.DISK_CACHE_MODES)
        finally:
            del os.environ["ECOS_DISK_CACHE"]


if __name__ == "__main__":
    unittest.main()
