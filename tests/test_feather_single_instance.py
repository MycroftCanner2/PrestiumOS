#!/usr/bin/python3
"""PRE-6: Feather's own single-instance check (a QLockFile plus a QLocalServer socket in /tmp) races
when two starts overlap: the later one finds the lock but no socket yet, calls the lock invalid,
takes it over and runs as well. Both then use ~/Monero/wallets: one creates wallet_1 and the other
says "File already exists", then opening it says "wallet_1.keys is opened by another wallet program"
(the other process holds monero's fcntl lock). The slower confined start made the overlap common.
app-confine now serialises Feather's starts: the first keeps a lock in the confine base directory
(not visible to any app) for the app's lifetime; a later one waits until the running Feather listens
on its socket, so the Feather it starts hands over and exits.
Nothing outside a temporary directory changes.
"""
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import types

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AC = os.path.join(R, "config/includes.chroot/usr/local/lib/prestium/app-confine")
fails = 0


def chk(cond, good, fail):
    global fails
    print(("OK   " + good) if cond else ("FAIL " + fail))
    fails += 0 if cond else 1


src = open(AC).read()
ac = types.ModuleType("app_confine")
exec(compile(src, AC, "exec"), ac.__dict__)

chk(ac.SINGLE.get("feather") == "feather-%(user)s.socket", "feather is a single-instance app",
    "SINGLE: %r" % getattr(ac, "SINGLE", None))
chk(ac.APPS["feather"][1] == "feather", "feather has its own group (its /tmp holds the socket)",
    "feather group %r" % (ac.APPS["feather"][1],))
m = src[src.index("def main("):]
chk(re.search(r"if name in SINGLE:\n\s+single_instance\(name, base, ptmp\)", m) is not None
    and m.index("single_instance(name, base, ptmp)") < m.index("os.fork()")
    and m.index("ptmp = safe_dir(") < m.index("single_instance(name, base, ptmp)"),
    "main() serialises before anything is started", "main() does not call single_instance before fork")

t = tempfile.mkdtemp(prefix="single-")
os.environ["USER"] = "user"
try:
    base = os.path.join(t, "base")
    ptmp = os.path.join(t, "tmp")
    os.mkdir(base, 0o700)
    os.mkdir(ptmp, 0o700)
    sp = os.path.join(ptmp, "feather-user.socket")
    first = ac.single_instance("feather", base, ptmp, wait=0.5)
    chk(isinstance(first, int), "first start takes the lock", "first start: %r" % first)
    chk(os.path.dirname(os.path.join(base, ".single-feather")) == base and os.path.exists(os.path.join(base, ".single-feather")),
        "lock file is in the confine base, not the app's runtime dir", "no lock in base")
    # second start while the first app is not listening yet: it must not go on (old: second Feather)
    t0 = time.monotonic()
    try:
        ac.single_instance("feather", base, ptmp, wait=0.8)
        chk(False, "", "second start went on while the first was still starting")
    except ac.Fail:
        chk(time.monotonic() - t0 >= 0.7, "second start waits, then refuses (no second Feather)",
            "second start refused without waiting")
    # a stale socket of an earlier run (nobody listening) does not count
    s = socket.socket(socket.AF_UNIX)
    s.bind(sp)
    s.close()
    try:
        ac.single_instance("feather", base, ptmp, wait=0.6)
        chk(False, "", "a stale socket let a second start go on")
    except ac.Fail:
        chk(True, "a stale socket is not a running Feather", "")
    os.unlink(sp)
    # the first Feather starts listening during the wait: the second start goes on (it hands over)
    srv = socket.socket(socket.AF_UNIX)

    def listen_late():
        time.sleep(0.6)
        srv.bind(sp)
        srv.listen(4)
    th = threading.Thread(target=listen_late)
    th.start()
    t0 = time.monotonic()
    r = ac.single_instance("feather", base, ptmp, wait=5)
    th.join()
    chk(r is None and time.monotonic() - t0 >= 0.5, "second start waits for the running Feather's socket",
        "second start: %r" % r)
    srv.close()
    os.unlink(sp)
    # the first app exits (its app-confine closes the lock): the next start is a first start again
    os.close(first)
    again = ac.single_instance("feather", base, ptmp, wait=0.5)
    chk(isinstance(again, int), "after the app exits the lock is free again", "lock stays held")
    os.close(again)
    # the lock fd is not passed to the app
    chk("O_CLOEXEC" in src[src.index("def single_instance("):src.index("def single_instance(") + 1200],
        "lock fd is close-on-exec", "lock fd inherited by the app")
finally:
    shutil.rmtree(t)

print("%d failure(s)" % fails)
sys.exit(1 if fails else 0)
