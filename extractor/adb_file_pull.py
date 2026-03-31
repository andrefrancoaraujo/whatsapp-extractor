"""
Simplified ADB module — only pulls backup files from device.
No UI automation, no screen scraping.
"""

import os
import subprocess
import sys
from pathlib import Path

from config import CRYPT15_PATH, CRYPT15_GLOB


class ADBError(Exception):
    pass


def _default_adb_path() -> str:
    """Find bundled ADB or system ADB."""
    # PyInstaller bundle
    if hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, "adb", "adb.exe")
        if os.path.exists(bundled):
            return bundled
    # Local adb directory
    local = os.path.join(os.path.dirname(__file__), "..", "adb", "adb.exe")
    if os.path.exists(local):
        return os.path.abspath(local)
    # System PATH
    return "adb"


class ADBFilePull:
    def __init__(self, adb_path: str = None, log_callback=None):
        self.adb = adb_path or _default_adb_path()
        self.log = log_callback or print

    def _run(self, *args, timeout=30) -> str:
        cmd = [self.adb] + list(args)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            raise ADBError(f"Comando ADB expirou: {' '.join(args)}")
        except FileNotFoundError:
            raise ADBError(f"ADB nao encontrado em: {self.adb}")

    def find_devices(self) -> list[str]:
        """List connected ADB devices. Returns list of serial numbers."""
        output = self._run("devices")
        devices = []
        for line in output.splitlines()[1:]:  # Skip "List of devices attached"
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def list_backups(self, device_serial: str = None) -> list[str]:
        """List available .crypt15 files on device."""
        args = []
        if device_serial:
            args = ["-s", device_serial]
        output = self._run(*args, "shell", "ls", "-la", CRYPT15_GLOB, timeout=10)
        files = []
        for line in output.splitlines():
            if "crypt15" in line or "crypt14" in line:
                # Extract filename from ls -la output
                parts = line.split()
                if parts:
                    files.append(parts[-1])
        if not files:
            # Try simpler ls
            output = self._run(*args, "shell", "ls", CRYPT15_GLOB, timeout=10)
            files = [l.strip() for l in output.splitlines() if l.strip() and "No such" not in l]
        return files

    def pull_crypt15(self, output_dir: str, device_serial: str = None) -> str:
        """
        Pull the crypt15 backup from device.
        Returns local path to the pulled file.
        """
        args = []
        if device_serial:
            args = ["-s", device_serial]

        self.log("Verificando dispositivo...")
        devices = self.find_devices()
        if not devices:
            raise ADBError(
                "Nenhum dispositivo conectado.\n"
                "Conecte o celular via USB e ative a Depuracao USB."
            )

        serial = device_serial or devices[0]
        self.log(f"Dispositivo encontrado: {serial}")

        self.log("Procurando backup do WhatsApp Business...")
        backups = self.list_backups(serial)
        if not backups:
            raise ADBError(
                "Arquivo de backup nao encontrado no celular.\n"
                "Verifique se o backup criptografado esta ativado no WhatsApp Business."
            )

        # Use the main msgstore.db.crypt15 (not dated backups)
        target = CRYPT15_PATH
        for f in backups:
            if f.endswith("msgstore.db.crypt15"):
                target = f
                break

        self.log(f"Copiando: {os.path.basename(target)}...")
        os.makedirs(output_dir, exist_ok=True)
        local_path = os.path.join(output_dir, "msgstore.db.crypt15")

        pull_args = ["-s", serial] if serial else []
        output = self._run(*pull_args, "pull", target, local_path, timeout=300)

        if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
            raise ADBError(
                "Falha ao copiar o arquivo.\n"
                "Tente copiar manualmente usando o gerenciador de arquivos."
            )

        size_mb = os.path.getsize(local_path) / (1024 * 1024)
        self.log(f"Copiado com sucesso! ({size_mb:.1f} MB)")
        return local_path


if __name__ == "__main__":
    puller = ADBFilePull()
    devices = puller.find_devices()
    print(f"Dispositivos: {devices}")
    if devices:
        backups = puller.list_backups(devices[0])
        print(f"Backups: {backups}")
