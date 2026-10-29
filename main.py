import os, re, json, time, base64, threading, requests
from datetime import date
from html import unescape
from urllib.parse import unquote
from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle, Rectangle, Ellipse
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

if platform == "android":
    from jnius import autoclass, PythonJavaClass, java_method
    from android import activity
    from android.runnable import run_on_ui_thread
    from android.permissions import request_permissions, check_permission, Permission
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    RecognizerIntent = autoclass("android.speech.RecognizerIntent")
    SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
    TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
    Locale = autoclass("java.util.Locale")

    class Listener(PythonJavaClass):
        __javainterfaces__ = ["android/speech/RecognitionListener"]
        __javacontext__ = "app"
        def __init__(self, on_text, on_err):
            super().__init__()
            self.on_text, self.on_err = on_text, on_err
        @java_method("(Landroid/os/Bundle;)V")
        def onReadyForSpeech(self, p): pass
        @java_method("()V")
        def onBeginningOfSpeech(self): pass
        @java_method("(F)V")
        def onRmsChanged(self, r): pass
        @java_method("([B)V")
        def onBufferReceived(self, b): pass
        @java_method("()V")
        def onEndOfSpeech(self): pass
        @java_method("(I)V")
        def onError(self, code): self.on_err(code)
        @java_method("(Landroid/os/Bundle;)V")
        def onResults(self, res):
            t = ""
            try:
                l = res.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                if l is not None and l.size() > 0:
                    t = str(l.get(0))
            except Exception:
                pass
            self.on_text(t)
        @java_method("(Landroid/os/Bundle;)V")
        def onPartialResults(self, p): pass
        @java_method("(ILandroid/os/Bundle;)V")
        def onEvent(self, t, p): pass

    class InitListener(PythonJavaClass):
        __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
        __javacontext__ = "app"
        def __init__(self, cb):
            super().__init__()
            self.cb = cb
        @java_method("(I)V")
        def onInit(self, status): self.cb(status)
else:
    def run_on_ui_thread(f): return f

BG = (.03, .045, .11, 1); SURF = (.055, .08, .17, 1); CARD = (.09, .125, .26, 1)
BLUE = (.18, .45, 1, 1); TEXT = (.92, .94, .98, 1); MUTE = (.56, .63, .82, 1)
URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5-5"
SPEECH_LANG = "hi-IN"
TTS_LANG = ("en", "IN")
WEB = True   # internet search band karna ho to False kar do
SYSTEM = ("Tum 'Namaste ToonSlee AI' ho, ek expert assistant. Jawab hamesha Roman script "
          "(English letters) mein Roman Urdu/Hindi mein do, kabhi Devanagari ya Urdu script nahi, "
          "kyunke app ka font unhe dikha nahi sakta. Agar sawal Devanagari ya Urdu script mein aaye "
          "(voice se), to pehli line 'Aapne kaha: ...' Roman mein likho, phir jawab do. Agar "
          "message ke saath internet search results diye hon, to unse jawab do aur source links batao. "
          "Files aur images ko dhyan se analyze karo.")
VOICE_NOTE = " Ye voice baat-cheet hai: jawab chhota rakho (2 se 4 vakya), bina list ya symbols ke."
TOOLS = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
IMG_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
CHIPS = [("Code", "Mujhe ek chhota Python code likh kar samjhao."),
         ("Research", "Aaj ki sabse badi khabrein search karke batao."),
         ("Likho", "Meri ek professional email likhne mein madad karo."),
         ("Samjhao", "Mujhe kisi mushkil topic ko aasan zaban mein samjhao.")]
ERR = {1: "Net slow hai", 2: "Net ki dikkat", 3: "Mic ki dikkat", 4: "Server ki dikkat",
       5: "Voice start nahi hui", 8: "Voice busy hai", 9: "Mic ki permission nahi mili",
       10: "Bahut zyada request", 11: "Server disconnect", 12: "Language support nahi",
       13: "Language ka data nahi hai"}


def web_search(q, n=5):
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": q}, timeout=15,
                      headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"})
    clean = lambda s: unescape(re.sub(r"<[^>]+>", "", s)).strip()
    out = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
                         r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.S):
        link, title, snip = m.groups()
        if "uddg=" in link:
            link = unquote(link.split("uddg=")[1].split("&")[0])
        out.append("%d. %s\n%s\n%s" % (len(out) + 1, clean(title), clean(snip), link))
        if len(out) >= n:
            break
    return "\n\n".join(out)


