#!/usr/bin/python3
"""2.0 r10: runs the real prestium-mac-guard against a mocked NetworkManager (python-dbusmock) on a
private system bus, and checks it reacts to the real-MAC cases. Needs python3-dbusmock, python3-gi."""
import os, subprocess, sys, tempfile, time, unittest
import dbus, dbusmock
from dbusmock.templates.networkmanager import DeviceState, MANAGER_IFACE, SETTINGS_IFACE, DEVICE_IFACE

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "includes.chroot",
                     "usr", "local", "sbin", "prestium-mac-guard")
PERM = "78:DD:08:D2:3D:43"   # the template's permanent address
WIRED = "org.freedesktop.NetworkManager.Device.Wired"


def wait(pred, t=10):
    end = time.time() + t
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.1)
    return False


class Guard(dbusmock.DBusTestCase):
    @classmethod
    def setUpClass(cls):
        cls.start_system_bus()
        cls.dbus_con = cls.get_dbus(system_bus=True)

    def setUp(self):
        self.p_mock, self.obj = self.spawn_server_template("networkmanager", {}, stdout=subprocess.DEVNULL)
        self.mock = dbus.Interface(self.obj, dbusmock.MOCK_IFACE)
        self.tmp = tempfile.mkdtemp()
        self.flagf = os.path.join(self.tmp, "flags"); self.nftf = os.path.join(self.tmp, "nft")
        for name, body in (("flag", 'echo "$@" >> %s' % self.flagf), ("nft", "cat >> %s" % self.nftf)):
            with open(os.path.join(self.tmp, name), "w") as f:
                f.write("#!/bin/sh\n%s\n" % body)
            os.chmod(os.path.join(self.tmp, name), 0o755)
        with open(os.path.join(self.tmp, "cmdline"), "w") as f:
            f.write("boot=live quiet\n")
        self.env = dict(os.environ, PRESTIUM_SAFETY_FLAG=os.path.join(self.tmp, "flag"),
                        PRESTIUM_NFT=os.path.join(self.tmp, "nft"),
                        PRESTIUM_CMDLINE=os.path.join(self.tmp, "cmdline"))
        self.guard = None

    def tearDown(self):
        if self.guard:
            self.guard.terminate(); self.guard.wait()
        self.p_mock.terminate(); self.p_mock.wait()

    def add_eth(self, state, hw=None):
        path = self.mock.AddEthernetDevice("eth0", "eth0", state)
        dev = self.dbus_con.get_object("org.freedesktop.NetworkManager", path)
        dmock = dbus.Interface(dev, dbusmock.MOCK_IFACE)
        dmock.AddMethod(DEVICE_IFACE, "Disconnect", "", "",
                        "self.Set('%s', 'State', dbus.UInt32(30))" % DEVICE_IFACE)
        if hw:
            dev.Set(WIRED, "HwAddress", hw, dbus_interface=dbus.PROPERTIES_IFACE)
        return dev

    def state(self, dev):
        return int(dev.Get(DEVICE_IFACE, "State", dbus_interface=dbus.PROPERTIES_IFACE))

    def start_guard(self):
        self.guard = subprocess.Popen([sys.executable, GUARD], env=self.env, stderr=subprocess.PIPE, text=True)
        time.sleep(1.5)

    def flags(self):
        try:
            return open(self.flagf).read()
        except OSError:
            return ""

    def test_active_device_with_real_mac_is_disconnected(self):
        dev = self.add_eth(DeviceState.ACTIVATED)          # HwAddress == PermHwAddress
        self.start_guard()
        ok = wait(lambda: self.state(dev) == 30)
        if not ok:
            self.guard.terminate(); print(self.guard.communicate()[1])
            self.guard = None
        self.assertTrue(ok, "device not disconnected")
        self.assertIn("real MAC address", self.flags())
        self.assertIn("ether saddr 78:dd:08:d2:3d:43 counter drop", open(self.nftf).read())

    def test_spoofed_device_left_alone(self):
        dev = self.add_eth(DeviceState.ACTIVATED, hw="78:DD:08:11:22:33")
        self.start_guard()
        time.sleep(1)
        self.assertEqual(self.state(dev), DeviceState.ACTIVATED)
        self.assertEqual(self.flags(), "")

    def test_device_switching_to_real_mac_later(self):
        dev = self.add_eth(DeviceState.ACTIVATED, hw="78:DD:08:11:22:33")
        self.start_guard()
        dev.Set(WIRED, "HwAddress", PERM, dbus_interface=dbus.PROPERTIES_IFACE)
        dbus.Interface(dev, dbusmock.MOCK_IFACE).EmitSignal(
            "org.freedesktop.DBus.Properties", "PropertiesChanged", "sa{sv}as",
            [WIRED, {"HwAddress": PERM}, dbus.Array([], signature="s")])
        self.assertTrue(wait(lambda: self.state(dev) == 30), "device not disconnected after MAC change")

    def test_new_connection_with_permanent_mac_is_reset(self):
        self.start_guard()
        settings = self.dbus_con.get_object("org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager/Settings")
        path = settings.AddConnection(dbus.Dictionary({
            "connection": dbus.Dictionary({"id": "Cafe", "type": "802-3-ethernet",
                                           "uuid": "11111111-2222-3333-4444-555555555555"}, signature="sv"),
            "802-3-ethernet": dbus.Dictionary({"assigned-mac-address": "permanent"}, signature="sv"),
        }, signature="sa{sv}"), dbus_interface=SETTINGS_IFACE)
        conn = self.dbus_con.get_object("org.freedesktop.NetworkManager", path)
        get = lambda: conn.GetSettings(dbus_interface="org.freedesktop.NetworkManager.Settings.Connection")
        self.assertTrue(wait(lambda: get()["802-3-ethernet"].get("assigned-mac-address") == "preserve"),
                        "connection not reset: %s" % get())
        self.assertIn("Cafe", self.flags())

    def test_permanent_address_change_reinstalls_egress_filter(self):
        # 2.1: same interface name, new permanent address (re-plug/driver reload): a second nft install
        dev = self.add_eth(DeviceState.ACTIVATED, hw="78:DD:08:11:22:33")
        self.start_guard()
        self.assertTrue(wait(lambda: os.path.exists(self.nftf) and "78:dd:08:d2:3d:43" in open(self.nftf).read()))
        new = "02:AB:CD:EF:01:23"
        dev.Set(WIRED, "PermHwAddress", new, dbus_interface=dbus.PROPERTIES_IFACE)
        dbus.Interface(dev, dbusmock.MOCK_IFACE).EmitSignal(
            "org.freedesktop.DBus.Properties", "PropertiesChanged", "sa{sv}as",
            [WIRED, {"PermHwAddress": new}, dbus.Array([], signature="s")])
        self.assertTrue(wait(lambda: "ether saddr 02:ab:cd:ef:01:23 counter drop" in open(self.nftf).read()),
                        "egress filter not re-installed for the new permanent address")

    def test_nomacspoof_disables_guard(self):
        with open(os.path.join(self.tmp, "cmdline"), "w") as f:
            f.write("boot=live nomacspoof\n")
        dev = self.add_eth(DeviceState.ACTIVATED)
        self.guard = subprocess.Popen([sys.executable, GUARD], env=self.env, stderr=subprocess.DEVNULL)
        self.assertEqual(self.guard.wait(timeout=10), 0)
        self.guard = None
        self.assertEqual(self.state(dev), DeviceState.ACTIVATED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
