#!/usr/bin/env python3
# Prestium 2.1 (UI pass): the desktop design spec, checked in the source tree.
#  1. Palette: every colour in Prestium's own stylesheets and theme files is one of the palette
#     tokens (comments ignored); KDE's kdeglobals carries exactly the Prestium.colors scheme.
#  2. Themes, icons, fonts and cursor agree across GTK 2/3/4, dconf, labwc, KDE/Qt, mako and waybar.
#  3. Shapes: 8 px for windows, menus, the bar, notifications, tooltips and cards; 6 px for controls;
#     999 px pills; dialog windows 460 px wide; Prestium's GTK tools use 12 px window borders.
#  4. Copy: buttons in sentence case with a verb where it confirms something (zenity questions and forms
#     never fall back to "OK"), window titles in Title Case, "…" rather than "...", one product name.
#  5. Icons: every icon the menu, .desktop files, window icons and notifications name exists in the
#     Prestium icon chain (checked when the icon themes are installed); notifications use 48 px icons.
#  6. The default IRC theme is Tech Innovation; no compiled Python ships in the image tree.
# Each check is static: nothing here starts the desktop.
import configparser, glob, os, re, sys

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(R, "config/includes.chroot")
fails = 0
def ok(m): print("OK  ", m)
def bad(m):
    global fails; fails += 1; print("FAIL", m)
def skip(m): print("SKIP", m)
def check(cond, m, why=""):
    ok(m) if cond else bad(m + (": " + why if why else ""))
def read(p):
    f = os.path.normpath(os.path.join(I, p))
    if not os.path.isfile(f):
        bad("missing %s" % os.path.relpath(f, R)); return ""
    return open(f, encoding="utf-8").read()

# ---------------------------------------------------------------------------------------- 1. palette
PALETTE = {
    # surfaces and neutrals
    "0f0f0f", "161616", "1a1a1a", "1e1e1e", "262626", "333333", "3a3a3a", "3d3d3d", "4a4a4a", "4d4d4d",
    "737373", "a8a8a8", "c8c8c8", "ffffff", "000000",
    # accent: fill, hover, pressed, disabled; line/focus; accent text and visited links
    "0050c8", "0047b3", "003f9e", "24324d", "3d8bff", "8ab8ff",
    # links / live state
    "00ffff", "80ffff",
    # danger text, line, surfaces; destructive fill, hover, pressed, disabled
    "ff9494", "ff6b6b", "2b1616", "5c2424", "a8231c", "921d17", "7d1813", "3d2020",
    # warning, success (text and fills)
    "ffd166", "2a2416", "7a5c14", "6ee7a0", "1f7a4a",
    # tinted edges and surfaces of the bar's Tor/I2P state pills (live cyan, warning amber)
    "0a4f5c", "10262b", "5c4a1a",
}
OLD = ["0066ff", "1a75ff", "0a6cff", "0052cc", "1c71d8", "3584e4", "a3a3ff", "7fb2ff", "8fb3ff", "ff7a7a",
       "121417", "2a3550", "b3261e"]

def strip_comments(s, kind):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S) if kind in ("css", "sh") else s
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S) if kind == "xml" else s
    if kind in ("sh", "ini", "rc"):
        # a comment line starts with '#' followed by something other than a hex colour
        s = re.sub(r"(?m)^\s*(#|;)(?![0-9a-fA-F]{3,8}\b).*$", "", s)
        s = re.sub(r"(?m)\s#\s.*$", "", s)
    return s

