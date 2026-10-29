import os, re, base64, threading, requests
from kivy.app import App
from kivy.clock import Clock
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button

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
            self.on_text = on_text
            self.on_err = on_err

        @java_method("(Landroid/os/Bundle;)V")
        def onReadyForSpeech(self, params):
            pass

        @java_method("()V")
        def onBeginningOfSpeech(self):
            pass

        @java_method("(F)V")
        def onRmsChanged(self, rms):
            pass

        @java_method("([B)V")
        def onBufferReceived(self, buf):
            pass

        @java_method("()V")
        def onEndOfSpeech(self):
            pass

        @java_method("(I)V")
        def onError(self, code):
            self.on_err(code)

        @java_method("(Landroid/os/Bundle;)V")
        def onResults(self, results):
            text = ""
            try:
                lst = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                if lst is not None and lst.size() > 0:
                    text = str(lst.get(0))
            except Exception:
                pass
            self.on_text(text)

        @java_method("(Landroid/os/Bundle;)V")
        def onPartialResults(self, partial):
            pass

        @java_method("(ILandroid/os/Bundle;)V")
        def onEvent(self, etype, params):
            pass

    class InitListener(PythonJavaClass):
        __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
        __javacontext__ = "app"

        def __init__(self, cb):
            super().__init__()
            self.cb = cb

        @java_method("(I)V")
        def onInit(self, status):
            self.cb(status)
else:
    def run_on_ui_thread(f):
        return f

URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5-5"
SPEECH_LANG = "hi-IN"        # English bolna ho to "en-IN"
TTS_LANG = ("en", "IN")      # awaaz kaisi lage: ("en","IN") ya ("hi","IN") try karo
SYSTEM = ("Tum ek expert AI assistant ho. Jawab hamesha Roman script (English letters) "
          "mein Roman Urdu/Hindi mein do, kabhi Devanagari ya Urdu script nahi, kyunke "
          "app ka font unhe dikha nahi sakta. Agar sawal Devanagari ya Urdu script mein "
          "aaye (voice se), to jawab ki pehli line 'Aapne kaha: ...' likho jisme sawal "
          "Roman mein ho, phir jawab do. Latest ya current jankari ke liye web_search "
          "use karo. Files aur images ko dhyan se analyze karo.")
VOICE_NOTE = (" Ye voice baat-cheet hai: jawab chhota rakho (2 se 4 vakya), bina list, "
              "bina symbols ke, jaise bol kar baat karte hain.")
TOOLS = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
IMG_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
ERR = {1: "Net slow hai", 2: "Net ki dikkat", 3: "Mic ki dikkat",
       4: "Server ki dikkat", 5: "Voice start nahi hui", 8: "Voice abhi busy hai",
       9: "Mic ki permission nahi mili", 10: "Bahut zyada request",
       11: "Server disconnect ho gaya",
       12: "Ye language support nahi (SPEECH_LANG badal ke dekho)",
       13: "Is language ka data phone mein nahi hai"}


