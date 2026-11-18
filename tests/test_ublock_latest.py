#!/usr/bin/env python3
"""Prestium 2.1: uBlock Origin is the newest release on addons.mozilla.org at build time
(scripts/amo-latest.py), never a committed copy. Offline: a throw-away CA stands in for Mozilla's AMO root
and signs test add-ons the way AMO does (PKCS#7 mozilla.rsa over mozilla.sf over manifest.mf)."""
import base64, hashlib, importlib.util, io, json, os, re, shutil, subprocess, sys, tempfile, zipfile

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
fails = 0


def check(c, msg):
    global fails
    print(("OK   " if c else "FAIL ") + msg)
    fails += 0 if c else 1


spec = importlib.util.spec_from_file_location("amo", os.path.join(R, "scripts/amo-latest.py"))
amo = importlib.util.module_from_spec(spec); spec.loader.exec_module(amo)
GUID = amo.GUID
W = tempfile.mkdtemp()


def ossl(*a):
    subprocess.run(["openssl"] + list(a), check=True, capture_output=True, cwd=W)


def ca(name, cn):
    open(os.path.join(W, name + ".cnf"), "w").write(
        "[req]\ndistinguished_name=dn\n[dn]\n[v3]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\nextendedKeyUsage=codeSigning\n"
        "[ee]\nbasicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=codeSigning\n")
    ossl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", name + ".key", "-out", name + ".pem", "-days", "30",
         "-subj", "/O=Test/CN=" + cn, "-config", name + ".cnf", "-extensions", "v3")


def ee(name, cn, issuer):
    ossl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", name + ".key", "-out", name + ".csr", "-subj", "/O=Addons/CN=" + cn)
    ossl("x509", "-req", "-in", name + ".csr", "-CA", issuer + ".pem", "-CAkey", issuer + ".key", "-CAcreateserial",
         "-out", name + ".pem", "-days", "30", "-extfile", issuer + ".cnf", "-extensions", "ee")


ca("root", "root-ca-test-amo"); ca("other", "someone-else")
ee("signer", GUID, "root"); ee("wrongcn", "evil@example", "root"); ee("othersigner", GUID, "other")
fpr = subprocess.run(["openssl", "x509", "-in", os.path.join(W, "root.pem"), "-noout", "-fingerprint", "-sha256"],
                     capture_output=True, text=True).stdout.strip().partition("=")[2].replace(":", "").upper()
amo.ROOT_FPR = fpr
ROOT = os.path.join(W, "root.pem")


def b64(b):
    return base64.b64encode(hashlib.sha256(b).digest()).decode()


def xpi(name, version="1.76.4", gid=GUID, signer="signer", tamper=None, extra=None, nocose=False, minv="115.0", drop=None):
    man = {"manifest_version": 2, "name": "uBlock Origin", "version": version,
           "browser_specific_settings": {"gecko": {"id": gid, "strict_min_version": minv}}}
    files = {"manifest.json": json.dumps(man).encode(), "js/a.js": b"console.log(1)\n"}
    if not nocose:
        files["META-INF/cose.manifest"] = b"x"; files["META-INF/cose.sig"] = b"y"
    mf = "Manifest-Version: 1.0\n\n" + "".join("Name: %s\nDigest-Algorithms: SHA256\nSHA256-Digest: %s\n\n" % (n, b64(c))
                                               for n, c in files.items())
    sf = ("Signature-Version: 1.0\nSHA256-Digest-Manifest: %s\n\n" % b64(mf.encode())).encode()
    open(os.path.join(W, "sf"), "wb").write(sf)
    ossl("cms", "-sign", "-binary", "-noattr", "-in", "sf", "-signer", signer + ".pem", "-inkey", signer + ".key",
         "-outform", "DER", "-out", "rsa", "-md", "sha256")
    rsa = open(os.path.join(W, "rsa"), "rb").read()
    if tamper:
        files[tamper] = files[tamper] + b"//changed"
    if extra:
        files[extra] = b"unsigned"
    p = os.path.join(W, name + ".xpi")
    with zipfile.ZipFile(p, "w") as z:
        for n, c in list(files.items()) + [("META-INF/manifest.mf", mf.encode()), ("META-INF/mozilla.sf", sf),
                                           ("META-INF/mozilla.rsa", rsa)]:
            if n != drop:
                z.writestr(n, c)
    return p, hashlib.sha256(open(p, "rb").read()).hexdigest()


def verr(p, sha, version="1.76.4", root=ROOT):
    try:
        amo.verify(p, sha, version, root)
        return None
    except amo.Bad as e:
        return str(e)


p, h = xpi("good")
check(verr(p, h) is None, "a correctly signed add-on passes")
check("SHA-256" in (verr(p, "0" * 64) or ""), "SHA-256 different from the AMO API: refused")
check("version" in (verr(p, h, "1.76.5") or ""), "version different from the AMO API: refused")
q, hq = xpi("tamper", tamper="js/a.js")
check("signed SHA-256" in (verr(q, hq) or ""), "a changed file: refused")
q, hq = xpi("extra", extra="js/evil.js")
check("unlisted" in (verr(q, hq) or ""), "a file not in manifest.mf: refused")
q, hq = xpi("otherca", signer="othersigner")
check("signature check failed" in (verr(q, hq) or ""), "signed by a CA other than the AMO root: refused")
q, hq = xpi("wrongcn", signer="wrongcn")
check("signing certificate" in (verr(q, hq) or ""), "signing certificate for another add-on id: refused")
q, hq = xpi("wrongid", gid="evil@example")
check("add-on id" in (verr(q, hq) or ""), "manifest.json with another gecko id: refused")
q, hq = xpi("nocose", nocose=True)
check("cose.sig missing" in (verr(q, hq) or ""), "no META-INF/cose.sig: refused")
q, hq = xpi("norsa", drop="META-INF/mozilla.rsa")
check("mozilla.rsa missing" in (verr(q, hq) or ""), "no META-INF/mozilla.rsa (unsigned): refused")
check("pinned AMO root" in (verr(p, h, root=os.path.join(W, "other.pem")) or ""), "a root other than the pinned one: refused")

