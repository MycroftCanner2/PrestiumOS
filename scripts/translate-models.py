#!/usr/bin/python3 -I
"""Prestium 2.1: fetch Mozilla's Firefox Translations models for Prestium Translate and verify them.

    translate-models.py fetch OUTDIR PAIR:VERSION [PAIR:VERSION ...]   e.g. fetch DIR enru:2.1 ruen:2.1
    translate-models.py verify DIR SHA256FILE                          re-check a staged copy (no network)

Firefox downloads these models from Mozilla's Remote Settings collection main/translations-models. Each
record names one file (model, lex = shortlist, vocab) with its size and SHA-256, and the collection as a whole
carries Mozilla's content signature, the one Firefox itself checks before it trusts a record. So the
models have a publisher signature, one level up: this script checks it, then the files against the signed
records, and fetch-thirdparty.sh checks them against the SHA-256 values pinned in thirdparty/versions.sh.
Every check must pass, or the build stops:
  1. the changeset (HTTPS, firefox.settings.services.mozilla.com) is signed with mode p384ecdsa by a
     certificate chain from content-signature-2.cdn.mozilla.net to Mozilla's AMO production root
     (thirdparty/keys/mozilla-amo-root.pem, the same pinned root as uBlock Origin's check; SHA-256 fingerprint
     below), code-signing purpose, and the signing certificate is for
     remote-settings.content-signature.mozilla.org. The signature is over "Content-Signature:\\x00" and the
     canonical JSON of the collection ({"data": records sorted by id, "last_modified": "<timestamp>"}).
  2. for each PAIR:VERSION exactly one signed record per file type (model, lex, vocab), fromLang/toLang
     and file name as Prestium expects (model.<pair>.intgemm.alphas.bin, lex.50.50.<pair>.s2t.bin,
     vocab.<pair>.spm: the int8 "shifted alphas" models with one shared vocabulary).
  3. the download (HTTPS only, from the collection's attachment server) has exactly the signed size and SHA-256.
It prints one line per file, "PIN <PAIR>_<TYPE> <sha256> <size> <version>", for fetch-thirdparty.sh to compare
with its pins (or print for --repin). The models are MPL-2.0 (mozilla/firefox-translations-models).
"""
import base64, hashlib, json, os, re, subprocess, sys, tempfile

SERVER = "https://firefox.settings.services.mozilla.com/v1"
CHANGESET = SERVER + "/buckets/main/collections/translations-models/changeset?_expected=0"
X5U = re.compile(r"https://content-signature-2\.cdn\.mozilla\.net/[A-Za-z0-9_./-]+\.chain")
ATTACH = re.compile(r"https://firefox-settings-attachments\.cdn\.mozilla\.net/")
SIGNER = "remote-settings.content-signature.mozilla.org"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("PRESTIUM_AMO_ROOT", os.path.join(HERE, "..", "thirdparty", "keys", "mozilla-amo-root.pem"))
# SHA-256 fingerprint of CN=root-ca-production-amo (Mozilla AMO Production Signing Service, 2024-02-01 to 2200-12-03),
# the root of both the add-on signatures and Remote Settings' content signatures
ROOT_FPR = "C8A80E9AFAEF4E219B6FB5D7A71D0F101223BAC5001AC28F9B0D43DC59A106DB"
TYPES = {"model": "model.%s.intgemm.alphas.bin", "lex": "lex.50.50.%s.s2t.bin", "vocab": "vocab.%s.spm"}
PAIRS = {"enru": ("en", "ru"), "ruen": ("ru", "en")}
VERSION = re.compile(r"[0-9]{1,3}(\.[0-9]{1,3}){0,2}([ab][0-9]{1,3})?")
MAXSIZE = 200 << 20


class Bad(Exception):
    pass


