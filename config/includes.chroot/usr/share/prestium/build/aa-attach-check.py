#!/usr/bin/env python3
"""Prestium 2.1: build-time check of the whole AppArmor profile set (hook 0600), as apparmor.service
loads it at boot.

  aa-attach-check.py DIR PRESTIUM_FILE...

1. Every profile file in DIR (what apparmor.service compiles at boot) must compile; one that doesn't
   makes the service fail ("At least one profile failed to load").
2. No other profile may attach to a program a Prestium profile attaches to. When two profiles match the
   same path equally well, the kernel attaches neither ("conflicting profile attachments") and the
   program runs unconfined; when the other one matches it more exactly, that one wins. Debian's
   libreoffice-common profiles (complain mode, exact paths) did that to Prestium's LibreOffice profile.

APPARMOR_PARSER: the parser (default apparmor_parser). Exit 1 on any problem.
"""
import os, re, shlex, subprocess, sys

PARSER = shlex.split(os.environ.get("APPARMOR_PARSER", "apparmor_parser"))
SKIP = re.compile(r'(^\.|^README$|\.dpkg-(new|old|dist|bak|tmp)$|\.rpm(new|save)$|~$)')


def expanded(d, f):
    p = subprocess.run(PARSER + ["-p", "-b", d, os.path.join(d, f)], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def profiles(text):
    """top-level (name, attachment) pairs and variables of `apparmor_parser -p` output"""
    lines = [re.sub(r'(^|\s)#.*$', '', l).strip() for l in text.splitlines()]
    var = {}
    for l in lines:
        m = re.match(r'^(@\{\w+\})\s*(\+?=)\s*(.*)$', l)
        if m:
            v = m.group(3).split()
            var[m.group(1)] = var.get(m.group(1), []) + v if m.group(2) == '+=' else v
    out, depth = [], 0
    for l in lines:
        if not l:
            continue
        if l.endswith('{'):
            if depth == 0:
                t = l[:-1].split()
                if t and t[0] == 'profile' and len(t) > 1:
                    name = t[1]
                    att = t[2] if len(t) > 2 and t[2][0] in '/@"' else (name if name[0] in '/@' else None)
                    out.append((name, att))
                elif t and t[0][0] in '/@"':
                    out.append((t[0], t[0]))
            depth += 1
        elif l.startswith('}'):
            depth = max(0, depth - 1)
    return out, var


def expand_vars(s, var, n=0):
    m = re.search(r'@\{\w+\}', s)
    if not m or n > 20:
        return [s]
    vals = var.get(m.group(0), [m.group(0)])
    return [x for v in vals for x in expand_vars(s[:m.start()] + v + s[m.end():], var, n + 1)]


def braces(s):
    m = re.search(r'\{([^{}]*)\}', s)
    if not m:
        return [s]
    return [x for alt in m.group(1).split(',') for x in braces(s[:m.start()] + alt + s[m.end():])]


def glob_re(g):
    out, i, depth = '', 0, 0
    while i < len(g):
        c = g[i]
        if c == '\\' and i + 1 < len(g):
            out += re.escape(g[i + 1]); i += 2; continue
        if g.startswith('**', i):
            out += '.*'; i += 2; continue
        if c == '*':
            out += '[^/]*'
        elif c == '?':
            out += '[^/]'
        elif c == '[':
            j = g.find(']', i + 1)
            if j < 0:
                out += re.escape(c)
            else:
                out += '[' + g[i + 1:j].replace('^', '\\^', 1) + ']'; i = j + 1; continue
        elif c == '{':
            out += '(?:'; depth += 1
        elif c == '}' and depth:
            out += ')'; depth -= 1
        elif c == ',' and depth:
            out += '|'
        else:
            out += re.escape(c)
        i += 1
    return re.compile('^' + out + '$')


def main():
    if len(sys.argv) < 3:
        print(__doc__.strip(), file=sys.stderr); return 2
    d, ours = sys.argv[1], set(sys.argv[2:])
    disabled = set(os.listdir(os.path.join(d, 'disable'))) if os.path.isdir(os.path.join(d, 'disable')) else set()
    bad, att = 0, []   # att: (file, name, [attachment patterns])
    for f in sorted(os.listdir(d)):
        if not os.path.isfile(os.path.join(d, f)) or SKIP.search(f) or f in disabled:
            continue
        rc, text, err = expanded(d, f)
        if rc != 0:
            print("E: %s does not compile, apparmor.service would fail at boot: %s" % (f, err.strip()[:400]))
            bad = 1
            continue
        ps, var = profiles(text)
        for name, a in ps:
            if a:
                att.append((f, name, [re.sub('/+', '/', x.strip('"')) for x in expand_vars(a, var)]))
    for f in ours:
        if not os.path.isfile(os.path.join(d, f)):
            print("E: %s: no such profile file in %s" % (f, d)); bad = 1
    rx = [(f, n, [glob_re(p) for p in pats]) for f, n, pats in att]
    for f, name, pats in att:
        if f not in ours:
            continue
        for p in pats:
            for path in braces(p):
                if re.search(r'[*?\[]', path):
                    continue   # not a single program; Prestium attaches to named programs only
                for f2, n2, rs in rx:
                    if n2 == name or not any(r.match(path) for r in rs):
                        continue
                    print("E: %s: Prestium profile %s (%s) and %s (%s) both attach; the kernel would run it "
                          "unconfined or under %s" % (path, name, f, n2, f2, n2))
                    bad = 1
    if not bad:
        print("P: %d profiles with attachments compile; no other profile attaches to Prestium's %d programs"
              % (len(att), sum(len(braces(p)) for f, _, ps in att if f in ours for p in ps)))
    return bad


if __name__ == '__main__':
    sys.exit(main())
