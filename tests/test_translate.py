#!/usr/bin/env python3
"""Prestium 2.1: Prestium Translate (config/includes.chroot/usr/local/lib/prestium-translate/core.py and
usr/local/bin/prestium-translate). Without a display and without network:
  - the Light rewriter's rules one by one (invisible characters, look-alike letters, emoji, spacing,
    fillers, spelling, punctuation, case), the leftovers list, the word diff, the settings file (only the
    choices, never text) and the command line's usage;
  - with the real engine and models (PRESTIUM_TRANSLATE_SHARE, or /usr/share/prestium-translate as the
    image installs them; SKIP when neither is there): translation both ways (loose checks: the other
    script, key words, numbers kept), auto-detect, the Strong rewrite (differs from the input, keeps the
    numbers and names, varies between runs), the pipe protocol's errors, and the same through bubblewrap
    when bwrap can make a namespace here.
Fetch the engine and models with scripts/fetch-thirdparty.sh and run hook 0210 with PRESTIUM_HOOK_ROOT to
get a share tree (see tests/test_translate_hook.sh)."""
import io, json, os, random, shutil, stat, subprocess, sys, tempfile, unittest

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INC = os.path.join(R, "config", "includes.chroot")
BIN = os.path.join(INC, "usr", "local", "bin", "prestium-translate")
sys.dont_write_bytecode = True     # no __pycache__ in config/includes.chroot (live-build would ship it)
sys.path.insert(0, os.path.join(INC, "usr", "local", "lib", "prestium-translate"))
import core  # noqa: E402

SHARE = os.environ.get("PRESTIUM_TRANSLATE_SHARE") or core.SHARE
HAVE_ENGINE = os.path.exists(os.path.join(SHARE, core.ENGINE_REL)) and core.cpu_supported()


def light(t, seed=1):
    return core.light(t, random.Random(seed))


class LightRules(unittest.TestCase):
    def test_invisible(self):
        self.assertEqual(core.strip_invisible("he\u200bl\u200dlo\u2060 w\u00a0o\u202erld\ufeff"), "hello w orld")
        self.assertEqual(core.strip_invisible("a\r\nb\u2028c\u2029d"), "a\nb\nc\nd")
        self.assertEqual(core.strip_invisible("\uff48\uff49 \U0001d41b\U0001d428\U0001d425\U0001d41d"), "hi bold")
        self.assertEqual(core.strip_invisible("e\u0301"), "\u00e9")              # one form for é
        self.assertEqual(core.strip_invisible("Z\u0336\u0337\u0338a"), "Za")      # "zalgo"
        self.assertEqual(light("tab\there"), "Tab here")

    def test_lookalikes(self):
        self.assertEqual(core.fix_lookalikes("H\u0435llo w\u043erld"), "Hello world")          # Cyrillic е, о
        self.assertEqual(core.fix_lookalikes("P\u0443\u0441\u0441\u043a\u0438\u0439"), "Русский")  # Latin P
        self.assertEqual(core.fix_lookalikes("Hello мир"), "Hello мир")                     # whole words alone

    def test_emoji(self):
        self.assertEqual(light("Hi \U0001F600 there :) <3"), "Hi there")
        self.assertEqual(light("Привет 🙂)) как дела"), "Привет как дела")

    def test_spacing_and_punctuation(self):
        self.assertEqual(light("Wait , what ?!?!"), "Wait, what?")
        self.assertEqual(light("no!!!!"), "No!")
        self.assertEqual(light("so  many   spaces"), "So many spaces")
        for seed in range(6):
            out = light("Well.... ok … fine..", seed)
            self.assertNotIn("....", out)
            self.assertRegex(out, r"^Well(\.\.\.|\u2026) OK ?(\.\.\.|\u2026) ?[Ff]ine")
        self.assertEqual(light("He said “hi”"), 'He said "hi"')
        self.assertEqual(light('Он сказал "привет" - и ушел'), "Он сказал «привет» — и ушел")

    def test_fillers_and_spelling(self):
        self.assertEqual(light("basically, i realise the colour is gr8 lol"), "I realize the color is great")
        self.assertIn(light("u know what ur doing"), ("You know what you're doing", "You know what you are doing"))
        self.assertEqual(light("Ну щас короче всё будет. Ёлка!!!"), "Ну сейчас все будет. Елка!")
        self.assertEqual(light("ok thx, pls call me"), "OK thanks, please call me")

    def test_case(self):
        self.assertEqual(light("WHY IS THIS SO BAD!!!"), "Why is this so bad!")
        self.assertIn(light("this is REALLY important"), ("This is really important", "This is very important"))
        self.assertEqual(light("hey , WHAT IS UP!!!"), "Hey, what is up!")
        self.assertEqual(light("i think so. and you?"), "I think so. And you?")
        self.assertEqual(light("Meet me at the NASA office"), "Meet me at the NASA office")   # short acronyms stay

    def test_contractions_one_style(self):
        outs = {light("I cannot go. It is late and I do not know.", s) for s in range(12)}
        for o in outs:      # either all expanded or all contracted
            self.assertTrue(o == "I cannot go. It is late and I do not know." or o == "I can't go. It's late and I don't know.", o)
        self.assertEqual(len(outs), 2)

    def test_empty_and_numbers(self):
        self.assertEqual(light(""), "")
        self.assertEqual(light("Pay 1,250.75 on 12.03.2024 at 9:30"), "Pay 1,250.75 on 12.03.2024 at 9:30")

    def test_rewrite_limits(self):
        self.assertRaises(ValueError, core.rewrite, "x", "medium")
        self.assertRaises(core.EngineError, core.rewrite, "x" * (core.MAX_CHARS + 1), "light")


