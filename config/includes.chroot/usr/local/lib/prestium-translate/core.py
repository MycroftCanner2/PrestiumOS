"""Prestium 2.1: Prestium Translate's logic, without GTK (the window is /usr/local/bin/prestium-translate).

English <-> Russian translation with Bergamot (the engine of Firefox Translations) and Mozilla's models,
and a style rewriter that lowers the chance that a text is matched to its author by how it is written:
  Light    rules only, instant: punctuation, spacing, capitals, emoji, invisible and look-alike characters,
           one spelling (US English, standard Russian), a short list of filler words and slang, and small
           random choices (synonyms, contractions, ellipsis and dash forms) so the output varies
  Strong   Light, then a round trip through the other language (English -> Russian -> English, Russian ->
           English -> Russian) with the same two models, then Light again
  leftovers() lists what a rewrite can't hide (numbers, times, names, addresses, repeated words).
It never writes the text anywhere: no history, no temporary files, no cache. The engine
(/usr/share/prestium-translate/bin/prestium-translate-engine) runs in bubblewrap with no network, no home
folder, the models read-only and a private /tmp, and is fed through a pipe.
"""
import difflib, json, os, random, re, subprocess, sys, threading, unicodedata

SHARE = "/usr/share/prestium-translate"
ENGINE_REL = "bin/prestium-translate-engine"
MODELS_REL = "models"
BWRAP = "/usr/bin/bwrap"
DIRECTIONS = ("en-ru", "ru-en")
STRENGTHS = ("light", "strong")
MAX_CHARS = 100000          # per translation or rewrite (the engine takes up to 1 MiB per request)
NOTE = ("Rewriting lowers the chance that your writing style is matched to you; it can't promise it. What you "
        "say (names, places, times, details only you know) can identify you more than how you say it.")
STATUS = "Offline, nothing saved"


class EngineError(Exception):
    pass


# ------------------------------------------------------------------------------------------- language
CYR = re.compile(r"[\u0400-\u04FF]")
LAT = re.compile(r"[A-Za-z]")


def has_cyrillic(text):
    return bool(CYR.search(text))


def language(text):
    """'ru' if most letters are Cyrillic, else 'en'."""
    c, l = len(CYR.findall(text)), len(LAT.findall(text))
    return "ru" if c > l else "en"


def detect_direction(text, current="en-ru"):
    """Cyrillic text is translated from Russian; Latin text from English; no letters: keep current."""
    c, l = len(CYR.findall(text)), len(LAT.findall(text))
    if c == l == 0:
        return current
    return "ru-en" if c > l else "en-ru"


def cpu_supported(cpuinfo="/proc/cpuinfo"):
    """The engine is built for x86-64 with SSE4.1 (Intel 2008+, AMD 2011+): True, False or None (unknown)."""
    try:
        with open(cpuinfo) as f:
            for line in f:
                if line.startswith("flags"):
                    flags = line.split(":", 1)[1].split()
                    return "sse4_1" in flags and "ssse3" in flags
    except OSError:
        return None
    return None


