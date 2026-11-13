#!/usr/bin/env python3
"""Prestium 2.1 (contrast review): WCAG 2 contrast of every text/background, indicator and focus colour
pair on the dark surfaces, read from the files the image ships: the lock screen's password prompt
(swaylock), GTK 3 and GTK 4 (the apps, the broker's zenity dialogs such as the Lock Screen password, the
Connection Assistants, the GNOME passphrase prompt), Qt (Kvantum), KDE (Kleopatra), labwc (titles, menus,
OSD), waybar, mako and the assistants' error text.
2.1 (UI pass): also GTK 3 destructive buttons, message bars and section cards, GTK 4 destructive buttons,
GTK 2 (Prestium-Dark's colour scheme for Pidgin and pinentry-gtk2), /etc/xdg/kdeglobals (as Prestium.colors),
the terminal (foot), The Lounge's default theme (Tech Innovation) and the I2P web pages (webconsole, torrents).
2.1: GTK 3/4 links and visited links #8ab8ff; progress bar text (show-text) on the trough and the fill.
Targets: text 7:1 (4.5:1 for disabled text and for coloured text on the selection), indicators, rings,
edges and focus 3:1. `-v` prints every pair; PRESTIUM_ROOT checks another checkout (for before/after)."""
import os, re, sys

R = os.environ.get("PRESTIUM_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
V = "-v" in sys.argv
fails = []
rows = []


def rgb(c):
    c = c.strip().lstrip('#')
    if re.fullmatch(r'\d+,\d+,\d+', c):
        return tuple(int(x) for x in c.split(',')) + (1.0,)
    if len(c) == 3:
        c = ''.join(x * 2 for x in c)
    a = int(c[6:8], 16) / 255 if len(c) == 8 else 1.0
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)


def over(fg, bg):
    r, g, b, a = rgb(fg)
    R_, G, B, _ = rgb(bg)
    return '#%02x%02x%02x' % tuple(round(x * a + y * (1 - a)) for x, y in ((r, R_), (g, G), (b, B)))


def lum(c):
    r, g, b, _ = rgb(c)
    f = lambda v: v / 255 / 12.92 if v / 255 <= 0.04045 else ((v / 255 + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    if rgb(a)[3] < 1:
        a = over(a, b)
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def need(surface, what, fg, bg, minimum):
    r = ratio(fg, bg)
    rows.append((surface, what, fg, bg, r, minimum))
    if r + 1e-9 < minimum:
        fails.append("%s: %s %s on %s is %.2f:1, needs %.1f:1" % (surface, what, fg, bg, r, minimum))


def read(p):
    return open(os.path.join(I, p)).read()


def css(text):
    """selector -> {property: value}, later rules win; @define-color names too"""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    out = {'@': dict(re.findall(r'@define-color\s+(\w+)\s+([^;]+);', text))}
    for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'@define-color[^;]+;', '', text)):
        decl = dict((k.strip(), v.strip()) for k, v in re.findall(r'([\w-]+)\s*:\s*([^;]+)', body))
        for s in sel.split(','):
            out.setdefault(' '.join(s.split()), {}).update(decl)
    return out


def col(v):
    m = re.search(r'#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\b|rgba?\(([^)]*)\)', v)
    if not m:
        raise KeyError(v)
    if m.group(0).startswith('#'):
        return m.group(0)
    p = [x.strip() for x in m.group(1).split(',')]
    a = float(p[3]) if len(p) > 3 else 1
    return '#%02x%02x%02x%02x' % (int(p[0]), int(p[1]), int(p[2]), round(a * 255))


TEXT, INDICATOR, DISABLED = 7.0, 3.0, 4.5

# --- lock screen (swaylock): the password prompt in every state ---
sw = dict(l.split('=', 1) for l in read("usr/share/prestium/swaylock.conf").splitlines() if '=' in l and not l.startswith('#'))
flags = set(l.strip() for l in read("usr/share/prestium/swaylock.conf").splitlines() if l and '=' not in l and not l.startswith('#'))
S = "lock screen"
for f in ("indicator-idle-visible", "indicator-caps-lock", "show-failed-attempts", "ignore-empty-password"):
    if f not in flags:
        fails.append("%s: %s missing" % (S, f))
