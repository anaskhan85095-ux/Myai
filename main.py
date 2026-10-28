import os, base64, threading, requests
from kivy.app import App
from kivy.clock import Clock
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button

if platform == "android":
    from jnius import autoclass
    from android import activity
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    RecognizerIntent = autoclass("android.speech.RecognizerIntent")

URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5-5"
SPEECH_LANG = "hi-IN"  # English bolna ho to "en-IN" likho
SYSTEM = ("Tum ek expert AI assistant ho. Jawab hamesha Roman script (English letters) "
          "mein Roman Urdu/Hindi mein do, kabhi Devanagari ya Urdu script nahi, kyunke "
          "app ka font unhe dikha nahi sakta. Agar sawal Devanagari ya Urdu script mein "
          "aaye (voice se), to jawab ki pehli line 'Aapne kaha: ...' likho jisme sawal "
          "Roman mein ho, phir jawab do. Latest ya current jankari ke liye web_search "
          "use karo. Files aur images ko dhyan se analyze karo.")
TOOLS = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
IMG_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")

class AI(App):
    def key_path(self):
        return os.path.join(self.user_data_dir, "key.txt")

    def build(self):
        self.history = []
        self.pending = []
        self.busy = False
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
        brow.add_widget(Button(text="Bolo", on_press=self.pick_voice))
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
        return root

    def on_pause(self):
        return True

    def on_resume(self):
        pass

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
        self.history = []
        self.pending = []
        self.log.text = "Naya chat shuru.\n"

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

    # ---------- Voice ----------
    def pick_voice(self, *a):
        if platform != "android":
            self.show("\nVoice input sirf phone par chalta hai.\n")
            return
        try:
            i = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                       RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, SPEECH_LANG)
            PythonActivity.mActivity.startActivityForResult(i, 1002)
        except Exception as e:
            self.show("\nVoice start nahi hui: " + str(e) + "\n")

    def on_result(self, code, res, intent):
        if res != -1 or intent is None:
            return
        try:
            if code == 1001:
                self.load_uri(intent.getData())
            elif code == 1002:
                lst = intent.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                if lst is not None and lst.size() > 0:
                    t = str(lst.get(0))
                    shown = t if t.isascii() else "(voice message)"
                    Clock.schedule_once(lambda dt: self.submit(t, shown))
        except Exception as e:
            self.show("\nError: " + str(e) + "\n")

    # ---------- Chat ----------
    def send(self, *a):
        self.submit(self.inp.text.strip())

    def submit(self, q, shown=None):
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
        self.show("(soch raha hai...)\n")
        threading.Thread(target=self.ask, daemon=True).start()

    def ask(self):
        try:
            msgs = list(self.history)
            out = ""
            for _ in range(4):
                r = requests.post(URL, timeout=120, headers={
                    "x-api-key": self.key.text.strip(),
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"},
                    json={"model": MODEL, "max_tokens": 3000, "system": SYSTEM,
                          "tools": TOOLS, "messages": msgs})
                data = r.json()
                if "content" not in data:
                    err = data.get("error", {}).get("message", str(data))
                    self.history.pop()
                    self.show("Error: " + err + "\n")
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
        except Exception as e:
            if self.history and self.history[-1]["role"] == "user":
                self.history.pop()
            self.show("Error: " + str(e) + "\n")
        finally:
            self.busy = False

AI().run()
