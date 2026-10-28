import os, threading, requests
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.clock import Clock

URL = "https://api.anthropic.com/v1/messages"
SYSTEM = "Tum ek expert AI assistant ho. Roman Urdu/Hindi mein jawab do."

class AI(App):
    def key_path(self):
        return os.path.join(self.user_data_dir, "key.txt")

    def build(self):
        self.history = []
        root = BoxLayout(orientation="vertical", padding=6, spacing=6)
        krow = BoxLayout(size_hint_y=None, height=110, spacing=6)
        self.key = TextInput(hint_text="API key (sk-ant-...)", password=True,
                             multiline=False)
        try:
            with open(self.key_path()) as f:
                self.key.text = f.read().strip()
        except Exception:
            pass
        kbtn = Button(text="Key hatao", size_hint_x=0.3, on_press=self.clear_key)
        krow.add_widget(self.key)
        krow.add_widget(kbtn)
        self.log = TextInput(readonly=True, text="AI ready.\n")
        row = BoxLayout(size_hint_y=None, height=130, spacing=6)
        self.inp = TextInput(hint_text="Sawal likho", multiline=False)
        btn = Button(text="Bhejo", size_hint_x=0.3, on_press=self.send)
        row.add_widget(self.inp)
        row.add_widget(btn)
        root.add_widget(krow)
        root.add_widget(self.log)
        root.add_widget(row)
        return root

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

    def show(self, text):
        Clock.schedule_once(lambda dt: setattr(self.log, "text", self.log.text + text))

    def send(self, *a):
        q = self.inp.text.strip()
        if not q:
            return
        self.save_key()
        self.inp.text = ""
        self.show("\nAap: " + q + "\n")
        self.history.append({"role": "user", "content": q})
        threading.Thread(target=self.ask, daemon=True).start()

    def ask(self):
        try:
            r = requests.post(URL, timeout=90, headers={
                "x-api-key": self.key.text.strip(),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"},
                json={"model": "claude-sonnet-5-5", "max_tokens": 2000,
                      "system": SYSTEM, "messages": self.history})
            data = r.json()
            text = "".join(b.get("text", "") for b in data.get("content", []))
            if not text:
                text = str(data)
            self.history.append({"role": "assistant", "content": text})
            self.show("AI: " + text + "\n")
        except Exception as e:
            self.show("Error: " + str(e) + "\n")

AI().run()