# strict_min_version against the browsers' Firefox versions
g = {"strict_min_version": "115.0"}
check(amo.supports(g, "140.5.0esr") and amo.supports(g, "145.0.1") and not amo.supports(g, "102.15.0esr"),
      "strict_min_version 115.0: 140 ESR and 145 yes, 102 ESR no")
check(not amo.supports({"strict_min_version": "146.0"}, "140.5.0"), "a release needing a newer Firefox than Tor Browser's: refused")
check(not amo.supports({"strict_max_version": "139.*"}, "140.5.0") and amo.supports({"strict_max_version": "140.*"}, "140.5.0"),
      "strict_max_version is honoured")
q, _ = xpi("min146", minv="146.0")
r = subprocess.run([sys.executable, os.path.join(R, "scripts/amo-latest.py"), "minver", q, "140.5.0", "146.0"],
                   capture_output=True, text=True)
check(r.returncode == 1 and "140.5.0" in r.stderr, "minver: fails the build for an unsupported browser")

# the API answer
def api_with(d):
    def fake(url, out, maxsize=None):
        open(out, "w").write(json.dumps(d))
    amo.curl = fake
    try:
        return amo.api(W)
    except amo.Bad as e:
        return "ERR " + str(e)
good = {"guid": GUID, "current_version": {"version": "1.76.4", "file": {
    "url": "https://addons.mozilla.org/firefox/downloads/file/5257481/ublock_origin-1.76.4.xpi",
    "hash": "sha256:" + "a" * 64, "size": 1000, "status": "public"}}}
check(api_with(good) == ("1.76.4", good["current_version"]["file"]["url"], "a" * 64, 1000), "API: version, URL, SHA-256, size")
for what, change in (("another guid", ("guid", "x@y")), ("an http URL", ("url", "http://addons.mozilla.org/firefox/downloads/file/1/a.xpi")),
                     ("a URL off AMO", ("url", "https://evil.example/firefox/downloads/file/1/a.xpi")),
                     ("a sha1 hash", ("hash", "sha1:" + "a" * 40)), ("an unlisted file", ("status", "disabled")),
                     ("a bad version", ("version", "1.76.4; rm -rf /"))):
    d = json.loads(json.dumps(good))
    k, v = change
    if k == "guid":
        d[k] = v
    elif k == "version":
        d["current_version"][k] = v
    else:
        d["current_version"]["file"][k] = v
    check(str(api_with(d)).startswith("ERR"), "API: %s is refused" % what)

# the shipped root is Mozilla's, with the pinned fingerprint
spec2 = importlib.util.spec_from_file_location("amo2", os.path.join(R, "scripts/amo-latest.py"))
amo2 = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(amo2)
try:
    amo2.root_ok(amo2.ROOT); ok = True
except amo2.Bad:
    ok = False
check(ok, "thirdparty/keys/mozilla-amo-root.pem is Mozilla's AMO root (pinned fingerprint)")
subj = subprocess.run(["openssl", "x509", "-in", amo2.ROOT, "-noout", "-subject"], capture_output=True, text=True).stdout
check("root-ca-production-amo" in subj, "root subject is root-ca-production-amo")

# wiring: nothing committed, fetched + staged + installed every build
ls = subprocess.run(["git", "-C", R, "ls-files"], capture_output=True, text=True).stdout.splitlines()
check(not [f for f in ls if "uBlock0@raymondhill.net" in f], "no uBlock Origin .xpi is committed")
check(len([f for f in ls if f.endswith("{73a6fe31-595d-460b-a920-fcc0f8843232}.xpi")]) == 2, "NoScript (LibreWolf) is still shipped")
F = open(os.path.join(R, "scripts/fetch-thirdparty.sh")).read()
check('amo-latest.py" fetch' in F and '"ublock-origin.xpi $UB_SHA256"' in F, "fetch-thirdparty.sh fetches and re-checks the staged copy")
H = open(os.path.join(R, "config/hooks/live/0200-prestium-thirdparty.hook.chroot")).read()
check('amo-latest.py" verify' in H and 'amo-latest.py" minver' in H, "hook 0200 verifies again and checks strict_min_version")
for d in ("/usr/share/librewolf/distribution/extensions", '"$O/librewolf/distribution/extensions"',
          '"$O/tor-browser/Browser/distribution/extensions"'):
    check(d in H, "hook 0200 installs into " + d)
check(H.index("# uBlock Origin (fetched") < H.index('cp -a "$O/tor-browser/." /opt/tor-browser/'),
      "installed into the overlay before Tor Browser is built from it")
for f in ("usr/local/share/prestium-tor-browser/user.js",):
    t = open(os.path.join(I, f)).read()
    check(not re.search(r'extensions\.update\.(enabled|autoUpdateDefault)"\s*,\s*false', t), f + ": add-on updates stay on")
for f in ("usr/share/librewolf/distribution/policies.json", "usr/share/prestium/opt-overlay/tor-browser/Browser/distribution/policies.json"):
    t = open(os.path.join(I, f)).read()
    check("extensions.update" not in t and '"ExtensionUpdate": false' not in t, f + ": add-on updates not disabled")
shutil.rmtree(W, ignore_errors=True)
print("ok" if not fails else "%d failed" % fails)
sys.exit(1 if fails else 0)
