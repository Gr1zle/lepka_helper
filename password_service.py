"""Общий формат пароля для регистрации, входа и изменения пароля."""
import hashlib
import hmac
import secrets


def createPasswordHash(password, passwordSalt=None):
    passwordSalt = passwordSalt or secrets.token_hex(16)
    passwordHash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), passwordSalt.encode("utf-8"), 100000
    ).hex()
    return "pbkdf2_sha256$" + passwordHash, passwordSalt


def checkPassword(password, passwordHash, passwordSalt):
    candidate, _ = createPasswordHash(password, passwordSalt)
    if passwordHash.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(candidate, passwordHash)
    # В исходной версии встречались SHA-256 и PBKDF2 без указания формата.
    legacy = hashlib.sha256(f"{password}{passwordSalt}".encode("utf-8")).hexdigest()
    return (hmac.compare_digest(candidate.split("$", 1)[1], passwordHash)
            or hmac.compare_digest(legacy, passwordHash))