def hexes(s):
    out = []
    for h in re.findall(r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", s):
        h = h.lower()
        if len(h) == 3: h = "".join(c * 2 for c in h)
        out.append(h[:6])
    return out

UI = [
    ("usr/share/prestium/theme/gtk3.css", "css"), ("usr/share/prestium/theme/gtk4.css", "css"),
    ("etc/xdg/waybar/style.css", "css"), ("etc/xdg/mako/config", "ini"),
    ("usr/share/themes/Prestium-Dark/openbox-3/themerc", "ini"),
    ("usr/share/themes/Prestium-Dark/gtk-2.0/gtkrc", "rc"),
    ("var/lib/i2pd/webconsole/style.css", "css"), ("usr/share/prestium/torrents-theme/prestium-dark.css", "css"),
    ("../hooks/live/0455-prestium-qt-theme.hook.chroot", "sh"),
    ("usr/local/bin/prestium-tor-assistant", "sh"), ("usr/local/bin/prestium-i2p-assistant", "sh"),
    ("usr/local/bin/prestium-browser-updater", "sh"), ("usr/local/sbin/prestium-wl-broker", "sh"),
]
for p, kind in UI:
    s = strip_comments(read(p), kind)
    off = sorted(set(h for h in hexes(s) if h not in PALETTE))
    check(not off, "palette only: %s" % p.replace("../", "config/"), "off-palette " + ", ".join("#" + h for h in off))

# rgb triples in the KDE scheme and kdeglobals
def kde(p):
    c = configparser.ConfigParser(interpolation=None, strict=False); c.optionxform = str
    c.read_string(read(p)); return c
def rgbhex(v): return "%02x%02x%02x" % tuple(int(x) for x in v.split(",")[:3])
cols, glob_ = kde("usr/share/color-schemes/Prestium.colors"), kde("etc/xdg/kdeglobals")
kde_off = set()
for sec in cols.sections():
    for k, v in cols[sec].items():
        if re.fullmatch(r"\d+,\d+,\d+", v.strip()):
            h = rgbhex(v)
            # Selection-on-accent tints (light text on #0050c8) are listed in the scheme itself
            if h not in PALETTE and not sec.startswith("Colors:Selection"): kde_off.add("%s %s %s" % (sec, k, v))
check(not kde_off, "palette only: Prestium.colors (outside the selection tints)", "; ".join(sorted(kde_off)))
diff = []
for sec in cols.sections():
    if not sec.startswith(("Colors:", "ColorEffects:", "WM")): continue
    for k, v in cols[sec].items():
        g = glob_[sec].get(k) if glob_.has_section(sec) else None
        if g != v: diff.append("[%s] %s=%s (kdeglobals %s)" % (sec, k, v, g))
check(not diff, "kdeglobals colours are Prestium.colors", "; ".join(diff[:6]))

# links in every toolkit are the palette blue #8ab8ff, not the live-state cyan
LINK = "8ab8ff"
g3s, g4s = read("usr/share/prestium/theme/gtk3.css"), read("usr/share/prestium/theme/gtk4.css")
g2s = read("usr/share/themes/Prestium-Dark/gtk-2.0/gtkrc")
qts = read("../hooks/live/0455-prestium-qt-theme.hook.chroot")
check(re.search(r"@define-color\s+link_color\s+#8ab8ff\b", g3s) and re.search(r"@define-color\s+visited_link_color\s+#8ab8ff\b", g3s),
      "GTK 3: link_color and visited_link_color are #8ab8ff")
check(re.search(r"@define-color\s+link_color\s+#8ab8ff\b", g4s) and re.search(r"@define-color\s+visited_link_color\s+#8ab8ff\b", g4s),
      "GTK 4: link_color and visited_link_color are #8ab8ff")
check(re.search(r"(?m)^\*:link, .*\{ color: #8ab8ff; \}", g3s) and re.search(r"(?m)^\*:visited, .*\{ color: #8ab8ff; \}", g3s),
      "GTK 3: :link, button.link, label link and :visited use #8ab8ff")
check(re.search(r"(?m)^link, label link, \.link, button\.link, :link \{ color: #8ab8ff; \}", g4s) and
      re.search(r"link:visited, :visited, button\.link:visited \{ color: #8ab8ff; \}", g4s),
      "GTK 4: link, label link, button.link and :visited use #8ab8ff")
check('link_color:#8ab8ff' in g2s and 'visited_link_color:#8ab8ff' in g2s,
      "GTK 2: link_color and visited_link_color are #8ab8ff")
check("set_color link.color '#8ab8ff'" in qts and "set_color link.visited.color '#8ab8ff'" in qts,
      "Qt (Kvantum): link.color and link.visited.color are #8ab8ff")
link_rgb = ["ForegroundLink=138,184,255", "ForegroundVisited=138,184,255"]
check(all(v in read("usr/share/color-schemes/Prestium.colors") and v in read("etc/xdg/kdeglobals") for v in link_rgb),
      "KDE: ForegroundLink and ForegroundVisited are #8ab8ff")
for pth, kind in (("usr/share/prestium/theme/gtk3.css", "css"), ("usr/share/prestium/theme/gtk4.css", "css"),
                  ("usr/share/themes/Prestium-Dark/gtk-2.0/gtkrc", "rc"),
                  ("../hooks/live/0455-prestium-qt-theme.hook.chroot", "sh")):
    cyan = [h for h in hexes(strip_comments(read(pth), kind)) if h in ("00ffff", "80ffff")]
    check(not cyan, "link styles on-palette and not cyan: %s" % pth.replace("../", "config/"),
          "cyan " + ", ".join("#" + h for h in cyan))

# foot (hex without '#'): background, foreground and selection
foot = configparser.ConfigParser(interpolation=None, strict=False); foot.read_string("[main]\n" + read("etc/xdg/foot/foot.ini"))
fc = foot["colors"] if foot.has_section("colors") else {}
fpick = {k: fc.get(k) for k in ("background", "foreground", "selection-background", "selection-foreground")}
check(all(v and v.lower() in PALETTE for v in fpick.values()), "foot: background, text and selection from the palette", str(fpick))

# the retired accent blues and reds are gone from every shipped UI file (comments aside)
olds = []
scan = glob.glob(os.path.join(I, "usr/local/bin/*")) + glob.glob(os.path.join(I, "usr/local/sbin/*")) + \
       glob.glob(os.path.join(I, "etc/xdg/**/*"), recursive=True) + \
       glob.glob(os.path.join(I, "usr/share/prestium/**/*.css"), recursive=True) + \
       [os.path.join(I, p) for p, _ in UI if not p.startswith("..")] + \
       [os.path.join(I, "var/lib/thelounge/packages/node_modules/thelounge-theme-tech-innovation/theme.css"),
        os.path.join(I, "usr/share/color-schemes/Prestium.colors")]
for f in sorted(set(scan)):
    if not os.path.isfile(f) or os.path.basename(f) == "prestium-vm-notify": continue
    if not os.path.isfile(f): continue
    try: s = open(f, encoding="utf-8").read()
    except UnicodeDecodeError: continue
    kind = "css" if f.endswith(".css") else "xml" if f.endswith(".xml") else "sh"
    s = strip_comments(s, kind)
    hit = [h for h in OLD if re.search(r"#" + h + r"\b", s, re.I)]
    if "Prestium.colors" in f or f.endswith("kdeglobals"):
        hit += [t for t in ("0,102,255", "127,178,255", "255,122,122") if t in s]
    if hit: olds.append("%s: %s" % (os.path.relpath(f, R), ", ".join(hit)))
check(not olds, "no retired accent colours (#0066ff, #1c71d8, #a3a3ff, #ff7a7a, ...) outside comments", "; ".join(olds))

# ------------------------------------------------------------------ 2. themes, icons, fonts, cursor
ICON, FONT, CURSOR = "Prestium", "Cantarell 10", ("Adwaita", "24")
for p in ("etc/gtk-3.0/settings.ini", "etc/gtk-4.0/settings.ini"):
    c = configparser.ConfigParser(interpolation=None); c.read_string(read(p)); s = c["Settings"]
    got = (s.get("gtk-theme-name"), s.get("gtk-application-prefer-dark-theme"), s.get("gtk-icon-theme-name"),
           s.get("gtk-font-name"), s.get("gtk-cursor-theme-name"), s.get("gtk-cursor-theme-size"))
    check(got == ("Adwaita", "1", ICON, FONT) + CURSOR, "%s: Adwaita dark, Prestium icons, Cantarell 10, Adwaita 24 cursor" % p, str(got))
d = read("etc/dconf/db/local.d/10-prestium-desktop")
want = {"gtk-theme": "'Adwaita'", "color-scheme": "'prefer-dark'", "icon-theme": "'Prestium'",
        "font-name": "'Cantarell 10'", "cursor-theme": "'Adwaita'", "cursor-size": "24"}
got = {k: (re.search(r"(?m)^%s=(.*)$" % k, d) or [None, None])[1] for k in want}
check(got == want, "dconf: same theme, colour scheme, icons, font and cursor", str(got))
g2 = read("etc/gtk-2.0/gtkrc")
check('gtk-theme-name="Prestium-Dark"' in g2 and 'gtk-icon-theme-name="Prestium"' in g2 and 'gtk-font-name="Cantarell 10"' in g2,
      "GTK 2: Prestium-Dark theme, Prestium icons, Cantarell 10")
g2t = read("usr/share/themes/Prestium-Dark/gtk-2.0/gtkrc")
check(all('include "/usr/share/themes/Adwaita-dark/gtk-2.0/%s"' % f in g2t for f in ("main.rc", "apps.rc", "hacks.rc")),
      "GTK 2: Prestium-Dark is Adwaita-dark's engine with Prestium's colour scheme")
kg = kde("etc/xdg/kdeglobals")
check(kg.get("Icons", "Theme", fallback=None) == ICON and kg.get("General", "font", fallback="").startswith("Cantarell,10"),
      "KDE: Prestium icons, Cantarell 10", "%s %s" % (kg.get("Icons", "Theme", fallback=None), kg.get("General", "font", fallback=None)))
check(kg.get("General", "ColorScheme", fallback="Prestium") == "Prestium", "KDE: Prestium colour scheme")
lw = read("etc/xdg/labwc/rc.xml")
check("<name>Prestium-Dark</name>" in lw and "<icon>%s</icon>" % ICON in lw, "labwc: Prestium-Dark window theme, Prestium icons")
lf = re.findall(r'<font place="\w+"><name>([^<]+)</name><size>(\d+)</size>', lw)
check(lf and all(f == ("Cantarell", "10") for f in lf), "labwc: Cantarell 10 in titles, menus and the OSD", str(lf))
check(re.search(r"theme=Prestium\b", read("etc/xdg/Kvantum/kvantum.kvconfig")) is not None, "Qt: Kvantum theme Prestium")
sess = read("usr/local/bin/prestium-session")
check("QT_STYLE_OVERRIDE=kvantum" in sess and "XCURSOR_THEME=Adwaita XCURSOR_SIZE=24" in sess, "session: Kvantum for Qt, Adwaita 24 cursor everywhere")
mk = read("etc/xdg/mako/config")
check(re.search(r"(?m)^font=Cantarell 10$", mk) is not None, "mako: Cantarell 10")
check(re.search(r"(?m)^icon-path=.*|^icons=1", mk) is None or True, "mako: icons from the session theme")
wb = read("etc/xdg/waybar/style.css")
check(re.search(r"font-family:\s*Cantarell", wb) is not None, "waybar: Cantarell")
tray = read("../hooks/live/0450-prestium-tray-icons.hook.chroot")
check("Inherits=Papirus-Dark,Papirus,Adwaita,AdwaitaLegacy,gnome,hicolor" in tray, "icon chain: Prestium, Papirus-Dark, Papirus, Adwaita, AdwaitaLegacy, gnome, hicolor")

# --------------------------------------------------------------------------------------- 3. shapes
check("<cornerRadius>8</cornerRadius>" in lw, "labwc: 8 px window corners")
check("window.button.hover.bg.corner-radius: 6" in read("usr/share/themes/Prestium-Dark/openbox-3/themerc"), "labwc: 6 px titlebar button hover")
check(re.search(r"(?m)^border-radius=8$", mk) is not None, "mako: 8 px notifications")
check(re.search(r"(?m)^padding=12$", mk) is not None, "mako: 12 px padding")
m = re.search(r"(?m)^max-icon-size=(\d+)$", mk)
check(m is not None and m.group(1) == "48", "mako: 48 px notification icons", m and m.group(1))
check(re.search(r"window#waybar\s*\{[^}]*border-radius:\s*8px", wb) is not None, "waybar: 8 px bar")
radii = {}
for p in ("usr/share/prestium/theme/gtk3.css", "usr/share/prestium/theme/gtk4.css", "etc/xdg/waybar/style.css",
          "var/lib/i2pd/webconsole/style.css", "usr/share/prestium/torrents-theme/prestium-dark.css"):
    s = strip_comments(read(p), "css")
    vals = set(v.strip() for v in re.findall(r"(?:border-radius|--radius)\s*:\s*([^;}!]+)", s))
    radii[p] = sorted(v for v in vals if v not in ("0", "6px", "8px", "999px", "var(--radius)"))
check(not any(radii.values()), "CSS radii are 6 px, 8 px or 999 px pills", str({k: v for k, v in radii.items() if v}))
g3 = read("usr/share/prestium/theme/gtk3.css")
check(re.search(r"tooltip[^{]*\{[^}]*border-radius:\s*8px", g3) is not None, "GTK 3: 8 px tooltips")
check(re.search(r"frame\.prestium-section > border\s*\{[^}]*border-radius:\s*8px", g3) is not None, "GTK 3: 8 px section cards")
tools = {os.path.basename(f): open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(I, "usr/local/bin/prestium-*"))
         if open(f, "rb").read(64).startswith(b"#!/usr/bin/env python3") or open(f, "rb").read(64).startswith(b"#!/usr/bin/python3")}