# ------------------------------------------------------------------------------------------- engine
class Engine:
    """The Bergamot engine, started once (in bubblewrap) and fed text through a pipe."""

    def __init__(self, share=SHARE, sandbox=True):
        self.share = share
        self.sandbox = sandbox
        self.proc = None
        self.lock = threading.Lock()

    def available(self):
        e = os.path.join(self.share, ENGINE_REL)
        m = os.path.join(self.share, MODELS_REL)
        return os.access(e, os.X_OK) and all(os.path.isdir(os.path.join(m, p)) for p in ("enru", "ruen"))

    def command(self):
        engine = os.path.join(self.share, ENGINE_REL)
        models = os.path.join(self.share, MODELS_REL)
        if not self.sandbox:
            return [engine, models]
        # inside: the engine and the models at their image paths, read-only; the C/C++ runtime libraries;
        # nothing else of the system, no home, no /run, no network (own empty network namespace), a
        # private /tmp and /dev; no capabilities; it dies with the app
        return [BWRAP, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
                "--setenv", "LANG", "C.UTF-8", "--setenv", "PATH", "/nonexistent",
                "--ro-bind", "/usr/lib/x86_64-linux-gnu", "/usr/lib/x86_64-linux-gnu",
                "--ro-bind", "/usr/lib64", "/usr/lib64", "--symlink", "usr/lib64", "/lib64",
                "--symlink", "usr/lib", "/lib",
                "--ro-bind", engine, "/usr/share/prestium-translate/" + ENGINE_REL,
                "--ro-bind", models, "/usr/share/prestium-translate/" + MODELS_REL,
                "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--chdir", "/",
                "--cap-drop", "ALL",
                "/usr/share/prestium-translate/" + ENGINE_REL, "/usr/share/prestium-translate/" + MODELS_REL]

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        if cpu_supported() is False:
            raise EngineError("This computer's processor is too old for the translation engine (it needs "
                              "SSE4.1: Intel from 2008, AMD from 2011). Light rewriting still works.")
        if not self.available():
            raise EngineError("The translation engine or its models are missing from %s." % self.share)
        try:
            self.proc = subprocess.Popen(self.command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, close_fds=True)
        except OSError as e:
            raise EngineError("The translation engine could not start (%s)." % e.strerror)

    def stop(self):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.stdin.close()
                p.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                p.kill()
                p.wait()
        if p:
            for f in (p.stdin, p.stdout):
                try:
                    f.close()
                except OSError:
                    pass

    def _request(self, cmd, data=b""):
        p = self.proc
        try:
            p.stdin.write(b"%s %d\n" % (cmd.encode(), len(data)) + data)
            p.stdin.flush()
            head = p.stdout.readline().decode("ascii", "replace").split()
            if len(head) != 2 or head[0] not in ("OK", "ERR") or not head[1].isdigit():
                raise EngineError("The translation engine stopped.")
            body = p.stdout.read(int(head[1])) if int(head[1]) else b""
            if len(body) != int(head[1]):
                raise EngineError("The translation engine stopped.")
        except (OSError, ValueError):
            raise EngineError("The translation engine stopped.")
        if head[0] == "ERR":
            raise EngineError("The translation engine failed: %s" % body.decode("utf-8", "replace"))
        return body.decode("utf-8", "replace")

    def call(self, cmd, data=b""):
        with self.lock:
            for attempt in (0, 1):
                self.start()
                try:
                    return self._request(cmd, data)
                except EngineError:
                    if self.proc and self.proc.poll() is None:
                        raise          # a real error from a running engine
                    self.stop()
                    if attempt:
                        raise

    def load(self, direction):
        if direction not in DIRECTIONS:
            raise ValueError(direction)
        self.call("load " + direction)

    def translate(self, text, direction):
        """Translate line by line (blank lines and leading spaces kept); a line is a paragraph."""
        if direction not in DIRECTIONS:
            raise ValueError(direction)
        if len(text) > MAX_CHARS:
            raise EngineError("The text is too long (more than %d characters)." % MAX_CHARS)
        out = []
        for line in text.split("\n"):
            core = line.strip()
            if not core:
                out.append("")
                continue
            lead = line[:len(line) - len(line.lstrip())]
            out.append(lead + self.call(direction, core.encode("utf-8")).strip())
        return "\n".join(out)


# ------------------------------------------------------------------------------------------- Light rules
INVISIBLE = re.compile("[\u00AD\u034F\u061C\u115F\u1160\u17B4\u17B5\u180B-\u180F\u200B-\u200F\u202A-\u202E"
                       "\u2060-\u206F\u3164\uFE00-\uFE0F\uFEFF\uFFA0\uFFF9-\uFFFB\U000E0000-\U000E007F"
                       "\U000E0100-\U000E01EF]")
ODD_SPACE = re.compile("[\t\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000\u2800]")
LINE_SEP = re.compile("[\u2028\u2029\u0085\r\v\f]")
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U0001FC00-\U0001FFFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF"
                   "\u2190-\u21FF\u25A0-\u25FF\u3030\u303D\u3297\u3299\u00A9\u00AE\u2122\u2139\u24C2]")
EMOTICON = re.compile(r"(?<!\w)(?:[:;=8xX][-'^o]?[()\[\]DPpOo3|\\/*@$]+|<3+|\^_*\^|[)(]{2,}|[хХ][Dd]+"
                      r"|[TtТ]_[TtТ]|o_O|O_o|\(\s*[\^\-o]\s*[_.]\s*[\^\-o]\s*\))(?!\w)")
