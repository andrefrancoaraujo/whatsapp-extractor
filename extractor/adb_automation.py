"""
ADB UI Automation for WhatsApp Business chat export.
Uses uiautomator dumps to find elements dynamically (works on any screen size).
"""

import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from config import (
    WHATSAPP_PACKAGE, WHATSAPP_MAIN, EXPORT_DIR, UI_DUMP_PATH,
    STRINGS, SCROLL_PAUSE, TAP_PAUSE, LOAD_PAUSE,
)


class ADBError(Exception):
    pass


class ADBAutomation:
    def __init__(self, adb_path: str = "adb", log_callback=None, device_serial=None,
                 server_url=None):
        self.adb = adb_path
        self.log = log_callback or print
        self.device_serial = device_serial
        self.server_url = server_url
        self.screen_width = 1080
        self.screen_height = 2340
        self.temp_dir = Path("temp_ui")
        self.temp_dir.mkdir(exist_ok=True)
        self.screenshots_dir = Path("diagnostics")
        self.screenshots_dir.mkdir(exist_ok=True)
        self._diag_counter = 0

    # ── Diagnostics ───────────────────────────────────────────────

    def capture_screenshot(self, label: str = "") -> Optional[str]:
        """Capture a screenshot from the device and save locally."""
        try:
            self._diag_counter += 1
            safe_label = re.sub(r'[^\w\-]', '_', label)[:50]
            filename = f"diag_{self._diag_counter:03d}_{safe_label}.png"
            remote = "/sdcard/diag_screen.png"
            local_path = str(self.screenshots_dir / filename)
            self.shell(f"screencap -p {remote}")
            self.run("pull", remote, local_path)
            self.shell(f"rm {remote}")
            return local_path
        except Exception as e:
            self.log(f"  [diag] Screenshot failed: {e}")
            return None

    def capture_ui_dump_diag(self, label: str = "") -> Optional[str]:
        """Save a copy of the UI dump for diagnostics."""
        try:
            safe_label = re.sub(r'[^\w\-]', '_', label)[:50]
            filename = f"diag_{self._diag_counter:03d}_{safe_label}_ui.xml"
            local_path = str(self.screenshots_dir / filename)
            self.shell(f"uiautomator dump {UI_DUMP_PATH}")
            time.sleep(0.5)
            self.run("pull", UI_DUMP_PATH, local_path)
            return local_path
        except Exception:
            return None

    def upload_diagnostics(self):
        """Upload all diagnostic files to the server."""
        if not self.server_url:
            return
        try:
            import requests
            diag_files = list(self.screenshots_dir.glob("diag_*"))
            if not diag_files:
                self.log("  [diag] No diagnostic files to upload.")
                return
            files_to_send = []
            for f in diag_files:
                files_to_send.append(
                    ("files", (f.name, open(f, "rb"), "application/octet-stream"))
                )
            url = self.server_url.replace("/whatsapp-upload", "/whatsapp-diagnostics")
            resp = requests.post(url, files=files_to_send, timeout=60)
            if resp.status_code == 200:
                self.log(f"  [diag] {len(diag_files)} diagnostic files uploaded.")
            else:
                self.log(f"  [diag] Upload returned HTTP {resp.status_code}")
        except Exception as e:
            self.log(f"  [diag] Upload failed: {e}")
            self.log(f"  [diag] Files saved locally in: {self.screenshots_dir.absolute()}")

    # ── ADB primitives ──────────────────────────────────────────────

    def run(self, *args, timeout=30) -> str:
        cmd = [self.adb]
        # Add -s flag for device-specific commands (not for server/pair/connect commands)
        skip_serial = args and args[0] in ("kill-server", "start-server", "pair", "connect", "disconnect", "devices")
        if self.device_serial and not skip_serial:
            cmd += ["-s", self.device_serial]
        cmd += list(args)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            output = result.stdout.strip()
            err = result.stderr.strip()
            if err:
                self.log(f"  [adb stderr] {err}")
            if not output and err:
                return err
            return output
        except subprocess.TimeoutExpired:
            raise ADBError(f"Timeout: {' '.join(cmd)}")
        except FileNotFoundError:
            raise ADBError(f"ADB not found at: {self.adb}")

    def shell(self, command: str, timeout=30) -> str:
        return self.run("shell", command, timeout=timeout)

    def check_device(self) -> bool:
        output = self.run("devices")
        lines = [l for l in output.splitlines() if "\tdevice" in l]
        if not lines:
            return False
        # Get screen dimensions
        size_out = self.shell("wm size")
        match = re.search(r"(\d+)x(\d+)", size_out)
        if match:
            self.screen_width = int(match.group(1))
            self.screen_height = int(match.group(2))
            self.log(f"Screen: {self.screen_width}x{self.screen_height}")
        return True

    def keep_screen_on(self):
        """Prevent screen from turning off during automation."""
        self.log("Keeping screen awake...")
        # Disable screen timeout (set to 30 min = 1800000ms)
        self.shell("settings put system screen_off_timeout 1800000")
        # Wake screen if it's off
        self.wake_screen()
        # Keep screen on while charging/USB
        self.shell("svc power stayon true")

    def restore_screen_settings(self):
        """Restore normal screen timeout after automation."""
        self.shell("settings put system screen_off_timeout 60000")  # 1 min default
        self.shell("svc power stayon false")

    def wake_screen(self):
        """Wake the screen if it's off and unlock if no PIN/pattern."""
        # Check if screen is on
        screen_state = self.shell("dumpsys power | grep 'Display Power'")
        if "state=OFF" in screen_state:
            self.log("  Screen is OFF, waking up...")
            self.shell("input keyevent KEYCODE_WAKEUP")
            time.sleep(1)
            # Swipe up to dismiss lock screen (works on most phones without PIN)
            x = self.screen_width // 2
            self.shell(f"input swipe {x} {int(self.screen_height * 0.8)} {x} {int(self.screen_height * 0.2)} 300")
            time.sleep(1)

    def tap(self, x: int, y: int):
        self.shell(f"input tap {x} {y}")
        time.sleep(TAP_PAUSE)

    def swipe_up(self):
        """Scroll down by swiping up."""
        x = self.screen_width // 2
        y_start = int(self.screen_height * 0.7)
        y_end = int(self.screen_height * 0.3)
        self.shell(f"input swipe {x} {y_start} {x} {y_end} 300")
        time.sleep(SCROLL_PAUSE)

    def press_back(self):
        self.shell("input keyevent KEYCODE_BACK")
        time.sleep(TAP_PAUSE)

    def press_home(self):
        self.shell("input keyevent KEYCODE_HOME")

    # ── UI analysis ─────────────────────────────────────────────────

    def dump_ui(self) -> Optional[ET.Element]:
        """Dump current UI hierarchy and parse it."""
        self.shell(f"uiautomator dump {UI_DUMP_PATH}")
        time.sleep(0.5)
        local_path = self.temp_dir / "ui_dump.xml"
        self.run("pull", UI_DUMP_PATH, str(local_path))
        try:
            tree = ET.parse(local_path)
            return tree.getroot()
        except ET.ParseError:
            self.log("Failed to parse UI dump")
            return None

    @staticmethod
    def get_bounds_center(bounds_str: str) -> tuple[int, int]:
        """Parse bounds like '[168,252][936,312]' and return center (x, y)."""
        match = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
        if len(match) == 2:
            x1, y1 = int(match[0][0]), int(match[0][1])
            x2, y2 = int(match[1][0]), int(match[1][1])
            return (x1 + x2) // 2, (y1 + y2) // 2
        return 0, 0

    def find_element(self, root: ET.Element, text: Optional[str] = None,
                     content_desc: Optional[str] = None,
                     resource_id: Optional[str] = None,
                     text_list: Optional[list] = None,
                     content_desc_list: Optional[list] = None,
                     partial_match: bool = False) -> Optional[dict]:
        """Find a UI element by various attributes."""
        for node in root.iter("node"):
            attrib = node.attrib
            node_text = attrib.get("text", "")
            node_desc = attrib.get("content-desc", "")
            node_rid = attrib.get("resource-id", "")

            matched = False

            if text and text.lower() == node_text.lower():
                matched = True
            if content_desc and content_desc.lower() == node_desc.lower():
                matched = True
            if resource_id and resource_id in node_rid:
                matched = True
            if text_list:
                for t in text_list:
                    if partial_match and t.lower() in node_text.lower():
                        matched = True
                    elif t.lower() == node_text.lower():
                        matched = True
            if content_desc_list:
                for d in content_desc_list:
                    if partial_match and d.lower() in node_desc.lower():
                        matched = True
                    elif d.lower() == node_desc.lower():
                        matched = True

            if matched:
                bounds = attrib.get("bounds", "")
                cx, cy = self.get_bounds_center(bounds)
                return {"text": node_text, "desc": node_desc, "rid": node_rid,
                        "x": cx, "y": cy, "bounds": bounds}
        return None

    def find_all_elements(self, root: ET.Element, resource_id: str) -> list[dict]:
        """Find all elements matching a resource ID."""
        results = []
        for node in root.iter("node"):
            attrib = node.attrib
            if resource_id in attrib.get("resource-id", ""):
                bounds = attrib.get("bounds", "")
                cx, cy = self.get_bounds_center(bounds)
                results.append({
                    "text": attrib.get("text", ""),
                    "desc": attrib.get("content-desc", ""),
                    "x": cx, "y": cy,
                    "bounds": bounds,
                })
        return results

    # ── WhatsApp-specific automation ────────────────────────────────

    def open_whatsapp(self):
        self.log("Opening WhatsApp Business...")
        self.shell(f"am start -n {WHATSAPP_PACKAGE}/{WHATSAPP_MAIN}")
        time.sleep(LOAD_PAUSE)

    def get_conversation_names(self) -> list[dict]:
        """Get all visible conversations from the chat list."""
        root = self.dump_ui()
        if root is None:
            return []

        # WhatsApp Business uses this resource-id for contact names
        convos = self.find_all_elements(root, "conversations_row_contact_name")
        if not convos:
            # Fallback: try alternative resource IDs
            convos = self.find_all_elements(root, "contactpic_container")
        return convos

    def scroll_and_collect_conversations(self) -> list[dict]:
        """Scroll through the entire conversation list and collect all contacts."""
        all_convos = {}
        max_scrolls = 50
        no_new_count = 0

        for i in range(max_scrolls):
            convos = self.get_conversation_names()
            new_found = 0
            for c in convos:
                name = c["text"]
                if name and name not in all_convos:
                    all_convos[name] = c
                    new_found += 1

            self.log(f"Scan {i+1}: found {new_found} new ({len(all_convos)} total)")

            if new_found == 0:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0

            self.swipe_up()

        # Scroll back to top
        for _ in range(max_scrolls):
            x = self.screen_width // 2
            y_start = int(self.screen_height * 0.3)
            y_end = int(self.screen_height * 0.7)
            self.shell(f"input swipe {x} {y_start} {x} {y_end} 200")
            time.sleep(0.3)

        time.sleep(1)
        return list(all_convos.values())

    def export_single_chat(self, contact_name: str, diagnostic_mode: bool = False) -> bool:
        """Export a single chat by navigating to it and using the export function.
        In diagnostic_mode, captures screenshots at every step for remote debugging."""
        self.log(f"Exporting: {contact_name}")

        def diag(label):
            if diagnostic_mode:
                self.capture_screenshot(label)
                self.capture_ui_dump_diag(label)

        # Step 1: Find and tap the conversation
        root = self.dump_ui()
        if root is None:
            diag("step1_no_ui_dump")
            return False

        diag("step1_chat_list")

        elem = self.find_element(root, text=contact_name)
        if not elem:
            # Try partial match (WhatsApp sometimes truncates names)
            elem = self.find_element(root, text_list=[contact_name], partial_match=True)
        if not elem:
            # Try scrolling to find it
            found = False
            for scroll_i in range(30):
                self.swipe_up()
                root = self.dump_ui()
                if root:
                    elem = self.find_element(root, text=contact_name)
                    if not elem:
                        elem = self.find_element(root, text_list=[contact_name], partial_match=True)
                    if elem:
                        found = True
                        break
            if not found:
                self.log(f"  Could not find conversation: {contact_name}")
                diag("step1_not_found")
                return False

        self.tap(elem["x"], elem["y"])
        time.sleep(LOAD_PAUSE)

        # Step 2: Tap 3-dot menu
        root = self.dump_ui()
        if root is None:
            diag("step2_no_ui_dump")
            self.press_back()
            return False

        diag("step2_inside_chat")

        menu_btn = self.find_element(root, content_desc_list=STRINGS["more_options"])
        if not menu_btn:
            # Fallback: look by resource-id patterns common in WhatsApp
            menu_btn = self.find_element(root, resource_id="menu_overflow")
            if not menu_btn:
                menu_btn = self.find_element(root, resource_id="action_overflow")
        if not menu_btn:
            # Last fallback: tap top-right corner where menu usually is
            self.log("  [fallback] Tapping top-right for menu")
            menu_btn = {"x": self.screen_width - 60, "y": 80}
        self.tap(menu_btn["x"], menu_btn["y"])

        # Step 3: Find "Export chat" (may be nested under "More")
        time.sleep(TAP_PAUSE)
        root = self.dump_ui()
        if root is None:
            diag("step3_no_ui_dump")
            self.press_back()
            self.press_back()
            return False

        diag("step3_menu_open")

        export_btn = self.find_element(root, text_list=STRINGS["export_chat"], partial_match=True)
        if not export_btn:
            # Try "More" submenu first
            more_btn = self.find_element(root, text_list=STRINGS["more"])
            if more_btn:
                self.tap(more_btn["x"], more_btn["y"])
                time.sleep(TAP_PAUSE)
                root = self.dump_ui()
                diag("step3_more_submenu")
                if root:
                    export_btn = self.find_element(root, text_list=STRINGS["export_chat"], partial_match=True)

        if not export_btn:
            # Try content-desc as well (some WA versions use it)
            if root:
                export_btn = self.find_element(root, content_desc_list=STRINGS["export_chat"], partial_match=True)

        if not export_btn:
            self.log(f"  Could not find 'Export chat' for: {contact_name}")
            diag("step3_export_not_found")
            self.press_back()
            self.press_back()
            return False

        self.tap(export_btn["x"], export_btn["y"])
        time.sleep(LOAD_PAUSE)

        # Step 4: Tap "Without media"
        root = self.dump_ui()
        diag("step4_media_choice")

        if root:
            no_media = self.find_element(root, text_list=STRINGS["without_media"], partial_match=True)
            if no_media:
                self.tap(no_media["x"], no_media["y"])
                time.sleep(LOAD_PAUSE)
            else:
                self.log("  [warn] 'Without media' button not found, trying to continue...")
                diag("step4_no_media_btn")

        # Step 5: Handle share sheet - try to save to Files/Downloads
        diag("step5_share_sheet")
        success = self._handle_share_sheet(contact_name, diagnostic_mode)

        # Step 6: Go back to chat list
        time.sleep(1)
        self.press_back()
        time.sleep(0.5)
        self.press_back()
        time.sleep(0.5)
        self.press_back()
        time.sleep(1)

        # Make sure we're back at the chat list
        self._ensure_chat_list()

        if not success:
            diag("step6_failed_back_to_list")

        return success

    def _handle_share_sheet(self, contact_name: str, diagnostic_mode: bool = False) -> bool:
        """Handle the Android share sheet - save the export file."""
        root = self.dump_ui()
        if root is None:
            return False

        # Strategy 1: Look for "Files" / "Arquivos" / "Save to" in share sheet
        files_btn = self.find_element(
            root,
            text_list=STRINGS["files"],
            content_desc_list=STRINGS["files"],
            partial_match=True
        )

        if files_btn:
            self.tap(files_btn["x"], files_btn["y"])
            time.sleep(LOAD_PAUSE)

            # Try to navigate to Downloads folder
            root = self.dump_ui()
            if root:
                dl_btn = self.find_element(root, text_list=STRINGS["downloads"], partial_match=True)
                if dl_btn:
                    self.tap(dl_btn["x"], dl_btn["y"])
                    time.sleep(TAP_PAUSE)

                # Tap Save button
                root = self.dump_ui()
                if root:
                    save_btn = self.find_element(root, text_list=STRINGS["save"])
                    if save_btn:
                        self.tap(save_btn["x"], save_btn["y"])
                        self.log(f"  Saved: {contact_name}")
                        return True

        # Strategy 2: Look for Gmail/Email as fallback
        email_btn = self.find_element(root, text_list=["Gmail", "Email", "E-mail"],
                                       content_desc_list=["Gmail", "Email"], partial_match=True)
        if email_btn:
            self.tap(email_btn["x"], email_btn["y"])
            time.sleep(LOAD_PAUSE)
            # Would need to enter email address - skip for now
            self.log(f"  Gmail found but skipping auto-send for: {contact_name}")
            self.press_back()

        # Strategy 3: Look for any "Save" or "Download" option
        root = self.dump_ui()
        if root:
            # Scroll the share sheet to find more options
            self.swipe_up()
            root = self.dump_ui()
            if root:
                save_any = self.find_element(
                    root,
                    text_list=["Salvar", "Save", "Download", "Baixar"],
                    partial_match=True
                )
                if save_any:
                    self.tap(save_any["x"], save_any["y"])
                    time.sleep(LOAD_PAUSE)
                    self.log(f"  Saved (fallback): {contact_name}")
                    return True

        self.log(f"  Could not save export for: {contact_name}")
        return False

    def _ensure_chat_list(self):
        """Make sure we're back at the WhatsApp chat list screen."""
        root = self.dump_ui()
        if root is None:
            self.open_whatsapp()
            return

        # Check if we see the conversation list
        convos = self.find_all_elements(root, "conversations_row_contact_name")
        if not convos:
            # We're not at the chat list, keep pressing back
            for _ in range(5):
                self.press_back()
                time.sleep(0.5)
                root = self.dump_ui()
                if root:
                    convos = self.find_all_elements(root, "conversations_row_contact_name")
                    if convos:
                        return
            # Last resort: reopen WhatsApp
            self.open_whatsapp()

    def pull_exported_files(self, local_dir: str) -> list[str]:
        """Pull all exported .txt files from the phone's Download folder."""
        os.makedirs(local_dir, exist_ok=True)

        # List .txt files in Download
        output = self.shell("ls /sdcard/Download/*.txt 2>/dev/null")
        if not output or "No such file" in output:
            # Also check for WhatsApp chat exports specifically
            output = self.shell('ls /sdcard/Download/WhatsApp*.txt 2>/dev/null')

        if not output or "No such file" in output:
            self.log("No exported files found in Downloads.")
            return []

        files = [f.strip() for f in output.splitlines() if f.strip()]
        pulled = []

        for remote_path in files:
            filename = os.path.basename(remote_path)
            if "WhatsApp" in filename or "Chat" in filename:
                local_path = os.path.join(local_dir, filename)
                self.run("pull", remote_path, local_path)
                pulled.append(local_path)
                self.log(f"  Pulled: {filename}")

        return pulled

    # ── Progress tracking ─────────────────────────────────────────

    PROGRESS_FILE = "export_progress.json"

    def _load_progress(self) -> dict:
        """Load progress from previous runs."""
        import json
        if os.path.exists(self.PROGRESS_FILE):
            try:
                with open(self.PROGRESS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"exported": [], "failed": [], "batch_completed": 0}

    def _save_progress(self, progress: dict):
        """Save progress after each successful export."""
        import json
        with open(self.PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)

    # ── Test single export (diagnostic) ─────────────────────────────

    def run_test_export(self, progress_callback=None) -> bool:
        """Test export of ONE conversation with full diagnostics.
        Captures screenshots at every step and uploads them to the server."""

        self.log("="*50)
        self.log("MODO TESTE — Exportando 1 conversa com diagnostico")
        self.log("="*50)

        # 1. Check device
        if not self.check_device():
            raise ADBError("No device connected.")

        # 1b. Keep screen awake and wake if needed
        self.keep_screen_on()

        # 2. Open WhatsApp
        self.open_whatsapp()

        # 3. Get first visible conversation
        self.log("Scanning conversations...")
        convos = self.get_conversation_names()
        if not convos:
            self.capture_screenshot("test_no_conversations")
            self.capture_ui_dump_diag("test_no_conversations")
            self.upload_diagnostics()
            raise ADBError("No conversations found on screen.")

        # Pick the first conversation with a name
        target = None
        for c in convos:
            if c["text"]:
                target = c["text"]
                break

        if not target:
            self.capture_screenshot("test_no_named_conversations")
            self.upload_diagnostics()
            raise ADBError("No named conversations found.")

        self.log(f"Testing with: {target}")

        if progress_callback:
            progress_callback(1, 1, target)

        # 4. Run export with full diagnostics
        success = self.export_single_chat(target, diagnostic_mode=True)

        # 5. Try to pull files
        if success:
            pulled = self.pull_exported_files("exported_chats")
            self.log(f"\nTEST SUCCESS! Pulled {len(pulled)} file(s).")
        else:
            self.log(f"\nTEST FAILED for '{target}'.")
            self.log("Diagnostic screenshots captured.")

        # 6. Upload diagnostics either way
        self.upload_diagnostics()

        return success

    # ── Main orchestration ──────────────────────────────────────────

    def run_full_export(self, progress_callback=None, batch_callback=None,
                        num_batches=5, batch_pause=10) -> list[str]:
        """Run the complete export process with batch support and resume."""

        # 1. Check device
        if not self.check_device():
            raise ADBError("No device connected. Check USB cable and USB debugging.")

        # 1b. Keep screen awake and wake if needed
        self.keep_screen_on()

        # 2. Create export directory on device
        self.shell(f"mkdir -p {EXPORT_DIR}")

        # 3. Load progress from previous runs
        progress = self._load_progress()
        already_exported = set(progress["exported"])
        if already_exported:
            self.log(f"Resuming: {len(already_exported)} conversations already exported.")

        # 4. Open WhatsApp Business
        self.open_whatsapp()

        # 5. Collect all conversations
        self.log("Scanning conversations...")
        conversations = self.scroll_and_collect_conversations()
        self.log(f"Found {len(conversations)} conversations total.")

        if not conversations:
            raise ADBError("No conversations found. Is WhatsApp Business open?")

        # 6. Filter out already exported
        pending = [c for c in conversations if c["text"] and c["text"] not in already_exported]
        self.log(f"Pending: {len(pending)} conversations to export.")

        if not pending:
            self.log("All conversations already exported!")
            self.log("\nPulling files from phone...")
            return self.pull_exported_files("exported_chats")

        # 7. Divide into batches
        batch_size = max(1, len(pending) // num_batches + (1 if len(pending) % num_batches else 0))
        batches = [pending[i:i + batch_size] for i in range(0, len(pending), batch_size)]
        self.log(f"Split into {len(batches)} batches of ~{batch_size} conversations each.")

        total_exported = len(already_exported)
        total_conversations = len(conversations)

        for batch_idx, batch in enumerate(batches):
            batch_num = batch_idx + 1
            self.log(f"\n{'='*50}")
            self.log(f"BATCH {batch_num}/{len(batches)} — {len(batch)} conversations")
            self.log(f"{'='*50}")

            if batch_callback:
                batch_callback(batch_num, len(batches))

            for i, convo in enumerate(batch):
                name = convo["text"]
                if not name:
                    continue

                if progress_callback:
                    progress_callback(total_exported + i + 1, total_conversations, name)

                # Scroll back to top every 10 exports to reset position
                if i > 0 and i % 10 == 0:
                    self._ensure_chat_list()
                    self._scroll_to_top()

                try:
                    success = self.export_single_chat(name)
                    if success:
                        progress["exported"].append(name)
                        self._save_progress(progress)
                    else:
                        if name not in progress["failed"]:
                            progress["failed"].append(name)
                            self._save_progress(progress)
                except Exception as e:
                    self.log(f"  Error exporting {name}: {e}")
                    if name not in progress["failed"]:
                        progress["failed"].append(name)
                        self._save_progress(progress)

            # Update batch counter
            total_exported += len(batch)
            progress["batch_completed"] = batch_num
            self._save_progress(progress)

            # Pull files after each batch
            self.log(f"\nBatch {batch_num} done. Pulling files...")
            self.pull_exported_files("exported_chats")

            # Pause between batches (except after last)
            if batch_idx < len(batches) - 1:
                self.log(f"Pausing {batch_pause}s before next batch...")
                time.sleep(batch_pause)
                # Re-open WhatsApp to ensure clean state
                self.open_whatsapp()
                time.sleep(2)

        # 8. Final summary
        exported_count = len(progress["exported"])
        failed_count = len(progress["failed"])
        self.log(f"\n{'='*50}")
        self.log(f"EXPORT COMPLETE")
        self.log(f"  Exported: {exported_count}/{total_conversations}")
        self.log(f"  Failed: {failed_count}")
        if progress["failed"]:
            self.log(f"  Failed names: {', '.join(progress['failed'][:20])}")
        self.log(f"  Progress saved to: {self.PROGRESS_FILE}")
        self.log(f"{'='*50}")

        # 9. Final pull
        self.log("\nFinal pull of all files...")
        pulled = self.pull_exported_files("exported_chats")
        return pulled

    def _scroll_to_top(self):
        """Scroll the conversation list back to the top."""
        for _ in range(20):
            x = self.screen_width // 2
            y_start = int(self.screen_height * 0.3)
            y_end = int(self.screen_height * 0.7)
            self.shell(f"input swipe {x} {y_start} {x} {y_end} 150")
            time.sleep(0.2)
        time.sleep(1)