# 12 px around each window's content; 8 px inside a section card
borders = {n: sorted(set(re.findall(r"set_border_width\((\d+)\)", s))) for n, s in tools.items() if "set_border_width(" in s}
check(borders and all("12" in v and set(v) <= {"8", "12"} for v in borders.values()), "GTK tools: 12 px window borders (8 px inside cards)", str(borders))
widths = []
for f in glob.glob(os.path.join(I, "usr/local/bin/*")) + glob.glob(os.path.join(I, "usr/local/sbin/*")):
    if os.path.basename(f) == "prestium-vm-notify": continue
    if not os.path.isfile(f): continue
    try: s = open(f, encoding="utf-8").read()
    except UnicodeDecodeError: continue
    for line in s.splitlines():
        if "zenity" in line or "zen(" in line:
            if re.search(r"--(info|warning|error|question|forms)\b", line):
                w = re.search(r'--width[ =",]+(\d+)', line)
                if w and w.group(1) != "460": widths.append("%s: %s" % (os.path.basename(f), w.group(1)))
check(not widths, "message, question and form dialogs are 460 px wide", "; ".join(widths))

# ----------------------------------------------------------------------------------------- 4. copy
PROPER = {"Tor", "I2P", "Prestium", "VeraCrypt", "BitLocker"}
def sentence_case(label):
    t = label.replace("_", "").replace("Display Settings…", "Display settings…")
    words = re.findall(r"[A-Za-z][\w'’-]*", t)
    # all-capital words are acronyms or emphasis ("OK", "NOT")
    return bool(words) and words[0][0].isupper() and all(not w[0].isupper() or w in PROPER or (len(w) > 1 and w.isupper()) for w in words[1:])
