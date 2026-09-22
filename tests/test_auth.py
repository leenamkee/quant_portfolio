from types import SimpleNamespace as User

import pytest

import auth

WITH_AUTH = {"auth": {"redirect_uri": "x"}, "ALLOWED_EMAILS": ["Kim@gmail.com", "lee@gmail.com"]}


def resolve(user, secrets, persistent=True):
    return auth.resolve_identity(user, secrets, persistent)


# ---------- 로그인 설정이 없는 경우 ----------

def test_dev_mode_without_auth_and_without_persistent_store():
    identity = resolve(User(), {}, persistent=False)
    assert identity.status == "ok" and identity.dev and identity.email == auth.DEV_EMAIL


def test_persistent_store_without_auth_is_blocked_fail_closed():
    identity = resolve(User(), {}, persistent=True)
    assert identity.status == "misconfigured" and "로그인" in identity.message


# ---------- 로그인 설정이 있는 경우 ----------

def test_not_logged_in_shows_login():
    assert resolve(User(is_logged_in=False), WITH_AUTH).status == "login"


def test_user_without_is_logged_in_attribute_shows_login():
    assert resolve(User(), WITH_AUTH).status == "login"


def test_allowed_email_is_accepted_case_insensitively():
    identity = resolve(User(is_logged_in=True, email="KIM@gmail.com", name="김"), WITH_AUTH)
    assert (identity.status, identity.email, identity.name, identity.dev) == ("ok", "kim@gmail.com", "김", False)
    assert identity.key == auth.user_key("kim@gmail.com")


def test_email_not_in_allowlist_is_denied():
    identity = resolve(User(is_logged_in=True, email="evil@gmail.com", name="x"), WITH_AUTH)
    assert identity.status == "denied" and "evil@gmail.com" in identity.message


def test_unverified_email_is_denied_even_if_allowed():
    assert resolve(User(is_logged_in=True, email="kim@gmail.com", email_verified=False), WITH_AUTH).status == "denied"


@pytest.mark.parametrize("secrets", [{"auth": {}}, {"auth": {}, "ALLOWED_EMAILS": []}, {"auth": {}, "ALLOWED_EMAILS": [" "]}])
def test_missing_or_empty_allowlist_denies_everyone(secrets):
    identity = resolve(User(is_logged_in=True, email="kim@gmail.com"), secrets)
    assert identity.status == "misconfigured" and "ALLOWED_EMAILS" in identity.message


def test_single_string_allowlist_is_accepted():
    identity = resolve(User(is_logged_in=True, email="kim@gmail.com"), {"auth": {}, "ALLOWED_EMAILS": "kim@gmail.com"})
    assert identity.status == "ok"


def test_missing_email_claim_is_denied():
    assert resolve(User(is_logged_in=True), WITH_AUTH).status == "denied"


# ---------- 사용자 키 ----------

def test_user_key_is_stable_short_and_case_insensitive():
    assert auth.user_key("A@B.com") == auth.user_key(" a@b.COM ")
    assert len(auth.user_key("a@b.com")) == 12
    assert auth.user_key("a@b.com") != auth.user_key("c@d.com")
    assert "@" not in auth.user_key("a@b.com")
