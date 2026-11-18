"""Prestium 2.1 (HiddenForge review): Landlock for Prestium's own Python helpers, with ctypes only.

Landlock (Linux 5.13+, Debian 13's 6.12 kernel: ABI 6) lets an unprivileged process give up access to
files and TCP ports for itself and everything it starts; nothing can lift it again. A helper calls
restrict() first thing, with the paths it really needs:

    import prestium_landlock
    prestium_landlock.restrict("prestium-timesync",
        read=prestium_landlock.SYSTEM_READ + ("/var/lib/tor",),
        write=("/run/prestium", "/var/lib/prestium-timesync"), devices=("/dev/null", "/dev/kmsg"),
        connect_tcp=(9050,))

  read        files and directories it may read (and list); everything else is unreadable
  write       directories (or files) it may also create, change, rename and delete in
  execute     where programs may be started from (default: /usr only, which holds /bin, /sbin and /lib
              on a merged-/usr system; nothing from /tmp, /run, /var or a home directory)
  devices     device files it may read and write (/dev/null, /dev/kmsg ...); the rest of /dev read-only
  connect_tcp TCP ports it may connect to; bind_tcp: ports it may listen on (ABI 4+). Neither given:
              no TCP at all. UDP is not covered by Landlock (the helpers' units restrict it).

Paths that don't exist are skipped. When the kernel has no Landlock (an older kernel, or "landlock" not
in the boot's LSM list) or refuses the ruleset, it logs one line and returns False: the helper runs as
before, under its unit's systemd sandbox. It never raises. Needs no_new_privs, which it sets (each
helper's unit already has NoNewPrivileges=yes).

Not for helpers that read other processes' /proc/<pid>/{exe,environ,maps} (onion-grater, the Wayland
broker): Landlock refuses ptrace-mode access to processes outside the sandbox, so they could no longer
tell who their clients are. Nor for anything that must start setuid programs (no_new_privs).
"""
import ctypes, errno, os, sys

__all__ = ["restrict", "abi_version", "SYSTEM_READ"]

# x86_64 syscall numbers (the same on every architecture with the generic table since 5.13)
_SYS_CREATE, _SYS_ADD_RULE, _SYS_RESTRICT = 444, 445, 446
_CREATE_RULESET_VERSION = 1
_RULE_PATH_BENEATH, _RULE_NET_PORT = 1, 2
_PR_SET_NO_NEW_PRIVS = 38

FS_EXECUTE = 1 << 0
FS_WRITE_FILE = 1 << 1
FS_READ_FILE = 1 << 2
FS_READ_DIR = 1 << 3
FS_REMOVE_DIR = 1 << 4
FS_REMOVE_FILE = 1 << 5
FS_MAKE_CHAR = 1 << 6
FS_MAKE_DIR = 1 << 7
FS_MAKE_REG = 1 << 8
FS_MAKE_SOCK = 1 << 9
FS_MAKE_FIFO = 1 << 10
FS_MAKE_BLOCK = 1 << 11
FS_MAKE_SYM = 1 << 12
FS_REFER = 1 << 13          # ABI 2
FS_TRUNCATE = 1 << 14       # ABI 3
NET_BIND_TCP = 1 << 0       # ABI 4
NET_CONNECT_TCP = 1 << 1

_FS_V1 = (1 << 13) - 1
# rights that may be given on a file (not a directory)
_FILE_ONLY = FS_EXECUTE | FS_WRITE_FILE | FS_READ_FILE | FS_TRUNCATE
READ = FS_READ_FILE | FS_READ_DIR
EXEC = FS_EXECUTE | READ
WRITE = (READ | FS_WRITE_FILE | FS_TRUNCATE | FS_REMOVE_DIR | FS_REMOVE_FILE | FS_MAKE_DIR | FS_MAKE_REG
         | FS_MAKE_SOCK | FS_MAKE_FIFO | FS_MAKE_SYM | FS_REFER)
DEVICE = FS_READ_FILE | FS_WRITE_FILE | FS_TRUNCATE

# what any Python helper needs to read: the interpreter and libraries, configuration, its own and the
# kernel's process information, and the runtime directory. Not /home, /root, /media, /tmp, /var, /opt.
SYSTEM_READ = ("/usr", "/etc", "/proc", "/sys", "/dev", "/run")


class _RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64), ("handled_access_net", ctypes.c_uint64)]