scr = sw["color"]
for st, tx, ins, ring in (("typing", "text-color", "inside-color", "ring-color"),
                          ("Verifying", "text-ver-color", "inside-ver-color", "ring-ver-color"),
                          ("Wrong", "text-wrong-color", "inside-wrong-color", "ring-wrong-color"),
                          ("Cleared", "text-clear-color", "inside-clear-color", "ring-clear-color"),
                          ("Caps Lock", "text-caps-lock-color", "inside-caps-lock-color", "ring-caps-lock-color")):
    need(S, "%s text in the disc" % st, sw[tx], sw[ins], TEXT)
    need(S, "%s ring on the screen" % st, sw[ring], scr, INDICATOR)
need(S, "key tick on the ring", sw["key-hl-color"], sw["ring-color"], INDICATOR)
need(S, "key tick on the screen", sw["key-hl-color"], scr, INDICATOR)
need(S, "backspace gap on the ring", sw["bs-hl-color"], sw["ring-color"], INDICATOR)
need(S, "Caps Lock key tick on its ring", sw["caps-lock-key-hl-color"], sw["ring-caps-lock-color"], INDICATOR)
need(S, "Caps Lock backspace on its ring", sw["caps-lock-bs-hl-color"], sw["ring-caps-lock-color"], INDICATOR)
need(S, "keyboard layout text", sw["layout-text-color"], sw["layout-bg-color"], TEXT)
rings = [sw[k] for k in ("ring-color", "ring-ver-color", "ring-wrong-color", "ring-clear-color", "ring-caps-lock-color")]
if len(set(r.lower() for r in rings)) != len(rings):
    fails.append("%s: two states share a ring colour" % S)

# --- GTK 3 (apps, broker dialogs, assistants, passphrase prompt) ---
g = css(read("usr/share/prestium/theme/gtk3.css"))
S = "GTK 3"
win, base = g['@']['theme_bg_color'], g['@']['theme_base_color']
fg = g['@']['theme_fg_color']
need(S, "text on windows", fg, win, TEXT)
need(S, "text on views", fg, base, TEXT)
need(S, "text on bars and dialogs", fg, col(g['headerbar']['background-color']), TEXT)
need(S, "secondary (dim) text", col(g['.dim-label']['color']), win, TEXT)
need(S, "selected text", col(g['selection']['color']), col(g['selection']['background-color']), TEXT)
need(S, "selected text (unfocused window)", "#ffffff", col(g['row:selected:backdrop']['background-color']), TEXT)
e = g['entry']
need(S, "entry text", col(e['color']), col(e['background-color']), TEXT)
need(S, "entry edge on the entry", col(e['border-color']), col(e['background-color']), INDICATOR)
for bgname, bg in (("window", win), ("dialog", "#262626")):
    need(S, "entry edge on the %s" % bgname, col(e['border-color']), bg, INDICATOR)
need(S, "entry focus edge", col(g['entry:focus']['border-color']), col(e['background-color']), INDICATOR)
need(S, "entry error edge", col(g['entry.error']['border-color']), col(e['background-color']), INDICATOR)
need(S, "disabled entry text", col(g['entry:disabled']['color']), col(g['entry:disabled']['background-color']), DISABLED)
need(S, "error text on windows", g['@']['error_color'], win, TEXT)
need(S, "error text on dialogs", g["@"]["error_color"], "#262626", TEXT)
need(S, "accent text on windows", g['@']['accent_color'], win, TEXT)
need(S, "focus outline on views", col(g['button:focus']['outline-color']), base, INDICATOR)
need(S, "focus outline on buttons", col(g['button:focus']['outline-color']), "#353535", INDICATOR)
sa = g['button.suggested-action']
for st, sel in (("", 'button.suggested-action'), (" (hover)", 'button.suggested-action:hover'),
                (" (pressed)", 'button.suggested-action:active'), (" (unfocused window)", 'button.suggested-action:backdrop')):
    need(S, "default button text" + st, col(sa['color']), col(g[sel]['background-color']), TEXT)