class Detection(unittest.TestCase):
    def test_direction(self):
        self.assertEqual(core.detect_direction("Привет, как дела?"), "ru-en")
        self.assertEqual(core.detect_direction("Hello there"), "en-ru")
        self.assertEqual(core.detect_direction("Hello there", "ru-en"), "en-ru")
        self.assertEqual(core.detect_direction("12:30 !!", "ru-en"), "ru-en")      # no letters: keep the choice
        self.assertEqual(core.detect_direction("Use Tor Browser, пожалуйста, это важно"), "ru-en")

    def test_cpu(self):
        with tempfile.NamedTemporaryFile("w") as f:
            f.write("flags\t: fpu sse sse2 ssse3 sse4_1 sse4_2\n"); f.flush()
            self.assertTrue(core.cpu_supported(f.name))
        with tempfile.NamedTemporaryFile("w") as f:
            f.write("flags\t: fpu sse sse2 ssse3\n"); f.flush()
            self.assertFalse(core.cpu_supported(f.name))


class Leftovers(unittest.TestCase):
    def test_kinds(self):
        got = core.leftovers("Write to bob@example.org or call 555-1234 on 12.03.2024 at 9:30. Ask Maria Ivanova. "
                             "The flux capacitor and the flux capacitor.")
        kinds = {(k, s) for k, s, n in got}
        for want in [("name", "Maria Ivanova"), ("time", "9:30"), ("date", "12.03.2024"), ("number", "555"),
                     ("address", "bob@example.org"), ("repeated word", "capacitor")]:
            self.assertIn(want, kinds)
        self.assertNotIn(("name", "Write"), kinds)
        self.assertEqual(core.leftovers("Meet John at 7:45")[0], ("name", "John", 1))
        self.assertIn(("name", "Москве"), {(k, s) for k, s, n in core.leftovers("Я живу в Москве.")})
        self.assertEqual(core.leftovers("Nothing here at all."), [])
        self.assertIn(("address", "@alice_99"), {(k, s) for k, s, n in core.leftovers("ping @alice_99")})

    def test_diff(self):
        d = core.diff_words("I dont know", "I don't know")
        self.assertEqual("".join(t for op, t in d if op != "insert"), "I dont know")
        self.assertEqual("".join(t for op, t in d if op != "delete"), "I don't know")
        self.assertIn(("delete", "dont"), d)
        self.assertEqual(core.diff_words("same", "same"), [("equal", "same")])


class Settings(unittest.TestCase):
    def test_only_choices(self):
        with tempfile.TemporaryDirectory() as h:
            p = core.settings_path(h)
            self.assertEqual(core.load_settings(p), core.DEFAULTS)
            s = dict(core.DEFAULTS, mode="rewrite", strength="strong", text="secret words", direction="ru-en")
            core.save_settings(s, p)
            with open(p) as f:
                d = json.load(f)
            self.assertEqual(set(d), set(core.SETTING_KEYS))
            self.assertNotIn("secret", json.dumps(d))
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(p)).st_mode), 0o700)
            self.assertEqual(sorted(os.listdir(os.path.dirname(p))), ["settings.json"])
            self.assertEqual(core.load_settings(p)["strength"], "strong")
            with open(p, "w") as f:
                f.write('{"mode": "evil", "direction": 3, "auto_detect": false}')
            self.assertEqual(core.load_settings(p), dict(core.DEFAULTS, auto_detect=False))
            with open(p, "w") as f:
                f.write("[not json")
            self.assertEqual(core.load_settings(p), core.DEFAULTS)


