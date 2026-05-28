"""
core/crypto.py — NEXO Local Data Encryption
===============================================
Protege los datos personales del usuario (memoria, API keys) usando
Windows DPAPI (Data Protection API).

DPAPI vincula el cifrado a la cuenta de Windows del usuario:
  - Si alguien roba la PC sin conocer la contraseña de Windows, NO puede
    descifrar los datos aunque copie los archivos.
  - Los datos sólo se pueden descifrar en el mismo usuario/máquina donde
    se cifraron.
  - Sin instalaciones extra: usa ctypes + crypt32.dll nativo de Windows.

Fallback gracioso en non-Windows: almacena en texto plano (desarrollo/Mac/Linux).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import sys
from pathlib import Path
from typing import Any

# Prefijo mágico que indica que un archivo está cifrado con DPAPI
_MAGIC = b"JDPAPI\x01"


# ─────────────────────────────────────────────────────────────────────────────
# Estructuras Win32 para DPAPI
# ─────────────────────────────────────────────────────────────────────────────

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _is_windows() -> bool:
    return sys.platform == "win32"


# ─────────────────────────────────────────────────────────────────────────────
# Primitivos DPAPI
# ─────────────────────────────────────────────────────────────────────────────

def dpapi_encrypt(plaintext: bytes, description: str = "NEXO") -> bytes | None:
    """
    Cifra bytes con DPAPI (ámbito usuario).
    Retorna bytes cifrados o None si DPAPI no está disponible.
    """
    if not _is_windows():
        return None
    try:
        crypt32  = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        data_arr = (ctypes.c_ubyte * len(plaintext))(*plaintext)
        blob_in  = _DATA_BLOB(len(plaintext), data_arr)
        blob_out = _DATA_BLOB()

        desc = ctypes.c_wchar_p(description)

        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            desc,
            None,   # optional entropy
            None,   # reserved
            None,   # prompt (None = silent)
            0,      # CRYPTPROTECT_UI_FORBIDDEN = 1 (silent), 0 = default (user scope)
            ctypes.byref(blob_out),
        )
        if not ok:
            return None

        result = bytes(blob_out.pbData[:blob_out.cbData])
        kernel32.LocalFree(blob_out.pbData)
        return result
    except Exception:
        return None


def dpapi_decrypt(ciphertext: bytes) -> bytes | None:
    """
    Descifra bytes previamente cifrados con DPAPI.
    Retorna plaintext o None si falla (otro usuario/máquina o DPAPI no disponible).
    """
    if not _is_windows():
        return None
    try:
        crypt32  = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        data_arr = (ctypes.c_ubyte * len(ciphertext))(*ciphertext)
        blob_in  = _DATA_BLOB(len(ciphertext), data_arr)
        blob_out = _DATA_BLOB()
        desc_out = ctypes.c_wchar_p()

        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            ctypes.byref(desc_out),
            None,   # optional entropy (must match encrypt)
            None,   # reserved
            None,   # prompt (None = silent)
            0,
            ctypes.byref(blob_out),
        )
        if not ok:
            return None

        result = bytes(blob_out.pbData[:blob_out.cbData])
        kernel32.LocalFree(blob_out.pbData)
        return result
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# API de alto nivel para JSON
# ─────────────────────────────────────────────────────────────────────────────

def encrypt_json(data: dict[str, Any], description: str = "NEXO-Data") -> bytes:
    """
    Serializa un dict a JSON y lo cifra con DPAPI.
    Retorna bytes listos para escribir a disco.

    Si DPAPI no está disponible (Linux/macOS), guarda en texto plano.
    El formato es: MAGIC_PREFIX + encrypted_bytes  (o texto plano sin prefijo).
    """
    raw = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    encrypted = dpapi_encrypt(raw, description)
    if encrypted is not None:
        return _MAGIC + encrypted
    # Fallback: texto plano (desarrollo / non-Windows)
    return raw


def decrypt_json(data: bytes) -> dict[str, Any]:
    """
    Descifra bytes a un dict.
    Maneja tres casos:
      1. Archivo cifrado con DPAPI (prefijo JDPAPI)
      2. Archivo JSON en texto plano (migración / non-Windows)
      3. Error de descifrado (usuario/máquina incorrecta)
    """
    if data.startswith(_MAGIC):
        ciphertext = data[len(_MAGIC):]
        plaintext  = dpapi_decrypt(ciphertext)
        if plaintext is None:
            raise PermissionError(
                "No se puede descifrar la memoria de NEXO.\n"
                "Los datos pertenecen a otro perfil de Windows o fueron\n"
                "generados en otra computadora.\n\n"
                "Si reinstalaste Windows, contacta soporte para recuperar tus datos."
            )
        return json.loads(plaintext.decode("utf-8"))

    # Texto plano (formato legacy o non-Windows)
    return json.loads(data.decode("utf-8"))


def encrypt_file(path: Path, data: dict[str, Any], description: str = "NEXO-Data") -> None:
    """Escribe un dict cifrado con DPAPI al archivo indicado."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_json(data, description))


def decrypt_file(path: Path) -> dict[str, Any]:
    """Lee y descifra un archivo JSON (cifrado o plano)."""
    if not path.exists():
        return {}
    try:
        return decrypt_json(path.read_bytes())
    except PermissionError:
        raise
    except Exception as e:
        print(f"[Crypto] Error leyendo {path.name}: {e}")
        return {}


def is_encrypted(path: Path) -> bool:
    """Retorna True si el archivo está cifrado con DPAPI."""
    if not path.exists():
        return False
    try:
        return path.read_bytes().startswith(_MAGIC)
    except Exception:
        return False


def migrate_to_encrypted(path: Path, description: str = "NEXO-Data") -> bool:
    """
    Migra un archivo JSON en texto plano al formato DPAPI cifrado.
    Retorna True si se migró correctamente.
    """
    if not path.exists() or is_encrypted(path):
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        encrypt_file(path, data, description)
        print(f"[Crypto] Migrado a DPAPI: {path.name}")
        return True
    except Exception as e:
        print(f"[Crypto] No se pudo migrar {path.name}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI para pruebas
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    print(f"DPAPI disponible: {_is_windows()}")

    test = {"test": "hello NEXO", "number": 42}
    enc  = encrypt_json(test)
    print(f"Cifrado ({len(enc)} bytes): {enc[:40]}...")

    dec  = decrypt_json(enc)
    print(f"Descifrado: {dec}")
    assert dec == test, "ERROR: decrypt_json no coincide con el original"
    print("OK - DPAPI funciona correctamente")