need(S, "default button text (disabled)", col(g['button.suggested-action:disabled']['color']),
     col(g['button.suggested-action:disabled']['background-color']), DISABLED)
need(S, "check mark", col(g['check:checked']['color']), col(g['check:checked']['background-color']), DISABLED)
need(S, "checked box edge", col(g['check:checked']['border-color']), win, INDICATOR)
need(S, "slider and level bar fill", col(g['scale highlight']['background-color']), win, INDICATOR)
need(S, "selected tab underline", col(g['notebook > header > tabs > tab:checked']['box-shadow']), win, INDICATOR)
need(S, "sidebar selection text", col(g['placessidebar row:selected']['color']), col(g['placessidebar row:selected']['background-color']), TEXT)
pt, tr, pf = col(g['progressbar']['color']), col(g['progressbar trough']['background-color']), col(g['progressbar progress']['background-color'])
need(S, "progress text on the trough", pt, tr, TEXT)
need(S, "progress text on the fill", pt, pf, TEXT)
need(S, "progress text on section cards", pt, "#262626", TEXT)
need(S, "progress trough edge on the trough", col(g['progressbar trough']['border-color']), tr, INDICATOR)
need(S, "progress trough edge on section cards", col(g['progressbar trough']['border-color']), "#262626", INDICATOR)
for bgname, bg in (("windows", win), ("views", base), ("section cards", "#262626")):
    need(S, "links on " + bgname, col(g['*:link']['color']), bg, TEXT)
    need(S, "visited links on " + bgname, col(g['*:visited']['color']), bg, TEXT)
    need(S, "link hover on " + bgname, col(g['*:link:hover']['color']), bg, TEXT)
need(S, "tooltip text", col(g['tooltip.background']['color']), col(g['tooltip.background']['background-color']), TEXT)

# --- GTK 4 / libadwaita ---
g4 = css(read("usr/share/prestium/theme/gtk4.css"))
S = "GTK 4"
d = g4['@']
need(S, "accent button text", d['accent_fg_color'], d['accent_bg_color'], TEXT)
need(S, "accent button text (hover)", d['accent_fg_color'], col(g4['button.suggested-action:hover']['background-color']), TEXT)
need(S, "accent button text (pressed)", d['accent_fg_color'], col(g4['button.suggested-action:active']['background-color']), TEXT)
for n in ("window_bg_color", "view_bg_color", "card_bg_color", "dialog_bg_color", "headerbar_bg_color"):
    need(S, "text on %s" % n, "#ffffff", d[n], TEXT)
    need(S, "accent text on %s" % n, d['accent_color'], d[n], TEXT)
    need(S, "error text on %s" % n, d['error_color'], d[n], TEXT)
ent = g4['entry']
need(S, "entry text", col(ent['color']), col(ent['background-color']), TEXT)
need(S, "entry placeholder", col(g4['entry > text > placeholder']['color']), col(ent['background-color']), DISABLED)
need(S, "entry edge", col(ent['box-shadow']), col(ent['background-color']), INDICATOR)
need(S, "entry edge on dialogs", col(ent['box-shadow']), d['dialog_bg_color'], INDICATOR)
need(S, "entry focus outline", col(g4['entry:focus-within']['outline-color']), col(ent['background-color']), INDICATOR)
need(S, "entry error edge", col(g4['entry.error']['box-shadow']), col(ent['background-color']), INDICATOR)
for n in ("window_bg_color", "view_bg_color", "card_bg_color", "dialog_bg_color"):
    need(S, "links on %s" % n, col(g4['link']['color']), d[n], TEXT)
    need(S, "visited links on %s" % n, col(g4['link:visited']['color']), d[n], TEXT)
    need(S, "link hover on %s" % n, col(g4['link:hover']['color']), d[n], TEXT)
