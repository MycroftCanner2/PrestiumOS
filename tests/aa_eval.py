#!/usr/bin/env python3
"""Prestium 2.1 (review of 7242e00): answer "does this compiled profile allow PATH with PERMS?" from
`apparmor_parser -p` output (abstractions and variables expanded), for the start-up and self-test
checks in test_apparmor_startup.sh. File rules only; "owner" is assumed to hold (the user's own
files); a deny rule wins over any allow, as in the kernel.

  aa_eval.py EXPANDED < checks      each check line:  allow|deny PROFILE PATH PERMS (PATH may hold spaces)
  PERMS: letters from r w m k l x; x may carry the transition, e.g. x:P (Px/Pix), x:i, x:C.
"""
import re, sys

def load(path):
    lines = []
    for l in open(path):
        l = re.sub(r'(^|\s)#.*$', '', l).strip()
        if l:
            lines.append(l)
    var = {}
    for l in lines:
        m = re.match(r'^(@\{\w+\})\s*(\+?=)\s*(.*)$', l)
        if m:
            vals = m.group(3).split()
            var[m.group(1)] = (var.get(m.group(1), []) + vals) if m.group(2) == '+=' else vals
    profs, stack = {}, []
    for l in lines:
        if l.endswith('{') and (l.startswith('profile ') or l.startswith('/')):
            stack.append(re.match(r'^(?:profile\s+)?(\S+)', l).group(1))
            profs.setdefault('//'.join(stack), [])
        elif l == '}':
            if stack:
                stack.pop()
        elif stack:
            profs['//'.join(stack)].append(l)
    return var, profs

def expand(s, var):
    m = re.search(r'@\{\w+\}', s)
    if not m or m.group(0) not in var:
        return [s]
    return [x for v in var[m.group(0)] for x in expand(s[:m.start()] + v + s[m.end():], var)]

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
            j = g.index(']', i + 1); out += '[' + g[i + 1:j] + ']'; i = j + 1; continue
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

RULE = re.compile(r'^(?:audit\s+)?(deny\s+|allow\s+)?(?:(?:owner|other)\s+)?(?:file\s+)?'
                  r'(?:("[^"]+"|[/@]\S*)\s+([a-zA-Z]+)|([a-zA-Z]+)\s+("[^"]+"|[/@]\S*))(?:\s+->\s+\S+)?\s*,$')

def rules(var, body):
    out = []
    for l in body:
        m = RULE.match(l)
        if not m:
            continue
        path = (m.group(2) or m.group(5)).strip('"'); perms = m.group(3) or m.group(4)
        if not re.fullmatch(r'[rwamlkxiuUpPcC]+', perms):
            continue
        for p in expand(path, var):
            out.append((bool(m.group(1) and m.group(1).startswith('deny')), glob_re(re.sub('/+', '/', p)), perms))
    return out

def check(rs, path, need):
    want_x = None
    if 'x:' in need:
        need, want_x = need.split('x:')[0] + 'x', need.split('x:')[1]
    have, denied, xm = set(), set(), ''
    for deny, rx, perms in rs:
        if not rx.match(path):
            continue
        eff = set(c for c in perms if c in 'rwamlk') | ({'x'} if 'x' in perms else set())
        if deny:
            denied |= eff
        else:
            have |= eff
            if 'x' in perms:
                xm += ''.join(c for c in perms if c in 'iuUpPcC')
    need = set(need)
    ok = not (need - have) and not (need & denied)
    if ok and want_x:
        ok = all(c in xm for c in want_x)
    return ok

def main():
    var, profs = load(sys.argv[1])
    cache, fail = {}, 0
    for l in sys.stdin:
        if not l.strip() or l.lstrip().startswith('#'):
            continue
        expect, prof, *path, need = l.split()
        path = ' '.join(path).strip('"')
        if prof not in profs:
            print(f"FAIL no profile {prof}"); fail = 1; continue
        rs = cache.setdefault(prof, rules(var, profs[prof]))
        got = 'allow' if check(rs, path, need) else 'deny'
        print(('OK   ' if got == expect else 'FAIL ') + f"{prof}: {path} {need} {got}")
        fail |= got != expect
    sys.exit(fail)

if __name__ == '__main__':
    main()