class CommandLine(unittest.TestCase):
    def run_cli(self, argv, text="", share="/nonexistent"):
        o, e = io.StringIO(), io.StringIO()
        rc = core.cli(argv, io.StringIO(text), o, e, share=share)
        return rc, o.getvalue(), e.getvalue()

    def test_usage(self):
        for argv in ([], ["--translate"], ["--translate", "en-de"], ["--rewrite", "medium"], ["--frob", "x"],
                     ["--translate", "en-ru", "extra"], ["--rewrite", "light", "--nope"]):
            rc, o, e = self.run_cli(argv)
            self.assertEqual(rc, 2, argv)
            self.assertIn("usage:", e)

    def test_light_without_engine(self):
        rc, o, e = self.run_cli(["--rewrite", "light", "--leftovers"], "basically , meet Bob at 9:30 lol")
        self.assertEqual((rc, o), (0, "Meet Bob at 9:30\n"))
        self.assertIn("leftover: a name or place: Bob", e)
        self.assertIn("leftover: a time: 9:30", e)

    def test_no_engine(self):
        rc, o, e = self.run_cli(["--translate", "en-ru"], "hello")
        self.assertEqual(rc, 1)
        self.assertIn("prestium-translate:", e)

    def test_script(self):
        p = subprocess.run([sys.executable, "-B", "-I", BIN, "--rewrite", "light"], input="hey , WHAT IS UP!!!",
                           capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, "Hey, what is up!\n"), p.stderr)
        p = subprocess.run([sys.executable, "-B", "-I", BIN, "--help"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0); self.assertIn("usage:", p.stdout)


@unittest.skipUnless(HAVE_ENGINE, "no engine and models at %s (or the CPU lacks SSE4.1)" % SHARE)
class RealModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = core.Engine(SHARE, sandbox=False)

    @classmethod
    def tearDownClass(cls):
        cls.e.stop()

    def test_en_ru(self):
        out = self.e.translate("The weather is good today. I have 3 cats and 12 books.", "en-ru")
        self.assertTrue(core.has_cyrillic(out), out)
        self.assertNotRegex(out, "[A-Za-z]{3,}")
        self.assertIn("3", out); self.assertIn("12", out)
        self.assertRegex(out.lower(), "погод|сегодня")
        self.assertRegex(out.lower(), "кош|кот")

    def test_ru_en(self):
        out = self.e.translate("Сегодня хорошая погода. У меня 3 кошки и 12 книг.", "ru-en")
        self.assertFalse(core.has_cyrillic(out), out)
        self.assertIn("3", out); self.assertIn("12", out)
        self.assertRegex(out.lower(), "weather")
        self.assertRegex(out.lower(), "cats")

    def test_lines_and_blank(self):
        out = self.e.translate("Hello.\n\nGood night.\n", "en-ru")
        self.assertEqual(out.count("\n"), 3, repr(out))
        self.assertEqual(self.e.translate("", "en-ru"), "")
        self.assertEqual(self.e.translate("  \n ", "ru-en").strip(), "")

    def test_auto_cli(self):
        o, e = io.StringIO(), io.StringIO()
        self.assertEqual(core.cli(["--translate", "auto"], io.StringIO("Доброе утро"), o, e, share=SHARE, sandbox=False), 0)
        self.assertRegex(o.getvalue().lower(), "morning")

    def test_strong(self):
        src = ("basically i think the new plan is gr8, we should start on monday with 25 people. "
               "honestly the budget of 4000 dollars is enough!!!")
        outs = [core.rewrite(src, "strong", self.e) for _ in range(6)]
        for o in outs:
            self.assertNotEqual(o, src)
            self.assertIn("25", o); self.assertIn("4000", o.replace(",", "").replace(" ", ""))
            self.assertFalse(core.has_cyrillic(o), o)
            self.assertRegex(o.lower(), "plan")
            self.assertNotIn("gr8", o); self.assertNotIn("!!!", o)
        self.assertGreater(len(set(outs)), 1, "Strong gave the same text every time")
        ru = core.rewrite("Короче, я щас думаю, что план норм, начнем в понедельник, нас будет 25.", "strong", self.e)
        self.assertTrue(core.has_cyrillic(ru)); self.assertIn("25", ru); self.assertNotIn("щас", ru)

    def test_protocol_errors(self):
        self.e.call("ping")                                  # no error
        with self.assertRaises(core.EngineError):
            self.e.call("de-fr", b"hallo")
        # the engine still answers after an error
        self.assertTrue(core.has_cyrillic(self.e.translate("Thank you", "en-ru")))

    def test_sandboxed(self):
        if not os.path.exists(core.BWRAP):
            self.skipTest("bwrap missing")
        if subprocess.run([core.BWRAP, "--unshare-all", "--ro-bind", "/", "/", "true"], capture_output=True).returncode:
            self.skipTest("bwrap cannot make namespaces here")
        e = core.Engine(SHARE, sandbox=True)
        try:
            self.assertIn("--unshare-all", e.command()); self.assertIn("--clearenv", e.command())
            self.assertNotIn("--share-net", e.command())
            self.assertRegex(e.translate("Good morning", "en-ru").lower(), "утр")
        finally:
            e.stop()


class Static(unittest.TestCase):
    def test_no_network_or_history_code(self):
        for p in (BIN, core.__file__):
            with open(p) as f:
                src = f.read()
            self.assertNotRegex(src, r"\bimport (socket|urllib|http|requests)|from (socket|urllib|http) ")
            self.assertNotIn("RecentManager", src)
            self.assertNotIn("tempfile", src)

    def test_bwrap_command(self):
        c = core.Engine("/usr/share/prestium-translate").command()
        self.assertEqual(c[0], core.BWRAP)
        for flag in ("--unshare-all", "--die-with-parent", "--new-session", "--clearenv", "--cap-drop"):
            self.assertIn(flag, c)
        self.assertNotIn("--bind", c)                  # read-only binds only, no home
        self.assertFalse(any("/home" in a or a == "/run" for a in c), c)
        self.assertEqual(c[c.index("--tmpfs") + 1], "/tmp")


if __name__ == "__main__":
    unittest.main(verbosity=1)