# Latin and Cyrillic letters that look the same
LAT2CYR = dict(zip("aceopxyABCEHKMOPTX", "асеорхуАВСЕНКМОРТХ"))
CYR2LAT = {v: k for k, v in LAT2CYR.items()}
CYR2LAT.update({"і": "i", "І": "I", "ј": "j", "Ј": "J", "ѕ": "s", "Ѕ": "S", "һ": "h", "ԁ": "d", "ԛ": "q", "ԝ": "w"})
WORD = re.compile(r"[A-Za-z\u0400-\u04FF]+")
FULLWIDTH = re.compile("[\uFF01-\uFF5E]")
MATH_ALNUM = re.compile("[\U0001D400-\U0001D7FF]")

US = {"colour": "color", "colours": "colors", "coloured": "colored", "favour": "favor", "favours": "favors",
      "favourite": "favorite", "favourites": "favorites", "honour": "honor", "honours": "honors",
      "behaviour": "behavior", "behaviours": "behaviors", "neighbour": "neighbor", "neighbours": "neighbors",
      "labour": "labor", "humour": "humor", "rumour": "rumor", "rumours": "rumors", "harbour": "harbor",
      "flavour": "flavor", "endeavour": "endeavor", "centre": "center", "centres": "centers",
      "theatre": "theater", "metre": "meter", "metres": "meters", "litre": "liter", "litres": "liters",
      "fibre": "fiber", "defence": "defense", "offence": "offense", "licence": "license",
      "travelled": "traveled", "travelling": "traveling", "traveller": "traveler", "cancelled": "canceled",
      "cancelling": "canceling", "labelled": "labeled", "modelling": "modeling", "programme": "program",
      "programmes": "programs", "catalogue": "catalog", "dialogue": "dialog", "analogue": "analog",
      "grey": "gray", "tyre": "tire", "tyres": "tires", "jewellery": "jewelry", "pyjamas": "pajamas",
      "aluminium": "aluminum", "mum": "mom", "cheque": "check", "plough": "plow", "sceptical": "skeptical",
      "aeroplane": "airplane", "enrol": "enroll", "fulfil": "fulfill", "whilst": "while", "amongst": "among",
      "learnt": "learned", "spelt": "spelled", "dreamt": "dreamed", "towards": "toward", "practise": "practice"}
IZE = re.compile(r"\b(organ|real|recogn|apolog|critic|emphas|summar|minim|maxim|optim|util|categor|"
                 r"memor|prior|special|fantas|sympath|author|character|civil|final|general|normal|"
                 r"standard|visual|modern|central|global|custom|priorit|stabil|surpris(?!e))is(e|es|ed|ing|ation|ations)\b",
                 re.I)
EN_SLANG = [(r"\bu\b", "you"),
            (r"\bur\b(?=\s+(?:\w+ing|a|an|the|not|so|very|too|right|wrong|welcome|kidding|joking)\b)", "you're"),
            (r"\bur\b", "your"), (r"\bpl[sz]\b", "please"), (r"\bplz\b", "please"),
            (r"\bthx\b", "thanks"), (r"\btnx\b", "thanks"), (r"\bty\b", "thank you"), (r"\bidk\b", "I don't know"),
            (r"\bimo\b", "in my opinion"), (r"\bimho\b", "in my opinion"), (r"\bbtw\b", "by the way"),
            (r"\bgonna\b", "going to"), (r"\bwanna\b", "want to"), (r"\bgotta\b", "have to"),
            (r"\bkinda\b", "kind of"), (r"\bsorta\b", "sort of"), (r"\bdunno\b", "don't know"),
            (r"\bcuz\b", "because"), (r"\bcos\b", "because"), (r"\bcause\b(?= I| you| we| they| it)", "because"),
            (r"\bya\b", "you"), (r"\byeah\b", "yes"), (r"\byep\b", "yes"), (r"\bnope\b", "no"),
            (r"\bdont\b", "don't"), (r"\bdoesnt\b", "doesn't"), (r"\bdidnt\b", "didn't"), (r"\bcant\b", "can't"),
            (r"\bisnt\b", "isn't"), (r"\bwasnt\b", "wasn't"), (r"\bim\b", "I'm"), (r"\bive\b", "I've"),
            (r"\bthats\b", "that's"), (r"\bwhats\b", "what's"), (r"\bthru\b", "through"), (r"\btho\b", "though"),
            (r"\bb4\b", "before"), (r"\bgr8\b", "great"), (r"\bppl\b", "people"), (r"\bmsg\b", "message"),
            (r"\bpic\b", "picture"), (r"\bpics\b", "pictures"), (r"\bok\b", "OK"), (r"\bokay\b", "OK")]
