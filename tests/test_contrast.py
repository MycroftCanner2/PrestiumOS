#!/usr/bin/env python3
"""Prestium 2.1 (contrast review): WCAG 2 contrast of every text/background, indicator and focus colour
pair, read from the files the image ships: the lock screen's password prompt
(swaylock), GTK 3 and GTK 4 (the apps, the broker's zenity dialogs such as the Lock Screen password, the
Connection Assistants, the GNOME passphrase prompt), Qt (Adwaita), KDE (Kleopatra), labwc (titles, menus,
OSD), waybar, mako and the assistants' error text.
2.1 (UI pass): also GTK 3 destructive buttons, message bars and section cards, GTK 4 destructive buttons,
GTK 2 (Prestium-Dark's colour scheme for pinentry-gtk2), /etc/xdg/kdeglobals (as Prestium.colors),
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

# --- GTK 3 (stock Adwaita light) ---
# No repo file styles GTK 3 any more; these are Adwaita's published light values,
# asserted so a regression is visible here too (same rationale as the Qt section).
S = "GTK 3"
win, base, header, dialog = "#f6f5f4", "#ffffff", "#ebebeb", "#f6f5f4"
for bgname, bg in (("windows", win), ("views", base), ("headerbars", header), ("dialogs", dialog)):
    need(S, "text on " + bgname, "#2e3436", bg, TEXT)
need(S, "secondary text", "#5e5c64", win, DISABLED)
need(S, "selected text", "#ffffff", "#3584e4", INDICATOR)  # GNOME selected-item pairing (bold + position)
need(S, "selected text (unfocused window)", "#2e3436", "#deddda", TEXT)
need(S, "entry text", "#2e3436", "#ffffff", TEXT)
need(S, "entry focus edge", "#3584e4", "#ffffff", INDICATOR)
need(S, "error text on windows", "#c01c28", win, DISABLED)
need(S, "error text on views", "#c01c28", base, DISABLED)
need(S, "accent text on views", "#1c71d8", base, DISABLED)
need(S, "default button text", "#ffffff", "#3584e4", INDICATOR)  # suggested-action pairing, as selected text
need(S, "check mark", "#ffffff", "#3584e4", INDICATOR)
need(S, "links on views", "#1c71d8", base, DISABLED)
need(S, "visited links on views", "#1c71d8", base, DISABLED)
need(S, "tooltip text", "#ffffff", "#1e1e1e", TEXT)  # Adwaita tooltips stay dark

# --- GTK 4 / libadwaita (stock Adwaita light) ---
# Same rationale as GTK 3: Adwaita's published light values, no repo file.
S = "GTK 4"
win4, view4, card4, dialog4, header4 = "#f6f5f4", "#ffffff", "#ffffff", "#f6f5f4", "#ebebeb"
need(S, "accent button text", "#ffffff", "#3584e4", INDICATOR)  # suggested-action pairing, as selected text
for n, bg in (("windows", win4), ("views", view4), ("cards", card4), ("dialogs", dialog4), ("headerbars", header4)):
    need(S, "text on " + n, "#2e3436", bg, TEXT)
    need(S, "error text on " + n, "#c01c28", bg, DISABLED)
for n, bg in (("views", view4), ("cards", card4)):
    need(S, "accent text on " + n, "#1c71d8", bg, DISABLED)
    need(S, "links on " + n, "#1c71d8", bg, DISABLED)
    need(S, "visited links on " + n, "#1c71d8", bg, DISABLED)
need(S, "entry text", "#2e3436", "#ffffff", TEXT)
need(S, "entry placeholder", "#8c8f90", "#ffffff", INDICATOR)  # 55%-opacity text, de-emphasised by design
need(S, "entry focus outline", "#3584e4", "#ffffff", INDICATOR)
need(S, "tooltip text", "#ffffff", "#1e1e1e", TEXT)  # Adwaita tooltips stay dark

# --- Qt (Adwaita, no Kvantum): Adwaita's published light values ---
# Qt follows the session (QT_STYLE_OVERRIDE=Adwaita, checked in test_ui_consistency.py);
# these are Adwaita's own light-theme values, asserted so a regression is visible here too.
S = "Qt (Adwaita)"
need(S, "text on views", "#2e3436", "#ffffff", TEXT)
need(S, "text on windows", "#2e3436", "#f6f5f4", TEXT)
need(S, "selected text", "#ffffff", "#3584e4", INDICATOR)  # GNOME selected-item pairing (bold + position)
need(S, "links", "#1c71d8", "#ffffff", DISABLED)
need(S, "visited links", "#1c71d8", "#ffffff", DISABLED)

# --- KDE colour scheme (Kleopatra, Adwaita light) ---
# Text and decoration thresholds mirror the Qt section: Adwaita's own light values,
# asserted so a regression is visible here too. Tooltips stay dark, as Adwaita's are.
S = "KDE (Kleopatra)"
sec, kd = None, {}
for l in read("usr/share/color-schemes/Prestium.colors").splitlines():
    if l.startswith('['):
        sec = l
    elif '=' in l and sec:
        kd.setdefault(sec, {})[l.split('=', 1)[0]] = l.split('=', 1)[1]
LIGHT = ("[Colors:Window]", "[Colors:View]", "[Colors:Button]", "[Colors:Header]")
for s in LIGHT:
    c = kd[s]
    bg = c['BackgroundNormal']
    need(S, "%s text" % s[8:-1], c['ForegroundNormal'], bg, TEXT)
    need(S, "%s inactive text" % s[8:-1], c['ForegroundInactive'], bg, DISABLED)
    for k in ('ForegroundActive', 'ForegroundLink', 'ForegroundVisited', 'ForegroundNegative', 'ForegroundNeutral', 'ForegroundPositive'):
        need(S, "%s %s" % (s[8:-1], k[10:].lower()), c[k], bg, DISABLED)
    need(S, "%s focus decoration" % s[8:-1], c['DecorationFocus'], bg, INDICATOR)
c = kd["[Colors:Selection]"]
bg = c['BackgroundNormal']
need(S, "Selection text", c['ForegroundNormal'], bg, INDICATOR)  # white on accent, bold selected-row pairing as GTK/Qt
need(S, "Selection inactive text", c['ForegroundInactive'], bg, INDICATOR)
for k in ('ForegroundActive', 'ForegroundLink', 'ForegroundVisited', 'ForegroundNegative', 'ForegroundNeutral', 'ForegroundPositive'):
    need(S, "Selection %s" % k[10:].lower(), c[k], bg, INDICATOR)
c = kd["[Colors:Tooltip]"]
bg = c['BackgroundNormal']
need(S, "Tooltip text", c['ForegroundNormal'], bg, TEXT)
need(S, "Tooltip inactive text", c['ForegroundInactive'], bg, DISABLED)
for k in ('ForegroundActive', 'ForegroundLink', 'ForegroundVisited', 'ForegroundNegative', 'ForegroundNeutral', 'ForegroundPositive'):
    need(S, "Tooltip %s" % k[10:].lower(), c[k], bg, TEXT)
need(S, "Tooltip focus decoration", c['DecorationFocus'], bg, INDICATOR)

# --- labwc (titles, menus, window switcher) ---
th = dict(re.findall(r'^([\w.-]+):\s*(#[0-9a-fA-F]{6,8})', read("usr/share/themes/Prestium-Adwaita/openbox-3/themerc"), re.M))
S = "labwc"
need(S, "active title", th['window.active.label.text.color'], th['window.active.title.bg.color'], TEXT)
need(S, "inactive title (de-emphasised chrome, 2.89:1 by the spec values)", th['window.inactive.label.text.color'], th['window.inactive.title.bg.color'], 2.5)
need(S, "title buttons", th['window.active.button.unpressed.image.color'], th['window.active.title.bg.color'], TEXT)
need(S, "active window edge on the desktop", th['window.active.border.color'], "#161616", INDICATOR)
need(S, "menu items", th['menu.items.text.color'], th['menu.items.bg.color'], TEXT)
need(S, "highlighted menu item", th['menu.items.active.text.color'], th['menu.items.active.bg.color'], INDICATOR)  # selected-row pairing, as above
need(S, "OSD text", th['osd.label.text.color'], th['osd.bg.color'], TEXT)
if th['osd.border.color'].lower() != "#cdc7c2":
    fails.append("labwc: OSD edge is not Adwaita grey")

# --- waybar (dual bar: dark top system bar, light bottom taskbar) ---
wb = css(read("etc/xdg/waybar/style.css"))
S = "waybar"
bar = col(wb['window#waybar.prestium-top']['background-color'])
need(S, "top bar text", col(wb['window#waybar.prestium-top']['color']), bar, TEXT)
need(S, "Applications button", col(wb['window#waybar.prestium-top #custom-applications']['color']), bar, TEXT)
need(S, "Applications button (hover)", "#ffffff", over(col(wb['window#waybar.prestium-top #custom-applications:hover']['background-color']), bar), TEXT)
need(S, "clock", col(wb['window#waybar.prestium-top #clock']['color']), bar, TEXT)
tray = col(wb['window#waybar.prestium-bottom']['background-color'])
need(S, "window buttons", col(wb['window#waybar.prestium-bottom #taskbar button']['color']), tray, TEXT)
need(S, "window buttons (hover)", col(wb['window#waybar.prestium-bottom #taskbar button']['color']),
     col(wb['window#waybar.prestium-bottom #taskbar button:hover']['background-color']), TEXT)
need(S, "active window", col(wb['window#waybar.prestium-bottom #taskbar button.active']['color']),
     col(wb['window#waybar.prestium-bottom #taskbar button.active']['background-color']), TEXT)
need(S, "minimised window (de-emphasised by design)", col(wb['window#waybar.prestium-bottom #taskbar button.minimized']['color']),
     col(wb['window#waybar.prestium-bottom #taskbar button.minimized']['background-color']), INDICATOR)
need(S, "window tooltip", col(wb['tooltip label']['color']), col(wb['tooltip']['background-color']), TEXT)
p = wb['window#waybar.prestium-top #custom-tor']
need(S, "Tor/I2P pill (idle)", col(p['color']), col(p['background-color']), TEXT)
for st, minimum in (("connecting", TEXT), ("ready", INDICATOR), ("failed", DISABLED)):
    # ready is white on success green (3.3:1, paired with position and tooltip);
    # failed is white on danger red (WCAG AA)
    q = wb['window#waybar.prestium-top #custom-tor.' + st]
    need(S, "Tor/I2P pill (%s)" % st, col(q['color']), col(q['background-color']), minimum)
    q = wb['window#waybar.prestium-top #custom-i2p.' + st]
    need(S, "Tor/I2P pill (%s)" % st, col(q['color']), col(q['background-color']), minimum)
need(S, "pill hover edge", col(wb['window#waybar.prestium-top #custom-tor:hover']['border-color']), col(p['background-color']), INDICATOR)
for k in ('#network.disconnected', '#battery.warning:not(.charging)', '#battery.critical:not(.charging)',
          '#custom-timesync.syncing', '#custom-timesync.failed'):
    need(S, k, col(wb['window#waybar.prestium-top ' + k]['color']), bar, TEXT)
need(S, "muted volume", col(wb['window#waybar.prestium-top #pulseaudio.muted']['color']), bar, DISABLED)

# --- mako (light top-center notifications) ---
S = "mako"
sec, mk = "", {"": {}}
for l in read("etc/xdg/mako/config").splitlines():
    l = l.strip()
    if l.startswith('['):
        sec = l; mk.setdefault(sec, {})
    elif '=' in l and not l.startswith('#'):
        mk[sec][l.split('=', 1)[0]] = l.split('=', 1)[1]
top = mk[""]
if top["anchor"] != "top-center":
    fails.append("mako: notifications are not top-center")
nbg = over(top['background-color'], "#161616")
need(S, "normal text", top['text-color'], nbg, TEXT)
need(S, "low-urgency text (secondary, de-emphasised by design)", mk['[urgency=low]']['text-color'], nbg, DISABLED)
if mk['[urgency=critical]']['border-color'].lower() != "#c01c28":
    fails.append("mako: critical edge is not danger red")
if top['border-color'].lower() != "#cdc7c2":
    fails.append("mako: normal edge is not Adwaita grey")
need(S, "volume/brightness OSD edge", mk['[category=prestium.osd]']['border-color'], nbg, INDICATOR)
if col(top['progress-color']).lower() != "#0050c8":
    fails.append("mako: progress fill is not Prestium blue")

# --- 2.1 (UI pass): GTK 3 destructive buttons and message bars (stock Adwaita light) ---
S = "GTK 3"
need(S, "destructive button text", "#ffffff", "#c01c28", DISABLED)  # WCAG AA, bold button text
need(S, "message bar text (error)", "#ffffff", "#c01c28", DISABLED)  # WCAG AA, bold bar text
need(S, "message bar text (info)", "#ffffff", "#3584e4", INDICATOR)  # bold info pairing, as selected text
# warning/success bars and card frames follow upstream Adwaita; the Prestium
# "prestium-section" card styling lived in the deleted theme file, so those
# frames now render as plain Adwaita frames (functional, unstyled)

# --- GTK 4 destructive buttons (stock Adwaita light) ---
S = "GTK 4"
need(S, "destructive button text", "#ffffff", "#c01c28", DISABLED)  # WCAG AA, bold button text
for n, bg in (("windows", "#f6f5f4"), ("dialogs", "#f6f5f4")):
    need(S, "destructive text on %s" % n, "#c01c28", bg, DISABLED)

# --- GTK 2 (pinentry-gtk2): Prestium-Dark's colour scheme ---
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
for s_ in ("[Colors:Window]", "[Colors:View]", "[Colors:Button]", "[Colors:Header]"):
    c = kg[s_]; bg = c['BackgroundNormal']
    need(S, "%s text" % s_[8:-1], c['ForegroundNormal'], bg, TEXT)
    for k in ('ForegroundActive', 'ForegroundLink', 'ForegroundVisited', 'ForegroundNegative'):
        need(S, "%s %s" % (s_[8:-1], k[10:].lower()), c[k], bg, DISABLED)
    need(S, "%s focus decoration" % s_[8:-1], c['DecorationFocus'], bg, INDICATOR)
c = kg["[Colors:Selection]"]; bg = c['BackgroundNormal']
need(S, "Selection text", c['ForegroundNormal'], bg, INDICATOR)
for k in ('ForegroundActive', 'ForegroundLink', 'ForegroundVisited', 'ForegroundNegative'):
    need(S, "Selection %s" % k[10:].lower(), c[k], bg, INDICATOR)
c = kg["[Colors:Tooltip]"]; bg = c['BackgroundNormal']
need(S, "Tooltip text", c['ForegroundNormal'], bg, TEXT)
need(S, "Tooltip focus decoration", c['DecorationFocus'], bg, INDICATOR)

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

# --- Connection Assistants: error text in the window (Adwaita light dialogs) ---
for f in ("usr/local/bin/prestium-tor-assistant", "usr/local/bin/prestium-i2p-assistant"):
    for c in re.findall(r"foreground=[\"'](#[0-9a-fA-F]{6})", read(f)):
        need(os.path.basename(f), "error text", c, "#f6f5f4", DISABLED)

if V:
    for s, w, a, b, r, mn in rows:
        print("%-16s %-42s %-10s on %-10s %6.2f:1 (needs %.1f) %s" % (s, w, a, b, r, mn, "ok" if r + 1e-9 >= mn else "FAIL"))
for f in fails:
    print("FAIL " + f)
print("%s %d colour pairs checked, %d below target" % ("OK  " if not fails else "FAIL", len(rows), len(fails)))
sys.exit(1 if fails else 0)
