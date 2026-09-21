import hashlib
from dataclasses import dataclass

DEV_EMAIL = "local@dev"


@dataclass
class Identity:
    status: str  # ok | login | denied | misconfigured
    email: str = ""
    name: str = ""
    key: str = ""
    dev: bool = False
    message: str = ""


def user_key(email):
    """저장소 파일명에 이메일이 그대로 드러나지 않도록 해시 앞 12자리를 쓴다."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:12]


def auth_configured(secrets):
    try:
        return "auth" in secrets
    except Exception:
        return False


def _allowed_emails(secrets):
    try:
        raw = secrets["ALLOWED_EMAILS"]
    except (KeyError, FileNotFoundError):
        return set()
    if isinstance(raw, str):
        raw = [raw]
    return {str(e).strip().lower() for e in raw if str(e).strip()}


def resolve_identity(user, secrets, persistent_store):
    """
    현재 접속자의 상태를 판정한다.
    - 로그인 설정([auth])이 있으면 Google 로그인 + ALLOWED_EMAILS 허용 목록을 요구한다.
    - 로그인 설정이 없고 영구 저장소(GitHub)만 설정된 경우는 데이터 보호를 위해 열지 않는다.
    - 둘 다 없으면 로컬 개발 모드(단일 사용자)로 동작한다.
    """
    if not auth_configured(secrets):
        if persistent_store:
            return Identity(
                "misconfigured",
                message="GitHub 저장소는 설정되어 있지만 Google 로그인([auth]) 설정이 없습니다. "
                        "데이터 보호를 위해 로그인을 설정하기 전에는 앱을 열지 않습니다. (docs/google-login-setup.md 참고)",
            )
        return Identity("ok", email=DEV_EMAIL, name="로컬 사용자", key=user_key(DEV_EMAIL), dev=True)

    if not getattr(user, "is_logged_in", False):
        return Identity("login")

    email = str(getattr(user, "email", "") or "").strip().lower()
    name = str(getattr(user, "name", "") or email)
    allowed = _allowed_emails(secrets)
    if not allowed:
        return Identity("misconfigured", email=email,
                        message="ALLOWED_EMAILS가 설정되지 않아 모든 계정의 접근을 거부합니다. Secrets에 허용할 이메일 목록을 추가하세요.")
    if getattr(user, "email_verified", True) is False:
        return Identity("denied", email=email, message="이메일이 인증되지 않은 Google 계정입니다.")
    if email not in allowed:
        return Identity("denied", email=email, message=f"{email} 계정은 이 앱의 사용 권한이 없습니다. 관리자에게 문의하세요.")
    return Identity("ok", email=email, name=name, key=user_key(email))