EN_FILLER = [r"\b(?:basically|literally|honestly|frankly|seriously|totally),?\s+", r"\byou know,\s*",
             r"\bI mean,\s*", r"\bto be honest,?\s*", r"\btbh,?\s*", r"\bngl,?\s*", r"\blol\b[.!]?\s*",
             r"\blmao\b[.!]?\s*", r"\brofl\b[.!]?\s*", r"\bso yeah,?\s*", r"\bwell,\s+", r"\banyway,\s+",
             r"\bjust saying,?\s*", r"\bum+,?\s+", r"\buh+,?\s+", r"\bhmm+,?\s*", r",\s*like,(?=\s)",
             r"\bat the end of the day,\s*", r"\bif you will,?\s*"]
RU_SLANG = [(r"\bщас\b", "сейчас"), (r"\bща\b", "сейчас"), (r"\bчё\b", "что"), (r"\bчо\b", "что"),
            (r"\bче\b", "что"), (r"\bшо\b", "что"), (r"\bспс\b", "спасибо"), (r"\bсяб\b", "спасибо"),
            (r"\bпжлст\b", "пожалуйста"), (r"\bпж\b", "пожалуйста"), (r"\bплз\b", "пожалуйста"),
            (r"\bпожалуста\b", "пожалуйста"), (r"\bоч\b", "очень"), (r"\bтока\b", "только"),
            (r"\bваще\b", "вообще"), (r"\bвобще\b", "вообще"), (r"\bсёдня\b", "сегодня"), (r"\bседня\b", "сегодня"),
            (r"\bничо\b", "ничего"), (r"\bниче\b", "ничего"), (r"\bскока\b", "сколько"), (r"\bтыщ[аи]?\b", "тысяч"),
            (r"\bприв\b", "привет"), (r"\bнорм\b", "нормально"), (r"\bинфа\b", "информация"),
            (r"\bкомп\b", "компьютер"), (r"\bспасиб\b", "спасибо"), (r"\bлан\b", "ладно"), (r"\bлады\b", "ладно"),
            (r"\bок\b", "хорошо"), (r"\bокей\b", "хорошо"), (r"\bканеш\b", "конечно"), (r"\bкороч\b", "короче"),
            (r"\bщя\b", "сейчас"), (r"\bмб\b", "может быть"), (r"\bхз\b", "не знаю"), (r"\bимхо\b", "по-моему")]
RU_FILLER = [r"\bкороче,?\s+", r"\bтипа,?\s+", r"\bкак бы,?\s+", r"\bв общем,?\s+", r"\bвообще-то,?\s+",
             r"\bблин,?\s*", r"\bну,\s+", r"\bсобственно,?\s+", r"\bна самом деле,?\s+", r"\bэто самое,?\s*",
             r"\bскажем так,?\s*", r"\bтак сказать,?\s*", r"\bзначит,\s+", r"\bслушай,\s+", r"\bпрям\b\s*",
             r"\bлол\b[.!]?\s*", r"\bахах[ах]*\b[.!]?\s*", r"\bхаха[ха]*\b[.!]?\s*", r"\bммм*,?\s*", r"\bэээ*,?\s*"]
# interchangeable words (same part of speech, no inflection): one is picked at random each time
EN_SYN = [("maybe", "perhaps"), ("often", "frequently"), ("usually", "normally"), ("almost", "nearly"),
          ("big", "large"), ("very", "really"), ("quickly", "fast"), ("buy", "purchase"), ("help", "assist"),
          ("start", "begin"), ("enough", "sufficiently"), ("also", "additionally")]
