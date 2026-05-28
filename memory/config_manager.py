import json
import sys
from pathlib import Path

# ── DPAPI encryption para API keys (protege contra robo de PC) ───────────────
try:
    from core.crypto import encrypt_file, decrypt_file, migrate_to_encrypted
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

    def decrypt_file(path):  # type: ignore[misc]
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def encrypt_file(path, data, description=""):  # type: ignore[misc]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def migrate_to_encrypted(path, description=""):  # type: ignore[misc]
        return False


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR    = get_base_dir()
CONFIG_DIR  = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "api_keys.json"

def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def config_exists() -> bool:
    return CONFIG_FILE.exists()

def save_api_keys(gemini_api_key: str) -> None:
    ensure_config_dir()

    # Leer config existente (puede estar cifrada o en texto plano)
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = decrypt_file(CONFIG_FILE)
        except Exception:
            data = {}

    data["gemini_api_key"] = gemini_api_key.strip()

    # Guardar cifrado con DPAPI (la API key es un dato sensible)
    encrypt_file(CONFIG_FILE, data, "NEXO-Config")

def load_api_keys() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        # Migrar al formato DPAPI si aún está en texto plano
        if _CRYPTO_OK:
            migrate_to_encrypted(CONFIG_FILE, "NEXO-Config")
        return decrypt_file(CONFIG_FILE)
    except PermissionError as e:
        print(f"[Config] Acceso denegado: {e}")
        return {}
    except Exception as e:
        print(f"❌ Failed to load api_keys.json: {e}")
        return {}

def get_gemini_key() -> str | None:
    return load_api_keys().get("gemini_api_key")

def is_configured() -> bool:
    key = get_gemini_key()
    return bool(key and len(key) > 15)