def gtex(top, bot, n=64):
    t = Texture.create(size=(1, n), colorfmt="rgb")
    buf = bytearray()
    for i in range(n):
        f = min(1.0, i / (n * 0.7))
        buf += bytes(int(bot[k] * 255 * (1 - f) + top[k] * 255 * f) for k in range(3))
    t.blit_buffer(bytes(buf), colorfmt="rgb", bufferfmt="ubyte")
    t.mag_filter = "linear"
    return t


def paint(w, col, rad=0):
    with w.canvas.before:
        Color(*col)
        r = RoundedRectangle(pos=w.pos, size=w.size, radius=[rad]) if rad else Rectangle(pos=w.pos, size=w.size)
    w.bind(pos=lambda *a: setattr(r, "pos", w.pos), size=lambda *a: setattr(r, "size", w.size))


def field(hint, val="", pw=False, h=46):
    return TextInput(text=val, hint_text=hint, password=pw, multiline=False, size_hint_y=None,
                     height=dp(h), background_normal="", background_active="", background_color=CARD,
                     foreground_color=TEXT, hint_text_color=MUTE, cursor_color=BLUE,
                     padding=[dp(12), dp(12)], font_size=sp(16))


class RBtn(Button):
    def __init__(self, bg=CARD, rad=14, **kw):
        super().__init__(background_normal="", background_down="", background_color=(0, 0, 0, 0),
                         color=TEXT, **kw)
        self.bg, self.rad = bg, rad
        self.bind(pos=self.draw, size=self.draw)

    def draw(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(self.rad)])


class CBtn(Button):
    def __init__(self, **kw):
        super().__init__(background_normal="", background_down="", background_color=(0, 0, 0, 0),
                         color=(1, 1, 1, 1), bold=True, **kw)
        self.bind(pos=self.draw, size=self.draw)

    def draw(self, *a):
        self.canvas.before.clear()
        d = min(self.size)
        with self.canvas.before:
            Color(*BLUE)
            Ellipse(pos=(self.center_x - d / 2, self.center_y - d / 2), size=(d, d))


class Orb(Widget):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self.d, size=self.d)

    def d(self, *a):
        self.canvas.clear()
        cx, cy = self.center
        r = min(self.size) / 2
        with self.canvas:
            for s, col in ((1.0, (.1, .3, .9, .12)), (.82, (.1, .35, .95, .25)),
                           (.64, (.12, .42, 1, .95)), (.5, (.28, .62, 1, 1))):
                Color(*col)
                Ellipse(pos=(cx - r * s, cy - r * s), size=(r * s * 2, r * s * 2))
            Color(.75, .9, 1, .5)
            Ellipse(pos=(cx - r * .3, cy + r * .02), size=(r * .55, r * .3))


class Bub(Label):
    def __init__(self, mine, **kw):
        super().__init__(size_hint=(.82 if mine else 1, None), height=dp(44), halign="left",
                         valign="middle", padding=(dp(14) if mine else dp(4), dp(10)),
                         font_size=sp(16), color=TEXT, **kw)
        self.mine = mine
        self.bind(width=self.tw, texture_size=self.th, pos=self.bg, size=self.bg)

    def tw(self, *a): self.text_size = (self.width - dp(28 if self.mine else 8), None)
    def th(self, *a): self.height = self.texture_size[1] + dp(20)

    def bg(self, *a):
        self.canvas.before.clear()
        if self.mine:
            with self.canvas.before:
                Color(*CARD)
                RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(18)])


