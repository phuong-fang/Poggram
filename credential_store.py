import logging
import os

import keyring
from cryptography.fernet import Fernet
from telethon.sessions import SQLiteSession, StringSession

import store

logger = logging.getLogger(__name__)

KEYRING_SERVICE = "Poggram"
KEYRING_KEY_NAME = "telegram_session_encryption_key"

ENCRYPTED_SESSION_PATH = os.path.join(store.DATA_DIR, "telegram_vault.session.enc")

LEGACY_SESSION_PATH = os.path.join(store.DATA_DIR, "telegram_vault.session")

def _get_or_create_fernet():
    key = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY_NAME)
    if key is None:

        if os.path.exists(ENCRYPTED_SESSION_PATH):
            logger.error(
                "No session encryption key found in the OS credential store, but an encrypted "
                "session file exists at %s - generating a new key will permanently orphan it "
                "and force a re-login. If this is unexpected, the existing key may still be "
                "recoverable from the credential store (service %r, key %r); nothing is deleted here.",
                ENCRYPTED_SESSION_PATH, KEYRING_SERVICE, KEYRING_KEY_NAME,
            )
        key = Fernet.generate_key().decode("ascii")
        keyring.set_password(KEYRING_SERVICE, KEYRING_KEY_NAME, key)
    return Fernet(key.encode("ascii"))

def _migrate_legacy_session_if_needed():

    if os.path.exists(ENCRYPTED_SESSION_PATH):
        return
    if not os.path.exists(LEGACY_SESSION_PATH):
        return
    old = SQLiteSession(LEGACY_SESSION_PATH)
    try:
        if not old.auth_key:
            return
        session_string = StringSession.save(old)
        save_session_string(session_string)
    finally:
        old.close()
    backup_path = LEGACY_SESSION_PATH + ".migrated-bak"
    if not os.path.exists(backup_path):
        os.replace(LEGACY_SESSION_PATH, backup_path)

def load_session_string():

    _migrate_legacy_session_if_needed()
    if not os.path.exists(ENCRYPTED_SESSION_PATH):
        return None
    fernet = _get_or_create_fernet()
    with open(ENCRYPTED_SESSION_PATH, "rb") as f:
        encrypted = f.read()
    if not encrypted:
        return None
    try:
        return fernet.decrypt(encrypted).decode("ascii")
    except Exception:

        logger.exception(
            "Found an encrypted session at %s but could not decrypt it - the encryption key in "
            "the OS credential store no longer matches this file. Treating as not-signed-in.",
            ENCRYPTED_SESSION_PATH,
        )
        return None

def clear_session():

    try:
        os.remove(ENCRYPTED_SESSION_PATH)
    except OSError:
        pass

def save_session_string(session_string):

    if not session_string:
        return
    fernet = _get_or_create_fernet()
    encrypted = fernet.encrypt(session_string.encode("ascii"))
    os.makedirs(store.DATA_DIR, exist_ok=True)
    tmp_path = ENCRYPTED_SESSION_PATH + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(encrypted)
    os.replace(tmp_path, ENCRYPTED_SESSION_PATH)