def curl(url, out, maxsize):
    r = subprocess.run(["curl", "-sfL", "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "5",
                        "--retry", "3", "-m", "1800", "--max-filesize", str(maxsize), "-o", out, url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise Bad("cannot download %s (curl exit %d)" % (url, r.returncode))


def openssl(*args, data=None):
    r = subprocess.run(["openssl"] + list(args), input=data, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def root_ok(root):
    rc, out, _ = openssl("x509", "-in", root, "-noout", "-fingerprint", "-sha256")
    fpr = out.strip().partition("=")[2].replace(":", "").upper()
    if rc != 0 or fpr != ROOT_FPR:
        raise Bad("%s is not Mozilla's pinned AMO root (fingerprint %s)" % (root, fpr or "unreadable"))


def der_int(b):
    b = b.lstrip(b"\0") or b"\0"
    if b[0] & 0x80:
        b = b"\0" + b
    return b"\x02" + der_len(len(b)) + b


def der_len(n):
    return bytes([n]) if n < 0x80 else b"\x81" + bytes([n])


def raw_to_der(raw):
    """p384ecdsa content signatures are r||s (48 bytes each), base64url; openssl wants DER."""
    if len(raw) != 96:
        raise Bad("the content signature is %d bytes, not 96 (P-384 r||s)" % len(raw))
    body = der_int(raw[:48]) + der_int(raw[48:])
    return b"\x30" + der_len(len(body)) + body


def canonical(records, timestamp):
    return json.dumps({"data": records, "last_modified": str(timestamp)}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_collection(tmp, changeset, root):
    """Mozilla's content signature over the collection; returns the live (not deleted) records."""
    try:
        meta = changeset["metadata"]
        sig = meta["signature"]
        ts = changeset["timestamp"]
        records = changeset["changes"]
    except (KeyError, TypeError) as e:
        raise Bad("the Remote Settings answer is not usable (%s)" % e)
    if sig.get("mode") != "p384ecdsa":
        raise Bad("unexpected content signature mode %r" % sig.get("mode"))
    x5u = sig.get("x5u", "")
    if not (isinstance(x5u, str) and X5U.fullmatch(x5u)):
        raise Bad("unexpected certificate chain URL %r" % (x5u,))
    chain = os.path.join(tmp, "chain.pem")
    curl(x5u, chain, 1 << 20)
    pems = re.findall(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", open(chain).read(), re.S)
    if len(pems) < 2:
        raise Bad("the certificate chain has %d certificates" % len(pems))
    leaf, inter = os.path.join(tmp, "leaf.pem"), os.path.join(tmp, "inter.pem")
    open(leaf, "w").write(pems[0] + "\n")
    open(inter, "w").write("\n".join(pems[1:]) + "\n")
    rc, out, err = openssl("verify", "-CAfile", root, "-no-CApath", "-no-CAstore", "-untrusted", inter,
                           "-purpose", "codesign", leaf)
    if rc != 0:
        raise Bad("the content signature certificate does not chain to Mozilla's root: %s"
                  % ((err or out).strip().splitlines() or ["openssl error"])[-1])
    rc, out, _ = openssl("x509", "-in", leaf, "-noout", "-ext", "subjectAltName")
    if rc != 0 or re.findall(r"DNS:([^,\s]+)", out) != [SIGNER]:
        raise Bad("the content signature certificate is not for %s (%s)" % (SIGNER, out.strip()))
    rc, pub, _ = openssl("x509", "-in", leaf, "-noout", "-pubkey")
    if rc != 0:
        raise Bad("cannot read the signing key")
    pubf, sigf, dataf = (os.path.join(tmp, n) for n in ("pub.pem", "sig.der", "data"))
    open(pubf, "w").write(pub)
    try:
        raw = base64.urlsafe_b64decode(sig["signature"] + "=" * (-len(sig["signature"]) % 4))
    except (ValueError, TypeError, KeyError):
        raise Bad("the content signature is not base64url")
    open(sigf, "wb").write(raw_to_der(raw))
    live = sorted((r for r in records if not r.get("deleted")), key=lambda r: r["id"])
    with open(dataf, "wb") as f:
        f.write(b"Content-Signature:\x00" + canonical(live, ts))
    rc, out, err = openssl("dgst", "-sha384", "-verify", pubf, "-signature", sigf, dataf)
    if rc != 0 or "Verified OK" not in out:
        raise Bad("Mozilla's content signature over the translations-models collection does not verify")
    return live


def pick(records, pair, version):
    src, trg = PAIRS[pair]
    out = {}
    for t, pat in TYPES.items():
        found = [r for r in records if r.get("fromLang") == src and r.get("toLang") == trg
                 and r.get("version") == version and r.get("fileType") == t]
        if len(found) != 1:
            raise Bad("Mozilla's signed collection has %d %s records for %s version %s (expected 1; pick another "
                      "version in thirdparty/versions.sh and --repin)" % (len(found), t, pair, version))
        r = found[0]
        a = r.get("attachment") or {}
        name, h, size, loc = r.get("name"), a.get("hash"), a.get("size"), a.get("location")
        if name != pat % pair or a.get("filename") != name:
            raise Bad("%s %s %s is %r, not the expected %s" % (pair, version, t, name, pat % pair))
        if not (isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h)):
            raise Bad("%s has no SHA-256 in its signed record" % name)
        if not (isinstance(size, int) and 0 < size < MAXSIZE):
            raise Bad("%s has a bad size %r in its signed record" % (name, size))
        if not (isinstance(loc, str) and re.fullmatch(r"[A-Za-z0-9_./-]+", loc) and ".." not in loc.split("/")):
            raise Bad("%s has a bad location %r" % (name, loc))
        out[t] = (name, h, size, loc)
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch(outdir, specs, root):
    pairs = [spec.partition(":")[0] for spec in specs]
    for spec in specs:
        pair, _, version = spec.partition(":")
        if pair not in PAIRS or not VERSION.fullmatch(version):
            raise Bad("bad model spec %r (PAIR:VERSION, PAIR enru or ruen)" % spec)
    if len(set(pairs)) != len(pairs):
        raise Bad("a language pair is named twice")
    root_ok(root)
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "changeset.json")
        curl(CHANGESET, p, 32 << 20)
        try:
            with open(p) as f:
                changeset = json.load(f)
        except ValueError as e:
            raise Bad("the Remote Settings answer is not JSON (%s)" % e)
        records = verify_collection(tmp, changeset, root)
        ip = os.path.join(tmp, "server.json")
        curl(SERVER + "/", ip, 1 << 20)
        with open(ip) as f:
            base = json.load(f)["capabilities"]["attachments"]["base_url"]
        if not ATTACH.fullmatch(base):
            raise Bad("unexpected attachment server %r" % base)
        lines = []
        for spec in specs:
            pair, _, version = spec.partition(":")
            d = os.path.join(outdir, "%s-%s" % (pair, version))
            os.makedirs(d, exist_ok=True)
            for t, (name, h, size, loc) in pick(records, pair, version).items():
                f = os.path.join(d, name)
                if not (os.path.isfile(f) and os.path.getsize(f) == size and sha256(f) == h):
                    curl(base + loc, f + ".part", size + 1)
                    if os.path.getsize(f + ".part") != size:
                        raise Bad("%s is %d bytes, the signed record says %d" % (name, os.path.getsize(f + ".part"), size))
                    got = sha256(f + ".part")
                    if got != h:
                        os.unlink(f + ".part")
                        raise Bad("%s SHA-256 %s != %s (Mozilla's signed record)" % (name, got, h))
                    os.chmod(f + ".part", 0o644)
                    os.replace(f + ".part", f)
                lines.append("PIN %s_%s %s %d %s" % (pair.upper(), t.upper(), h, size, version))
        print("\n".join(lines))


def verify(d, sumfile):
    """every file listed in SHA256FILE (sha256sum format, relative names) matches; nothing else is in d."""
    want = {}
    for l in open(sumfile):
        m = re.fullmatch(r"([0-9a-f]{64})  ([a-z]{4}/[A-Za-z0-9_.]+)\n?", l)
        if not m:
            raise Bad("bad line in %s: %r" % (sumfile, l[:80]))
        want[m.group(2)] = m.group(1)
    have = sorted(os.path.relpath(os.path.join(a, f), d) for a, _, fs in os.walk(d) for f in fs)
    if have != sorted(want):
        raise Bad("%s holds %s, expected %s" % (d, have, sorted(want)))
    for n, h in sorted(want.items()):
        got = sha256(os.path.join(d, n))
        if got != h:
            raise Bad("%s SHA-256 %s != pinned %s" % (n, got, h))
    print("OK %d model files" % len(want))


def main(a):
    if len(a) >= 3 and a[0] == "fetch":
        fetch(a[1], a[2:], ROOT)
    elif len(a) == 3 and a[0] == "verify":
        verify(a[1], a[2])
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (Bad, OSError, ValueError, KeyError, TypeError) as e:
        print("ERROR: translation models: %s" % e, file=sys.stderr)
        sys.exit(1)