RU_SYN = [("возможно", "может быть"), ("часто", "нередко"), ("обычно", "как правило"), ("почти", "практически"),
          ("очень", "весьма"), ("сразу", "немедленно"), ("иногда", "порой"), ("конечно", "разумеется")]
CONTRACTIONS = [("do not", "don't"), ("does not", "doesn't"), ("did not", "didn't"), ("cannot", "can't"),
                ("will not", "won't"), ("is not", "isn't"), ("are not", "aren't"), ("was not", "wasn't"),
                ("were not", "weren't"), ("have not", "haven't"), ("has not", "hasn't"), ("would not", "wouldn't"),
                ("should not", "shouldn't"), ("could not", "couldn't"), ("I am", "I'm"), ("I have", "I've"),
                ("I will", "I'll"), ("you are", "you're"), ("we are", "we're"), ("they are", "they're"),
                ("it is", "it's"), ("that is", "that's"), ("there is", "there's"), ("let us", "let's")]


def _case_like(src, word):
    if src.isupper() and len(src) > 1:
        return word.upper()
    if src[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def _sub_words(text, pairs, flags=re.I):
    for pat, rep in pairs:
        text = re.sub(pat, lambda m, r=rep: _case_like(m.group(0), r) if r[:1].islower() else r, text, flags=flags)
    return text


def strip_invisible(text):
    """Zero-width and formatting characters, odd spaces, line separators, fancy Unicode letters."""
    text = LINE_SEP.sub("\n", text.replace("\r\n", "\n"))
    text = INVISIBLE.sub("", text)
    text = ODD_SPACE.sub(" ", text)
    # full-width and "mathematical" letters and digits (𝐛𝐨𝐥𝐝, ｗｉｄｅ) to plain ones
    text = FULLWIDTH.sub(lambda m: unicodedata.normalize("NFKC", m.group(0)), text)
    text = MATH_ALNUM.sub(lambda m: unicodedata.normalize("NFKC", m.group(0)), text)
    # composed letters (é as e + combining accent) in one form; stray combining marks dropped
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"([A-Za-z\u00C0-\u024F\u0400-\u04FF])[\u0300-\u036F]{2,}", r"\1", text)   # "zalgo"
    text = re.sub(r"(?<![A-Za-z\u00C0-\u024F\u0400-\u04FF])[\u0300-\u036F]+", "", text)
    return text


def fix_lookalikes(text):
    """In a word that is mostly Cyrillic, Latin look-alikes become Cyrillic, and the other way round."""
    def fix(m):
        w = m.group(0)
        c, l = len(CYR.findall(w)), len(LAT.findall(w))
        if c and l:
            if c >= l:
                return "".join(LAT2CYR.get(ch, ch) for ch in w)
            return "".join(CYR2LAT.get(ch, ch) for ch in w)
        if c and language(text) == "en" and all(ch in CYR2LAT for ch in w):
            return "".join(CYR2LAT[ch] for ch in w)       # a whole "English" word typed in Cyrillic look-alikes
        return w
    return WORD.sub(fix, text)


def remove_emoji(text):
    text = EMOJI.sub("", text)
    text = EMOTICON.sub("", text)
    return text


