#!/usr/bin/python3
"""Prestium 2.1: print Tor's bootstrap progress (0-100) for the local status checks.

prestium-netstatus (panel pills), prestium-vm-netcheck (VM diagnosis),
prestium-clockfix and prestium-timesync ask here instead of reading Tor's
journal: in the default boot entry Tor logs nowhere (`Log err file /dev/null`,
prestium-network-logs), so the journal never contains "Bootstrapped 100" and
every journal-based check reported Tor as never connected while Tor itself
worked. This asks Tor's control port for status/bootstrap-phase through the
same onion-grater filter the Tor Connection Assistant uses, so it works in
every boot entry, and copies nothing but a number. Prints nothing and exits
non-zero on any failure; callers treat that as "not bootstrapped yet".
"""
import re
import socket
import sys

CONTROL = "/run/onion-grater/control"


def main():
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(CONTROL)
        f = s.makefile("rwb", buffering=0)
        f.write(b"AUTHENTICATE\r\n")
        if not f.readline().startswith(b"250"):
            return 1
        f.write(b"GETINFO status/bootstrap-phase\r\n")
        pct = None
        while True:
            line = f.readline()
            if not line:
                break
            if line.startswith(b"250-status/bootstrap-phase="):
                m = re.search(rb"PROGRESS=(\d+)", line)
                if m:
                    pct = int(m.group(1))
            elif line.startswith(b"250 ") or line[:1] in (b"4", b"5"):
                break
        if pct is None:
            return 1
        sys.stdout.write("%d\n" % min(max(pct, 0), 100))
        return 0
    except (OSError, ValueError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