pt4, tr4, pf4 = col(g4['progressbar']['color']), col(g4['progressbar trough']['background-color']), col(g4['progressbar progress']['background-color'])
need(S, "progress text on the trough", pt4, tr4, TEXT)
need(S, "progress text on the fill", pt4, pf4, TEXT)
need(S, "progress text on dialogs", pt4, d['dialog_bg_color'], TEXT)
need(S, "progress trough edge on the trough", col(g4['progressbar trough']['border-color']), tr4, INDICATOR)
need(S, "progress trough edge on dialogs", col(g4['progressbar trough']['border-color']), d['dialog_bg_color'], INDICATOR)

# --- Qt (Kvantum "Prestium", hook 0455) ---
kv = dict(re.findall(r"^set_color (\S+) '(#[0-9a-fA-F]{6})'", open(os.path.join(R, "config/hooks/live/0455-prestium-qt-theme.hook.chroot")).read(), re.M))
S = "Qt (Kvantum)"
need(S, "text on windows", kv['window.text.color'], kv['window.color'], TEXT)
need(S, "text on views", kv['text.color'], kv['base.color'], TEXT)
need(S, "text on alternate rows", kv['text.color'], kv['alt.base.color'], TEXT)
need(S, "button text", kv['button.text.color'], kv['button.color'], TEXT)
need(S, "selected text", kv['highlight.text.color'], kv['highlight.color'], TEXT)
need(S, "selected text (unfocused window)", kv['highlight.text.color'], kv['inactive.highlight.color'], TEXT)
need(S, "disabled text", kv['disabled.text.color'], kv['button.color'], DISABLED)
need(S, "links", kv['link.color'], kv['base.color'], TEXT)
need(S, "visited links", kv['link.visited.color'], kv['base.color'], TEXT)

# --- KDE colour scheme (Kleopatra) ---
S = "KDE (Kleopatra)"
sec, kd = None, {}
for l in read("usr/share/color-schemes/Prestium.colors").splitlines():
    if l.startswith('['):
        sec = l
    elif '=' in l and sec:
        kd.setdefault(sec, {})[l.split('=', 1)[0]] = l.split('=', 1)[1]
for s in ("[Colors:Window]", "[Colors:View]", "[Colors:Button]", "[Colors:Selection]", "[Colors:Tooltip]", "[Colors:Header]"):
    c = kd[s]
    bg = c['BackgroundNormal']
    sel = s == "[Colors:Selection]"
    need(S, "%s text" % s[8:-1], c['ForegroundNormal'], bg, TEXT)
    need(S, "%s inactive text" % s[8:-1], c['ForegroundInactive'], bg, DISABLED)
    for k in ('ForegroundActive', 'ForegroundLink', 'ForegroundVisited', 'ForegroundNegative', 'ForegroundNeutral', 'ForegroundPositive'):
        need(S, "%s %s" % (s[8:-1], k[10:].lower()), c[k], bg, DISABLED if sel else TEXT)
    if not sel:
        need(S, "%s focus decoration" % s[8:-1], c['DecorationFocus'], bg, INDICATOR)

# --- labwc (titles, menus, window switcher) ---
th = dict(re.findall(r'^([\w.-]+):\s*(#[0-9a-fA-F]{6,8})', read("usr/share/themes/Prestium-Dark/openbox-3/themerc"), re.M))
S = "labwc"
need(S, "active title", th['window.active.label.text.color'], th['window.active.title.bg.color'], TEXT)
need(S, "inactive title", th['window.inactive.label.text.color'], th['window.inactive.title.bg.color'], DISABLED)
need(S, "title buttons", th['window.active.button.unpressed.image.color'], th['window.active.title.bg.color'], INDICATOR)
need(S, "active window edge", th['window.active.border.color'], th['window.active.title.bg.color'], INDICATOR)
need(S, "active window edge on the desktop", th['window.active.border.color'], "#161616", INDICATOR)
need(S, "menu items", th['menu.items.text.color'], th['menu.items.bg.color'], TEXT)
need(S, "highlighted menu item", th['menu.items.active.text.color'], th['menu.items.active.bg.color'], TEXT)
need(S, "OSD text", th['osd.label.text.color'], th['osd.bg.color'], TEXT)
need(S, "OSD edge", th['osd.border.color'], th['osd.bg.color'], INDICATOR)