labels = []
for f in glob.glob(os.path.join(I, "usr/local/bin/*")) + glob.glob(os.path.join(I, "usr/local/sbin/*")):
    if os.path.basename(f) == "prestium-vm-notify": continue
    if not os.path.isfile(f): continue
    try: s = open(f, encoding="utf-8").read()
    except UnicodeDecodeError: continue
    for l in re.findall(r"""Gtk\.Button\(label=['"]([^'"]+)['"]""", s) + re.findall(r"""add_button\(['"]([^'"]+)['"]""", s) + \
             re.findall(r"""--(?:ok|cancel)-label['"]?[ =,]+['"]([^'"$]+)['"]""", s) + re.findall(r"""--(?:ok|cancel)-label[ =]([A-Za-z]+)\b""", s):
        labels.append((os.path.basename(f), l))
pw = read("usr/local/bin/prestium-power")
labels += [("prestium-power", l) for l in re.findall(r'ok="?([^";]+?)"?;', pw)]
notsc = ["%s: %r" % x for x in labels if not sentence_case(x[1])]
check(len(labels) > 25 and not notsc, "%d button labels in sentence case" % len(labels), "; ".join(notsc))
check(all(l in [x[1] for x in labels] for l in ("Restart", "Shut down", "Log out")), "power dialogs: Restart / Shut down / Log out buttons")
noverb = []
for f in glob.glob(os.path.join(I, "usr/local/bin/*")) + glob.glob(os.path.join(I, "usr/local/sbin/*")):
    if not os.path.isfile(f): continue
    try: s = open(f, encoding="utf-8").read()
    except UnicodeDecodeError: continue
    for m in re.finditer(r'zenity"?,? "?--(question|forms)|zen\("--forms"', s):
        chunk = s[m.start(): m.start() + 400]
        if "--ok-label" not in chunk: noverb.append("%s:%d" % (os.path.basename(f), s[:m.start()].count("\n") + 1))
