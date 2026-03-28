import sys
import os
import time
import random
import threading
import tkinter as tk
import ctypes
import io

import pystray
from PIL import Image, ImageDraw, ImageFont, ImageTk
import pygame
import keyboard

MIN_INTERVAL = 30
MAX_INTERVAL = 900
RESPONSE_TIME = 1.2

FADE_IN_TIME = 0.08
FADE_OUT_TIME = 0.35
ALERT_SOUND = "alert.mp3"
PUDDLE = "puddle.mp3"
SUCCESS_SOUND = "parry.mp3"

PAIRS_LOSE = [
    ("fail.mp3", "abrams.png", 1.2, 3),
    ("fail.mp3", "billy.png", 1.2, 3),
    ("fail.mp3", "lash.png", 1.2, 3),
    ("fail.mp3", "viscous.png", 1.2, 3),
    ("fart1.mp3", "secret1.png", 2.5, 1),
]

PAIRS_WIN = [
    ("win1.mp3", "mina.png", 6.2, 2),
    ("boosh.mp3", "lash_win.png", 1.2, 2),
    ("vindicta.mp3", "vindicta.png", 3.3, 2),
    ("lady_geist.mp3", "lady_geist.png", 4, 2),
    ("apollo.mp3", "apollo.png", 3.3, 200),
    ("fart2.mp3", "secret2.png", 6.0, 1),
]