# --- waybar ---
wb = css(read("etc/xdg/waybar/style.css"))
S = "waybar"
bar = over(col(wb['window#waybar']['background']), "#161616")
need(S, "bar text", col(wb['window#waybar']['color']), bar, TEXT)
m = wb['#custom-menu']
need(S, "Menu button", col(m['color']), col(m['background']), TEXT)
need(S, "Menu button (hover)", col(m['color']), col(wb['#custom-menu:hover']['background']), TEXT)
need(S, "window buttons", col(wb['#taskbar button']['color']), bar, TEXT)
need(S, "window buttons (hover)", col(wb['#taskbar button:hover']['color']), col(wb['#taskbar button:hover']['background']), TEXT)
need(S, "active window underline", col(wb['#taskbar button.active']['box-shadow']), col(wb['#taskbar button.active']['background']), INDICATOR)
p = wb['#custom-tor']
need(S, "Tor/I2P pill (idle)", col(p['color']), col(p['background']), TEXT)
for st in ("connecting", "ready", "failed"):
    q = wb['#custom-tor.' + st]
    need(S, "Tor/I2P pill (%s)" % st, col(q['color']), col(q['background']), TEXT)
need(S, "pill hover edge", col(wb['#custom-tor:hover']['border-color']), col(p['background']), INDICATOR)
for k in ('#network.disconnected', '#battery.warning:not(.charging)', '#battery.critical:not(.charging)', '#custom-timesync.syncing', '#custom-timesync.failed'):
    need(S, k, col(wb[k]['color']), bar, TEXT)
need(S, "muted volume", col(wb['#pulseaudio.muted']['color']), bar, DISABLED)
need(S, "tooltip text", col(wb['tooltip label']['color']), col(wb['tooltip']['background']), TEXT)

# --- mako (notifications) ---
S = "mako"
sec, mk = "", {"": {}}
for l in read("etc/xdg/mako/config").splitlines():
    l = l.strip()
    if l.startswith('['):
        sec = l; mk.setdefault(sec, {})
    elif '=' in l and not l.startswith('#'):
        mk[sec][l.split('=', 1)[0]] = l.split('=', 1)[1]
top = mk[""]
nbg = over(top['background-color'], "#161616")
need(S, "normal text", top['text-color'], nbg, TEXT)
need(S, "normal edge", top['border-color'], nbg, INDICATOR)
need(S, "low-urgency text", mk['[urgency=low]']['text-color'], nbg, TEXT)
need(S, "low-urgency edge", mk['[urgency=low]']['border-color'], nbg, INDICATOR)
cbg = over(mk['[urgency=critical]']['background-color'], "#161616")
need(S, "critical text", top['text-color'], cbg, TEXT)
need(S, "critical edge", mk['[urgency=critical]']['border-color'], cbg, INDICATOR)
need(S, "volume/brightness OSD edge", mk['[category=prestium.osd]']['border-color'], nbg, INDICATOR)
need(S, "text over the progress bar", top['text-color'], col(top['progress-color']), TEXT)

# --- 2.1 (UI pass): GTK 3 destructive buttons, message bars, section cards ---
S = "GTK 3"
for st, sel in (("", 'button.destructive-action'), (" (hover)", 'button.destructive-action:hover'),
                (" (pressed)", 'button.destructive-action:active'), (" (unfocused window)", 'button.destructive-action:backdrop')):
    need(S, "destructive button text" + st, col(g['button.destructive-action']['color']), col(g[sel]['background-color']), TEXT)
need(S, "destructive button text (disabled)", col(g['button.destructive-action:disabled']['color']),
     col(g['button.destructive-action:disabled']['background-color']), DISABLED)