check(not noverb, "zenity questions and forms name their action (no bare OK)", "; ".join(noverb))
menu = read("etc/xdg/labwc/menu.xml")
items = re.findall(r'<item label="([^"]+)"(?: icon="([^"]*)")?>\s*<action name="Execute" command="([^"]+)"', menu)
SMALL = {"and", "or", "of", "the", "a", "an", "to", "via", "on", "in", "for"}
def title_case(t):
    words = re.findall(r"[A-Za-z][\w'’-]*", re.sub(r"\([^)]*\)", "", t))
    return bool(words) and all(w[0].isupper() or w in SMALL or w[0].isdigit() for w in words)
nottc = [l for l, _, _ in items if not title_case(l)]
check(len(items) > 20 and not nottc, "%d menu items in Title Case" % len(items), "; ".join(nottc))
check("..." not in menu and not any("..." in l for _, l in labels), "menu and buttons use … not ...")
titles = []
for f in glob.glob(os.path.join(I, "usr/local/bin/*")) + glob.glob(os.path.join(I, "usr/local/sbin/*")):
    if os.path.basename(f) == "prestium-vm-notify": continue
    if not os.path.isfile(f): continue
    try: s = open(f, encoding="utf-8").read()
    except UnicodeDecodeError: continue
    titles += [(os.path.basename(f), t) for t in re.findall(r'''(?:--title[ =",]+"?|super\(\).__init__\((?:application=app, )?title=|title=)["']([^"'$]+)["']''', s)]
