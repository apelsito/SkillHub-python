from skillhub_api.services.auth.passwords import hash_password, verify_password


def test_hash_password_roundtrips() -> None:
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert h.startswith("$2b$12$")  # bcrypt cost factor 12
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password", h)


def test_verify_tolerates_malformed_hash() -> None:
    assert not verify_password("anything", "not-a-bcrypt-hash")
    assert not verify_password("anything", "")
