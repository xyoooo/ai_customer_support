from packages.security.passwords import hash_password, verify_password


def test_password_is_hashed_and_verifiable() -> None:
    password = "correct horse battery staple"
    encoded = hash_password(password)
    assert password not in encoded
    assert verify_password(password, encoded)
    assert not verify_password("incorrect password", encoded)