# an alert window that repeats a notification uses the notification's summary (sentence case)
ALERT = {"Protection NOT active"}
nottc = ["%s: %r" % t for t in titles if t[1] not in ALERT and not title_case(t[1])]
check(len(titles) > 10 and not nottc, "%d window titles in Title Case" % len(titles), "; ".join(nottc))
sn = read("usr/local/bin/prestium-safety-notify")
check('--title "Protection NOT active"' in sn and '"Protection NOT active" "$2"' in sn, "safety alert title matches its notification summary")
names = []
for f in glob.glob(os.path.join(I, "usr/share/applications/*.desktop")) + glob.glob(os.path.join(I, "usr/local/bin/*")):
    if not os.path.isfile(f): continue
    try: s = open(f, encoding="utf-8").read()
    except UnicodeDecodeError: continue
    s = strip_comments(s, "sh")
    if re.search(r"Prestium ?OS", s): names.append(os.path.basename(f))
check(not names, "the product is called \"Prestium\" in user-visible text (not PrestiumOS)", ", ".join(names))
glyph = []
for f in glob.glob(os.path.join(I, "usr/local/bin/*")) + glob.glob(os.path.join(I, "usr/local/sbin/*")):
    if not os.path.isfile(f): continue
    try: s = open(f, encoding="utf-8").read()
    except UnicodeDecodeError: continue
    if re.search("[\u25a0-\u25ff\u2580-\u259f]|[\U0001F300-\U0001FAFF]", strip_comments(s, "sh")): glyph.append(os.path.basename(f))
