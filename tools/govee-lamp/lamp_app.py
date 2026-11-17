"""Desktop control panel for the Govee H6052 lamp.  Run:  pythonw lamp_app.py"""
import colorsys
import threading
import time
import tkinter as tk
from tkinter import colorchooser, ttk

from govee_lamp import DEFAULT_ADDRESS, LampThread

SWATCHES = ["#ff0000", "#ff6a00", "#ffd000", "#00ff40", "#00e0ff",
            "#0040ff", "#8000ff", "#ff00c0", "#ffffff"]
BG, FG, MUTED, CARD = "#16181d", "#e8e8ea", "#8a8f98", "#22252c"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.lt = LampThread(DEFAULT_ADDRESS)
        self.lt.lamp.on_state_change = lambda c: root.after(0, self._set_conn, c)
        self.is_on = False
        self._pending: dict[str, str] = {}
        self._sync_stop: threading.Event | None = None

        root.title("Govee Aura Lamp")
        root.configure(bg=BG)
        root.resizable(False, False)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TScale", background=BG, troughcolor=CARD)

        pad = dict(padx=16, pady=(0, 12))
        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=16, pady=14)
        tk.Label(top, text="Aura Lamp", bg=BG, fg=FG, font=("Segoe UI Semibold", 15)).pack(side="left")
        self.conn = tk.Label(top, text="● connecting…", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.conn.pack(side="left", padx=10)
        self.power_btn = tk.Button(top, text="OFF", width=6, relief="flat", bg=CARD, fg=FG,
                                   activebackground="#30343c", font=("Segoe UI Semibold", 10),
                                   command=self.toggle_power)
        self.power_btn.pack(side="right")

        self.preview = tk.Canvas(root, height=44, bg=CARD, highlightthickness=0)
        self.preview.pack(fill="x", **pad)
        self.preview.bind("<Button-1>", lambda e: self.pick_color())

        sw = tk.Frame(root, bg=BG)
        sw.pack(fill="x", **pad)
        for c in SWATCHES:
            b = tk.Label(sw, bg=c, width=3, height=1, cursor="hand2")
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e, c=c: self.set_color(c))
        tk.Button(sw, text="Custom…", relief="flat", bg=CARD, fg=FG, command=self.pick_color).pack(side="right")

        self.bright = self._slider("Brightness", 1, 100, 100, lambda v: self._debounce("b", v))
        self.kelvin = self._slider("White temperature (K)", 2000, 9000, 4000, lambda v: self._debounce("k", v))

        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", **pad)
        self.sync_var = tk.BooleanVar()
        tk.Checkbutton(row, text="Match my screen", variable=self.sync_var, command=self.toggle_sync,
                       bg=BG, fg=FG, selectcolor=CARD, activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 10)).pack(side="left")
        tk.Button(row, text="Refresh", relief="flat", bg=CARD, fg=FG, command=self.refresh).pack(side="right")

        self.status = tk.Label(root, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.status.pack(fill="x", padx=16, pady=(0, 12))

        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.lt.call("connect").add_done_callback(lambda f: root.after(0, self._after_connect, f))

    # ---- UI helpers -----------------------------------------------------
    def _slider(self, label, lo, hi, init, cb):
        f = tk.Frame(self.root, bg=BG)
        f.pack(fill="x", padx=16, pady=(0, 10))
        val = tk.Label(f, text=str(init), bg=BG, fg=MUTED, font=("Segoe UI", 9))
        tk.Label(f, text=label, bg=BG, fg=FG, font=("Segoe UI", 10)).pack(anchor="w")
        s = ttk.Scale(f, from_=lo, to=hi, value=init, length=300,
                      command=lambda v: (val.config(text=str(int(float(v)))), cb(int(float(v)))))
        s.pack(side="left", fill="x", expand=True)
        val.pack(side="right", padx=(8, 0))
        s.value_label = val
        return s

    def _debounce(self, key, value):
        # sliders fire constantly; send at most ~8 updates/sec
        first = key not in self._pending
        self._pending[key] = value
        if first:
            self.root.after(120, self._flush, key)

    def _flush(self, key):
        v = self._pending.pop(key, None)
        if v is None:  # cancelled by a refresh that moved the slider itself
            return
        if key == "b":
            self.send("brightness", v)
        else:
            self.stop_sync()
            self.send("white", v)
            self._show_preview("#%02x%02x%02x" % __import__("govee_lamp").kelvin_to_rgb(v))

    def send(self, name, *args):
        f = self.lt.call(name, *args)
        f.add_done_callback(lambda f: f.exception() and self.root.after(
            0, self.status.config, {"text": f"⚠ {f.exception()}"}))
        return f

    def _set_conn(self, ok):
        self.conn.config(text="● connected" if ok else "● reconnecting…", fg="#4cd964" if ok else "#ff9f0a")

    def _show_preview(self, hexcolor):
        self.preview.configure(bg=hexcolor)

    def _set_power_ui(self, on):
        self.is_on = on
        self.power_btn.config(text="ON" if on else "OFF", bg="#3a7afe" if on else CARD)

    # ---- actions --------------------------------------------------------
    def _after_connect(self, f):
        if f.exception():
            self.status.config(text=f"⚠ Could not connect: {f.exception()}  (close the Govee phone app?)")
            self._set_conn(False)
            self.root.after(4000, lambda: self.lt.call("connect").add_done_callback(
                lambda f: self.root.after(0, self._after_connect, f)))
            return
        self._set_conn(True)
        self.refresh()

    def refresh(self):
        self.lt.call("state").add_done_callback(lambda f: self.root.after(0, self._apply_state, f))

    def _apply_state(self, f):
        if f.exception():
            self.status.config(text=f"⚠ {f.exception()}")
            return
        st = f.result()
        self._set_power_ui(st["on"])
        if st["brightness"]:
            self.bright.set(st["brightness"])
            self.bright.value_label.config(text=str(st["brightness"]))
        if st["mode"] == "color":
            self._show_preview("#%02x%02x%02x" % st["rgb"])
            self.status.config(text="Colour mode")
        elif st["mode"] == "white":
            self.kelvin.set(st["kelvin"])
            self.kelvin.value_label.config(text=str(st["kelvin"]))
            self.status.config(text=f"White {st['kelvin']} K")
        elif st["mode"] == "scene":
            self.status.config(text=f"Scene {st['scene']} (set from phone app)")
        self._pending.clear()

    def toggle_power(self):
        self._set_power_ui(not self.is_on)
        self.send("power", self.is_on)

    def set_color(self, hexcolor, stop_sync=True):
        if stop_sync:
            self.stop_sync()
        r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
        if not self.is_on:
            self._set_power_ui(True)
            self.send("power", True)
        self.send("color", r, g, b)
        self._show_preview(hexcolor)

    def pick_color(self):
        c = colorchooser.askcolor(title="Lamp colour")[1]
        if c:
            self.set_color(c)

    # ---- screen sync ----------------------------------------------------
    def toggle_sync(self):
        if self.sync_var.get():
            self._sync_stop = threading.Event()
            threading.Thread(target=self._sync_loop, args=(self._sync_stop,), daemon=True).start()
            self.status.config(text="Matching screen colour…")
        else:
            self.stop_sync()

    def stop_sync(self):
        if self._sync_stop:
            self._sync_stop.set()
            self._sync_stop = None
            self.sync_var.set(False)
            self.status.config(text="")

    def _sync_loop(self, stop: threading.Event):
        from PIL import ImageGrab
        last = None
        cur = None
        while not stop.is_set():
            img = ImageGrab.grab(all_screens=False).resize((32, 18))
            px = list(img.getdata())
            # weight vivid pixels more so dark/grey UI doesn't wash everything out
            tot = [0.0, 0.0, 0.0]
            wsum = 0.0
            for r, g, b in px:
                h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                w = 0.05 + s * v
                tot[0] += r * w; tot[1] += g * w; tot[2] += b * w
                wsum += w
            target = [t / wsum for t in tot]
            h, s, v = colorsys.rgb_to_hsv(*(t / 255 for t in target))
            target = [c * 255 for c in colorsys.hsv_to_rgb(h, min(1, s * 1.4), max(v, 0.35))]
            cur = target if cur is None else [c + (t - c) * 0.5 for c, t in zip(cur, target)]  # smooth
            rgb = tuple(int(c) for c in cur)
            if last is None or sum(abs(a - b) for a, b in zip(rgb, last)) > 6:
                self.lt.call("color", *rgb)
                self.root.after(0, self._show_preview, "#%02x%02x%02x" % rgb)
                last = rgb
            time.sleep(0.15)

    def quit(self):
        self.stop_sync()
        self.lt.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