def normalize_punctuation(text, lang, rng):
    # ellipsis: one form for the whole text (picked at random); "...." and ". . ." too
    ell = rng.choice(["...", "\u2026"]) if lang == "en" else "..."
    text = re.sub(r"\.(?:[ ]?\.){2,}|\u2026+", "\u0000", text)
    # repeated ! and ?: one mark ("?!" and "!?" become "?")
    text = re.sub(r"[!?]*\?[!?]*", lambda m: "?" if len(m.group(0)) > 1 else m.group(0), text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"([,;:])\1+", r"\1", text)
    text = re.sub(r"\.{2}(?!\.)", ".", text)
    text = text.replace("\u0000", ell)
    # quotes: straight in English, «guillemets» in Russian; apostrophes straight
    text = re.sub("[\u2018\u2019\u201B\u2032`\u00B4]", "'", text)
    if lang == "ru":
        text = re.sub("[\u201C\u201D\u201E\u201F\u2033\u00AB\u00BB\"]", "\"", text)
        text = re.sub(r'"(\S(?:[^"\n]*?\S)?)"', "\u00AB\\1\u00BB", text)
    else:
        text = re.sub("[\u201C\u201D\u201E\u201F\u2033\u00AB\u00BB]", "\"", text)
    # dashes between words: one form ("—" in Russian with spaces; English picks one at random)
    dash = " \u2014 " if lang == "ru" else rng.choice(["\u2014", " \u2014 ", " \u2013 "])
    text = re.sub(r"(?<=\S)[ ]+(?:-{1,3}|\u2013|\u2014|\u2012|\u2015)[ ]+(?=\S)|(?<=\w)(?:-{2,3}|\u2014|\u2015)(?=\w)",
                  dash, text)
    text = re.sub("[\u2010\u2011]", "-", text)
    # spacing around punctuation
    text = re.sub(r"[ ]+([,.;:!?\u2026\u00BB)])", r"\1", text)
    text = re.sub(r"([(\u00AB])[ ]+", r"\1", text)
    text = re.sub(r"([,;:!?])(?=[A-Za-z\u0400-\u04FF])", r"\1 ", text)
    text = re.sub(r"(?<=[a-z\u0430-\u044f])\.(?=[A-Z\u0410-\u042f][a-z\u0430-\u044f])", ". ", text)
    return text