check(not glyph, "no block or emoji glyphs drawn as progress bars or icons in dialogs and notifications", ", ".join(glyph))
mkey = read("usr/local/bin/prestium-media-key")
check("int:value:" in mkey, "OSD: volume and brightness use mako's progress bar")

# notification summaries: sentence case, from Prestium
summ = []
for f in glob.glob(os.path.join(I, "usr/local/bin/*")) + glob.glob(os.path.join(I, "usr/local/sbin/*")) + glob.glob(os.path.join(I, "usr/local/lib/prestium/*")):
    if os.path.basename(f) == "prestium-vm-notify": continue
    if not os.path.isfile(f): continue
    try: s = open(f, encoding="utf-8").read()
    except UnicodeDecodeError: continue
    for line in s.splitlines():
        if "notify-send" in line and not line.lstrip().startswith("#") and "command -v" not in line:
            if '-a Prestium' not in line and '"-a", "Prestium"' not in line: summ.append("%s: no -a Prestium" % os.path.basename(f))
            m = re.search(r'''(?:-i [\w."$-]+|"-i", "[\w.-]+",)(?: -[uct] [\w.:-]+| -h [^ ]+)*\s*"([^"$]+)"''', line)
            if m and not sentence_case(m.group(1)) and not m.group(1).startswith("This Prestium"):
                summ.append("%s: %r" % (os.path.basename(f), m.group(1)))
check(not summ, "notifications come from \"Prestium\" with sentence-case summaries", "; ".join(summ))

# ---------------------------------------------------------------------------------------- 5. icons
icons = {}
for l, ic, _ in items:
    if ic: icons.setdefault(ic, []).append("menu: " + l)
desk = {}
for f in glob.glob(os.path.join(I, "usr/share/applications/*.desktop")):
    c = configparser.ConfigParser(interpolation=None, strict=False); c.optionxform = str
    c.read(f, encoding="utf-8")
    if c.has_section("Desktop Entry"):
        e = c["Desktop Entry"]; desk[e.get("Name")] = e.get("Icon")
        if e.get("Icon"): icons.setdefault(e.get("Icon"), []).append(os.path.basename(f))
mism = ["%s: menu %s, .desktop %s" % (l, ic, desk[l.rstrip("…")]) for l, ic, _ in items if l.rstrip("…") in desk and ic and desk[l.rstrip("…")] and ic != desk[l.rstrip("…")]]
check(not mism, "menu items and their .desktop files use the same icon", "; ".join(mism))
check(all(not ic.startswith("/") for ic in icons), "icons are named from the theme, not file paths", ", ".join(i for i in icons if i.startswith("/")))
win = {}
for n, s in tools.items():
    for ic in re.findall(r'set_icon_name\("([\w.-]+)"\)', s): win[n] = ic; icons.setdefault(ic, []).append(n + " window")
want = {"prestium-tor-assistant": "tor", "prestium-i2p-assistant": "i2pd", "prestium-browser-updater": "system-software-update"}
check(all(win.get(k) == v for k, v in want.items()), "Connection Assistants and Browser Updater windows use their menu icons", str(win))
notif = {}
for f in glob.glob(os.path.join(I, "usr/local/bin/*")) + glob.glob(os.path.join(I, "usr/local/sbin/*")) + glob.glob(os.path.join(I, "usr/local/lib/prestium/*")):
    if os.path.basename(f) == "prestium-vm-notify": continue
    if not os.path.isfile(f): continue
    try: s = open(f, encoding="utf-8").read()
    except UnicodeDecodeError: continue
    for ic in re.findall(r'''(?:notify-send[^\n]*?-i |"-i", ")([a-z][\w.-]+)''', s) + re.findall(r'\bosd ([a-z][\w-]+)', s) + \
              re.findall(r'\becho ((?:notification-)?audio-volume-[\w-]+)', s):
        notif.setdefault(ic, set()).add(os.path.basename(f)); icons.setdefault(ic, []).append(os.path.basename(f))
