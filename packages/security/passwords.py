from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
# Used only to keep unknown-email login attempts on the same expensive verification path.
DUMMY_PASSWORD_HASH = password_hash.hash("supportpilot-dummy-password-not-a-user")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hash.verify(password, encoded_hash)