def normalize_spacing(text):
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"[ ]+(?=[,;:!?)\u00BB]|\.(?!\.))", "", text)
    text = "\n".join(l.strip() for l in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


SENT_START = re.compile(r"(^|[.!?\u2026]\s+|\n)([\"\u00AB(]?)([a-z\u0430-\u044f\u0451])")


def normalize_case(text, lang):
    # a whole sentence in capitals (shouting) becomes normal sentence case
    def unshout(m):
        letters = [c for c in m.group(0) if c.isalpha()]
        if len(letters) >= 8 and all(c.isupper() for c in letters):
            return m.group(0).lower()
        return m.group(0)
    text = re.sub(r"[^.!?\u2026\n]+[.!?\u2026]*", unshout, text)
    # single words in capitals for emphasis (6+ letters; shorter ones are often abbreviations)
    text = re.sub(r"\b[A-Z\u0410-\u042f\u0401]{6,}\b", lambda m: m.group(0).lower(), text)
    # three or more words in capitals in a row ("hey, WHAT IS UP")
    text = re.sub(r"\b[A-Z\u0410-\u042f\u0401]{2,}(?:[ ,]+[A-Z\u0410-\u042f\u0401]{1,}){2,}\b",
                  lambda m: m.group(0).lower(), text)
    if lang == "en":
        text = re.sub(r"\bi\b(?!\.)", "I", text)
        text = re.sub(r"\bi'(m|ve|ll|d)\b", r"I'\1", text)
    return SENT_START.sub(lambda m: m.group(1) + m.group(2) + m.group(3).upper(), text)


def standard_spelling(text, lang):
    if lang == "en":
        text = re.sub(r"\b(%s)\b" % "|".join(US), lambda m: _case_like(m.group(0), US[m.group(0).lower()]),
                      text, flags=re.I)
        text = IZE.sub(lambda m: m.group(0)[:-len(m.group(2)) - 2] + ("iz" if m.group(0)[-len(m.group(2)) - 2] == "i"
                                                                         else "IZ") + m.group(2), text)
        text = _sub_words(text, EN_SLANG)
    else:
        text = text.replace("ё", "е").replace("Ё", "Е")
        text = _sub_words(text, RU_SLANG)
    return text


def neutralize_fillers(text, lang):
    for pat in (EN_FILLER if lang == "en" else RU_FILLER):
        text = re.sub(pat, "", text, flags=re.I)
    return text


def vary(text, lang, rng):
    """Small random choices: synonyms; in English also contractions, all expanded or all contracted."""
    pairs = EN_SYN if lang == "en" else RU_SYN
    for a, b in pairs:
        pat = r"\b(%s|%s)\b" % (re.escape(a), re.escape(b))
        text = re.sub(pat, lambda m: _case_like(m.group(0), rng.choice((a, b))), text, flags=re.I)
    if lang == "en":
        contract = rng.random() < 0.5
        for full, short in CONTRACTIONS:
            src, dst = (full, short) if contract else (short, full)
            pat = r"\b%s\b" % re.escape(src).replace(r"\ ", r"\s+")
            text = re.sub(pat, lambda m, d=dst: _case_like(m.group(0), d) if not d.startswith("I") else d,
                          text, flags=re.I)
    return text


def light(text, rng=None, lang=None):
    rng = rng or random.SystemRandom()
    text = strip_invisible(text)
    lang = lang or language(text)
    text = fix_lookalikes(text)
    text = remove_emoji(text)
    text = normalize_spacing(text)
    text = neutralize_fillers(text, lang)
    text = standard_spelling(text, lang)
    text = normalize_punctuation(text, lang, rng)
    text = normalize_case(text, lang)
    text = vary(text, lang, rng)
    text = normalize_spacing(text)
    return text


def strong(text, engine, rng=None):
    rng = rng or random.SystemRandom()
    lang = language(strip_invisible(text))
    t = light(text, rng, lang)
    if not t:
        return t
    if lang == "en":
        t = engine.translate(engine.translate(t, "en-ru"), "ru-en")
    else:
        t = engine.translate(engine.translate(t, "ru-en"), "en-ru")
    return light(t, rng, lang)


def rewrite(text, strength, engine=None, rng=None):
    if strength not in STRENGTHS:
        raise ValueError(strength)
    if len(text) > MAX_CHARS:
        raise EngineError("The text is too long (more than %d characters)." % MAX_CHARS)
    if strength == "light":
        return light(text, rng)
    return strong(text, engine, rng)


# ------------------------------------------------------------------------------------------- leftovers
EN_COMMON = set("""about above after again against because before being below between could doing during
every first great might never other right should still their there these thing think those three through
today under until where which while would years people really always little going something nothing
everything anything someone without within another around please thanks thank""".split())
RU_COMMON = set("""сейчас всегда потом когда очень только тоже также потому поэтому которые который
которая которое может можно нужно будет было были если чтобы этого этому этой этот этих сегодня завтра
вчера спасибо пожалуйста хорошо просто вообще ничего всего всех себя тебя меня""".split())
# common first words of a sentence that are not names (for "Meet John" or "Встречай Ивана")
SENTENCE_WORDS = set("""meet ask tell call send bring take see thanks thank hello hi hey dear please let give
tomorrow today yesterday when where what why how then so but and if after before with from tell
привет здравствуй здравствуйте спроси скажи позвони встречай встреть передай напиши дорогой дорогая
спасибо пожалуйста завтра сегодня вчера когда где что почему как потом но если после до""".split())
LEFTOVER_PATTERNS = [
    ("date", r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct"
             r"|Nov|Dec)[a-z]*\.? \d{1,2}\b|\b\d{1,2} (?:января|февраля|марта|апреля|мая|июня|июля|августа"
             r"|сентября|октября|ноября|декабря)\b"),
    ("time", r"\b(?:[01]?\d|2[0-3])[:.][0-5]\d(?:\s?[AaPp]\.?[Mm]\.?)?\b|\b\d{1,2}\s?(?:am|pm|AM|PM)\b"),
    ("address", r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b|\bhttps?://\S+|\b[a-z2-7]{16,56}\.onion\b|(?<!\w)@\w{2,}"),
    ("number", r"\b\d[\d.,]*\b"),
]


def leftovers(text):
    """What a rewrite can't hide, for the person to check: [(kind, text, count)] in order of appearance."""
    found, seen = [], {}

    def add(kind, s):
        k = (kind, s.lower())
        if k in seen:
            found[seen[k]][2] += 1
        else:
            seen[k] = len(found)
            found.append([kind, s, 1])
    taken = []
    for kind, pat in LEFTOVER_PATTERNS:
        for m in re.finditer(pat, text):
            if any(a <= m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            add(kind, m.group(0))
    # names: capitalized words that don't start a sentence (and aren't "I")
    for m in re.finditer(r"\b([A-Z\u0410-\u042f\u0401][a-z\u0430-\u044f\u0451]{1,}"
                         r"(?:\s[A-Z\u0410-\u042f\u0401][a-z\u0430-\u044f\u0451]+)*)", text):
        before = text[:m.start()].rstrip()
        name = m.group(1)
        if not before or before[-1] in ".!?\u2026\n\"\u00AB:":
            if " " not in name:
                continue                 # one capitalized word at the start of a sentence
            first, rest = name.split(" ", 1)
            if first.lower() in SENTENCE_WORDS or len(first) < 3:
                name = rest              # "Meet John": the sentence's first word is not part of the name
        add("name", name)
    # rare words used more than once (a habit of the writer can show in them)
    counts = {}
    for w in re.findall(r"[A-Za-z\u0400-\u04FF']{6,}", text):
        lw = w.lower()
        if lw not in EN_COMMON and lw not in RU_COMMON:
            counts[lw] = counts.get(lw, 0) + 1
    for w, n in counts.items():
        if n >= 2:
            found.append(["repeated word", w, n])
    order = {"name": 0, "time": 1, "date": 2, "number": 3, "address": 4, "repeated word": 5}
    return [tuple(f) for f in sorted(found, key=lambda f: order[f[0]])]


LEFTOVER_HINT = {"name": "a name or place", "time": "a time", "date": "a date", "number": "a number",
                 "address": "an address, link or handle", "repeated word": "a rare word used more than once"}


def diff_words(a, b):
    """[(op, text)] with op 'equal', 'insert' or 'delete', word by word, to show what a rewrite changed."""
    ta, tb = re.findall(r"\s+|\w+|[^\w\s]", a), re.findall(r"\s+|\w+|[^\w\s]", b)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(("equal", "".join(ta[i1:i2])))
        else:
            if i2 > i1:
                out.append(("delete", "".join(ta[i1:i2])))
            if j2 > j1:
                out.append(("insert", "".join(tb[j1:j2])))
    return out


# ------------------------------------------------------------------------------------------- settings
SETTING_KEYS = {"mode": ("translate", "rewrite"), "direction": DIRECTIONS, "strength": STRENGTHS,
                "auto_detect": (True, False), "clear_clipboard": (True, False)}
DEFAULTS = {"mode": "translate", "direction": "en-ru", "strength": "light", "auto_detect": True,
            "clear_clipboard": False}


def settings_path(home=None):
    return os.path.join(home or os.path.expanduser("~"), ".config", "prestium-translate", "settings.json")


def load_settings(path=None):
    s = dict(DEFAULTS)
    try:
        with open(path or settings_path()) as f:
            d = json.load(f)
        for k, allowed in SETTING_KEYS.items():
            if d.get(k) in allowed:
                s[k] = d[k]
    except (OSError, ValueError, AttributeError):
        pass
    return s


def save_settings(s, path=None):
    """Only the choices in SETTING_KEYS (never any text)."""
    path = path or settings_path()
    d = {k: s[k] for k in SETTING_KEYS if s.get(k) in SETTING_KEYS[k]}
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".new"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(d, f, sort_keys=True)
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------- command line
USAGE = ("usage: prestium-translate [--translate en-ru|ru-en|auto | --rewrite light|strong [--leftovers]]\n"
         "  with no option: the window. --translate and --rewrite read the text from stdin and print the result.")


def cli(argv, stdin=None, stdout=None, stderr=None, share=SHARE, sandbox=True):
    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    if len(argv) < 2 or argv[0] not in ("--translate", "--rewrite") \
            or (argv[0] == "--translate" and (argv[1] not in DIRECTIONS + ("auto",) or len(argv) != 2)) \
            or (argv[0] == "--rewrite" and (argv[1] not in STRENGTHS or argv[2:] not in ([], ["--leftovers"]))):
        print(USAGE, file=stderr)
        return 2
    text = stdin.read()
    engine = Engine(share, sandbox)
    try:
        if argv[0] == "--translate":
            d = detect_direction(text) if argv[1] == "auto" else argv[1]
            out = engine.translate(text, d)
        else:
            out = rewrite(text, argv[1], engine)
        stdout.write(out + ("\n" if out and not out.endswith("\n") else ""))
        if argv[2:] == ["--leftovers"]:
            for kind, s, n in leftovers(out):
                print("leftover: %s: %s%s" % (LEFTOVER_HINT[kind], s, " (%d times)" % n if n > 1 else ""), file=stderr)
        return 0
    except EngineError as e:
        print("prestium-translate: %s" % e, file=stderr)
        return 1
    finally:
        engine.stop()