for kind, sel in (("info", 'infobar > revealer > box'), ("warning", 'infobar.warning > revealer > box'),
                  ("error", 'infobar.error > revealer > box')):
    bg = col(g[sel]['background-color'])
    need(S, "message bar text (%s)" % kind, col(g['infobar > revealer > box label']['color']), bg, TEXT)
    need(S, "message bar edge (%s)" % kind, col(g[sel]['box-shadow']), bg, INDICATOR)
ibb = g['infobar button:not(.default):not(.suggested-action)']
need(S, "message bar button text", col(ibb['color']), col(ibb['background-color']), TEXT)
need(S, "message bar button text (hover)", col(ibb['color']),
     col(g['infobar button:not(.default):not(.suggested-action):hover']['background-color']), TEXT)
card = col(g['frame.prestium-section > border']['background-color'])
need(S, "section title on windows", col(g['frame.prestium-section > label']['color']), win, TEXT)
need(S, "text in section cards", fg, card, TEXT)
need(S, "secondary text in section cards", col(g['.dim-label']['color']), card, TEXT)
need(S, "entry edge in section cards", col(e['border-color']), card, INDICATOR)

# --- GTK 4 destructive buttons ---
S = "GTK 4"
need(S, "destructive button text", d['destructive_fg_color'], d['destructive_bg_color'], TEXT)
need(S, "destructive button text (hover)", d['destructive_fg_color'], col(g4['button.destructive-action:hover']['background-color']), TEXT)
need(S, "destructive button text (pressed)", d['destructive_fg_color'], col(g4['button.destructive-action:active']['background-color']), TEXT)
for n in ("window_bg_color", "dialog_bg_color"):
    need(S, "destructive text on %s" % n, d['destructive_color'], d[n], TEXT)

# --- GTK 2 (Pidgin, pinentry-gtk2): Prestium-Dark's colour scheme ---
S = "GTK 2"
g2 = dict(re.findall(r'(\w+):(#[0-9a-fA-F]{6})', " ".join(re.findall(r'^gtk-color-scheme\s*=\s*"([^"]*)"',
          read("usr/share/themes/Prestium-Dark/gtk-2.0/gtkrc"), re.M)).replace("\\n", " ")))
need(S, "text on views", g2['text_color'], g2['base_color'], TEXT)
need(S, "text on windows", g2['fg_color'], g2['bg_color'], TEXT)
need(S, "selected text", g2['selected_fg_color'], g2['selected_bg_color'], TEXT)
need(S, "disabled text", g2['insensitive_fg_color'], g2['insensitive_bg_color'], DISABLED)
need(S, "menu text", g2['fg_color'], g2['menu_color'], TEXT)
need(S, "links", g2['link_color'], g2['base_color'], TEXT)
need(S, "visited links", g2['visited_link_color'], g2['base_color'], TEXT)
need(S, "tooltips", g2['tooltip_fg_color'], g2['tooltip_bg_color'], TEXT)
need(S, "column headers", g2['column_header_color'], g2['base_color'], TEXT)

# --- KDE: /etc/xdg/kdeglobals carries the same colours as Prestium.colors ---
S = "KDE (kdeglobals)"
sec, kg = None, {}
for l in read("etc/xdg/kdeglobals").splitlines():
    if l.startswith('['):
        sec = l
    elif '=' in l and sec:
        kg.setdefault(sec, {})[l.split('=', 1)[0]] = l.split('=', 1)[1]
for s_ in ("[Colors:Window]", "[Colors:View]", "[Colors:Button]", "[Colors:Selection]", "[Colors:Tooltip]", "[Colors:Header]"):
    c = kg[s_]; bg = c['BackgroundNormal']; sel = s_ == "[Colors:Selection]"
    need(S, "%s text" % s_[8:-1], c['ForegroundNormal'], bg, TEXT)
    for k in ('ForegroundActive', 'ForegroundLink', 'ForegroundVisited', 'ForegroundNegative'):
        need(S, "%s %s" % (s_[8:-1], k[10:].lower()), c[k], bg, DISABLED if sel else TEXT)
    if not sel:
        need(S, "%s focus decoration" % s_[8:-1], c['DecorationFocus'], bg, INDICATOR)

