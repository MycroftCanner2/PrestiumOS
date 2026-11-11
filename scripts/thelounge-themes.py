#!/usr/bin/env python3
"""Prestium 2.1: generate The Lounge theme packages from the Theme Factory palettes.

Writes config/includes.chroot/var/lib/thelounge/packages/node_modules/thelounge-theme-<slug>/
{index.js,package.json,theme.css} for the 10 Theme Factory themes, all from one template, and
checks WCAG contrast (>= 4.5:1) for every text/background pair the template uses.
The committed files are what ships; run this after changing the template or a palette.
  scripts/thelounge-themes.py          write the packages
  scripts/thelounge-themes.py --check  only verify the committed files match and contrast holds
No network, no Node.

Palettes: Theme Factory, https://github.com/anthropics/skills/tree/
8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4/skills/theme-factory (Apache License 2.0, see
packages/THEME-FACTORY-NOTICE.txt). Where a raw palette hex is too low-contrast for text, the role
uses a darker/lighter shade of the same colour; each such case is noted next to the value below.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKGS = os.path.join(ROOT, "config/includes.chroot/var/lib/thelounge/packages")
SRC = "github.com/anthropics/skills, commit 8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4, skills/theme-factory"
MIN = 4.5

# Fonts: only families Prestium ships (fonts-dejavu-core, fonts-cantarell, fonts-urw-base35).
# FreeSans/FreeSerif (fonts-freefont) and DejaVu Serif are not shipped: FreeSans -> Nimbus Sans,
# FreeSerif -> Nimbus Roman, DejaVu Serif -> C059 (all URW base35, metric clones of the same designs).
SANS_DEJAVU = '"DejaVu Sans", Cantarell, sans-serif'
SANS_FREE = '"Nimbus Sans", "DejaVu Sans", Cantarell, sans-serif'
SERIF_DEJAVU = 'C059, "Nimbus Roman", serif'
SERIF_FREE = '"Nimbus Roman", C059, serif'

# Roles:
#  side_*   sidebar (The Lounge's --body-bg-color: channel list, footer, page background)
#  win      chat/settings window background (--window-bg-color); panel = header, message form
#  fg       chat message text (--body-color); muted = time stamps, secondary text
#  link, button, button_hover (text on a filled button), sel = selected user / nick box background
#  in_bg/in_fg/in_line text fields (Settings, Connect, message form), placeholder text = muted
THEMES = [
    dict(slug="ocean-depths", name="Ocean Depths", dark=True,
         desc="Ocean Depths: deep navy, teal and seafoam",
         palette="Deep Navy #1a2332, Teal #2d8b8b, Seafoam #a8dadc, Cream #f1faee",
         body_font=SANS_DEJAVU, head_font=SANS_DEJAVU,
         side_bg="#141b27", side_fg="#f1faee", side_muted="#a8dadc", side_hover="#22303f",
         side_active_bg="#236d6d",  # Teal #2d8b8b darkened: cream on raw teal is under 4.5:1
         side_active_fg="#ffffff", side_lobby="#a8dadc",
         win="#1a2332", panel="#202b3d", line="#2c3c4e", line2="#3d5166",
         fg="#ffffff", muted="#a3b6c2", link="#a8dadc", button="#a8dadc", button_hover="#1a2332",
         sel="#236d6d", in_bg="#111823", in_fg="#ffffff", in_line="#3d5166",
         hl_bg="#1f3a3f", hl_line="#2d8b8b", ok="#8fd9a8", warn="#f0c674", bad="#ff8a80",
         date="#a8dadc", unread="#ff8a80"),
    dict(slug="sunset-boulevard", name="Sunset Boulevard", dark=False,
         desc="Sunset Boulevard: burnt orange, coral, warm sand and deep purple",
         palette="Burnt Orange #e76f51, Coral #f4a261, Warm Sand #e9c46a, Deep Purple #264653",
         body_font=SANS_DEJAVU, head_font=SERIF_DEJAVU,
         side_bg="#264653", side_fg="#ffffff", side_muted="#e9c46a", side_hover="#30586a",
         side_active_bg="#3a6a7e", side_active_fg="#ffffff", side_lobby="#f4a261",
         win="#fdf6e6",  # Warm Sand #e9c46a lightened for the chat surface
         panel="#f7e6b8", line="#e9c46a", line2="#d9ae4a",
         fg="#264653", muted="#4f6670",
         link="#a8432a",  # Burnt Orange #e76f51 darkened: raw is under 4.5:1 on sand
         button="#a8432a", button_hover="#ffffff",
         sel="#f9d3b0", in_bg="#fffcf5", in_fg="#264653", in_line="#d9ae4a",
         hl_bg="#fbd9c9", hl_line="#e76f51", ok="#2a7a3b", warn="#8a5a00", bad="#b3261e",
         date="#2a7a3b", unread="#b3261e"),
    dict(slug="forest-canopy", name="Forest Canopy", dark=True,
         desc="Forest Canopy: forest green, sage, olive and ivory",
         palette="Forest Green #2d4a2b, Sage #7d8471, Olive #a4ac86, Ivory #faf9f6",
         body_font=SANS_FREE, head_font=SERIF_FREE,
         side_bg="#233b22", side_fg="#faf9f6",
         side_muted="#c4caa9",  # Olive #a4ac86 lightened: raw is under 4.5:1 on forest green
         side_hover="#335431", side_active_bg="#5a6150",  # Sage #7d8471 darkened for white text
         side_active_fg="#ffffff", side_lobby="#d6dcb8",
         win="#2d4a2b", panel="#33532f", line="#41633d", line2="#58784f",
         fg="#ffffff", muted="#c4caa9", link="#dfe6bf", button="#dfe6bf", button_hover="#2d4a2b",
         sel="#5a6150", in_bg="#1f341e", in_fg="#ffffff", in_line="#58784f",
         hl_bg="#4a4a22", hl_line="#a4ac86", ok="#a8e6a1", warn="#f2d27a", bad="#ffa094",
         date="#c4caa9", unread="#ffa094"),
    dict(slug="modern-minimalist", name="Modern Minimalist", dark=False,
         desc="Modern Minimalist: charcoal, slate gray, light gray and white",
         palette="Charcoal #36454f, Slate Gray #708090, Light Gray #d3d3d3, White #ffffff",
         body_font=SANS_DEJAVU, head_font=SANS_DEJAVU,
         side_bg="#36454f", side_fg="#ffffff", side_muted="#d3d3d3", side_hover="#435561",
         side_active_bg="#556672", side_active_fg="#ffffff", side_lobby="#ffffff",
         win="#ffffff", panel="#f2f2f2", line="#d3d3d3", line2="#b5b5b5",
         fg="#36454f",
         muted="#5d6b7a",  # Slate Gray #708090 darkened: raw is under 4.5:1 on white
         link="#36454f", button="#36454f", button_hover="#ffffff",
         sel="#e4e4e4", in_bg="#ffffff", in_fg="#36454f", in_line="#b5b5b5",
         hl_bg="#eef0f2", hl_line="#708090", ok="#2b7a3d", warn="#8a5a00", bad="#b3261e",
         date="#5d6b7a", unread="#b3261e"),
    dict(slug="golden-hour", name="Golden Hour", dark=False,
         desc="Golden Hour: mustard yellow, terracotta, warm beige and chocolate brown",
         palette="Mustard Yellow #f4a900, Terracotta #c1666b, Warm Beige #d4b896, Chocolate Brown #4a403a",
         body_font=SANS_FREE, head_font=SANS_FREE,
         side_bg="#4a403a", side_fg="#ffffff", side_muted="#e3cfb5", side_hover="#584c45",
         side_active_bg="#6a5a50", side_active_fg="#ffffff", side_lobby="#f4a900",
         win="#f7efe4",  # Warm Beige #d4b896 lightened for the chat surface
         panel="#ecdcc4", line="#d4b896", line2="#bfa07a",
         fg="#4a403a", muted="#6b5d53",
         link="#94434a",  # Terracotta #c1666b darkened: raw is under 4.5:1 on beige
         button="#94434a", button_hover="#ffffff",
         sel="#f3d892", in_bg="#fffaf2", in_fg="#4a403a", in_line="#bfa07a",
         hl_bg="#fbe3a6", hl_line="#f4a900", ok="#2f6f35", warn="#7f5600", bad="#a52a2a",
         date="#2f6f35", unread="#a52a2a"),
    dict(slug="arctic-frost", name="Arctic Frost", dark=False,
         desc="Arctic Frost: ice blue, steel blue, silver and crisp white",
         palette="Ice Blue #d4e4f7, Steel Blue #4a6fa5, Silver #c0c0c0, Crisp White #fafafa",
         body_font=SANS_DEJAVU, head_font=SANS_DEJAVU,
         side_bg="#3d5c8a",  # Steel Blue #4a6fa5 darkened: ice-blue sidebar text is under 4.5:1 on it
         side_fg="#ffffff", side_muted="#d4e4f7", side_hover="#4a6c9c",
         side_active_bg="#2c4670", side_active_fg="#ffffff", side_lobby="#ffffff",
         win="#fafafa", panel="#e8f0fa", line="#d4e4f7", line2="#c0c0c0",
         fg="#1f3350",  # Steel Blue #4a6fa5 darkened: dark steel text, never white on white/ice
         muted="#4a5e78", link="#3a5a88", button="#3a5a88", button_hover="#ffffff",
         sel="#d4e4f7", in_bg="#ffffff", in_fg="#1f3350", in_line="#c0c0c0",
         hl_bg="#fff1cc", hl_line="#c99a2e", ok="#2b7a3d", warn="#8a5a00", bad="#b3261e",
         date="#3a5a88", unread="#b3261e"),
    dict(slug="desert-rose", name="Desert Rose", dark=False,
         desc="Desert Rose: dusty rose, clay, sand and deep burgundy",
         palette="Dusty Rose #d4a5a5, Clay #b87d6d, Sand #e8d5c4, Deep Burgundy #5d2e46",
         body_font=SANS_FREE, head_font=SANS_FREE,
         side_bg="#5d2e46", side_fg="#ffffff", side_muted="#e8d5c4", side_hover="#6c3853",
         side_active_bg="#7d4562", side_active_fg="#ffffff", side_lobby="#f0c8c8",
         win="#f9f2ec",  # Sand #e8d5c4 lightened for the chat surface
         panel="#efe1d4", line="#e8d5c4", line2="#d4a5a5",
         fg="#5d2e46", muted="#7a4e5f",
         link="#8a4f40",  # Clay #b87d6d darkened: raw is under 4.5:1 on sand
         button="#8a4f40", button_hover="#ffffff",
         sel="#ecd0d0", in_bg="#fffbf8", in_fg="#5d2e46", in_line="#d4a5a5",
         hl_bg="#f3d6d6", hl_line="#b87d6d", ok="#2b6e3a", warn="#7f5600", bad="#a32020",
         date="#2b6e3a", unread="#a32020"),
    dict(slug="tech-innovation", name="Tech Innovation", dark=True,
         desc="Tech Innovation: electric blue, neon cyan, dark gray and white (Prestium's default)",
         palette="Electric Blue #0066ff, Neon Cyan #00ffff, Dark Gray #1e1e1e, White #ffffff",
         body_font=SANS_DEJAVU, head_font=SANS_DEJAVU,
         side_bg="#161616", side_fg="#ffffff", side_muted="#b4b4b4", side_hover="#262626",
         side_active_bg="#0066ff", side_active_fg="#ffffff", side_lobby="#00ffff",
         win="#1e1e1e", panel="#262626", line="#333333", line2="#4a4a4a",
         fg="#ffffff", muted="#a8a8a8",
         link="#00ffff",  # Neon Cyan for links: Electric Blue #0066ff is under 4.5:1 on #1e1e1e
         button="#00ffff", button_hover="#1e1e1e",
         sel="#0052cc", in_bg="#141414", in_fg="#ffffff", in_line="#4a4a4a",
         hl_bg="#0a2a5c", hl_line="#00ffff", ok="#6ee7a0", warn="#ffd166", bad="#ff7a7a",
         date="#00ffff", unread="#ff7a7a"),
    dict(slug="botanical-garden", name="Botanical Garden", dark=False,
         desc="Botanical Garden: fern green, marigold, terracotta and cream",
         palette="Fern Green #4a7c59, Marigold #f9a620, Terracotta #b7472a, Cream #f5f3ed",
         body_font=SANS_DEJAVU, head_font=SERIF_DEJAVU,
         side_bg="#3b6347",  # Fern Green #4a7c59 darkened: cream sidebar text is under 4.5:1 on it
         side_fg="#ffffff", side_muted="#f5f3ed", side_hover="#467353",
         side_active_bg="#2c4c36", side_active_fg="#ffffff", side_lobby="#fcd68e",
         win="#f5f3ed", panel="#ebe7da", line="#ddd7c4", line2="#c4bca3",
         fg="#2c4c36",  # Fern Green #4a7c59 darkened for body text
         muted="#4f5e50", link="#a33e24", button="#a33e24", button_hover="#ffffff",
         sel="#fbe2b0", in_bg="#fffdf8", in_fg="#2c4c36", in_line="#c4bca3",
         hl_bg="#fde7bb", hl_line="#f9a620", ok="#2c6e3d", warn="#7f5600", bad="#a33e24",
         date="#3e6a4b",  # Fern Green darkened for the date marker
         unread="#b7472a"),
    dict(slug="midnight-galaxy", name="Midnight Galaxy", dark=True,
         desc="Midnight Galaxy: deep purple, cosmic blue, lavender and silver",
         palette="Deep Purple #2b1e3e, Cosmic Blue #4a4e8f, Lavender #a490c2, Silver #e6e6fa",
         body_font=SANS_FREE, head_font=SANS_FREE,
         side_bg="#21172f", side_fg="#e6e6fa", side_muted="#b3a3cf", side_hover="#33264a",
         side_active_bg="#4a4e8f", side_active_fg="#ffffff", side_lobby="#c9b8ec",
         win="#2b1e3e", panel="#33254a", line="#3f3160", line2="#55467a",
         fg="#ffffff", muted="#b3a3cf",  # Lavender #a490c2 lightened a little for small text
         link="#c9b8ec", button="#c9b8ec", button_hover="#2b1e3e",
         sel="#4a4e8f", in_bg="#1e1530", in_fg="#ffffff", in_line="#55467a",
         hl_bg="#3d2d5e", hl_line="#a490c2", ok="#9be3b0", warn="#f5d08a", bad="#ff9aa8",
         date="#a490c2", unread="#ff9aa8"),
]
DEFAULT = "tech-innovation"

# Nickname colours: Prestium's pastels on dark themes, The Lounge 4.5.2's own on light ones,
# pushed lighter/darker until each is >= 4.5:1 on the window.
NICK_DARK = """f7adf7 abf99f 86efdc c890eb f9a4b3 f7999a f497b9 f9a9d7 85a7e3 a8b8ff b695fc f4aead
fc7cb1 ff72e0 8cb6ea f9857c ed9b82 8df484 ffcce3 efcc81 92a2ed f4d484 97ea70 fcbbba eef975 c7ff93
ffade1 98ecf2 91a2f5 b19aea f2a4eb 85f27d""".split()
NICK_LIGHT = """107ead a86500 008a3c e00096 f0000c 000094 006441 00566e e6006b 0d8766 006b3b 00857e
00465b eb005a e62600 0f8546 e60067 eb002b eb003f 007a56 095092 000bde 008577 00367d 007e9e 006119
007ea8 3c8500 e6007e c75300 eb0400 e60082""".split()


def rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def hexc(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in c)

def lum(h):
    def ch(v):
        v /= 255; return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in rgb(h)); return 0.2126 * r + 0.7152 * g + 0.0722 * b

def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True); return (la + 0.05) / (lb + 0.05)

def fit(color, bg, dark):
    """Mix color toward white (dark theme) or black (light) until it reaches MIN on bg."""
    c = rgb(color); t = (255, 255, 255) if dark else (0, 0, 0)
    for i in range(0, 101):
        h = hexc(tuple(c[k] + (t[k] - c[k]) * i / 100 for k in range(3)))
        if ratio(h, bg) >= MIN:
            return h
    raise SystemExit("cannot fit %s on %s" % (color, bg))

def pairs(t):
    """Every text/background pair the template draws: (label, text, background)."""
    p = [("chat text / window", t["fg"], t["win"]),
         ("chat text / header+form", t["fg"], t["panel"]),
         ("chat text / highlight", t["fg"], t["hl_bg"]),
         ("chat text / selected", t["fg"], t["sel"]),
         ("muted / window", t["muted"], t["win"]),
         ("muted / header+form", t["muted"], t["panel"]),
         ("link / window", t["link"], t["win"]),
         ("button / window", t["button"], t["win"]),
         ("button hover text / button", t["button_hover"], t["button"]),
         ("input text / input", t["in_fg"], t["in_bg"]),
         ("placeholder / input", t["muted"], t["in_bg"]),
         ("message form text / form", t["in_fg"], t["panel"]),
         ("sidebar text / sidebar", t["side_fg"], t["side_bg"]),
         ("sidebar muted / sidebar", t["side_muted"], t["side_bg"]),
         ("sidebar text / hover", t["side_fg"], t["side_hover"]),
         ("sidebar active text / active", t["side_active_fg"], t["side_active_bg"]),
         ("sidebar lobby / sidebar", t["side_lobby"], t["side_bg"]),
         ("badge / sidebar", t["side_bg"], t["link"] if t["dark"] else t["side_muted"])]
    for k in ("ok", "warn", "bad", "date", "unread"):
        p.append((k + " / window", t[k], t["win"]))
    return p

TEMPLATE = open(os.path.join(ROOT, "scripts/thelounge-theme.css.in")).read()

def render(t):
    v = dict(t)
    v["scheme"] = "dark" if t["dark"] else "light"
    v["logo_show"], v["logo_hide"] = (".logo-inverted", ".logo") if t["dark"] else (".logo", ".logo-inverted")
    v["badge_hl_bg"] = t["link"] if t["dark"] else t["side_muted"]
    v["overlay"] = "rgb(0 0 0 / 60%)" if t["dark"] else "rgb(0 0 0 / 40%)"
    v["shadow"] = "rgb(0 0 0 / 70%)" if t["dark"] else "rgb(0 0 0 / 25%)"
    v["kind"] = "dark" if t["dark"] else "light"
    base = NICK_DARK if t["dark"] else NICK_LIGHT
    nicks = [fit("#" + c, t["win"], t["dark"]) for c in base]
    v["nicks"] = "\n".join(".user.color-%d { color: %s; }" % (i + 1, c) for i, c in enumerate(nicks))
    v["nick_base"] = fit(t["muted"], t["win"], t["dark"])
    if t["dark"]:
        v["extra"] = ("\n/* IRC colours that are too dark on a dark window */\n"
                      ".irc-fg1 { color: %s; }\n.irc-fg2 { color: %s; }\n.irc-fg5 { color: %s; }\n"
                      ".irc-fg12 { color: %s; }\n\nkbd {\n\tcolor: #eee;\n\ttext-shadow: 0 -1px 0 #000;\n"
                      "\tborder-color: #000;\n\tbackground-color: #333;\n"
                      "\tbackground-image: linear-gradient(rgb(0 0 0 / 25%%), transparent);\n"
                      "\tbox-shadow: 0 2px 0 #000, inset 0 1px 1px #777, inset 0 -1px 3px #222;\n}\n") % (
                          t["muted"], fit("#0000fc", t["win"], True), fit("#7f0000", t["win"], True),
                          fit("#0000fc", t["win"], True))
    else:
        v["extra"] = ("\n/* IRC colours that are too light on a light window */\n"
                      ".irc-fg0 { color: %s; }\n.irc-fg8 { color: %s; }\n.irc-fg9 { color: %s; }\n"
                      ".irc-fg11 { color: %s; }\n") % (
                          t["muted"], fit("#ffff00", t["win"], False), fit("#00fc00", t["win"], False),
                          fit("#00ffff", t["win"], False))
    v["src"] = SRC
    out = TEMPLATE
    for k in sorted(v, key=len, reverse=True):
        out = out.replace("@" + k + "@", str(v[k]))
    assert "@" not in out.replace('@import "default.css";', ""), "unfilled placeholder in " + t["slug"]
    return out, nicks

def package_json(t):
    return json.dumps({
        "name": "thelounge-theme-" + t["slug"], "version": "1.0.0",
        "description": t["desc"] + ". Theme Factory palette for The Lounge, local only (Prestium)",
        "main": "index.js", "keywords": ["thelounge", "thelounge-theme"], "license": "Apache-2.0",
        "thelounge": {"name": t["name"], "type": "theme", "css": "theme.css",
                      "themeColor": t["side_bg"] if not t["dark"] else t["win"], "supports": ">=4.5.0"},
    }, indent=2) + "\n"

INDEX = ('"use strict";\n// Prestium 2.1: The Lounge require()s every package; a theme needs no code '
         '(theme.css is the theme).\nmodule.exports = {};\n')

def main():
    check = "--check" in sys.argv[1:]
    fail = 0
    for t in THEMES:
        css, nicks = render(t)
        worst = min(ratio(a, b) for _, a, b in pairs(t))
        for label, a, b in pairs(t):
            r = ratio(a, b)
            if r < MIN:
                print("FAIL %s: %s %s on %s = %.2f:1" % (t["slug"], label, a, b, r)); fail = 1
        if not check:
            print("%-18s chat %.2f:1  input %.2f:1  worst pair %.2f:1" % (
                t["slug"], ratio(t["fg"], t["win"]), ratio(t["in_fg"], t["in_bg"]), worst))
        d = os.path.join(PKGS, "node_modules", "thelounge-theme-" + t["slug"])
        files = {"theme.css": css, "package.json": package_json(t), "index.js": INDEX}
        for name, data in files.items():
            path = os.path.join(d, name)
            if check:
                if not os.path.isfile(path) or open(path).read() != data:
                    print("FAIL %s is not what scripts/thelounge-themes.py generates" % path); fail = 1
            else:
                os.makedirs(d, exist_ok=True)
                with open(path, "w") as f:
                    f.write(data)
    return fail

if __name__ == "__main__":
    sys.exit(main())
