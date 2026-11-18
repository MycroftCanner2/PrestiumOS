#!/usr/bin/python3 -I
"""Prestium 2.1: fetch the newest release of an add-on from addons.mozilla.org and verify it.

    amo-latest.py fetch OUT.xpi          newest uBlock Origin from the AMO API, verified, written to OUT.xpi
    amo-latest.py verify XPI SHA256 VER  re-verify a downloaded or staged copy (the same checks, no network)
    amo-latest.py minver XPI APP_VERSION [APP_VERSION ...]   the add-on supports every given Firefox version

Used by scripts/fetch-thirdparty.sh (fetch) and hook 0200 (verify + minver). Every check must pass, or the
build stops; there is no fallback to an older copy:
  1. AMO API (HTTPS, https://addons.mozilla.org/api/v5/addons/addon/<slug>/): the add-on's guid must be
     the expected one, current_version.file must be public, its URL on addons.mozilla.org, and its hash a
     sha256 (64 hex).
  2. the download (HTTPS only, redirects HTTPS only) has exactly that size and SHA-256.
  3. Mozilla's add-on signature, as Firefox checks it: META-INF/mozilla.rsa (PKCS#7) is a valid signature
     over META-INF/mozilla.sf by a certificate chain to Mozilla's AMO production root
     (thirdparty/keys/mozilla-amo-root.pem, the root Firefox ships as security/manager/ssl/addons-public.pem,
     its SHA-256 fingerprint pinned below), code-signing purpose, and the signing certificate's CN is the
     add-on id. mozilla.sf's SHA256-Digest-Manifest matches META-INF/manifest.mf, and manifest.mf lists every
     other file in the archive with a matching SHA-256 (nothing unlisted, nothing missing, no path tricks).
     META-INF/cose.sig (Mozilla's COSE signature) must be present too; it is covered by manifest.mf.
  4. manifest.json: browser_specific_settings.gecko.id is the add-on id, version is the API's version.
"""
import base64, hashlib, json, os, re, subprocess, sys, tempfile, zipfile

SLUG = "ublock-origin"
GUID = "uBlock0@raymondhill.net"
API = "https://addons.mozilla.org/api/v5/addons/addon/%s/" % SLUG
FILE_URL = re.compile(r"https://addons\.mozilla\.org/firefox/downloads/file/[0-9]+/[A-Za-z0-9_.-]+\.xpi")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("PRESTIUM_AMO_ROOT", os.path.join(HERE, "..", "thirdparty", "keys", "mozilla-amo-root.pem"))
# SHA-256 fingerprint of CN=root-ca-production-amo (Mozilla AMO Production Signing Service, 2024-02-01 to 2200-12-03)
ROOT_FPR = "C8A80E9AFAEF4E219B6FB5D7A71D0F101223BAC5001AC28F9B0D43DC59A106DB"
SIGFILES = {"META-INF/mozilla.rsa", "META-INF/mozilla.sf", "META-INF/manifest.mf"}
VERSION = re.compile(r"[0-9]{1,4}(\.[0-9]{1,6}){0,3}([a-z][0-9a-z]{0,8})?")


class Bad(Exception):
    pass


def curl(url, out, maxsize=None):
    cmd = ["curl", "-sfL", "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "5",
           "--retry", "3", "-m", "600", "-o", out]
    if maxsize:
        cmd += ["--max-filesize", str(maxsize)]
    r = subprocess.run(cmd + [url], capture_output=True, text=True)
    if r.returncode != 0:
        raise Bad("cannot download %s (curl exit %d)" % (url, r.returncode))


def api(tmp):
    p = os.path.join(tmp, "api.json")
    curl(API, p, 1 << 20)
    try:
        d = json.load(open(p))
        v = d["current_version"]
        f = v["file"]
        ver, url, h, size, status = v["version"], f["url"], f["hash"], f["size"], f["status"]
    except (ValueError, KeyError, TypeError) as e:
        raise Bad("the AMO API answer is not usable (%s)" % e)
    if d.get("guid") != GUID:
        raise Bad("the AMO API names add-on %r, not %s" % (d.get("guid"), GUID))
    if not (isinstance(ver, str) and VERSION.fullmatch(ver)):
        raise Bad("the AMO API gave a bad version %r" % (ver,))
    if status != "public":
        raise Bad("the newest file on AMO is not public (%r)" % (status,))
    if not (isinstance(url, str) and FILE_URL.fullmatch(url)):
        raise Bad("the AMO API gave an unexpected download URL %r" % (url,))
    m = re.fullmatch(r"sha256:([0-9a-f]{64})", h if isinstance(h, str) else "")
    if not m:
        raise Bad("the AMO API gave no SHA-256 for the file (%r)" % (h,))
    if not (isinstance(size, int) and 0 < size < 64 << 20):
        raise Bad("the AMO API gave a bad file size %r" % (size,))
    return ver, url, m.group(1), size


