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
    def __init__(self, adb_path: str = "adb", log_callback=None):
        self.adb = adb_path
        self.log = log_callback or print
        self.screen_width = 1080
        self.screen_height = 2340
        self.temp_dir = Path("temp_ui")
        self.temp_dir.mkdir(exist_ok=True)

    # ── ADB primitives ──────────────────────────────────────────────

    def run(self, *args, timeout=30) -> str:
        cmd = [self.adb] + list(args)
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

    def export_single_chat(self, contact_name: str) -> bool:
        """Export a single chat by navigating to it and using the export function."""
        self.log(f"Exporting: {contact_name}")

        # Step 1: Find and tap the conversation
        root = self.dump_ui()
        if root is None:
            return False

        elem = self.find_element(root, text=contact_name)
        if not elem:
            # Try scrolling to find it
            found = False
            for _ in range(30):
                self.swipe_up()
                root = self.dump_ui()
                if root:
                    elem = self.find_element(root, text=contact_name)
                    if elem:
                        found = True
                        break
            if not found:
                self.log(f"  Could not find conversation: {contact_name}")
                return False

        self.tap(elem["x"], elem["y"])
        time.sleep(LOAD_PAUSE)

        # Step 2: Tap 3-dot menu
        root = self.dump_ui()
        if root is None:
            self.press_back()
            return False

        menu_btn = self.find_element(root, content_desc_list=STRINGS["more_options"])
        if not menu_btn:
            # Fallback: tap top-right corner where menu usually is
            menu_btn = {"x": self.screen_width - 60, "y": 80}
        self.tap(menu_btn["x"], menu_btn["y"])

        # Step 3: Tap "Mais" / "More"
        root = self.dump_ui()
        if root is None:
            self.press_back()
            self.press_back()
            return False

        # Sometimes "Export chat" is directly in the menu, sometimes under "More"
        export_btn = self.find_element(root, text_list=STRINGS["export_chat"])
        if not export_btn:
            more_btn = self.find_element(root, text_list=STRINGS["more"])
            if more_btn:
                self.tap(more_btn["x"], more_btn["y"])
                root = self.dump_ui()
                if root:
                    export_btn = self.find_element(root, text_list=STRINGS["export_chat"])

        if not export_btn:
            self.log(f"  Could not find 'Export chat' for: {contact_name}")
            self.press_back()
            self.press_back()
            return False

        self.tap(export_btn["x"], export_btn["y"])
        time.sleep(LOAD_PAUSE)

        # Step 4: Tap "Without media"
        root = self.dump_ui()
        if root:
            no_media = self.find_element(root, text_list=STRINGS["without_media"])
            if no_media:
                self.tap(no_media["x"], no_media["y"])
                time.sleep(LOAD_PAUSE)

        # Step 5: Handle share sheet - try to save to Files/Downloads
        success = self._handle_share_sheet(contact_name)

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

        return success

    def _handle_share_sheet(self, contact_name: str) -> bool:
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

    # ── Main orchestration ──────────────────────────────────────────

    def run_full_export(self, progress_callback=None) -> list[str]:
        """Run the complete export process."""

        # 1. Check device
        if not self.check_device():
            raise ADBError("No device connected. Check USB cable and USB debugging.")

        # 2. Create export directory on device
        self.shell(f"mkdir -p {EXPORT_DIR}")

        # 3. Open WhatsApp Business
        self.open_whatsapp()

        # 4. Collect all conversations
        self.log("Scanning conversations...")
        conversations = self.scroll_and_collect_conversations()
        self.log(f"Found {len(conversations)} conversations total.")

        if not conversations:
            raise ADBError("No conversations found. Is WhatsApp Business open?")

        # 5. Export each conversation
        exported = 0
        failed = []

        for i, convo in enumerate(conversations):
            name = convo["text"]
            if not name:
                continue

            if progress_callback:
                progress_callback(i + 1, len(conversations), name)

            # Scroll back to top before each export to reset position
            if i > 0 and i % 10 == 0:
                self._ensure_chat_list()
                # Scroll to top
                for _ in range(20):
                    x = self.screen_width // 2
                    y_start = int(self.screen_height * 0.3)
                    y_end = int(self.screen_height * 0.7)
                    self.shell(f"input swipe {x} {y_start} {x} {y_end} 150")
                    time.sleep(0.2)
                time.sleep(1)

            success = self.export_single_chat(name)
            if success:
                exported += 1
            else:
                failed.append(name)

        self.log(f"\nExport complete: {exported}/{len(conversations)} successful")
        if failed:
            self.log(f"Failed: {', '.join(failed)}")

        # 6. Pull exported files
        self.log("\nPulling files from phone...")
        pulled = self.pull_exported_files("exported_chats")

        return pulled
