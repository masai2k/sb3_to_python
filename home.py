#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox
from urllib.request import urlopen
import ssl

BASE_RAW = "https://raw.githubusercontent.com/masai2k/sb3_to_python/main"

HOME_BG = "#0f172a"
CARD_BG = "#111827"
BTN_CONVERT = "#2563eb"
BTN_DEBUG = "#059669"
TEXT = "#f8fafc"
MUTED = "#cbd5e1"

def download_text(url: str) -> str:
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()

    with urlopen(url, context=ctx) as resp:
        return resp.read().decode("utf-8")


def run_remote_script(script_name: str, file_path: str) -> tuple[int, str, str]:
    script_url = f"{BASE_RAW}/{script_name}"
    code = download_text(script_url)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path, file_path],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(file_path) or None
        )
        return result.returncode, result.stdout, result.stderr
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SB3 to Python")
        self.geometry("520x320")
        self.minsize(480, 300)
        self.configure(bg=HOME_BG)

        outer = tk.Frame(self, bg=HOME_BG)
        outer.pack(fill="both", expand=True, padx=24, pady=24)

        card = tk.Frame(outer, bg=CARD_BG, highlightthickness=1, highlightbackground="#334155")
        card.pack(fill="both", expand=True)

        title = tk.Label(
            card,
            text="SB3 Converter & Debugger",
            font=("Helvetica", 20, "bold"),
            bg=CARD_BG,
            fg=TEXT
        )
        title.pack(pady=(28, 8))

        subtitle = tk.Label(
            card,
            text="Choose what you want to do.",
            font=("Helvetica", 11),
            bg=CARD_BG,
            fg=MUTED
        )
        subtitle.pack(pady=(0, 24))

        btn_wrap = tk.Frame(card, bg=CARD_BG)
        btn_wrap.pack(pady=8)

        convert_btn = tk.Button(
            btn_wrap,
            text="Convert",
            command=self.convert_file,
            font=("Helvetica", 13, "bold"),
            bg=BTN_CONVERT,
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=26,
            pady=14,
            cursor="hand2",
            width=14
        )
        convert_btn.grid(row=0, column=0, padx=10)

        debug_btn = tk.Button(
            btn_wrap,
            text="Debug",
            command=self.debug_file,
            font=("Helvetica", 13, "bold"),
            bg=BTN_DEBUG,
            fg="white",
            activebackground="#047857",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=26,
            pady=14,
            cursor="hand2",
            width=14
        )
        debug_btn.grid(row=0, column=1, padx=10)

        self.status = tk.Label(
            card,
            text="Ready.",
            font=("Helvetica", 10),
            bg=CARD_BG,
            fg=MUTED,
            wraplength=430,
            justify="center"
        )
        self.status.pack(pady=(26, 10))

        hint = tk.Label(
            card,
            text="Convert asks for a .sb3 file. Debug asks for a .py file.",
            font=("Helvetica", 10),
            bg=CARD_BG,
            fg="#94a3b8"
        )
        hint.pack(pady=(0, 20))

    def set_status(self, text: str):
        self.status.config(text=text)
        self.update_idletasks()

    def convert_file(self):
        file_path = filedialog.askopenfilename(
            title="Choose an SB3 file to convert",
            filetypes=[("SB3 files", "*.sb3"), ("All files", "*.*")]
        )
        if not file_path:
            return

        self.set_status(f"Converting: {os.path.basename(file_path)}")
        try:
            rc, out, err = run_remote_script("convertitore.py", file_path)
            if rc == 0:
                output_py = os.path.splitext(file_path)[0] + ".py"
                debugged_py = os.path.splitext(file_path)[0] + "debuggato.py"
                msg = f"Conversion completed.\n\nGenerated:\n{output_py}"
                if os.path.exists(debugged_py):
                    msg += f"\n{debugged_py}"
                if out.strip():
                    msg += f"\n\nOutput:\n{out.strip()}"
                self.set_status("Conversion completed.")
                messagebox.showinfo("Convert", msg)
            else:
                self.set_status("Conversion failed.")
                messagebox.showerror("Convert error", (err or out or "Unknown error").strip())
        except Exception as e:
            self.set_status("Conversion failed.")
            messagebox.showerror("Convert error", str(e))

    def debug_file(self):
        file_path = filedialog.askopenfilename(
            title="Choose a Python file to debug",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if not file_path:
            return

        self.set_status(f"Debugging: {os.path.basename(file_path)}")
        try:
            rc, out, err = run_remote_script("debug.py", file_path)
            if rc == 0:
                debugged_py = os.path.splitext(file_path)[0] + "debuggato.py"
                msg = f"Debug completed.\n\nGenerated:\n{debugged_py}"
                if out.strip():
                    msg += f"\n\nOutput:\n{out.strip()}"
                self.set_status("Debug completed.")
                messagebox.showinfo("Debug", msg)
            else:
                self.set_status("Debug failed.")
                messagebox.showerror("Debug error", (err or out or "Unknown error").strip())
        except Exception as e:
            self.set_status("Debug failed.")
            messagebox.showerror("Debug error", str(e))


if __name__ == "__main__":
    app = App()
    app.mainloop()
