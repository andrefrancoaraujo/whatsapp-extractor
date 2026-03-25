"""
WhatsApp Business Extractor - Windows GUI Application
Extracts all WhatsApp Business conversations via ADB screen automation.
"""

import os
import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
import requests

from config import SERVER_URL
from adb_automation import ADBAutomation, ADBError


def resource_path(relative_path):
    """Get absolute path to resource (works for PyInstaller bundles)."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)


class WhatsAppExtractorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("WhatsApp Business Extractor")
        self.root.geometry("700x600")
        self.root.resizable(False, False)
        self.root.configure(bg="#0D2520")

        self.adb_path = self._find_adb()
        self.is_running = False

        self._build_ui()

    def _find_adb(self) -> str:
        """Find ADB executable."""
        # Check bundled ADB first
        bundled = resource_path(os.path.join("adb", "adb.exe"))
        if os.path.exists(bundled):
            return bundled
        # Check PATH
        return "adb"

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Header
        header = tk.Frame(self.root, bg="#0D2520", pady=15)
        header.pack(fill="x")

        tk.Label(header, text="WhatsApp Business Extractor",
                 font=("Segoe UI", 18, "bold"), fg="#00C9A7", bg="#0D2520").pack()
        tk.Label(header, text="Extraia todas as conversas automaticamente",
                 font=("Segoe UI", 10), fg="#AAAAAA", bg="#0D2520").pack()

        # Instructions
        instr_frame = tk.Frame(self.root, bg="#143D33", padx=15, pady=10)
        instr_frame.pack(fill="x", padx=15, pady=(0, 10))

        instructions = [
            "1. Conecte o celular via cabo USB",
            "2. No celular: Configuracoes > Sobre o telefone > toque 7x no 'Numero da versao'",
            "3. Volte em Configuracoes > Opcoes do desenvolvedor > Ative 'Depuracao USB'",
            "4. Aceite a permissao no celular quando conectar o cabo",
            "5. Clique 'Verificar Conexao' abaixo",
        ]
        for instr in instructions:
            tk.Label(instr_frame, text=instr, font=("Segoe UI", 9),
                     fg="#FFFFFF", bg="#143D33", anchor="w").pack(fill="x")

        # Buttons
        btn_frame = tk.Frame(self.root, bg="#0D2520", pady=5)
        btn_frame.pack(fill="x", padx=15)

        self.btn_check = tk.Button(btn_frame, text="Verificar Conexao",
                                    font=("Segoe UI", 11, "bold"),
                                    bg="#00C9A7", fg="#0D2520",
                                    command=self._check_connection,
                                    width=20, height=1)
        self.btn_check.pack(side="left", padx=5)

        self.btn_extract = tk.Button(btn_frame, text="EXTRAIR TUDO",
                                      font=("Segoe UI", 11, "bold"),
                                      bg="#E8B731", fg="#0D2520",
                                      command=self._start_extraction,
                                      state="disabled",
                                      width=20, height=1)
        self.btn_extract.pack(side="left", padx=5)

        self.btn_upload = tk.Button(btn_frame, text="Enviar pro Servidor",
                                     font=("Segoe UI", 11, "bold"),
                                     bg="#4A90D9", fg="#FFFFFF",
                                     command=self._upload_files,
                                     state="disabled",
                                     width=20, height=1)
        self.btn_upload.pack(side="left", padx=5)

        # Progress
        prog_frame = tk.Frame(self.root, bg="#0D2520", pady=5)
        prog_frame.pack(fill="x", padx=15)

        self.progress_label = tk.Label(prog_frame, text="Aguardando...",
                                        font=("Segoe UI", 9), fg="#AAAAAA", bg="#0D2520")
        self.progress_label.pack(fill="x")

        self.progress_bar = ttk.Progressbar(prog_frame, mode="determinate", length=660)
        self.progress_bar.pack(fill="x", pady=5)

        # Log
        log_frame = tk.Frame(self.root, bg="#0D2520")
        log_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.log_area = scrolledtext.ScrolledText(
            log_frame, font=("Consolas", 9),
            bg="#0A1F1A", fg="#00C9A7",
            insertbackground="#00C9A7",
            height=15
        )
        self.log_area.pack(fill="both", expand=True)

    def _log(self, message: str):
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.root.update_idletasks()

    def _check_connection(self):
        self._log("Checking ADB connection...")
        try:
            automation = ADBAutomation(adb_path=self.adb_path, log_callback=self._log)
            if automation.check_device():
                self._log("Device connected!")
                self.btn_extract.config(state="normal")
                self.progress_label.config(text="Device connected. Ready to extract.", fg="#00C9A7")
            else:
                self._log("No device found. Check USB cable and USB debugging settings.")
                self.progress_label.config(text="No device found.", fg="#FF4444")
        except ADBError as e:
            self._log(f"Error: {e}")
            self.progress_label.config(text="ADB error.", fg="#FF4444")

    def _start_extraction(self):
        if self.is_running:
            return
        self.is_running = True
        self.btn_extract.config(state="disabled")
        self.btn_check.config(state="disabled")
        thread = threading.Thread(target=self._run_extraction, daemon=True)
        thread.start()

    def _run_extraction(self):
        try:
            automation = ADBAutomation(adb_path=self.adb_path, log_callback=self._log)

            def progress_cb(current, total, name):
                pct = (current / total) * 100
                self.progress_bar["value"] = pct
                self.progress_label.config(
                    text=f"Exporting {current}/{total}: {name}",
                    fg="#E8B731"
                )
                self.root.update_idletasks()

            pulled = automation.run_full_export(progress_callback=progress_cb)

            self._log(f"\n{'='*50}")
            self._log(f"Done! {len(pulled)} files extracted.")
            self.progress_label.config(text=f"Done! {len(pulled)} files extracted.", fg="#00C9A7")
            self.progress_bar["value"] = 100

            if pulled:
                self.btn_upload.config(state="normal")
                self.pulled_files = pulled

        except ADBError as e:
            self._log(f"\nError: {e}")
            self.progress_label.config(text="Extraction failed.", fg="#FF4444")
        except Exception as e:
            self._log(f"\nUnexpected error: {e}")
            self.progress_label.config(text="Extraction failed.", fg="#FF4444")
        finally:
            self.is_running = False
            self.btn_extract.config(state="normal")
            self.btn_check.config(state="normal")

    def _upload_files(self):
        if not hasattr(self, "pulled_files") or not self.pulled_files:
            self._log("No files to upload.")
            return

        self._log(f"\nUploading {len(self.pulled_files)} files to server...")
        self.btn_upload.config(state="disabled")

        thread = threading.Thread(target=self._do_upload, daemon=True)
        thread.start()

    def _do_upload(self):
        try:
            files_to_send = []
            for fpath in self.pulled_files:
                if os.path.exists(fpath):
                    files_to_send.append(
                        ("files", (os.path.basename(fpath), open(fpath, "rb"), "text/plain"))
                    )

            if not files_to_send:
                self._log("No valid files found.")
                return

            response = requests.post(SERVER_URL, files=files_to_send, timeout=120)

            if response.status_code == 200:
                result = response.json()
                self._log(f"Upload complete! Server received {result.get('count', '?')} files.")
                self.progress_label.config(text="Upload complete!", fg="#00C9A7")
            else:
                self._log(f"Upload failed: HTTP {response.status_code}")
                self.progress_label.config(text="Upload failed.", fg="#FF4444")

        except requests.exceptions.ConnectionError:
            self._log("Could not connect to server. Saving files locally instead.")
            self._log(f"Files are in: {os.path.abspath('exported_chats')}")
            self.progress_label.config(text="Saved locally (server offline).", fg="#E8B731")
        except Exception as e:
            self._log(f"Upload error: {e}")
            self._log(f"Files are saved locally in: {os.path.abspath('exported_chats')}")
        finally:
            self.btn_upload.config(state="normal")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = WhatsAppExtractorApp()
    app.run()