def resource_path(filename: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        p = os.path.join(sys._MEIPASS, filename)
        if os.path.exists(p):
            return p
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    p = os.path.join(exe_dir, filename)
    if os.path.exists(p):
        return p
    return os.path.join(os.path.abspath("."), filename)

def load_sound(filename: str, fallback_freq=880) -> pygame.mixer.Sound:
    path = resource_path(filename)
    return pygame.mixer.Sound(path)

def load_image(filename: str) -> Image.Image:
    path = resource_path(filename)
    return Image.open(path).convert("RGB")

def make_tray_icon() -> Image.Image:
    path = resource_path("icon.ico")
    return Image.open(path).convert("RGBA")

class PressFApp:
    def __init__(self):
        self.running = True
        self.alert_active = False
        self.f_pressed = False
        self.countdown = RESPONSE_TIME
        self.tray_icon = None
        self.hit_count = 0
        self.miss_count = 0
        self.min_interval = MIN_INTERVAL
        self.max_interval = MAX_INTERVAL
        self._reset_timer = False
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        pygame.mixer.set_num_channels(8)

        self.pairs_lose: list[tuple[pygame.mixer.Sound, Image.Image, float, float]] = []
        for fail_file, image_file, show_time, weight in PAIRS_LOSE:
            snd1 = load_sound(fail_file, fallback_freq=200)
            img1 = load_image(image_file)
            self.pairs_lose.append((snd1, img1, show_time, weight))

        self.pairs_win: list[tuple[pygame.mixer.Sound, Image.Image, float, float]] = []
        for fail_file, image_file, show_time, weight in PAIRS_WIN:
            snd2 = load_sound(fail_file, fallback_freq=200)
            img2 = load_image(image_file)
            self.pairs_win.append((snd2, img2, show_time, weight))

        self.success_sound = load_sound(SUCCESS_SOUND, fallback_freq=1200)
        self._current_fail_sound: pygame.mixer.Sound = self.pairs_lose[0][0]
        self._current_fail_image: Image.Image = self.pairs_lose[0][1]
        self._current_fail_show_time: float = self.pairs_lose[0][2]

        self._current_win_sound: pygame.mixer.Sound = self.pairs_win[0][0]
        self._current_win_image: Image.Image = self.pairs_win[0][1]
        self._current_win_show_time: float = self.pairs_win[0][2]

        self.hotkey = "f"
        keyboard.on_press_key(self.hotkey, self._on_f)

    def _on_f(self, _event):
        if self.alert_active:
            self.f_pressed = True

    def _alert_loop(self):
        while self.running:
            self._reset_timer = False
            delay = random.uniform(self.min_interval, self.max_interval)
            for _ in range(int(delay * 10)):
                if not self.running:
                    return
                if self._reset_timer:
                    break
                time.sleep(0.1)
            if self.running and not self._reset_timer:
                self._trigger_alert()

    def _trigger_alert(self):

        if random.randint(1, 4) == 4:
            self.alert_sound = load_sound(PUDDLE, fallback_freq=880)
        else:
            self.alert_sound = load_sound(ALERT_SOUND, fallback_freq=880)

        weights1 = [p[3] for p in self.pairs_lose]
        weights2 = [p[3] for p in self.pairs_win]
        chosen_pair_fail = random.choices(self.pairs_lose, weights=weights1, k=1)[0]
        chosen_pair_win = random.choices(self.pairs_win, weights=weights2, k=1)[0]

        self._current_fail_sound = chosen_pair_fail[0]
        self._current_fail_image = chosen_pair_fail[1]
        self._current_fail_show_time = chosen_pair_fail[2]

        self._current_win_sound = chosen_pair_win[0]
        self._current_win_image = chosen_pair_win[1]
        self._current_win_show_time = chosen_pair_win[2]

        self.f_pressed = False
        self.alert_active = True
        self.countdown = RESPONSE_TIME

        self.alert_sound.play()

        def _wait():
            deadline = time.time() + RESPONSE_TIME
            while time.time() < deadline:
                if not self.running:
                    return
                if self.f_pressed:
                    self.success_sound.play()
                    break
                time.sleep(0.05)

            self.alert_active = False

            if self.f_pressed:
                self._current_win_sound.play()
                self._show_reward(self._current_win_image, self._current_win_show_time)
            else:
                self._current_fail_sound.play()
                self._show_jumpscare(self._current_fail_image, self._current_fail_show_time)

        threading.Thread(target=_wait, daemon=True).start()

    def _show_reward(self, pil_img: Image.Image, show_time: float):
        def _build():
            win = tk.Tk()
            win.attributes("-fullscreen", True)
            win.attributes("-topmost", True)
            win.overrideredirect(True)
            win.configure(bg="black")

            win.attributes("-alpha", 0.0)

            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()

            resized = pil_img.resize((sw, sh), Image.LANCZOS)

            canvas = tk.Canvas(win, width=sw, height=sh,
                               bg="black", highlightthickness=0)
            canvas.pack(fill="both", expand=True)

            tk_img = ImageTk.PhotoImage(resized)
            canvas.create_image(sw // 2, sh // 2, anchor="center", image=tk_img)
            canvas.image = tk_img

            steps_in = 15
            steps_out = 20

            delay_in = int((FADE_IN_TIME * 1000) / steps_in)
            delay_out = int((FADE_OUT_TIME * 1000) / steps_out)

            hold_time = int((show_time - FADE_IN_TIME - FADE_OUT_TIME) * 1000)
            if hold_time < 0:
                hold_time = 0

            def fade_in(step=0):
                if step <= steps_in:
                    alpha = step / steps_in
                    win.attributes("-alpha", alpha)
                    win.after(delay_in, fade_in, step + 1)
                else:
                    win.attributes("-alpha", 1.0)
                    win.after(hold_time, fade_out)

            def fade_out(step=0):
                if step <= steps_out:
                    alpha = 1.0 - (step / steps_out)
                    win.attributes("-alpha", alpha)
                    win.after(delay_out, fade_out, step + 1)
                else:
                    win.destroy()

            win.after(0, fade_in)
            win.mainloop()

        threading.Thread(target=_build, daemon=True).start()


    def _show_jumpscare(self, pil_img: Image.Image, show_time: float):
        def _build():
            win = tk.Tk()
            win.attributes("-fullscreen", True)
            win.attributes("-topmost", True)
            win.overrideredirect(True)
            win.configure(bg="black")

            win.attributes("-alpha", 0.0)

            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()

            resized = pil_img.resize((sw, sh), Image.LANCZOS)

            canvas = tk.Canvas(win, width=sw, height=sh,
                               bg="black", highlightthickness=0)
            canvas.pack(fill="both", expand=True)

            tk_img = ImageTk.PhotoImage(resized)
            canvas.create_image(sw // 2, sh // 2, anchor="center", image=tk_img)
            canvas.image = tk_img

            steps_in = 15
            steps_out = 20

            delay_in = int((FADE_IN_TIME * 1000) / steps_in)
            delay_out = int((FADE_OUT_TIME * 1000) / steps_out)

            hold_time = int((show_time - FADE_IN_TIME - FADE_OUT_TIME) * 1000)
            if hold_time < 0:
                hold_time = 0

            def fade_in(step=0):
                if step <= steps_in:
                    alpha = step / steps_in
                    win.attributes("-alpha", alpha)
                    win.after(delay_in, fade_in, step + 1)
                else:
                    win.attributes("-alpha", 1.0)
                    win.after(hold_time, fade_out)

            def fade_out(step=0):
                if step <= steps_out:
                    alpha = 1.0 - (step / steps_out)
                    win.attributes("-alpha", alpha)
                    win.after(delay_out, fade_out, step + 1)
                else:
                    win.destroy()

            win.after(0, fade_in)
            win.mainloop()

        threading.Thread(target=_build, daemon=True).start()

    def _change_key(self, *_):
        threading.Thread(target=self._show_key_dialog, daemon=True).start()

    def _show_key_dialog(self):
        win = tk.Tk()
        win.title("Change parry key")
        win.geometry("300x130")
        win.attributes("-topmost", True)
        win.resizable(False, False)

        tk.Label(win, text=f"Current parry key: [{self.hotkey.upper()}]",
                 font=("Arial", 12, "bold")).pack(pady=12)
        info = tk.Label(win, text="Press any button...", font=("Arial", 11))
        info.pack()

        win.update()
        result = [None]

        def read_key():
            key = keyboard.read_key(suppress=False)
            result[0] = key
            win.after(0, apply_key)

        def apply_key():
            new_key = result[0]
            if new_key:
                keyboard.unhook_all()
                self.hotkey = new_key
                keyboard.on_press_key(new_key, self._on_f)
                if self.tray_icon:
                    self.tray_icon.update_menu()
            win.destroy()

        threading.Thread(target=read_key, daemon=True).start()
        win.mainloop()

    def _change_interval(self, *_):
        threading.Thread(target=self._show_interval_dialog, daemon=True).start()

    def _show_interval_dialog(self):
        win = tk.Tk()
        win.title("Change melee sound interval")
        win.geometry("300x200")
        win.attributes("-topmost", True)
        win.resizable(False, False)

        tk.Label(win, text="MIN Interval (s):", font=("Arial", 11)).pack(pady=(16, 2))
        min_var = tk.StringVar(value=str(self.min_interval))
        tk.Entry(win, textvariable=min_var, font=("Arial", 11), justify="center", width=10).pack()

        tk.Label(win, text="MAX Interval (s):", font=("Arial", 11)).pack(pady=(12, 2))
        max_var = tk.StringVar(value=str(self.max_interval))
        tk.Entry(win, textvariable=max_var, font=("Arial", 11), justify="center", width=10).pack()

        status = tk.Label(win, text="", font=("Arial", 10), fg="red")
        status.pack(pady=4)

        def apply():
            try:
                new_min = float(min_var.get().replace(",", "."))
                new_max = float(max_var.get().replace(",", "."))
                if new_min <= 0 or new_max <= 0:
                    raise ValueError
                if new_min >= new_max:
                    status.config(text="Min has to be less than Max!")
                    return
            except ValueError:
                status.config(text="Input correct numbers!")
                return

            self.min_interval = new_min
            self.max_interval = new_max
            self._reset_timer = True
            if self.tray_icon:
                self.tray_icon.update_menu()
            win.destroy()

        tk.Button(win, text="Apply", font=("Arial", 11), command=apply).pack(pady=6)
        win.mainloop()


    def _set_tray(self, title: str):
        if self.tray_icon:
            self.tray_icon.title = title

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                lambda item: f"Key: [{self.hotkey.upper()}]",
                None, enabled=False,
            ),
            pystray.MenuItem("Change key", self._change_key),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: f"Melee sound interval: {self.min_interval}–{self.max_interval}s",
                None, enabled=False,
            ),
            pystray.MenuItem("Change melee sound interval", self._change_interval),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _quit(self, *_):
        self.running = False
        keyboard.unhook_all()
        pygame.mixer.quit()
        if self.tray_icon:
            self.tray_icon.stop()
        sys.exit(0)

    def run(self):
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.ShowWindow(
                    ctypes.windll.kernel32.GetConsoleWindow(), 0)
            except Exception:
                pass

        threading.Thread(target=self._alert_loop, daemon=True).start()

        self.tray_icon = pystray.Icon(
            "Parry Trainer", make_tray_icon(),
            "Parry Trainer – working",
            menu=self._build_menu(),
        )
        self.tray_icon.run()

if __name__ == "__main__":
    app = PressFApp()
    app.run()
