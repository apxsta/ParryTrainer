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
SUCCESS_SOUND = "parry.mp3"

PAIRS = [
    ("fail.mp3", "abrams.png", 1.2, 250),
    ("fail.mp3", "billy.png", 1.2, 250),
    ("fail.mp3", "lash.png", 1.2, 250),
    ("fail.mp3", "viscous.png", 1.2, 250),
    ("fart1.mp3", "secret1.png", 2.5, 10.0),
    ("fart2.mp3", "secret2.png", 6.0, 1.0),
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
    sz = 64
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, sz - 2, sz - 2], fill=(200, 30, 30, 255))
    try:
        font = ImageFont.truetype("arialbd.ttf", 38)
    except Exception:
        font = ImageFont.load_default()
    draw.text((sz // 2, sz // 2), "F", font=font, fill=(255, 255, 255, 255), anchor="mm")
    return img

class PressFApp:
    def __init__(self):
        self.running = True
        self.alert_active = False
        self.f_pressed = False
        self.countdown = RESPONSE_TIME
        self.tray_icon = None
        self.hit_count = 0
        self.miss_count = 0

        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        pygame.mixer.set_num_channels(8)

        self.pairs: list[tuple[pygame.mixer.Sound, Image.Image, float, float]] = []
        for fail_file, image_file, show_time, weight in PAIRS:
            snd = load_sound(fail_file, fallback_freq=200)
            img = load_image(image_file)
            self.pairs.append((snd, img, show_time, weight))

        self.alert_sound = load_sound(ALERT_SOUND, fallback_freq=880)
        self.success_sound = load_sound(SUCCESS_SOUND, fallback_freq=1200)

        self._current_fail_sound: pygame.mixer.Sound = self.pairs[0][0]
        self._current_image: Image.Image = self.pairs[0][1]
        self._current_show_time: float = self.pairs[0][2]

        keyboard.on_press_key("f", self._on_f)
        keyboard.on_press_key("F", self._on_f)

    def _on_f(self, _event):
        if self.alert_active:
            self.f_pressed = True

    def _alert_loop(self):
        while self.running:
            delay = random.uniform(MIN_INTERVAL, MAX_INTERVAL)
            for _ in range(int(delay * 10)):
                if not self.running:
                    return
                time.sleep(0.1)
            if self.running:
                self._trigger_alert()

    def _trigger_alert(self):
        weights = [p[3] for p in self.pairs]
        chosen_pair = random.choices(self.pairs, weights=weights, k=1)[0]

        self._current_fail_sound = chosen_pair[0]
        self._current_image = chosen_pair[1]
        self._current_show_time = chosen_pair[2]

        self.f_pressed = False
        self.alert_active = True
        self.countdown = RESPONSE_TIME

        self.alert_sound.play()

        def _wait():
            for remaining in range(int(RESPONSE_TIME), 0, -1):
                if not self.running:
                    return
                if self.f_pressed:
                    break
                self.countdown = remaining
                time.sleep(1)

            self.alert_active = False

            if self.f_pressed:
                self.success_sound.play()
            else:
                self._current_fail_sound.play()
                self._show_jumpscare(self._current_image, self._current_show_time)

        threading.Thread(target=_wait, daemon=True).start()

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

    def _set_tray(self, title: str):
        if self.tray_icon:
            self.tray_icon.title = title

    def _build_menu(self):
        return pystray.Menu(
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
            "press_f", make_tray_icon(),
            "Press F – aktywny",
            menu=self._build_menu(),
        )
        self.tray_icon.run()

if __name__ == "__main__":
    app = PressFApp()
    app.run()