def b64sha256(b):
    return base64.b64encode(hashlib.sha256(b).digest()).decode()


def mf_entries(text):
    text = text.replace("\r\n", "\n")
    lines = []
    for l in text.split("\n"):
        if l.startswith(" ") and lines:
            lines[-1] += l[1:]
        else:
            lines.append(l)
    secs, cur = [], {}
    for l in lines + [""]:
        if not l:
            if cur:
                secs.append(cur)
            cur = {}
            continue
        k, sep, v = l.partition(": ")
        if not sep:
            raise Bad("manifest.mf: bad line %r" % l[:80])
        cur[k] = v
    if not secs or "Manifest-Version" not in secs[0]:
        raise Bad("manifest.mf has no main section")
    out = {}
    for s in secs[1:]:
        if "Name" not in s or "SHA256-Digest" not in s:
            raise Bad("manifest.mf section without Name or SHA256-Digest")
        if s["Name"] in out:
            raise Bad("manifest.mf lists %s twice" % s["Name"])
        out[s["Name"]] = s["SHA256-Digest"]
    return out


def openssl_verify(tmp, rsa, sf, root):
    pr, ps = os.path.join(tmp, "mozilla.rsa"), os.path.join(tmp, "mozilla.sf")
    open(pr, "wb").write(rsa)
    open(ps, "wb").write(sf)
    r = subprocess.run(["openssl", "cms", "-verify", "-inform", "DER", "-in", pr, "-binary", "-content", ps,
                        "-CAfile", root, "-no-CApath", "-no-CAstore", "-purpose", "codesign", "-out", os.devnull],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise Bad("Mozilla signature check failed: %s" % (r.stderr.strip().splitlines() or ["openssl error"])[0])
    # the signer is the certificate whose CN is the add-on id (openssl cms prints signer certs)
    signer = os.path.join(tmp, "signer.pem")
    subprocess.run(["openssl", "cms", "-verify", "-inform", "DER", "-in", pr, "-binary", "-content", ps,
                    "-CAfile", root, "-no-CApath", "-no-CAstore", "-purpose", "codesign", "-out", os.devnull,
                    "-signer", signer], capture_output=True, check=True)
    subj = subprocess.run(["openssl", "x509", "-in", signer, "-noout", "-subject", "-nameopt", "multiline"],
                          capture_output=True, text=True, check=True).stdout
    cns = re.findall(r"^\s*commonName\s*=\s*(.*)$", subj, re.M)
    if cns != [GUID]:
        raise Bad("the signing certificate is for %r, not %s" % (cns, GUID))


def root_ok(root):
    """root must be Mozilla's AMO root (pinned fingerprint), whichever file PRESTIUM_AMO_ROOT names."""
    r = subprocess.run(["openssl", "x509", "-in", root, "-noout", "-fingerprint", "-sha256"],
                       capture_output=True, text=True)
    fpr = r.stdout.strip().partition("=")[2].replace(":", "").upper()
    if r.returncode != 0 or fpr != ROOT_FPR:
        raise Bad("%s is not Mozilla's pinned AMO root (fingerprint %s)" % (root, fpr or "unreadable"))


def verify(path, sha, version, root=None):
    """All checks on a downloaded .xpi; returns manifest.json's gecko settings."""
    root = root or ROOT
    root_ok(root)
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if h != sha:
        raise Bad("%s SHA-256 %s != %s (from the AMO API)" % (os.path.basename(path), h, sha))
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise Bad("not a zip archive")
    with z, tempfile.TemporaryDirectory() as tmp:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise Bad("the archive has duplicate entries")
        for n in names:
            if n.startswith("/") or "\\" in n or ".." in n.split("/") or "\0" in n:
                raise Bad("bad path in the archive: %r" % n)
        files = [n for n in names if not n.endswith("/")]
        for need in sorted(SIGFILES) + ["META-INF/cose.sig", "manifest.json"]:
            if need not in files:
                raise Bad("%s missing: not a Mozilla-signed add-on" % need)
        sf = z.read("META-INF/mozilla.sf")
        mf = z.read("META-INF/manifest.mf")
        openssl_verify(tmp, z.read("META-INF/mozilla.rsa"), sf, root)
        m = re.search(r"^SHA256-Digest-Manifest: (\S+)\s*$", sf.decode("utf-8", "replace"), re.M)
        if not m or m.group(1) != b64sha256(mf):
            raise Bad("mozilla.sf does not match META-INF/manifest.mf")
        listed = mf_entries(mf.decode("utf-8"))
        content = set(files) - SIGFILES
        if set(listed) != content:
            raise Bad("manifest.mf and the archive differ: unlisted %s, missing %s"
                      % (sorted(content - set(listed))[:5], sorted(set(listed) - content)[:5]))
        for n in sorted(content):
            if b64sha256(z.read(n)) != listed[n]:
                raise Bad("%s does not match its signed SHA-256" % n)
        try:
            man = json.loads(z.read("manifest.json").decode("utf-8-sig"))
            gecko = (man.get("browser_specific_settings") or man.get("applications") or {}).get("gecko") or {}
        except (ValueError, AttributeError) as e:
            raise Bad("manifest.json unreadable (%s)" % e)
        if gecko.get("id") != GUID:
            raise Bad("manifest.json add-on id %r, not %s" % (gecko.get("id"), GUID))
        if man.get("version") != version:
            raise Bad("manifest.json version %r, not %s" % (man.get("version"), version))
        return gecko


def vkey(v):
    parts = []
    for p in v.split("."):
        m = re.match(r"([0-9]*)(.*)", p)
        parts.append((int(m.group(1) or 0), m.group(2)))
    while len(parts) < 4:
        parts.append((0, ""))
    return parts


def supports(gecko, app):
    """app (a Firefox version, e.g. 140.5.0esr) is within strict_min_version .. strict_max_version."""
    a = re.sub(r"esr$", "", app)
    lo, hi = gecko.get("strict_min_version"), gecko.get("strict_max_version")
    if lo and vkey(a) < vkey(lo):
        return False
    if hi and hi != "*" and vkey(a) > vkey(hi.replace("*", "999999")):
        return False
    return True


def main(a):
    if len(a) == 2 and a[0] == "fetch":
        out = a[1]
        with tempfile.TemporaryDirectory() as tmp:
            ver, url, sha, size = api(tmp)
            p = os.path.join(tmp, "a.xpi")
            curl(url, p, size + 1)
            if os.path.getsize(p) != size:
                raise Bad("download is %d bytes, the AMO API says %d" % (os.path.getsize(p), size))
            g = verify(p, sha, ver)
            with open(p, "rb") as s, open(out + ".part", "wb") as d:
                d.write(s.read())
            os.chmod(out + ".part", 0o644)
            os.replace(out + ".part", out)
        print(json.dumps({"version": ver, "sha256": sha, "url": url,
                          "strict_min_version": g.get("strict_min_version"),
                          "strict_max_version": g.get("strict_max_version")}))
    elif len(a) == 4 and a[0] == "verify":
        verify(a[1], a[2], a[3])
        print("OK %s %s %s" % (GUID, a[3], a[2]))
    elif len(a) >= 3 and a[0] == "minver":
        with zipfile.ZipFile(a[1]) as z:
            man = json.loads(z.read("manifest.json").decode("utf-8-sig"))
        g = (man.get("browser_specific_settings") or man.get("applications") or {}).get("gecko") or {}
        bad = [v for v in a[2:] if not supports(g, v)]
        if bad:
            raise Bad("uBlock Origin %s needs Firefox %s..%s; this image has %s"
                      % (man.get("version"), g.get("strict_min_version", "any"), g.get("strict_max_version", "any"),
                         ", ".join(bad)))
        print("OK %s %s supports %s (strict_min_version %s)" % (GUID, man.get("version"), ", ".join(a[2:]),
                                                                  g.get("strict_min_version", "none")))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (Bad, OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as e:
        print("ERROR: uBlock Origin: %s" % e, file=sys.stderr)
        sys.exit(1)
