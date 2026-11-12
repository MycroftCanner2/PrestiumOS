#!/usr/bin/env python3
"""2.1: the exact control commands OnionShare 2.6.3 (stem 1.8.2) and Tor Browser's client-key prompt
send pass onion-grater, and torrc gives Tor Browser's socket ExtendedErrors (needed for the key prompt)."""
import os, re, types, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "config", "includes.chroot")
src = open(os.path.join(ROOT, "usr/local/sbin/prestium-onion-grater")).read().replace(
    'if __name__ == "__main__":', "if False:")
g = types.ModuleType("grater"); exec(compile(src, "grater", "exec"), g.__dict__)
K = "E2GOT5LTUTP3OAMRCRXO4GSH6VKJEUOXZQUC336SRKAHTTT5OVSA"
ADDR = "a" * 56

class T(unittest.TestCase):
    def fwd(self, prof, line):
        f, r = g.check(prof, line)
        self.assertIsNotNone(f, "%s refused: %s -> %s" % (prof, line, r))
        return f

    def test_onionshare_flow(self):
        for l in ["GETCONF __OwningControllerProcess", "GETINFO version", "SETEVENTS HS_DESC",
                  "ADD_ONION NEW:ED25519-V3 Flags=V3Auth Port=1,1 ClientAuthV3=" + K,
                  "DEL_ONION " + ADDR,
                  "ADD_ONION NEW:ED25519-V3 Flags=V3Auth Port=80,17605 ClientAuthV3=" + K,
                  "ADD_ONION NEW:ED25519-V3 Port=80,17650",
                  "ADD_ONION ED25519-V3:YWJj+/= Flags=V3Auth Port=80,17600 ClientAuthV3=" + K,
                  "GETINFO onions/current"]:
            self.fwd("onionshare", l)

    def test_onionshare_limits_kept(self):
        for l in ["ADD_ONION NEW:ED25519-V3 Port=80,17651", "ADD_ONION NEW:ED25519-V3 Port=80,127.0.0.1:22",
                  "ADD_ONION NEW:ED25519-V3 Flags=NonAnonymous Port=80,17605",
                  "ONION_CLIENT_AUTH_ADD %s x25519:%s" % (ADDR, K)]:
            self.assertIsNone(g.check("onionshare", l)[0], l)

    def test_tor_browser_key_prompt(self):
        self.assertEqual(self.fwd("tor-browser", "ONION_CLIENT_AUTH_ADD %s x25519:abc=" % ADDR),
                         "ONION_CLIENT_AUTH_ADD %s x25519:abc=" % ADDR)
        # "Remember this key": the flag is dropped, never forwarded
        self.assertEqual(self.fwd("tor-browser", "ONION_CLIENT_AUTH_ADD %s x25519:abc= Flags=Permanent" % ADDR),
                         "ONION_CLIENT_AUTH_ADD %s x25519:abc=" % ADDR)
        self.assertIsNone(g.check("tor-browser", "ONION_CLIENT_AUTH_ADD %s x25519:abc= Flags=Other" % ADDR)[0])
        self.fwd("tor-browser", "ONION_CLIENT_AUTH_REMOVE " + ADDR)
        self.fwd("tor-browser", "ONION_CLIENT_AUTH_VIEW")

    def test_tor_browser_auth_arguments_checked(self):
        # 2.1 (verification of 9d289eb): only well-formed arguments reach Tor
        self.fwd("tor-browser", "ONION_CLIENT_AUTH_ADD %s.onion x25519:%s ClientName=Bob_1" % (ADDR, "A" * 43 + "="))
        self.fwd("tor-browser", "ONION_CLIENT_AUTH_VIEW " + ADDR)
        for l in ["ONION_CLIENT_AUTH_ADD %s" % ADDR,
                  "ONION_CLIENT_AUTH_ADD %s x25519:abc= ClientName=x\x00y" % ADDR,
                  "ONION_CLIENT_AUTH_ADD %s x25519:abc= ClientName=" % ADDR,
                  "ONION_CLIENT_AUTH_ADD %s x25519:abc= ClientName=a b" % ADDR,
                  "ONION_CLIENT_AUTH_ADD %s x25519:abc= SETCONF ControlPort=1" % ADDR,
                  "ONION_CLIENT_AUTH_ADD %s ed25519:abc=" % ADDR,
                  "ONION_CLIENT_AUTH_ADD %s x25519:abc=" % ("1" * 56),
                  "ONION_CLIENT_AUTH_ADD %s x25519:abc=" % ADDR[:55],
                  "ONION_CLIENT_AUTH_REMOVE",
                  "ONION_CLIENT_AUTH_REMOVE %s extra" % ADDR,
                  "ONION_CLIENT_AUTH_VIEW %s %s" % (ADDR, ADDR)]:
            self.assertIsNone(g.check("tor-browser", l)[0], l)

    def test_torrc_extended_errors(self):
        t = open(os.path.join(ROOT, "etc/tor/torrc")).read()
        line = [l for l in t.splitlines() if l.startswith("SocksPort unix:/run/prestium-tbb/socks")]
        self.assertEqual(len(line), 1)
        self.assertIn("ExtendedErrors", line[0].split())

if __name__ == "__main__":
    unittest.main()