# --- terminal (foot) ---
S = "terminal (foot)"
ft = dict(l.split('=', 1) for l in read("etc/xdg/foot/foot.ini").splitlines() if '=' in l and not l.startswith('#'))
need(S, "text", ft['foreground'], ft['background'], TEXT)
need(S, "selected text", ft['selection-foreground'], ft['selection-background'], TEXT)

# --- The Lounge's default theme (Tech Innovation): Prestium's palette ---
S = "The Lounge (default)"
tl = dict(re.findall(r'(--t-[\w-]+):\s*(#[0-9a-fA-F]{6})', read(
    "var/lib/thelounge/packages/node_modules/thelounge-theme-tech-innovation/theme.css")))
need(S, "active channel text", tl['--t-side-active-fg'], tl['--t-side-active'], TEXT)
need(S, "chat text", tl['--t-fg'], tl['--t-win'], TEXT)
need(S, "selected nick text", tl['--t-fg'], tl['--t-sel'], TEXT)
need(S, "message field text", tl['--t-in-fg'], tl['--t-in-bg'], TEXT)
need(S, "message field edge", tl['--t-in-line'], tl['--t-in-bg'], INDICATOR)

# --- I2P web pages (webconsole, torrents): the desktop's palette ---
for S, f in (("I2P webconsole", "var/lib/i2pd/webconsole/style.css"),
             ("I2P torrents", "usr/share/prestium/torrents-theme/prestium-dark.css")):
    t = re.sub(r'/\*.*?\*/', '', read(f), flags=re.S)
    v = dict(re.findall(r'--([\w-]+):\s*(#[0-9a-fA-F]{6})', t))
    for bgk in ("bg", "panel") + (("panel2",) if "panel2" in v else ()):
        need(S, "text on %s" % bgk, v['fg'], v[bgk], TEXT)
        need(S, "secondary text on %s" % bgk, v['muted'], v[bgk], DISABLED if bgk == "panel2" else TEXT)
        need(S, "accent text on %s" % bgk, v['accent'], v[bgk], TEXT)
        for k in ("ok", "warn", "bad"):
            need(S, "%s text on %s" % (k, bgk), v[k], v[bgk], TEXT)
    need(S, "text on the accent fill (hover)", "#ffffff", v['accent-bg'], TEXT)
    if "dl" in v:
        need(S, "download speed text", v['dl'], v['panel'], DISABLED)
# torrent progress bars: bold 12 px white text over each state's fill (4.5:1)
tt = read("usr/share/prestium/torrents-theme/prestium-dark.css")
tv = dict(re.findall(r'--([\w-]+):\s*(#[0-9a-fA-F]{6})', tt))
for fill, state in re.findall(r'\.progress-fill\[style\*="[^"]+"\]\s*\{\s*background-color:\s*([^ ;!]+)[^}]*\}\s*/\*\s*([\w /]+?)\s*\*/', tt):
    fill = tv[fill[6:-1]] if fill.startswith("var(--") else fill
    need("I2P torrents", "progress text (bold, %s)" % state, "#ffffff", fill, DISABLED)

# --- Connection Assistants: error text in the window ---
for f in ("usr/local/bin/prestium-tor-assistant", "usr/local/bin/prestium-i2p-assistant"):
    for c in re.findall(r"foreground=[\"'](#[0-9a-fA-F]{6})", read(f)):
        need(os.path.basename(f), "error text", c, g['@']['theme_bg_color'], TEXT)

if V:
    for s, w, a, b, r, mn in rows:
        print("%-16s %-42s %-10s on %-10s %6.2f:1 (needs %.1f) %s" % (s, w, a, b, r, mn, "ok" if r + 1e-9 >= mn else "FAIL"))
for f in fails:
    print("FAIL " + f)
print("%s %d colour pairs checked, %d below target" % ("OK  " if not fails else "FAIL", len(rows), len(fails)))
sys.exit(1 if fails else 0)
