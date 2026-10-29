import os, re, json, time, base64, threading, requests
from datetime import date
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle, Rectangle
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

BG = (.043, .051, .071, 1); SURF = (.07, .082, .11, 1); CARD = (.11, .125, .165, 1)
BLUE = (.23, .51, .96, 1); TEXT = (.91, .92, .95, 1); MUTE = (.55, .58, .65, 1)
URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5-5"
SPEECH_LANG = "hi-IN"
TTS_LANG = ("en", "IN")
SYSTEM = ("Tum 'Namaste ToonSlee AI' ho, ek expert assistant. Jawab hamesha Roman script "
          "(English letters) mein Roman Urdu/Hindi mein do, kabhi Devanagari ya Urdu script nahi, "
          "kyunke app ka font unhe dikha nahi sakta. Agar sawal Devanagari ya Urdu script mein aaye "
          "(voice se), to pehli line 'Aapne kaha: ...' Roman mein likho, phir jawab do. Latest "
          "jankari ke liye web_search use karo. Files aur images ko dhyan se analyze karo.")
VOICE_NOTE = " Ye voice baat-cheet hai: jawab chhota rakho (2 se 4 vakya), bina list ya symbols ke."
TOOLS = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
IMG_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
ERR = {1: "Net slow hai", 2: "Net ki dikkat", 3: "Mic ki dikkat", 4: "Server ki dikkat",
       5: "Voice start nahi hui", 8: "Voice busy hai", 9: "Mic ki permission nahi mili",
       10: "Bahut zyada request", 11: "Server disconnect", 12: "Language support nahi",
       13: "Language ka data nahi hai"}


def paint(w, col):
    with w.canvas.before:
        Color(*col)
        r = Rectangle(pos=w.pos, size=w.size)
    w.bind(pos=lambda *a: setattr(r, "pos", w.pos), size=lambda *a: setattr(r, "size", w.size))


def field(hint, val="", pw=False, h=46):
    return TextInput(text=val, hint_text=hint, password=pw, multiline=False, size_hint_y=None,
                     height=dp(h), background_normal="", background_active="", background_color=CARD,
                     foreground_color=TEXT, hint_text_color=MUTE, cursor_color=BLUE,
                     padding=[dp(12), dp(12)], font_size=sp(16))


class RBtn(Button):
    def __init__(self, bg=CARD, **kw):
        super().__init__(background_normal="", background_down="", background_color=(0, 0, 0, 0),
                         color=TEXT, **kw)
        self.bg = bg
        self.bind(pos=self.draw, size=self.draw)

    def draw(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])


class Bub(Label):
    def __init__(self, mine, **kw):
        super().__init__(size_hint=(.85, None), height=dp(44), halign="left", valign="middle",
                         padding=(dp(12), dp(10)), font_size=sp(16),
                         color=(1, 1, 1, 1) if mine else TEXT, **kw)
        self.mine = mine
        self.bind(width=self.tw, texture_size=self.th, pos=self.bg, size=self.bg)

    def tw(self, *a): self.text_size = (self.width - dp(24), None)
    def th(self, *a): self.height = self.texture_size[1] + dp(20)

    def bg(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*(BLUE if self.mine else CARD))
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(16)])


class AI(App):
    def build(self):
        Window.clearcolor = BG
        self.db = {"chats": [], "cur": None, "set": {"key": "", "name": "", "speak": False}}
        self.load()
        self.pending = []; self.busy = False; self.listening = False; self.handsfree = False
        self.speak_reply = False; self.misses = 0; self.poll_n = 0; self.pend_b = None
        self.sr = self.listener = self.tts = self.init_l = None; self.tts_ok = False
        self.hf_btn = RBtn(text="Auto-sunna: OFF", size_hint_y=None, height=dp(48),
                           on_press=self.toggle_hf)
        root = BoxLayout(orientation="vertical")
        top = BoxLayout(size_hint_y=None, height=dp(56), padding=dp(8), spacing=dp(8))
        paint(top, SURF)
        top.add_widget(RBtn(text="Menu", size_hint_x=None, width=dp(72), on_press=self.open_side))
        top.add_widget(Label(text="Namaste ToonSlee AI", bold=True, font_size=sp(18), color=TEXT))
        top.add_widget(RBtn(text="Naya", bg=BLUE, size_hint_x=None, width=dp(72), on_press=self.new_chat))
        self.scroll = ScrollView()
        self.box = GridLayout(cols=1, size_hint_y=None, spacing=dp(10), padding=dp(10))
        self.box.bind(minimum_height=self.box.setter("height"))
        self.scroll.add_widget(self.box)
        self.fl = Label(text="", size_hint_y=None, height=0, color=MUTE, font_size=sp(13))
        bar = BoxLayout(size_hint_y=None, height=dp(64), padding=dp(8), spacing=dp(6))
        paint(bar, SURF)
        bar.add_widget(RBtn(text="+", size_hint_x=None, width=dp(48), on_press=self.pick_file))
        self.inp = field("Message likho...", h=48)
        self.inp.bind(on_text_validate=self.send)
        bar.add_widget(self.inp)
        bar.add_widget(RBtn(text="Mic", size_hint_x=None, width=dp(56), on_press=self.start_listen))
        bar.add_widget(RBtn(text="Bhejo", bg=BLUE, size_hint_x=None, width=dp(72), on_press=self.send))
        for w in (top, self.scroll, self.fl, bar):
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
        gap = Widget(size_hint_x=.15)
        for w in ((gap, b) if mine else (b, gap)):
            row.add_widget(w)
        self.box.add_widget(row)
        return b

    def render(self):
        self.box.clear_widgets()
        c = self.chat()
        if not c or not c["msgs"]:
            w = Label(text="Namaste!\nHow can I help you today?", font_size=sp(22), color=TEXT,
                      size_hint_y=None, height=dp(260), halign="center")
            w.bind(size=lambda *a: setattr(w, "text_size", w.size))
            self.box.add_widget(w)
            return
        for m in c["msgs"]:
            self.add_bubble(m.get("s", m["c"]), m["r"] == "user", m.get("f"))
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
                    h = Label(text=g, color=MUTE, size_hint_y=None, height=dp(26), font_size=sp(13))
                    lst.add_widget(h)
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
        paint(box, SURF)
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
            if blocks:
                msgs[-1]["content"] = blocks + [{"type": "text", "text": msgs[-1]["content"]}]
            n = self.db["set"].get("name")
            system = SYSTEM + (" User ka naam " + n + " hai." if n else "") + (VOICE_NOTE if voice else "")
            for _ in range(4):
                r = requests.post(URL, timeout=120, headers={
                    "x-api-key": self.db["set"]["key"], "anthropic-version": "2023-06-01",
                    "content-type": "application/json"},
                    json={"model": MODEL, "max_tokens": 3000, "system": system,
                          "tools": TOOLS, "messages": msgs})
                d = r.json()
                if "content" not in d:
                    err = d.get("error", {}).get("message", str(d)); break
                out += "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text")
                if d.get("stop_reason") == "pause_turn":
                    msgs.append({"role": "assistant", "content": d["content"]}); continue
                break
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
        self.down()
        if self.speak_reply:
            self.after_answer(out)


AI().run()