class AI(App):
    def build(self):
        Window.clearcolor = BG
        Window.softinput_mode = "below_target"
        self.db = {"chats": [], "cur": None, "set": {"key": "", "name": "", "speak": False}}
        self.load()
        self.pending = []; self.busy = False; self.listening = False; self.handsfree = False
        self.speak_reply = False; self.misses = 0; self.poll_n = 0; self.pend_b = None
        self.act_row = None
        self.sr = self.listener = self.tts = self.init_l = None; self.tts_ok = False
        self.hf_btn = RBtn(text="Auto-sunna: OFF", size_hint_y=None, height=dp(48),
                           on_press=self.toggle_hf)
        root = BoxLayout(orientation="vertical")
        tex = gtex((.03, .045, .11), (.06, .22, .65))
        with root.canvas.before:
            Color(1, 1, 1, 1)
            bgr = Rectangle(texture=tex, pos=root.pos, size=root.size)
        root.bind(pos=lambda *a: setattr(bgr, "pos", root.pos),
                  size=lambda *a: setattr(bgr, "size", root.size))
        top = BoxLayout(size_hint_y=None, height=dp(60), padding=dp(10), spacing=dp(8))
        top.add_widget(RBtn(text="Menu", size_hint_x=None, width=dp(76), on_press=self.open_side))
        top.add_widget(Label(text="Namaste ToonSlee AI", bold=True, font_size=sp(18), color=TEXT))
        top.add_widget(RBtn(text="Naya", size_hint_x=None, width=dp(76), on_press=self.new_chat))
        self.scroll = ScrollView(bar_width=0)
        self.box = GridLayout(cols=1, size_hint_y=None, spacing=dp(10), padding=dp(12))
        self.box.bind(minimum_height=self.box.setter("height"))
        self.scroll.add_widget(self.box)
        self.fl = Label(text="", size_hint_y=None, height=0, color=MUTE, font_size=sp(13))
        outer = BoxLayout(size_hint_y=None, height=dp(76), padding=dp(10))
        pill = BoxLayout(spacing=dp(4), padding=[dp(6), dp(6)])
        paint(pill, CARD, dp(30))
        pill.add_widget(Button(text="+", size_hint_x=None, width=dp(40), font_size=sp(24),
                               background_normal="", background_color=(0, 0, 0, 0),
                               on_press=self.pick_file))
        self.inp = TextInput(hint_text="Message likho...", multiline=False, background_normal="",
                             background_active="", background_color=(0, 0, 0, 0),
                             foreground_color=TEXT, hint_text_color=MUTE, cursor_color=BLUE,
                             padding=[dp(6), dp(14)], font_size=sp(16))
        self.inp.bind(on_text_validate=self.send)
        pill.add_widget(self.inp)
        pill.add_widget(Button(text="Mic", size_hint_x=None, width=dp(50), color=MUTE,
                               background_normal="", background_color=(0, 0, 0, 0),
                               on_press=self.start_listen))
        pill.add_widget(CBtn(text="↑", font_size=sp(22), size_hint_x=None, width=dp(52),
                             on_press=self.send))
        outer.add_widget(pill)
        for w in (top, self.scroll, self.fl, outer):
            root.add_widget(w)
        self.render()
        if platform == "android":
            activity.bind(on_activity_result=self.on_result)
            Clock.schedule_once(lambda dt: self._init_tts(), 1)
        return root

    def on_pause(self): return True
    def on_resume(self): pass
    def on_stop(self): self.stop_all()

    # ---------- data ----------
    def path(self): return os.path.join(self.user_data_dir, "data.json")

    def load(self):
        try:
            with open(self.path()) as f:
                d = json.load(f)
            self.db["chats"] = d.get("chats", [])
            self.db["cur"] = d.get("cur")
            self.db["set"].update(d.get("set", {}))
        except Exception:
            pass

    def save(self):
        try:
            with open(self.path(), "w") as f:
                json.dump(self.db, f)
        except Exception:
            pass

    def chat(self):
        for c in self.db["chats"]:
            if c["id"] == self.db["cur"]:
                return c

    # ---------- UI ----------
    def down(self):
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.15)

    def note(self, t):
        def f(dt):
            l = Label(text=t, color=MUTE, font_size=sp(13), size_hint_y=None, halign="center")
            l.bind(width=lambda *a: setattr(l, "text_size", (l.width, None)),
                   texture_size=lambda *a: setattr(l, "height", l.texture_size[1] + dp(8)))
            self.box.add_widget(l)
            self.down()
        Clock.schedule_once(f)

    def add_bubble(self, text, mine, files=None):
        if files:
            text = "[" + ", ".join(files) + "]\n" + text
        b = Bub(mine, text=text)
        row = BoxLayout(size_hint_y=None, height=b.height)
        b.bind(height=row.setter("height"))
        if mine:
            row.add_widget(Widget(size_hint_x=.18))
        row.add_widget(b)
        self.box.add_widget(row)
        return b

    def add_actions(self, text):
        row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
        for t, f in (("Copy", lambda *a: (Clipboard.copy(text), self.note("Copy ho gaya."))),
                     ("Sunao", lambda *a: self.read_aloud(text)),
                     ("Phir se", self.regen),
                     ("Share", lambda *a: self.share(text))):
            row.add_widget(RBtn(text=t, bg=SURF, rad=12, font_size=sp(13), size_hint_x=None,
                                width=dp(74), on_press=f))
        row.add_widget(Widget())
        self.box.add_widget(row)
        self.act_row = row

    def read_aloud(self, text):
        try:
            if self.tts is not None and self.tts.isSpeaking():
                self.tts.stop(); return
        except Exception:
            pass
        self.speak(text)

    def share(self, text):
        try:
            i = Intent(Intent.ACTION_SEND)
            i.setType("text/plain")
            i.putExtra(Intent.EXTRA_TEXT, text)
            PythonActivity.mActivity.startActivity(Intent.createChooser(i, "Share"))
        except Exception as e:
            self.note("Share nahi hua: " + str(e))

    def regen(self, *a):
        c = self.chat()
        if self.busy or not c or not c["msgs"] or c["msgs"][-1]["r"] != "assistant":
            return
        c["msgs"].pop()
        self.save(); self.render()
        self.pend_b = self.add_bubble("...", False)
        self.busy = True
        self.speak_reply = False
        threading.Thread(target=self.ask, args=(False, []), daemon=True).start()

    def home(self):
        h = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(430), spacing=dp(14))
        h.add_widget(Widget(size_hint_y=None, height=dp(20)))
        h.add_widget(Orb(size_hint_y=None, height=dp(170)))
        l = Label(text="Namaste!\nHow can I help you today?", font_size=sp(21), color=TEXT,
                  halign="center", size_hint_y=None, height=dp(70))
        l.bind(size=lambda *a: setattr(l, "text_size", l.size))
        h.add_widget(l)
        g = GridLayout(cols=2, spacing=dp(10), size_hint_y=None, height=dp(110), padding=[dp(6), 0])
        for t, p in CHIPS:
            g.add_widget(RBtn(text=t, bg=CARD, rad=18, on_press=lambda b, p=p: self.submit(p)))
        h.add_widget(g)
        return h

    def render(self):
        self.box.clear_widgets()
        self.act_row = None
        c = self.chat()
        if not c or not c["msgs"]:
            self.box.add_widget(self.home())
            return
        for m in c["msgs"]:
            self.add_bubble(m.get("s", m["c"]), m["r"] == "user", m.get("f"))
        if c["msgs"][-1]["r"] == "assistant":
            self.add_actions(c["msgs"][-1]["c"])
        self.down()

    def new_chat(self, *a):
        self.stop_all()
        self.set_handsfree(False)
        self.db["cur"] = None
        self.pending = []; self.set_fl()
        self.save(); self.render()

    def set_fl(self):
        n = [x[0] for x in self.pending]
        self.fl.text = "Jude: " + ", ".join(n) if n else ""
        self.fl.height = dp(24) if n else 0

    def open_side(self, *a):
        mv = ModalView(size_hint=(.86, 1), pos_hint={"x": 0}, background="",
                       background_color=(0, 0, 0, 0), overlay_color=(0, 0, 0, .55))
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        paint(box, SURF)
        box.add_widget(RBtn(text="+ Naya chat", bg=BLUE, size_hint_y=None, height=dp(48),
                            on_press=lambda *a: (mv.dismiss(), self.new_chat())))
        q = field("Chats dhoondo")
        lst = GridLayout(cols=1, size_hint_y=None, spacing=dp(6))
        lst.bind(minimum_height=lst.setter("height"))
        sv = ScrollView()
        sv.add_widget(lst)

        def fill(*a):
            lst.clear_widgets()
            last = None
            for c in sorted(self.db["chats"], key=lambda x: -x["ts"]):
                if q.text.lower() not in c["title"].lower():
                    continue
                d = (date.today() - date.fromtimestamp(c["ts"])).days
                g = "Aaj" if d == 0 else "Kal" if d == 1 else "Pehle"
                if g != last:
                    lst.add_widget(Label(text=g, color=MUTE, size_hint_y=None, height=dp(26),
                                         font_size=sp(13)))
                    last = g
                row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
                row.add_widget(RBtn(text=c["title"][:26], on_press=lambda b, c=c: self.open_chat(c, mv)))
                row.add_widget(RBtn(text="X", size_hint_x=None, width=dp(44),
                                    on_press=lambda b, c=c: self.del_chat(c, fill)))
                lst.add_widget(row)
            if not lst.children:
                lst.add_widget(Label(text="Abhi koi chat nahi", color=MUTE, size_hint_y=None, height=dp(40)))
        q.bind(text=fill)
        fill()
        box.add_widget(q)
        box.add_widget(sv)
        if self.hf_btn.parent:
            self.hf_btn.parent.remove_widget(self.hf_btn)
        box.add_widget(self.hf_btn)
        box.add_widget(RBtn(text="Settings", size_hint_y=None, height=dp(48),
                            on_press=lambda *a: (mv.dismiss(), self.open_set())))
        mv.add_widget(box)
        mv.open()

    def open_chat(self, c, mv):
        self.db["cur"] = c["id"]
        self.save(); mv.dismiss(); self.render()

    def del_chat(self, c, refill):
        self.db["chats"].remove(c)
        if self.db["cur"] == c["id"]:
            self.db["cur"] = None
            self.render()
        self.save(); refill()

    def open_set(self, *a):
        s = self.db["set"]
        mv = ModalView(size_hint=(.92, .8), background="", background_color=(0, 0, 0, 0),
                       overlay_color=(0, 0, 0, .6))
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        paint(box, SURF, dp(18))
        box.add_widget(Label(text="Settings", bold=True, font_size=sp(20), color=TEXT,
                             size_hint_y=None, height=dp(36)))
        key = field("Anthropic API key (sirf is phone mein)", s["key"], True)
        name = field("Aapka naam", s["name"])
        tg = RBtn(text="", size_hint_y=None, height=dp(46))

        def lab(): tg.text = "Jawab bolkar sunao: " + ("ON" if s.get("speak") else "OFF")

        def flip(*a):
            s["speak"] = not s.get("speak")
            lab(); self.save()
        tg.bind(on_press=flip)
        lab()
        clr = RBtn(text="Saari history hatao", size_hint_y=None, height=dp(46))

        def wipe(*a):
            if clr.text.startswith("Pakka"):
                self.db["chats"] = []; self.db["cur"] = None
                self.save(); self.render(); clr.text = "Saari history hatao"
            else:
                clr.text = "Pakka? Dobara dabao"
        clr.bind(on_press=wipe)

        def ok(*a):
            s["key"] = key.text.strip(); s["name"] = name.text.strip(); self.save()
        mv.bind(on_dismiss=ok)
        for w in (key, name, tg, clr,
                  RBtn(text="Key hatao", size_hint_y=None, height=dp(46),
                       on_press=lambda *a: setattr(key, "text", "")),
                  Widget(),
                  RBtn(text="Save", bg=BLUE, size_hint_y=None, height=dp(50),
                       on_press=lambda *a: mv.dismiss())):
            box.add_widget(w)
        mv.add_widget(box)
        mv.open()

    # ---------- TTS ----------
    @run_on_ui_thread
    def _init_tts(self):
        try:
            self.init_l = InitListener(self.tts_ready)
            self.tts = TextToSpeech(PythonActivity.mActivity, self.init_l)
        except Exception as e:
            self.note("Awaaz start nahi hui: " + str(e))

    def tts_ready(self, status):
        if status != 0:
            self.note("Bolne wali awaaz start nahi hui.")
            return
        try:
            self.tts.setLanguage(Locale(TTS_LANG[0], TTS_LANG[1]))
            self.tts_ok = True
        except Exception as e:
            self.note("Awaaz error: " + str(e))

    def speak(self, text):
        if not self.tts_ok:
            return
        try:
            self.tts.speak(re.sub(r"[*#_`>|]", "", text)[:3500], 0, None, "ai")
        except Exception as e:
            self.note("Bolne mein error: " + str(e))

    def stop_speaking(self):
        try:
            if self.tts is not None:
                self.tts.stop()
        except Exception:
            pass

    # ---------- Voice input ----------
    def set_handsfree(self, on):
        self.handsfree = on
        self.misses = 0
        self.hf_btn.text = "Auto-sunna: ON" if on else "Auto-sunna: OFF"

    def toggle_hf(self, *a):
        if self.handsfree:
            self.set_handsfree(False); self.stop_all(); self.note("Auto-sunna band.")
        else:
            self.set_handsfree(True)
            Clock.schedule_once(lambda dt: self.start_listen(), 0.4)

    def perm_done(self, perms, grants):
        if grants and all(grants):
            Clock.schedule_once(lambda dt: self.start_listen(), 0)

    def start_listen(self, *a):
        if platform != "android":
            self.note("Voice sirf phone par chalti hai."); return
        if self.busy:
            self.note("Jawab aa raha hai, thoda ruko."); return
        if self.listening:
            return
        if not check_permission(Permission.RECORD_AUDIO):
            request_permissions([Permission.RECORD_AUDIO], self.perm_done)
            self.note("Mic ki permission allow karo."); return
        self.stop_speaking()
        self.listening = True
        self.note("(Sun raha hai... bolo)")
        self._listen_ui()

    @run_on_ui_thread
    def _listen_ui(self):
        try:
            if self.sr is not None:
                try: self.sr.destroy()
                except Exception: pass
            self.sr = SpeechRecognizer.createSpeechRecognizer(PythonActivity.mActivity)
            self.listener = Listener(self.got_text, self.got_error)
            self.sr.setRecognitionListener(self.listener)
            i = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, SPEECH_LANG)
            self.sr.startListening(i)
        except Exception as e:
            self.listening = False
            self.note("Voice start nahi hui: " + str(e))

    @run_on_ui_thread
    def _cancel_ui(self):
        try:
            if self.sr is not None:
                self.sr.cancel()
        except Exception:
            pass

    def stop_all(self):
        self.stop_speaking()
        if platform == "android" and self.listening:
            self._cancel_ui()
        self.listening = False

    def got_text(self, t): Clock.schedule_once(lambda dt: self.handle_text(t))
    def got_error(self, c): Clock.schedule_once(lambda dt: self.handle_error(c))

    def handle_text(self, text):
        self.listening = False
        text = text.strip()
        if not text:
            self.handle_error(7); return
        self.misses = 0
        self.submit(text, text if text.isascii() else "(voice message)", voice=True)

    def handle_error(self, code):
        self.listening = False
        if code in (6, 7):
            if self.handsfree and self.misses < 2:
                self.misses += 1
                Clock.schedule_once(lambda dt: self.start_listen(), 0.6); return
            self.set_handsfree(False)
            self.note("Kuch sunai nahi diya. Dobara Mic dabao."); return
        self.set_handsfree(False)
        self.note("Voice error (%s): %s" % (code, ERR.get(code, "pata nahi")))

    def after_answer(self, out):
        self.speak(out)
        if self.handsfree:
            self.poll_n = 0
            Clock.unschedule(self.wait_end)
            Clock.schedule_interval(self.wait_end, 0.5)

    def wait_end(self, dt):
        if not self.handsfree:
            return False
        self.poll_n += 1
        if self.poll_n < 3:
            return True
        try:
            if self.tts is not None and self.tts.isSpeaking() and self.poll_n < 240:
                return True
        except Exception:
            pass
        self.start_listen()
        return False

    # ---------- Files ----------
    def pick_file(self, *a):
        if platform != "android":
            self.note("File picker sirf phone par chalta hai."); return
        try:
            i = Intent(Intent.ACTION_GET_CONTENT)
            i.setType("*/*")
            i.addCategory(Intent.CATEGORY_OPENABLE)
            PythonActivity.mActivity.startActivityForResult(i, 1001)
        except Exception as e:
            self.note("Error: " + str(e))

    def on_result(self, code, res, intent):
        if code != 1001 or res != -1 or intent is None:
            return
        try:
            self.load_uri(intent.getData())
        except Exception as e:
            self.note("Error: " + str(e))

    def load_uri(self, uri):
        rs = PythonActivity.mActivity.getContentResolver()
        mime = rs.getType(uri) or ""
        name = "file"
        try:
            c = rs.query(uri, None, None, None, None)
            if c is not None:
                if c.moveToFirst():
                    i = c.getColumnIndex("_display_name")
                    if i >= 0:
                        name = c.getString(i) or name
                c.close()
        except Exception:
            pass
        pfd = rs.openFileDescriptor(uri, "r")
        with os.fdopen(pfd.detachFd(), "rb") as f:
            data = f.read()
        mb = len(data) / 1048576.0
        if len(self.pending) >= 3:
            self.note("3 se zyada file nahi jud sakti."); return
        if mime in IMG_TYPES:
            if mb > 3.5:
                self.note("%s badi hai (%.1f MB). 3.5 MB tak chalti hai." % (name, mb)); return
            blk = {"type": "image", "source": {"type": "base64", "media_type": mime,
                                               "data": base64.b64encode(data).decode()}}
        elif mime == "application/pdf":
            if mb > 15:
                self.note("PDF 15 MB tak chalti hai."); return
            blk = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                  "data": base64.b64encode(data).decode()}}
        else:
            try:
                txt = data.decode("utf-8")
            except Exception:
                self.note("%s ka type support nahi. Image, PDF ya text/CSV chuno." % name); return
            blk = {"type": "text", "text": "File: " + name + "\n\n" + txt[:60000]}
        self.pending.append((name, blk))
        Clock.schedule_once(lambda dt: self.set_fl())

    # ---------- Chat ----------
    def send(self, *a):
        self.submit(self.inp.text.strip())

    def submit(self, q, shown=None, voice=False):
        if self.busy:
            self.note("Pehla jawab aa raha hai, thoda ruko."); return
        if not q and not self.pending:
            return
        s = self.db["set"]
        if not s["key"]:
            self.note("Pehle Menu > Settings mein API key daalo."); return
        c = self.chat()
        if not c:
            c = {"id": str(time.time()), "title": (q or "File")[:36], "ts": time.time(), "msgs": []}
            self.db["chats"].insert(0, c)
            self.db["cur"] = c["id"]
            self.box.clear_widgets()
        if self.act_row is not None and self.act_row.parent:
            self.box.remove_widget(self.act_row)
        self.act_row = None
        blocks = [b for n, b in self.pending]
        names = [n for n, b in self.pending]
        self.pending = []
        self.set_fl()
        text = q or "Is file ka detailed analysis karo."
        disp = shown if shown is not None else text
        c["msgs"].append({"r": "user", "c": text, "s": disp, "f": names})
        c["ts"] = time.time()
        self.save()
        self.inp.text = ""
        self.add_bubble(disp, True, names)
        self.pend_b = self.add_bubble("...", False)
        self.down()
        self.busy = True
        self.speak_reply = voice or bool(s.get("speak"))
        threading.Thread(target=self.ask, args=(voice, blocks), daemon=True).start()

    def ask(self, voice, blocks):
        out, err = "", None
        try:
            c = self.chat()
            msgs = [{"role": m["r"], "content": m["c"]} for m in c["msgs"]]
            q = msgs[-1]["content"]
            if WEB and len(q.split()) >= 3:
                self.note("(internet par dhoondh raha hai...)")
                try:
                    res = web_search(q)
                except Exception:
                    res = ""
                if res:
                    msgs[-1]["content"] = ("Internet search results:\n" + res +
                                           "\n\nIn results se jawab do aur source links batao.\n\nSawal: " + q)
            if blocks:
                msgs[-1]["content"] = blocks + [{"type": "text", "text": msgs[-1]["content"]}]
            n = self.db["set"].get("name")
            system = SYSTEM + (" User ka naam " + n + " hai." if n else "") + (VOICE_NOTE if voice else "")
            body = {"model": MODEL, "max_tokens": 3000, "system": system, "messages": msgs}
            if not WEB:
                body["tools"] = TOOLS
            r = requests.post(URL, timeout=120, json=body, headers={
                "x-api-key": self.db["set"]["key"], "anthropic-version": "2023-06-01",
                "content-type": "application/json"})
            d = r.json()
            if "content" not in d:
                err = d.get("error", {}).get("message", str(d))
            else:
                out = "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text")
        except Exception as e:
            err = str(e)
        Clock.schedule_once(lambda dt: self.done(out.strip(), err))

    def done(self, out, err):
        self.busy = False
        c = self.chat()
        if err or not out:
            if c and c["msgs"]:
                c["msgs"].pop()
            self.save()
            if self.pend_b is not None:
                self.pend_b.text = "Error: " + (err or "jawab khali aaya")
            self.set_handsfree(False)
            return
        c["msgs"].append({"r": "assistant", "c": out})
        c["ts"] = time.time()
        self.save()
        self.pend_b.text = out
        self.add_actions(out)
        self.down()
        if self.speak_reply:
            self.after_answer(out)


AI().run()