class _PathBeneath(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


class _NetPort(ctypes.Structure):
    _fields_ = [("allowed_access", ctypes.c_uint64), ("port", ctypes.c_uint64)]


_libc = None


def _syscall():
    global _libc
    if _libc is None:
        _libc = ctypes.CDLL(None, use_errno=True)
        _libc.syscall.restype = ctypes.c_long
    return _libc


def _log(name, msg):
    print("%s: landlock: %s" % (name, msg), file=sys.stderr, flush=True)


def abi_version():
    """The kernel's Landlock ABI (0: none: not built, not enabled, or not this architecture)."""
    if os.uname().machine != "x86_64":
        return 0
    libc = _syscall()
    v = libc.syscall(ctypes.c_long(_SYS_CREATE), None, ctypes.c_size_t(0), ctypes.c_uint32(_CREATE_RULESET_VERSION))
    return v if v > 0 else 0


def _handled_fs(abi):
    fs = _FS_V1
    if abi >= 2:
        fs |= FS_REFER
    if abi >= 3:
        fs |= FS_TRUNCATE
    # not handled (stays allowed): IOCTL_DEV (ABI 5), so a tty or /dev/null ioctl never fails
    return fs


def _add_path(libc, rfd, path, access, handled):
    try:
        fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
    except OSError:
        return None                                    # missing: nothing to allow
    try:
        isdir = os.path.isdir("/proc/self/fd/%d" % fd)
        a = access & handled
        if not isdir:
            a &= _FILE_ONLY
        if not a:
            return None
        attr = _PathBeneath(a, fd)
        if libc.syscall(ctypes.c_long(_SYS_ADD_RULE), ctypes.c_int(rfd), ctypes.c_int(_RULE_PATH_BENEATH),
                        ctypes.byref(attr), ctypes.c_uint32(0)) != 0:
            return ctypes.get_errno()
        return 0
    finally:
        os.close(fd)


def restrict(name, read=SYSTEM_READ, write=(), execute=("/usr",), devices=("/dev/null",),
             connect_tcp=(), bind_tcp=()):
    """Apply the ruleset to this process and everything it starts later. True if in force."""
    try:
        abi = abi_version()
        if abi < 1:
            _log(name, "not available in this kernel, running without it"); return False
        libc = _syscall()
        handled = _handled_fs(abi)
        attr = _RulesetAttr(handled, (NET_BIND_TCP | NET_CONNECT_TCP) if abi >= 4 else 0)
        size = ctypes.sizeof(_RulesetAttr) if abi >= 4 else 8
        rfd = libc.syscall(ctypes.c_long(_SYS_CREATE), ctypes.byref(attr), ctypes.c_size_t(size), ctypes.c_uint32(0))
        if rfd < 0:
            _log(name, "could not create a ruleset (%s), running without it" % errno.errorcode.get(ctypes.get_errno(), "?"))
            return False
        try:
            rules = {}
            for paths, acc in ((read, READ), (execute, EXEC), (write, WRITE), (devices, DEVICE)):
                for p in paths:
                    rules[p] = rules.get(p, 0) | acc
            for p, acc in rules.items():
                e = _add_path(libc, rfd, p, acc, handled)
                if e:
                    _log(name, "rule for %s refused (%s), running without Landlock" % (p, errno.errorcode.get(e, e)))
                    return False
            if abi >= 4:
                for ports, acc in ((connect_tcp, NET_CONNECT_TCP), (bind_tcp, NET_BIND_TCP)):
                    for port in ports:
                        na = _NetPort(acc, int(port))
                        if libc.syscall(ctypes.c_long(_SYS_ADD_RULE), ctypes.c_int(rfd), ctypes.c_int(_RULE_NET_PORT),
                                        ctypes.byref(na), ctypes.c_uint32(0)) != 0:
                            _log(name, "port rule %s refused, running without Landlock" % port); return False
            if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
                _log(name, "no_new_privs refused, running without Landlock"); return False
            if libc.syscall(ctypes.c_long(_SYS_RESTRICT), ctypes.c_int(rfd), ctypes.c_uint32(0)) != 0:
                _log(name, "restrict_self refused (%s), running without it" % errno.errorcode.get(ctypes.get_errno(), "?"))
                return False
        finally:
            os.close(rfd)
        _log(name, "in force (ABI %d%s)" % (abi, "" if abi >= 4 else ", no TCP rules before ABI 4"))
        return True
    except Exception as e:                             # never stop a helper because of its sandbox
        _log(name, "error (%s), running without it" % e)
        return False
