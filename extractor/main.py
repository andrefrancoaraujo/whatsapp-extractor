"""
WhatsApp Business Extractor - Windows GUI Application
Extracts all WhatsApp Business conversations via ADB screen automation.
Supports USB and Wi-Fi (wireless ADB) connections.
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
        self.root.geometry("700x700")
        self.root.resizable(False, False)
        self.root.configure(bg="#0D2520")

        self.adb_path = self._find_adb()
        self.is_running = False

        self._build_ui()

    def _find_adb(self) -> str:
        """Find ADB executable."""
        bundled = resource_path(os.path.join("adb", "adb.exe"))
        if os.path.exists(bundled):
            return bundled
        return "adb"

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Header
        header = tk.Frame(self.root, bg="#0D2520", pady=10)
        header.pack(fill="x")

        tk.Label(header, text="WhatsApp Business Extractor",
                 font=("Segoe UI", 18, "bold"), fg="#00C9A7", bg="#0D2520").pack()
        tk.Label(header, text="Extraia todas as conversas automaticamente",
                 font=("Segoe UI", 10), fg="#AAAAAA", bg="#0D2520").pack()

        # ── Wi-Fi Connection Section ──
        wifi_frame = tk.LabelFrame(self.root, text="  Conexao Wi-Fi (sem cabo)  ",
                                    font=("Segoe UI", 10, "bold"),
                                    fg="#E8B731", bg="#143D33",
                                    padx=15, pady=10)
        wifi_frame.pack(fill="x", padx=15, pady=(5, 5))

        tk.Label(wifi_frame,
                 text="No celular: Configuracoes > Opcoes do desenvolvedor > Depuracao sem fio > Parear dispositivo",
                 font=("Segoe UI", 8), fg="#AAAAAA", bg="#143D33", anchor="w").pack(fill="x")

        # Row 1: IP and pairing port
        row1 = tk.Frame(wifi_frame, bg="#143D33", pady=3)
        row1.pack(fill="x")

        tk.Label(row1, text="IP e porta de pareamento:",
                 font=("Segoe UI", 9), fg="#FFFFFF", bg="#143D33", width=22, anchor="w").pack(side="left")
        self.entry_pair_addr = tk.Entry(row1, font=("Consolas", 11), bg="#0A1F1A", fg="#00C9A7",
                                         insertbackground="#00C9A7", width=25)
        self.entry_pair_addr.pack(side="left", padx=5)
        self.entry_pair_addr.insert(0, "")

        # Row 2: Pairing code
        row2 = tk.Frame(wifi_frame, bg="#143D33", pady=3)
        row2.pack(fill="x")

        tk.Label(row2, text="Codigo de pareamento:",
                 font=("Segoe UI", 9), fg="#FFFFFF", bg="#143D33", width=22, anchor="w").pack(side="left")
        self.entry_pair_code = tk.Entry(row2, font=("Consolas", 11), bg="#0A1F1A", fg="#00C9A7",
                                         insertbackground="#00C9A7", width=25)
        self.entry_pair_code.pack(side="left", padx=5)

        # Row 3: Connect address (shown after pairing)
        row3 = tk.Frame(wifi_frame, bg="#143D33", pady=3)
        row3.pack(fill="x")

        tk.Label(row3, text="IP e porta de conexao:",
                 font=("Segoe UI", 9), fg="#FFFFFF", bg="#143D33", width=22, anchor="w").pack(side="left")
        self.entry_connect_addr = tk.Entry(row3, font=("Consolas", 11), bg="#0A1F1A", fg="#00C9A7",
                                            insertbackground="#00C9A7", width=25)
        self.entry_connect_addr.pack(side="left", padx=5)

        tk.Label(wifi_frame,
                 text="(IP e porta de conexao aparece na tela 'Depuracao sem fio', abaixo do toggle)",
                 font=("Segoe UI", 8), fg="#AAAAAA", bg="#143D33", anchor="w").pack(fill="x", pady=(3, 0))

        self.btn_wifi = tk.Button(wifi_frame, text="Conectar via Wi-Fi",
                                   font=("Segoe UI", 10, "bold"),
                                   bg="#E8B731", fg="#0D2520",
                                   command=self._connect_wifi,
                                   width=20)
        self.btn_wifi.pack(pady=(8, 0))

        # ── Separator ──
        sep_frame = tk.Frame(self.root, bg="#0D2520", pady=2)
        sep_frame.pack(fill="x", padx=15)
        tk.Label(sep_frame, text="--- ou conecte via cabo USB ---",
                 font=("Segoe UI", 9), fg="#666666", bg="#0D2520").pack()

        # ── USB Button ──
        usb_frame = tk.Frame(self.root, bg="#0D2520", pady=3)
        usb_frame.pack(fill="x", padx=15)

        self.btn_check = tk.Button(usb_frame, text="Verificar Conexao USB",
                                    font=("Segoe UI", 10, "bold"),
                                    bg="#00C9A7", fg="#0D2520",
                                    command=self._check_connection,
                                    width=25)
        self.btn_check.pack()

        # ── Action Buttons ──
        btn_frame = tk.Frame(self.root, bg="#0D2520", pady=5)
        btn_frame.pack(fill="x", padx=15)

        self.btn_test = tk.Button(btn_frame, text="Testar 1 Conversa",
                                    font=("Segoe UI", 10, "bold"),
                                    bg="#FF9800", fg="#0D2520",
                                    command=self._start_test,
                                    state="disabled",
                                    width=20, height=1)
        self.btn_test.pack(side="left", padx=3)

        self.btn_extract = tk.Button(btn_frame, text="EXTRAIR TUDO",
                                      font=("Segoe UI", 11, "bold"),
                                      bg="#E8B731", fg="#0D2520",
                                      command=self._start_extraction,
                                      state="disabled",
                                      width=20, height=1)
        self.btn_extract.pack(side="left", padx=3)

        self.btn_upload = tk.Button(btn_frame, text="Enviar pro Servidor",
                                     font=("Segoe UI", 11, "bold"),
                                     bg="#4A90D9", fg="#FFFFFF",
                                     command=self._upload_files,
                                     state="disabled",
                                     width=20, height=1)
        self.btn_upload.pack(side="left", padx=3)

        # Progress
        prog_frame = tk.Frame(self.root, bg="#0D2520", pady=3)
        prog_frame.pack(fill="x", padx=15)

        self.progress_label = tk.Label(prog_frame, text="Aguardando conexao...",
                                        font=("Segoe UI", 9), fg="#AAAAAA", bg="#0D2520")
        self.progress_label.pack(fill="x")

        self.progress_bar = ttk.Progressbar(prog_frame, mode="determinate", length=660)
        self.progress_bar.pack(fill="x", pady=3)

        # Log
        log_frame = tk.Frame(self.root, bg="#0D2520")
        log_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        self.log_area = scrolledtext.ScrolledText(
            log_frame, font=("Consolas", 9),
            bg="#0A1F1A", fg="#00C9A7",
            insertbackground="#00C9A7",
            height=10
        )
        self.log_area.pack(fill="both", expand=True)

    def _log(self, message: str):
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.root.update_idletasks()

    def _connect_wifi(self):
        pair_addr = self.entry_pair_addr.get().strip()
        pair_code = self.entry_pair_code.get().strip()
        connect_addr = self.entry_connect_addr.get().strip()

        if not pair_addr or not pair_code:
            self._log("Preencha o IP:porta e o codigo de pareamento.")
            return

        if not connect_addr:
            self._log("Preencha tambem o IP:porta de conexao (aparece na tela 'Depuracao sem fio').")
            return

        self._log("Reiniciando ADB server...")
        try:
            automation = ADBAutomation(adb_path=self.adb_path, log_callback=self._log)

            # Step 0: Kill server, disconnect all, start fresh
            automation.run("kill-server", timeout=10)
            import time
            time.sleep(2)
            automation.run("start-server", timeout=10)
            time.sleep(1)
            automation.run("disconnect", timeout=10)
            time.sleep(1)

            # Step 1: Pair
            self._log(f"Pairing with {pair_addr} ...")
            pair_result = automation.run("pair", pair_addr, pair_code, timeout=15)
            self._log(f"Pair result: {pair_result}")

            if "Successfully" in pair_result or "success" in pair_result.lower():
                self._log("Pareamento OK!")
            else:
                self._log("Pareamento pode ter falhado. Tentando conectar mesmo assim...")

            # Step 2: Connect
            time.sleep(1)
            self._log(f"Connecting to {connect_addr} ...")
            connect_result = automation.run("connect", connect_addr, timeout=15)
            self._log(f"Connect result: {connect_result}")

            if "connected" in connect_result.lower():
                self._log("Conectado via Wi-Fi!")
                # Set device serial for all future commands
                self.wifi_device_serial = connect_addr
                automation_with_serial = ADBAutomation(
                    adb_path=self.adb_path,
                    log_callback=self._log,
                    device_serial=connect_addr
                )
                if automation_with_serial.check_device():
                    self.btn_extract.config(state="normal")
                    self.btn_test.config(state="normal")
                    self.progress_label.config(text="Conectado via Wi-Fi. Pronto para extrair.", fg="#00C9A7")
                else:
                    self._log("Conectou mas nao encontrou o device. Tente novamente.")
            else:
                self._log("Falha na conexao. Verifique os dados e tente novamente.")
                self.progress_label.config(text="Falha na conexao Wi-Fi.", fg="#FF4444")

        except ADBError as e:
            self._log(f"Erro: {e}")
            self.progress_label.config(text="Erro ADB.", fg="#FF4444")

    def _check_connection(self):
        self._log("Checking USB connection...")
        try:
            automation = ADBAutomation(adb_path=self.adb_path, log_callback=self._log)
            if automation.check_device():
                self._log("Device connected via USB!")
                self.btn_extract.config(state="normal")
                self.btn_test.config(state="normal")
                self.progress_label.config(text="Conectado via USB. Pronto para extrair.", fg="#00C9A7")
            else:
                self._log("Nenhum dispositivo encontrado. Verifique o cabo e a depuracao USB.")
                self.progress_label.config(text="Dispositivo nao encontrado.", fg="#FF4444")
        except ADBError as e:
            self._log(f"Erro: {e}")
            self.progress_label.config(text="Erro ADB.", fg="#FF4444")

    def _start_test(self):
        if self.is_running:
            return
        self.is_running = True
        self._disable_all_buttons()
        thread = threading.Thread(target=self._run_test, daemon=True)
        thread.start()

    def _run_test(self):
        try:
            device_serial = getattr(self, "wifi_device_serial", None)
            automation = ADBAutomation(
                adb_path=self.adb_path, log_callback=self._log,
                device_serial=device_serial, server_url=SERVER_URL
            )

            def progress_cb(current, total, name):
                self.progress_label.config(
                    text=f"Testando: {name}", fg="#FF9800"
                )
                self.root.update_idletasks()

            success = automation.run_test_export(progress_callback=progress_cb)

            if success:
                self.progress_label.config(
                    text="Teste OK! Pode clicar em EXTRAIR TUDO.", fg="#00C9A7"
                )
                self._log("\nTeste deu certo! Clique em EXTRAIR TUDO para exportar todas as conversas.")
            else:
                self.progress_label.config(
                    text="Teste falhou. Diagnosticos enviados.", fg="#FF4444"
                )
                self._log("\nTeste falhou. Screenshots de diagnostico foram capturados e enviados.")
                self._log(f"Screenshots locais em: {os.path.abspath('diagnostics')}")

        except ADBError as e:
            self._log(f"\nErro: {e}")
            self.progress_label.config(text="Teste falhou.", fg="#FF4444")
        except Exception as e:
            self._log(f"\nErro inesperado: {e}")
            self.progress_label.config(text="Teste falhou.", fg="#FF4444")
        finally:
            self.is_running = False
            self._enable_all_buttons()

    def _disable_all_buttons(self):
        self.btn_extract.config(state="disabled")
        self.btn_test.config(state="disabled")
        self.btn_check.config(state="disabled")
        self.btn_wifi.config(state="disabled")

    def _enable_all_buttons(self):
        self.btn_extract.config(state="normal")
        self.btn_test.config(state="normal")
        self.btn_check.config(state="normal")
        self.btn_wifi.config(state="normal")

    def _start_extraction(self):
        if self.is_running:
            return
        self.is_running = True
        self._disable_all_buttons()
        thread = threading.Thread(target=self._run_extraction, daemon=True)
        thread.start()

    def _run_extraction(self):
        try:
            device_serial = getattr(self, "wifi_device_serial", None)
            automation = ADBAutomation(
                adb_path=self.adb_path, log_callback=self._log,
                device_serial=device_serial, server_url=SERVER_URL
            )

            def progress_cb(current, total, name):
                pct = (current / total) * 100
                self.progress_bar["value"] = pct
                self.progress_label.config(
                    text=f"Exportando {current}/{total}: {name}",
                    fg="#E8B731"
                )
                self.root.update_idletasks()

            def batch_cb(batch_num, total_batches):
                self._log(f"\n>>> Batch {batch_num} de {total_batches}")
                self.progress_label.config(
                    text=f"Batch {batch_num}/{total_batches}",
                    fg="#E8B731"
                )
                self.root.update_idletasks()

            pulled = automation.run_full_export(
                progress_callback=progress_cb,
                batch_callback=batch_cb,
                num_batches=5,
                batch_pause=10
            )

            self._log(f"\n{'='*50}")
            self._log(f"Pronto! {len(pulled)} arquivos extraidos.")
            self.progress_label.config(text=f"Pronto! {len(pulled)} arquivos extraidos.", fg="#00C9A7")
            self.progress_bar["value"] = 100

            if pulled:
                self.btn_upload.config(state="normal")
                self.pulled_files = pulled

        except ADBError as e:
            self._log(f"\nErro: {e}")
            self.progress_label.config(text="Extracao falhou.", fg="#FF4444")
        except Exception as e:
            self._log(f"\nErro inesperado: {e}")
            self.progress_label.config(text="Extracao falhou.", fg="#FF4444")
        finally:
            self.is_running = False
            self._enable_all_buttons()

    def _upload_files(self):
        if not hasattr(self, "pulled_files") or not self.pulled_files:
            self._log("Nenhum arquivo para enviar.")
            return

        self._log(f"\nEnviando {len(self.pulled_files)} arquivos para o servidor...")
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
                self._log("Nenhum arquivo valido encontrado.")
                return

            response = requests.post(SERVER_URL, files=files_to_send, timeout=120)

            if response.status_code == 200:
                result = response.json()
                self._log(f"Upload completo! Servidor recebeu {result.get('count', '?')} arquivos.")
                self.progress_label.config(text="Upload completo!", fg="#00C9A7")
            else:
                self._log(f"Upload falhou: HTTP {response.status_code}")
                self.progress_label.config(text="Upload falhou.", fg="#FF4444")

        except requests.exceptions.ConnectionError:
            self._log("Nao conectou ao servidor. Arquivos salvos localmente.")
            self._log(f"Arquivos em: {os.path.abspath('exported_chats')}")
            self.progress_label.config(text="Salvo localmente (servidor offline).", fg="#E8B731")
        except Exception as e:
            self._log(f"Erro no upload: {e}")
            self._log(f"Arquivos salvos em: {os.path.abspath('exported_chats')}")
        finally:
            self.btn_upload.config(state="normal")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = WhatsAppExtractorApp()
    app.run()