class AI(App):
    def key_path(self):
        return os.path.join(self.user_data_dir, "key.txt")

    def build(self):
        self.history = []
        self.pending = []
        self.busy = False
        self.listening = False
        self.handsfree = False
        self.speak_reply = False
        self.misses = 0
        self.poll_n = 0
        self.sr = None
        self.listener = None
        self.tts = None
        self.init_l = None
        self.tts_ok = False

        root = BoxLayout(orientation="vertical", padding=6, spacing=6)
        krow = BoxLayout(size_hint_y=None, height=110, spacing=6)
        self.key = TextInput(hint_text="API key (sk-ant-...)", password=True,
                             multiline=False)
        try:
            with open(self.key_path()) as f:
                self.key.text = f.read().strip()
        except Exception:
            pass
        krow.add_widget(self.key)
        krow.add_widget(Button(text="Key hatao", size_hint_x=0.3,
                               on_press=self.clear_key))
        self.log = TextInput(readonly=True, text="AI ready.\n")
        brow = BoxLayout(size_hint_y=None, height=110, spacing=6)
        brow.add_widget(Button(text="File", on_press=self.pick_file))
        brow.add_widget(Button(text="Bolo", on_press=self.start_listen))
        self.hf_btn = Button(text="Auto-sunna: OFF", on_press=self.toggle_hf)
        brow.add_widget(self.hf_btn)
        brow.add_widget(Button(text="Naya chat", on_press=self.new_chat))
        row = BoxLayout(size_hint_y=None, height=130, spacing=6)
        self.inp = TextInput(hint_text="Sawal likho", multiline=False,
                             on_text_validate=self.send)
        row.add_widget(self.inp)
        row.add_widget(Button(text="Bhejo", size_hint_x=0.3, on_press=self.send))
        for w in (krow, self.log, brow, row):
            root.add_widget(w)
        if platform == "android":
            activity.bind(on_activity_result=self.on_result)
            Clock.schedule_once(lambda dt: self._init_tts(), 1)
        return root

    def on_pause(self):
        return True

    def on_resume(self):
        pass

    def on_stop(self):
        self.stop_all()

    def show(self, text):
        Clock.schedule_once(lambda dt: setattr(self.log, "text", self.log.text + text))

    def save_key(self):
        k = self.key.text.strip()
        if k:
            try:
                with open(self.key_path(), "w") as f:
                    f.write(k)
            except Exception:
                pass

    def clear_key(self, *a):
        try:
            os.remove(self.key_path())
        except Exception:
            pass
        self.key.text = ""
        self.show("\nKey hata di gayi.\n")

    def new_chat(self, *a):
        self.stop_all()
        self.set_handsfree(False)
        self.history = []
        self.pending = []
        self.log.text = "Naya chat shuru.\n"

    # ---------- Bolne wali awaaz (TTS) ----------
    @run_on_ui_thread
    def _init_tts(self):
        try:
            self.init_l = InitListener(self.tts_ready)
            self.tts = TextToSpeech(PythonActivity.mActivity, self.init_l)
        except Exception as e:
            self.show("\nBolne wali awaaz start nahi hui: " + str(e) + "\n")

    def tts_ready(self, status):
        if status != 0:
            self.show("\nBolne wali awaaz start nahi hui.\n")
            return
        try:
            r = self.tts.setLanguage(Locale(TTS_LANG[0], TTS_LANG[1]))
            self.tts_ok = True
            if r < 0:
                self.show("\n(Is awaaz ki language phone mein nahi hai, "
                          "default awaaz chalegi.)\n")
        except Exception as e:
            self.show("\nAwaaz error: " + str(e) + "\n")

    def speak(self, text):
        if not self.tts_ok:
            self.show("(Awaaz abhi ready nahi hai.)\n")
            return
        t = re.sub(r"[*#_`>|]", "", text)[:3500]
        try:
            self.tts.speak(t, 0, None, "ai")
        except Exception as e:
            self.show("\nBolne mein error: " + str(e) + "\n")

    def stop_speaking(self):
        try:
            if self.tts is not None:
                self.tts.stop()
        except Exception:
            pass

    # ---------- Sunna (voice input) ----------
    def set_handsfree(self, on):
        self.handsfree = on
        self.misses = 0
        self.hf_btn.text = "Auto-sunna: ON" if on else "Auto-sunna: OFF"

    def toggle_hf(self, *a):
        if self.handsfree:
            self.set_handsfree(False)
            self.stop_all()
            self.show("\nAuto-sunna band.\n")
        else:
            self.set_handsfree(True)
            self.start_listen()

    def perm_done(self, perms, grants):
        if grants and all(grants):
            Clock.schedule_once(lambda dt: self.start_listen(), 0)

    def start_listen(self, *a):
        if platform != "android":
            self.show("\nVoice sirf phone par chalti hai.\n")
            return
        if self.busy:
            self.show("\n(Jawab aa raha hai, thoda ruko.)\n")
            return
        if self.listening:
            return
        if not check_permission(Permission.RECORD_AUDIO):
            request_permissions([Permission.RECORD_AUDIO], self.perm_done)
            self.show("\nMic ki permission allow karo.\n")
            return
        self.stop_speaking()
        self.listening = True
        self.show("\n(Sun raha hai... bolo)\n")
        self._listen_ui()

    @run_on_ui_thread
    def _listen_ui(self):
        try:
            if self.sr is not None:
                try:
                    self.sr.destroy()
                except Exception:
                    pass
            self.sr = SpeechRecognizer.createSpeechRecognizer(PythonActivity.mActivity)
            self.listener = Listener(self.got_text, self.got_error)
            self.sr.setRecognitionListener(self.listener)
            i = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                       RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, SPEECH_LANG)
            self.sr.startListening(i)
        except Exception as e:
            self.listening = False
            self.show("\nVoice start nahi hui: " + str(e) + "\n")

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

    def got_text(self, text):
        Clock.schedule_once(lambda dt: self.handle_text(text))

    def got_error(self, code):
        Clock.schedule_once(lambda dt: self.handle_error(code))

    def handle_text(self, text):
        self.listening = False
        text = text.strip()
        if not text:
            self.handle_error(7)
            return
        self.misses = 0
        shown = text if text.isascii() else "(voice message)"
        self.submit(text, shown, voice=True)

    def handle_error(self, code):
        self.listening = False
        if code in (6, 7):
            if self.handsfree and self.misses < 2:
                self.misses += 1
                Clock.schedule_once(lambda dt: self.start_listen(), 0.6)
                return
            self.set_handsfree(False)
            self.show("\nKuch sunai nahi diya. Dobara Bolo dabao.\n")
            return
        self.set_handsfree(False)
        self.show("\nVoice error (%s): %s\n" % (code, ERR.get(code, "pata nahi")))

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

    # ---------- File ----------
    def pick_file(self, *a):
        if platform != "android":
            self.show("\nFile picker sirf phone par chalta hai.\n")
            return
        try:
            i = Intent(Intent.ACTION_GET_CONTENT)
            i.setType("*/*")
            i.addCategory(Intent.CATEGORY_OPENABLE)
            PythonActivity.mActivity.startActivityForResult(i, 1001)
        except Exception as e:
            self.show("\nError: " + str(e) + "\n")

    def on_result(self, code, res, intent):
        if code != 1001 or res != -1 or intent is None:
            return
        try:
            self.load_uri(intent.getData())
        except Exception as e:
            self.show("\nError: " + str(e) + "\n")

    def load_uri(self, uri):
        resolver = PythonActivity.mActivity.getContentResolver()
        mime = resolver.getType(uri) or ""
        name = "file"
        try:
            c = resolver.query(uri, None, None, None, None)
            if c is not None:
                if c.moveToFirst():
                    idx = c.getColumnIndex("_display_name")
                    if idx >= 0:
                        name = c.getString(idx) or name
                c.close()
        except Exception:
            pass
        pfd = resolver.openFileDescriptor(uri, "r")
        with os.fdopen(pfd.detachFd(), "rb") as f:
            data = f.read()
        mb = len(data) / 1048576.0
        if len(self.pending) >= 3:
            self.show("\nEk baar mein 3 se zyada file nahi jud sakti. Pehle Bhejo dabao.\n")
            return
        if mime in IMG_TYPES:
            if mb > 3.5:
                self.show("\n%s bahut badi hai (%.1f MB). 3.5 MB se chhoti image "
                          "chuno, jaise screenshot.\n" % (name, mb))
                return
            block = {"type": "image", "source": {
                "type": "base64", "media_type": mime,
                "data": base64.b64encode(data).decode()}}
        elif mime == "application/pdf":
            if mb > 15:
                self.show("\nPDF bahut badi hai (%.1f MB). 15 MB se chhoti chuno.\n" % mb)
                return
            block = {"type": "document", "source": {
                "type": "base64", "media_type": "application/pdf",
                "data": base64.b64encode(data).decode()}}
        else:
            try:
                txt = data.decode("utf-8")
            except Exception:
                self.show("\n%s ka type support nahi hai. JPG/PNG image, PDF, "
                          "ya text/CSV file chuno.\n" % name)
                return
            block = {"type": "text", "text": "File: " + name + "\n\n" + txt[:60000]}
        self.pending.append(block)
        self.show("\nFile jud gayi: %s. Ab sawal likho aur Bhejo dabao.\n" % name)

    # ---------- Chat ----------
    def send(self, *a):
        self.submit(self.inp.text.strip())

    def submit(self, q, shown=None, voice=False):
        if self.busy:
            self.show("\n(Pehla jawab abhi aa raha hai, thoda ruko.)\n")
            return
        if not q and not self.pending:
            return
        if not self.key.text.strip():
            self.show("\nPehle upar API key daalo.\n")
            return
        self.save_key()
        self.inp.text = ""
        self.show("\nAap: " + (shown if shown is not None else q) + "\n")
        blocks = self.pending + [{"type": "text",
                                  "text": q or "Is file ka detailed analysis karo."}]
        self.pending = []
        self.history.append({"role": "user", "content": blocks})
        self.busy = True
        self.speak_reply = voice
        self.show("(soch raha hai...)\n")
        threading.Thread(target=self.ask, args=(voice,), daemon=True).start()

    def ask(self, voice):
        try:
            msgs = list(self.history)
            system = SYSTEM + (VOICE_NOTE if voice else "")
            out = ""
            for _ in range(4):
                r = requests.post(URL, timeout=120, headers={
                    "x-api-key": self.key.text.strip(),
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"},
                    json={"model": MODEL, "max_tokens": 3000, "system": system,
                          "tools": TOOLS, "messages": msgs})
                data = r.json()
                if "content" not in data:
                    err = data.get("error", {}).get("message", str(data))
                    self.history.pop()
                    self.show("Error: " + err + "\n")
                    Clock.schedule_once(lambda dt: self.set_handsfree(False))
                    return
                out += "".join(b.get("text", "") for b in data["content"]
                               if b.get("type") == "text")
                if data.get("stop_reason") == "pause_turn":
                    msgs.append({"role": "assistant", "content": data["content"]})
                    continue
                break
            out = out.strip() or "(Jawab khali aaya)"
            self.history.append({"role": "assistant", "content": out})
            self.show("AI: " + out + "\n")
            if voice:
                Clock.schedule_once(lambda dt, o=out: self.after_answer(o))
        except Exception as e:
            if self.history and self.history[-1]["role"] == "user":
                self.history.pop()
            self.show("Error: " + str(e) + "\n")
            Clock.schedule_once(lambda dt: self.set_handsfree(False))
        finally:
            self.busy = False


AI().run()
