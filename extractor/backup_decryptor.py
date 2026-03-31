"""
Decrypt WhatsApp Business crypt15 backup using a 64-digit hex key.
Uses wa-crypt-tools library.
"""

import re
import sqlite3
import tempfile
from pathlib import Path

from wa_crypt_tools.lib.db.dbfactory import DatabaseFactory
from wa_crypt_tools.lib.key.keyfactory import KeyFactory


class DecryptionError(Exception):
    """Raised when decryption fails."""
    pass


def validate_hex_key(hex_key: str) -> str:
    """Validate and normalize a 64-character hex key."""
    cleaned = hex_key.strip().replace(" ", "").replace("-", "")
    if len(cleaned) != 64:
        raise DecryptionError(
            f"A chave deve ter 64 caracteres hexadecimais (tem {len(cleaned)})."
        )
    if not re.match(r"^[0-9a-fA-F]{64}$", cleaned):
        raise DecryptionError("A chave contem caracteres invalidos. Use apenas 0-9 e A-F.")
    return cleaned


def decrypt_crypt15(hex_key: str, crypt15_path: str, output_path: str = None) -> str:
    """
    Decrypt a crypt15 backup file.

    Args:
        hex_key: 64-character hex string (the E2E backup key)
        crypt15_path: Path to the .crypt15 file
        output_path: Where to save decrypted msgstore.db (auto-generated if None)

    Returns:
        Path to the decrypted msgstore.db file.

    Raises:
        DecryptionError: If decryption fails for any reason.
    """
    hex_key = validate_hex_key(hex_key)

    crypt15 = Path(crypt15_path)
    if not crypt15.exists():
        raise DecryptionError(f"Arquivo nao encontrado: {crypt15_path}")
    if crypt15.stat().st_size == 0:
        raise DecryptionError("Arquivo de backup esta vazio.")

    if output_path is None:
        output_path = str(crypt15.parent / "msgstore.db")

    try:
        # Build key from hex string
        key_bytes = bytes.fromhex(hex_key)
        # Write to temp file for KeyFactory (expects file path)
        key_tmp = Path(tempfile.mktemp(suffix=".key"))
        key_tmp.write_bytes(key_bytes)

        try:
            key = KeyFactory.new(key_tmp)
        finally:
            key_tmp.unlink(missing_ok=True)

        # Read and decrypt
        with open(crypt15_path, "rb") as f:
            db = DatabaseFactory.from_file(f)
            f.seek(0)
            encrypted = f.read()

        decrypted = db.decrypt(key=key, encrypted=encrypted)

        # Write decrypted database
        Path(output_path).write_bytes(decrypted)

    except DecryptionError:
        raise
    except Exception as e:
        err_msg = str(e).lower()
        if "tag" in err_msg or "authentication" in err_msg or "mac" in err_msg:
            raise DecryptionError(
                "Chave incorreta. Verifique se copiou os 64 digitos corretamente."
            ) from e
        if "crypt12" in err_msg or "crypt14" in err_msg:
            raise DecryptionError(
                "Este arquivo usa um formato antigo. "
                "Ative o backup criptografado de ponta a ponta no WhatsApp."
            ) from e
        raise DecryptionError(f"Erro na descriptografia: {e}") from e

    # Validate output is a real SQLite database
    try:
        conn = sqlite3.connect(output_path)
        conn.execute("SELECT count(*) FROM sqlite_master")
        conn.close()
    except sqlite3.Error as e:
        raise DecryptionError(
            f"Arquivo descriptografado nao e um banco de dados valido: {e}"
        ) from e

    return output_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Uso: python backup_decryptor.py <hex_key_64chars> <arquivo.crypt15>")
        sys.exit(1)
    result = decrypt_crypt15(sys.argv[1], sys.argv[2])
    print(f"Descriptografado com sucesso: {result}")