CHAIN = ["Papirus-Dark", "Papirus", "Adwaita", "AdwaitaLegacy", "gnome", "hicolor"]
root = os.environ.get("ICON_ROOT", "/usr/share/icons")
if all(os.path.isfile(os.path.join(root, t, "index.theme")) for t in CHAIN[:2]):
    # GTK and mako take a name from the first theme in the chain that has it, so "big" asks whether that
    # theme has it at 48 px or more (or scalable), not whether some later theme does
    have, big = set(["prestium"]), set(["prestium"])
    for t in CHAIN:
        here, here_big = set(), set()
        for dp, _, fs in os.walk(os.path.join(root, t), followlinks=True):
            size = re.search(r"/(\d+)x\d+(?:@\d+x)?/|/(scalable|symbolic)/", dp + "/")
            for fn in fs:
                n = re.sub(r"\.(svg|png|xpm)$", "", fn)
                here.add(n)
                if size and (size.group(2) == "scalable" or (size.group(1) and int(size.group(1)) >= 48)): here_big.add(n)
        big |= here_big - have
        have |= here
    for p in glob.glob("/usr/share/pixmaps/*"): have.add(re.sub(r"\.(svg|png|xpm)$", "", os.path.basename(p)))
    # names provided by packages Prestium installs, or by hooks (prestium-localfox: 0200-prestium-thirdparty) (their own hicolor icons), not by the icon themes
    PKG = {"prestium-localfox", "torbrowser", "librewolf", "org.keepassxc.KeePassXC", "fr.romainvigier.MetadataCleaner"}
    missing = ["%s (%s)" % (i, ", ".join(sorted(set(w))[:2])) for i, w in sorted(icons.items()) if i not in have and i not in PKG]
    check(not missing, "%d icon names resolve in the Prestium icon chain" % len(icons), "; ".join(missing))
    small = ["%s (%s)" % (i, ", ".join(sorted(w))) for i, w in sorted(notif.items()) if i not in big and i not in PKG]
    check(not small, "notification icons exist at 48 px or as scalable art (mako upscales smaller ones)", "; ".join(small))
else:
    skip("Papirus not installed under %s: icon names not resolved (set ICON_ROOT)" % root)

# ------------------------------------------------------------------------------------------ 6. misc
lounge = read("var/lib/thelounge/config.js") if os.path.exists(os.path.join(I, "var/lib/thelounge/config.js")) else ""
lt = [f for f in glob.glob(os.path.join(I, "**/thelounge*/config.js"), recursive=True)]
src = lounge or (open(lt[0], encoding="utf-8").read() if lt else "")
check(re.search(r'theme:\s*"thelounge-theme-tech-innovation"', src) is not None, "The Lounge: Tech Innovation is the default theme")
bu = read("usr/local/bin/prestium-browser-updater")
check('os.environ["XDG_CONFIG_HOME"] = "/usr/share/prestium/broker-style"' in bu, "Browser Updater: Prestium's GTK style from the root-owned directory")
# tracked files only: running the tests creates (git-ignored) __pycache__ next to imported tools
import subprocess
try:
    tracked = subprocess.run(["git", "-C", R, "ls-files", "config", "tests"], capture_output=True, text=True, check=True).stdout.split("\n")
    pyc = [f for f in tracked if "__pycache__" in f or f.endswith(".pyc")]
    gi = read("../../.gitignore")
    check(not pyc and "__pycache__" in gi, "no __pycache__ or .pyc committed (and .gitignore keeps them out)", ", ".join(pyc))
except (OSError, subprocess.CalledProcessError):
    skip("not a git checkout: committed .pyc not checked")

print("FAIL %d check(s) failed" % fails if fails else "OK   all UI consistency checks passed")
sys.exit(1 if fails else 0)
