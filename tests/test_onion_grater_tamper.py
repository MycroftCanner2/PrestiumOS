#!/usr/bin/python3
"""2.1 (audit of 96468c5, L-1): onion-grater refuses a Python client (nyx, OnionShare, the Tor
Connection Assistant) whose environment points Python or the dynamic loader elsewhere, or that runs
executable code from outside the system directories; and the build turns the user's own
site-packages off. Runs onion-grater's own check on fake /proc entries."""
import os, re, sys, tempfile
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
src = open(os.path.join(I, "usr/local/sbin/prestium-onion-grater")).read()
fail = 0
def ok(m): print("OK   " + m)
def bad(m):
    global fail; print("FAIL " + m); fail = 1
a = src.index("ENV_BAD = "); b = src.index("\ndef identify(")
g = {"re": re}; exec(src[a:b], g); tampered = g["tampered"]
SYS_MAPS = ("5581a000-5581b000 r-xp 00000000 08:01 1 /usr/bin/python3.13\n"
            "7f00-7f10 r-xp 00000000 08:01 2 /usr/lib/x86_64-linux-gnu/libc.so.6\n"
            "7f10-7f20 r--p 00000000 08:01 3 /home/user/.cache/fontconfig/abc.cache-9\n"
            "7f20-7f30 rw-p 00000000 00:00 0 \n7ffd-7ffe r-xp 00000000 00:00 0 [vdso]\n")
def case(env, maps=SYS_MAPS):
    d = tempfile.mkdtemp(); os.makedirs(d + "/42")
    open(d + "/42/environ", "wb").write(b"\0".join(env) + b"\0")
    open(d + "/42/maps", "w").write(maps)
    return tampered(42, proc=d)
clean = [b"HOME=/home/user", b"PATH=/usr/bin", b"WAYLAND_DISPLAY=/run/prestium-wl/1000/apps", b"PYTHONDONTWRITEBYTECODE=1"]
r = case(clean); (ok if r is None else bad)("a normal start is accepted (%s)" % r)
for e in (b"PYTHONPATH=/home/user/x", b"PYTHONHOME=/tmp/py", b"PYTHONSTARTUP=/tmp/s.py", b"PYTHONUSERBASE=/tmp",
          b"LD_PRELOAD=/home/user/evil.so", b"LD_LIBRARY_PATH=/tmp", b"LD_AUDIT=/tmp/a.so", b"GCONV_PATH=/tmp",
          b"GLIBC_TUNABLES=glibc.x=1"):
    r = case(clean + [e]); (ok if r else bad)("refused: %s (%s)" % (e.decode(), r))
for m in ("7f40-7f50 r-xp 00000000 08:01 9 /home/user/evil.so\n", "7f40-7f50 r-xp 00000000 08:01 9 /tmp/x/_mod.cpython-313.so\n",
          "7f40-7f50 r-xp 00000000 08:01 9 /dev/shm/x (deleted)\n"):
    r = case(clean, SYS_MAPS + m); (ok if r else bad)("refused: code from %s (%s)" % (m.split()[-1], r))
r = case(clean, SYS_MAPS + "7f40-7f50 r--p 00000000 08:01 9 /home/user/data.bin\n")
(ok if r is None else bad)("a non-executable mapping from the home is fine (%s)" % r)
d = tempfile.mkdtemp(); r = tampered(42, proc=d); (ok if r else bad)("unreadable /proc entry refused (%s)" % r)
ident = src[src.index("def identify("):src.index("def split_args(")]
(ok if "why = tampered(pid)" in ident else bad)("identify() runs the check for the Python clients")
aa = open(os.path.join(I, "etc/apparmor.d/usr.local.sbin.prestium-onion-grater")).read()
(ok if "@{PROC}/[0-9]*/environ r," in aa and "@{PROC}/[0-9]*/maps r," in aa and "deny @{PROC}/*/mem rwx," in aa else bad)(
    "onion-grater profile: environ and maps readable, memory never")
h = open(os.path.join(R, "config/hooks/live/0460-prestium-python-usersite.hook.chroot")).read()
(ok if "ENABLE_USER_SITE = False  # Prestium" in h and "exit 1" in h else bad)("hook 0460 turns the user site off, or fails the build")
sys.exit(fail)
