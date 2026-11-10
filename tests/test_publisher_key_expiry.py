#!/usr/bin/python3
"""Prestium 2.1: fail when a publisher key the Browser Updater pins would expire within 90 days.

Checks the keys the updater verifies with (thirdparty/keys/torbrowser.asc, thirdparty/keys/mozilla.asc,
the image's /usr/share/keyrings/librewolf.gpg, and the copies under /usr/share/prestium/keys/). Only
pub and sub records are read (gpg --show-keys --with-colons). Subkeys that already expired or were
revoked are history and ignored. Passes when the primary key (if it has an expiry) and at least one
current signing subkey (or a signing-capable primary) stay valid for 90 more days; no expiry is fine.
When this fails: refresh the key in thirdparty/keys/ (and the image copy), or the updater stops
working with "key expired, use a newer ISO"."""
import os, subprocess, sys, time, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import browser_update_testlib as T  # noqa: E402
from browser_update_testlib import bu  # noqa: E402

DAYS = 90
KEYFILES = [
    ("tor-browser", os.path.join(T.ROOT, "thirdparty/keys/torbrowser.asc")),
    ("tor-browser", os.path.join(T.INC, "usr/share/prestium/keys/torbrowser.asc")),
    ("firefox", os.path.join(T.ROOT, "thirdparty/keys/mozilla.asc")),
    ("firefox", os.path.join(T.INC, "usr/share/prestium/keys/mozilla.asc")),
    ("librewolf", os.path.join(T.INC, "usr/share/keyrings/librewolf.gpg")),
]


def records(path):
    out = subprocess.run(["gpg", "--batch", "--show-keys", "--with-colons", path], capture_output=True,
                         text=True, env=dict(os.environ, LANG="C")).stdout
    recs, cur = [], None
    for line in out.splitlines():
        f = line.split(":")
        if f[0] in ("pub", "sub"):
            cur = {"type": f[0], "validity": f[1], "expires": int(f[6]) if f[6] else None,
                   "caps": f[11] if len(f) > 11 else "", "fpr": None}
            recs.append(cur)
        elif f[0] == "fpr" and cur is not None and cur["fpr"] is None:
            cur["fpr"] = f[9]
    return recs


def problems(recs, pinned, now=None, days=DAYS):
    """Empty list = fine."""
    now = now or time.time()
    limit = now + days * 86400
    pubs = [r for r in recs if r["type"] == "pub"]
    if len(pubs) != 1:
        return ["expected one primary key, found %d" % len(pubs)]
    p = pubs[0]
    out = []
    if p["fpr"] != pinned:
        out.append("primary %s is not the pinned %s" % (p["fpr"], pinned))
    if p["validity"] in ("r", "e"):
        return out + ["primary key is %s" % {"r": "revoked", "e": "expired"}[p["validity"]]]
    if p["expires"] is not None and p["expires"] < limit:
        out.append("primary key expires on %s" % time.strftime("%Y-%m-%d", time.gmtime(p["expires"])))
    signing = [r for r in recs if r["type"] == "sub" and "s" in r["caps"] and r["validity"] not in ("r", "e")
               and (r["expires"] is None or r["expires"] > now)]
    ok = [r for r in signing if r["expires"] is None or r["expires"] >= limit]
    if "s" in p["caps"]:                       # lower case: the primary key itself can sign
        ok.append(p)
    if not ok:
        soon = min((r["expires"] for r in signing if r["expires"]), default=None)
        out.append("no signing key stays valid for %d days%s" % (
            days, " (the current one expires on %s)" % time.strftime("%Y-%m-%d", time.gmtime(soon)) if soon else ""))
    return out


@unittest.skipUnless(T.have("gpg"), "gpg missing")
class TestKeyExpiry(unittest.TestCase):
    def test_shipped_keys(self):
        for browser, path in KEYFILES:
            with self.subTest(path=path):
                self.assertTrue(os.path.exists(path), path)
                self.assertEqual(problems(records(path), bu.KEYS[browser][1]), [], path)

    def test_rule(self):
        now = 1_800_000_000
        F = "A" * 40
        pub = {"type": "pub", "validity": "-", "expires": None, "caps": "cSC", "fpr": F}
        sub = lambda e, v="-": {"type": "sub", "validity": v, "expires": e, "caps": "s", "fpr": "B" * 40}
        self.assertEqual(problems([pub, sub(now + 91 * 86400)], F, now), [])
        self.assertEqual(problems([pub, sub(None)], F, now), [])
        self.assertTrue(problems([pub, sub(now + 89 * 86400)], F, now))
        self.assertTrue(problems([pub, sub(now - 1, "e")], F, now), "only historical subkeys")
        self.assertEqual(problems([pub, sub(now - 1, "e"), sub(now + 200 * 86400)], F, now), [])
        self.assertTrue(problems([dict(pub, expires=now + 30 * 86400), sub(None)], F, now))
        self.assertTrue(problems([pub, sub(None, "r")], F, now), "revoked subkey only")
        self.assertEqual(problems([dict(pub, caps="scSC")], F, now), [], "signing-capable primary, no expiry")
        self.assertTrue(problems([pub, sub(None)], "C" * 40, now), "wrong pin")


if __name__ == "__main__":
    unittest.main(verbosity=2)
