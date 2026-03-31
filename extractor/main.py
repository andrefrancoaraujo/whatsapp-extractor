"""
WhatsApp Business Backup Extractor — 3-step wizard GUI.
Decrypts crypt15 backups using the user's 64-digit E2E key.
"""

import json
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
from pathlib import Path

# Try tkinterdnd2 for drag-and-drop; fall back gracefully
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

from backup_decryptor import decrypt_crypt15, DecryptionError
from msgstore_parser import parse_msgstore, ParseError
from uploader import upload_conversations, UploadError
from adb_file_pull import ADBFilePull, ADBError
from config import BACKUP_UPLOAD_URL


# ── Visual constants ───────────────────────────────────────────
BG = "#0D2520"
BG2 = "#143D33"
BG_DARK = "#0A1F1A"
ACCENT = "#00C9A7"
GOLD = "#E8B731"
RED = "#FF4444"
WHITE = "#FFFFFF"
GRAY = "#AAAAAA"
FONT = "Segoe UI"
MONO = "Consolas"


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)


class BackupExtractorApp:
    def __init__(self):
        # Create root window
        if HAS_DND:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.title("WhatsApp Business Extractor")
        self.root.geometry("700x650")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)

        # State
        self.hex_key = ""
        self.crypt15_path = ""
        self.conversations = []
        self.is_running = False
        self.current_step = 1

        self._build_ui()
        self._show_step(1)

    # ── UI Construction ────────────────────────────────────────

    def _build_ui(self):
        # Title
        title_frame = tk.Frame(self.root, bg=BG)
        title_frame.pack(fill="x", pady=(15, 5))
        tk.Label(
            title_frame, text="WhatsApp Business Extractor",
            font=(FONT, 18, "bold"), fg=ACCENT, bg=BG
        ).pack()
        tk.Label(
            title_frame, text="Extraia todas as conversas via backup criptografado",
            font=(FONT, 9), fg=GRAY, bg=BG
        ).pack()

        # Step indicator
        self.step_frame = tk.Frame(self.root, bg=BG)
        self.step_frame.pack(fill="x", padx=40, pady=(15, 10))
        self.step_indicators = []
        self.step_labels = ["Chave", "Arquivo", "Extrair"]
        for i in range(3):
            col_frame = tk.Frame(self.step_frame, bg=BG)
            col_frame.pack(side="left", expand=True)
            circle = tk.Label(
                col_frame, text=str(i + 1), width=3,
                font=(FONT, 11, "bold"), fg=BG, bg=GRAY,
                relief="flat"
            )
            circle.pack()
            label = tk.Label(
                col_frame, text=self.step_labels[i],
                font=(FONT, 8), fg=GRAY, bg=BG
            )
            label.pack()
            self.step_indicators.append((circle, label))

        # Separator lines between steps
        # (drawn via the step frame layout)

        # Content area — three frames stacked, only one visible at a time
        self.content = tk.Frame(self.root, bg=BG)
        self.content.pack(fill="both", expand=True, padx=20, pady=10)

        self._build_step1()
        self._build_step2()
        self._build_step3()

    def _build_step1(self):
        """Step 1: Enter the 64-digit encryption key."""
        self.frame1 = tk.Frame(self.content, bg=BG)

        # Instructions
        instructions = tk.LabelFrame(
            self.frame1, text=" Como obter a chave ",
            font=(FONT, 10, "bold"), fg=ACCENT, bg=BG2,
            labelanchor="n", padx=15, pady=10
        )
        instructions.pack(fill="x", pady=(0, 15))

        steps = [
            "1. Abra o WhatsApp Business no celular",
            "2. Va em Configuracoes > Conversas > Backup de conversas",
            "3. Toque em 'Backup criptografado de ponta a ponta'",
            "4. Ative e escolha 'Usar chave de criptografia de 64 digitos'",
            "5. Copie a chave de 64 digitos e cole abaixo",
        ]
        for step in steps:
            tk.Label(
                instructions, text=step, font=(FONT, 10),
                fg=WHITE, bg=BG2, anchor="w", justify="left"
            ).pack(fill="x", pady=1)

        # Key input
        key_frame = tk.LabelFrame(
            self.frame1, text=" Chave de 64 digitos ",
            font=(FONT, 10, "bold"), fg=GOLD, bg=BG2,
            labelanchor="n", padx=15, pady=10
        )
        key_frame.pack(fill="x", pady=(0, 15))

        self.key_var = tk.StringVar()
        self.key_var.trace_add("write", self._on_key_change)

        self.key_entry = tk.Entry(
            key_frame, textvariable=self.key_var,
            font=(MONO, 12), fg=WHITE, bg=BG_DARK,
            insertbackground=WHITE, relief="flat",
            justify="center"
        )
        self.key_entry.pack(fill="x", ipady=8)

        self.key_status = tk.Label(
            key_frame, text="Cole a chave acima (64 caracteres hexadecimais)",
            font=(FONT, 9), fg=GRAY, bg=BG2
        )
        self.key_status.pack(pady=(5, 0))

        # Next button
        self.btn_step1_next = tk.Button(
            self.frame1, text="Proximo",
            font=(FONT, 11, "bold"), bg=ACCENT, fg=BG,
            command=self._step1_next, state="disabled",
            width=20, height=1, relief="flat", cursor="hand2"
        )
        self.btn_step1_next.pack(pady=15)

    def _build_step2(self):
        """Step 2: Get the crypt15 file."""
        self.frame2 = tk.Frame(self.content, bg=BG)

        # Drop zone / file selector
        drop_frame = tk.LabelFrame(
            self.frame2, text=" Arquivo de backup (.crypt15) ",
            font=(FONT, 10, "bold"), fg=ACCENT, bg=BG2,
            labelanchor="n", padx=15, pady=15
        )
        drop_frame.pack(fill="x", pady=(0, 10))

        # Where to find the file
        tk.Label(
            drop_frame,
            text="O arquivo fica em:\nCelular > Android > media > com.whatsapp.w4b >\nWhatsApp Business > Databases > msgstore.db.crypt15",
            font=(FONT, 9), fg=GRAY, bg=BG2, justify="center"
        ).pack(pady=(0, 10))

        # Drop zone area
        self.drop_zone = tk.Label(
            drop_frame,
            text="Arraste o arquivo .crypt15 aqui\nou clique em 'Procurar arquivo'",
            font=(FONT, 12), fg=GRAY, bg=BG_DARK,
            relief="groove", width=50, height=5, cursor="hand2"
        )
        self.drop_zone.pack(fill="x", ipady=15)

        if HAS_DND:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._on_file_drop)
            self.drop_zone.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            self.drop_zone.dnd_bind("<<DragLeave>>", self._on_drag_leave)

        # Buttons row
        btn_row = tk.Frame(drop_frame, bg=BG2)
        btn_row.pack(fill="x", pady=(10, 0))

        tk.Button(
            btn_row, text="Procurar arquivo...",
            font=(FONT, 10), bg=BG2, fg=ACCENT,
            command=self._browse_file, relief="flat", cursor="hand2"
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            btn_row, text="Copiar via USB (ADB)",
            font=(FONT, 10), bg=BG2, fg=ACCENT,
            command=self._pull_via_adb, relief="flat", cursor="hand2"
        ).pack(side="left")

        # File status
        self.file_status = tk.Label(
            drop_frame, text="", font=(FONT, 9), fg=GRAY, bg=BG2
        )
        self.file_status.pack(pady=(5, 0))

        # Navigation
        nav_frame = tk.Frame(self.frame2, bg=BG)
        nav_frame.pack(fill="x", pady=10)

        tk.Button(
            nav_frame, text="Voltar",
            font=(FONT, 10), bg=BG2, fg=GRAY,
            command=lambda: self._show_step(1), relief="flat", cursor="hand2"
        ).pack(side="left")

        self.btn_step2_next = tk.Button(
            nav_frame, text="Proximo",
            font=(FONT, 11, "bold"), bg=ACCENT, fg=BG,
            command=self._step2_next, state="disabled",
            relief="flat", cursor="hand2"
        )
        self.btn_step2_next.pack(side="right")

    def _build_step3(self):
        """Step 3: Decrypt, parse, and upload."""
        self.frame3 = tk.Frame(self.content, bg=BG)

        # Action buttons
        action_frame = tk.Frame(self.frame3, bg=BG)
        action_frame.pack(fill="x", pady=(0, 10))

        self.btn_extract = tk.Button(
            action_frame, text="Iniciar Extracao",
            font=(FONT, 12, "bold"), bg=GOLD, fg=BG,
            command=self._start_extraction, width=20, height=1,
            relief="flat", cursor="hand2"
        )
        self.btn_extract.pack(side="left", padx=(0, 10))

        self.btn_upload = tk.Button(
            action_frame, text="Enviar para Servidor",
            font=(FONT, 12, "bold"), bg=ACCENT, fg=BG,
            command=self._start_upload, width=20, height=1,
            state="disabled", relief="flat", cursor="hand2"
        )
        self.btn_upload.pack(side="left")

        # Progress
        self.progress_label = tk.Label(
            self.frame3, text="", font=(FONT, 10), fg=ACCENT, bg=BG, anchor="w"
        )
        self.progress_label.pack(fill="x")

        self.progress_bar = ttk.Progressbar(
            self.frame3, mode="determinate", length=660
        )
        self.progress_bar.pack(fill="x", pady=(5, 10))

        # Summary (hidden until extraction completes)
        self.summary_frame = tk.Frame(self.frame3, bg=BG2)
        # Not packed yet — shown after extraction

        self.summary_label = tk.Label(
            self.summary_frame, text="", font=(FONT, 11), fg=WHITE, bg=BG2,
            justify="left", anchor="w"
        )
        self.summary_label.pack(fill="x", padx=10, pady=10)

        # Log area
        self.log_area = scrolledtext.ScrolledText(
            self.frame3, font=(MONO, 10), bg=BG_DARK, fg=WHITE,
            insertbackground=WHITE, height=12, relief="flat",
            state="disabled"
        )
        self.log_area.pack(fill="both", expand=True)

        # Back button
        tk.Button(
            self.frame3, text="Voltar",
            font=(FONT, 10), bg=BG2, fg=GRAY,
            command=lambda: self._show_step(2), relief="flat", cursor="hand2"
        ).pack(anchor="w", pady=(10, 0))

    # ── Step Navigation ────────────────────────────────────────

    def _show_step(self, step: int):
        self.current_step = step

        # Hide all frames
        for f in (self.frame1, self.frame2, self.frame3):
            f.pack_forget()

        # Show current
        [self.frame1, self.frame2, self.frame3][step - 1].pack(
            fill="both", expand=True
        )

        # Update step indicators
        for i, (circle, label) in enumerate(self.step_indicators):
            if i + 1 < step:  # Completed
                circle.config(text="OK", bg=ACCENT, fg=BG)
                label.config(fg=ACCENT)
            elif i + 1 == step:  # Current
                circle.config(text=str(i + 1), bg=ACCENT, fg=BG)
                label.config(fg=WHITE)
            else:  # Future
                circle.config(text=str(i + 1), bg=GRAY, fg=BG)
                label.config(fg=GRAY)

    # ── Step 1: Key ────────────────────────────────────────────

    def _on_key_change(self, *args):
        raw = self.key_var.get().strip().replace(" ", "").replace("-", "")
        valid = len(raw) == 64 and bool(re.match(r"^[0-9a-fA-F]+$", raw))

        if valid:
            self.hex_key = raw
            self.key_status.config(text="Chave valida!", fg=ACCENT)
            self.btn_step1_next.config(state="normal")
        else:
            count = len(raw)
            self.key_status.config(
                text=f"{count}/64 caracteres", fg=GRAY if count < 64 else RED
            )
            self.btn_step1_next.config(state="disabled")

    def _step1_next(self):
        self._show_step(2)

    # ── Step 2: File ───────────────────────────────────────────

    def _set_crypt15_path(self, path: str):
        if not path:
            return
        # Clean path (tkinterdnd2 may wrap in braces on Windows)
        path = path.strip().strip("{}")
        if not os.path.exists(path):
            self.file_status.config(text=f"Arquivo nao encontrado: {path}", fg=RED)
            return
        self.crypt15_path = path
        size_mb = os.path.getsize(path) / (1024 * 1024)
        name = os.path.basename(path)
        self.file_status.config(
            text=f"Selecionado: {name} ({size_mb:.1f} MB)", fg=ACCENT
        )
        self.drop_zone.config(text=f"{name}\n({size_mb:.1f} MB)", fg=ACCENT)
        self.btn_step2_next.config(state="normal")

    def _on_file_drop(self, event):
        self._set_crypt15_path(event.data)

    def _on_drag_enter(self, event):
        self.drop_zone.config(bg="#1A3D33")

    def _on_drag_leave(self, event):
        self.drop_zone.config(bg=BG_DARK)

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Selecionar backup do WhatsApp",
            filetypes=[
                ("WhatsApp Backup", "*.crypt15 *.crypt14"),
                ("Todos os arquivos", "*.*"),
            ]
        )
        if path:
            self._set_crypt15_path(path)

    def _pull_via_adb(self):
        if self.is_running:
            return
        self.is_running = True
        self.file_status.config(text="Conectando via USB...", fg=GOLD)
        thread = threading.Thread(target=self._run_adb_pull, daemon=True)
        thread.start()

    def _run_adb_pull(self):
        try:
            output_dir = os.path.join(os.path.dirname(__file__), "backup_temp")
            puller = ADBFilePull(
                adb_path=resource_path(os.path.join("adb", "adb.exe")),
                log_callback=lambda msg: self.root.after(
                    0, lambda m=msg: self.file_status.config(text=m, fg=GOLD)
                )
            )
            path = puller.pull_crypt15(output_dir)
            self.root.after(0, lambda: self._set_crypt15_path(path))
        except ADBError as e:
            self.root.after(
                0, lambda: self.file_status.config(text=str(e), fg=RED)
            )
        finally:
            self.is_running = False

    def _step2_next(self):
        self._show_step(3)

    # ── Step 3: Extract & Upload ───────────────────────────────

    def _log(self, message: str):
        def _append():
            self.log_area.config(state="normal")
            self.log_area.insert("end", message + "\n")
            self.log_area.see("end")
            self.log_area.config(state="disabled")
        self.root.after(0, _append)

    def _start_extraction(self):
        if self.is_running:
            return
        self.is_running = True
        self.btn_extract.config(state="disabled")
        self.btn_upload.config(state="disabled")
        self.summary_frame.pack_forget()
        thread = threading.Thread(target=self._run_extraction, daemon=True)
        thread.start()

    def _run_extraction(self):
        try:
            # Phase 1: Decrypt
            self.root.after(0, lambda: self.progress_label.config(
                text="Descriptografando backup...", fg=GOLD
            ))
            self._log("Descriptografando backup...")

            output_dir = os.path.join(os.path.dirname(__file__), "backup_temp")
            os.makedirs(output_dir, exist_ok=True)
            db_path = os.path.join(output_dir, "msgstore.db")

            decrypt_crypt15(self.hex_key, self.crypt15_path, db_path)
            self._log("Backup descriptografado com sucesso!")

            # Phase 2: Parse
            self.root.after(0, lambda: self.progress_label.config(
                text="Lendo conversas...", fg=GOLD
            ))
            self._log("\nLendo banco de dados...")

            def progress_cb(current, total, name):
                self.root.after(0, lambda c=current, t=total: (
                    self.progress_bar.config(value=c / t * 100),
                    self.progress_label.config(text=f"Lendo: {name} ({c}/{t})")
                ))
                self._log(f"  [{current}/{total}] {name}")

            self.conversations = parse_msgstore(db_path, progress_callback=progress_cb)

            total_msgs = sum(c["message_count"] for c in self.conversations)
            groups = sum(1 for c in self.conversations if c.get("is_group"))
            individuals = len(self.conversations) - groups

            self._log(f"\nExtracao completa!")
            self._log(f"  {len(self.conversations)} conversas")
            self._log(f"  {individuals} individuais, {groups} grupos")
            self._log(f"  {total_msgs} mensagens total")

            # Show summary
            summary_text = (
                f"  {len(self.conversations)} conversas encontradas\n"
                f"  {individuals} individuais  |  {groups} grupos\n"
                f"  {total_msgs:,} mensagens total"
            )
            self.root.after(0, lambda: (
                self.summary_label.config(text=summary_text),
                self.summary_frame.pack(fill="x", pady=(0, 10)),
                self.progress_label.config(text="Extracao completa!", fg=ACCENT),
                self.progress_bar.config(value=100),
                self.btn_upload.config(state="normal"),
            ))

            # Also save JSON locally
            json_path = os.path.join(output_dir, "conversations.json")
            Path(json_path).write_text(
                json.dumps(self.conversations, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            self._log(f"\nJSON salvo localmente: {json_path}")

        except DecryptionError as e:
            self._log(f"\nErro na descriptografia: {e}")
            self.root.after(0, lambda: self.progress_label.config(
                text=str(e), fg=RED
            ))
        except ParseError as e:
            self._log(f"\nErro ao ler banco de dados: {e}")
            self.root.after(0, lambda: self.progress_label.config(
                text=str(e), fg=RED
            ))
        except Exception as e:
            self._log(f"\nErro inesperado: {e}")
            self.root.after(0, lambda: self.progress_label.config(
                text=f"Erro: {e}", fg=RED
            ))
        finally:
            self.is_running = False
            self.root.after(0, lambda: self.btn_extract.config(state="normal"))

    def _start_upload(self):
        if self.is_running or not self.conversations:
            return
        self.is_running = True
        self.btn_upload.config(state="disabled")
        thread = threading.Thread(target=self._run_upload, daemon=True)
        thread.start()

    def _run_upload(self):
        try:
            self.root.after(0, lambda: self.progress_label.config(
                text="Enviando para o servidor...", fg=GOLD
            ))
            self._log("\nEnviando dados para o servidor...")

            result = upload_conversations(self.conversations)

            self._log(f"Envio concluido com sucesso!")
            self._log(f"Resposta do servidor: {json.dumps(result, indent=2)}")
            self.root.after(0, lambda: self.progress_label.config(
                text="Enviado com sucesso!", fg=ACCENT
            ))

        except UploadError as e:
            self._log(f"\nErro no envio: {e}")
            self.root.after(0, lambda: (
                self.progress_label.config(text=str(e), fg=RED),
                self.btn_upload.config(state="normal"),
            ))
        except Exception as e:
            self._log(f"\nErro inesperado: {e}")
            self.root.after(0, lambda: (
                self.progress_label.config(text=f"Erro: {e}", fg=RED),
                self.btn_upload.config(state="normal"),
            ))
        finally:
            self.is_running = False

    # ── Run ────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = BackupExtractorApp()
    app.run()
