"""users 기반 계정, 캠페인 가입, 만료와 취소가 가능한 서버 세션."""
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import time
from datetime import datetime, timezone
from uuid import UUID, uuid5

from azure.core import MatchConditions
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceExistsError, CosmosResourceNotFoundError
from .trip_service import ApiError

ITERATIONS = 600_000
SESSION_SECONDS = 7 * 24 * 3600


def login_name(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 120:
        raise ApiError(400, "invalid_login", "이메일 또는 개발자 ID를 확인해주세요.")
    return value.strip().lower()


def account_id(name):
    # 같은 이메일은 같은 파티션과 id로 생성. 동시 가입도 create 충돌로 차단.
    return str(uuid5(UUID("c4984568-e15c-4935-9c46-5c349ad3ee73"), name))


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return {"algorithm": "pbkdf2_sha256", "iterations": ITERATIONS, "salt": salt, "hash": digest}


def check_password(password, record):
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        return False
    if not record or record.get("algorithm") != "pbkdf2_sha256" or record.get("iterations") != ITERATIONS:
        password_hash(password, "00" * 16)
        return False
    return hmac.compare_digest(password_hash(password, record["salt"])["hash"], record["hash"])


def valid_password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128 or not value.strip():
        raise ApiError(400, "invalid_password", "비밀번호는 12자 이상 128자 이하로 입력해주세요.")
    if value.lower() in {"123456789012", "password1234", "canopydev1234"}:
        raise ApiError(400, "invalid_password", "쉽게 추측할 수 없는 비밀번호를 입력해주세요.")
    return value


def place(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"name", "address", "latitude", "longitude", "id"}:
        raise ApiError(400, "invalid_place", "출퇴근 장소를 확인해주세요.")
    if not isinstance(value.get("name"), str) or not 1 <= len(value["name"].strip()) <= 200:
        raise ApiError(400, "invalid_place", "장소 이름을 확인해주세요.")
    for key, bound in (("latitude", 90), ("longitude", 180)):
        n = value.get(key)
        if isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n) or abs(n) > bound:
            raise ApiError(400, "invalid_place", "장소 좌표를 확인해주세요.")
    for key in ("address", "id"):
        if key in value and (not isinstance(value[key], str) or len(value[key]) > 300):
            raise ApiError(400, "invalid_place", "장소 정보를 확인해주세요.")
    if '행정동 중심점' in value.get('address',''):
        raise ApiError(400,'imprecise_place','집·직장은 현재 위치 또는 정확한 좌표로 설정해주세요.')
    return dict(value)


class CampaignRegistry:
    """서버에서만 관리하는 코드 목록. 미설정 시 기존 TEST 캠페인만 허용."""
    def __init__(self, default_campaign, entries=None):
        self.entries = entries if entries is not None else {"TEST": {"campaign_id": default_campaign, "accepting_signups": True}}

    @classmethod
    def from_env(cls):
        raw = os.environ.get("CANOPY_CAMPAIGNS_JSON")
        return cls(os.environ["TRIP_CAMPAIGN_ID"], json.loads(raw) if raw else None)

    def resolve(self, code, now):
        if not isinstance(code, str) or not 1 <= len(code.strip()) <= 32:
            raise ApiError(400, "invalid_campaign", "캠페인 코드를 확인해주세요.")
        code = code.strip().upper()
        entry = self.entries.get(code)
        if not isinstance(entry, dict) or entry.get("accepting_signups") is not True:
            raise ApiError(400, "invalid_campaign", "존재하지 않거나 가입이 종료된 캠페인입니다.")
        for key, is_start in (("signup_starts_at", True), ("signup_ends_at", False)):
            if entry.get(key):
                boundary = datetime.fromisoformat(entry[key].replace("Z", "+00:00"))
                if boundary.tzinfo is None:
                    raise RuntimeError("Campaign dates require timezone")
                if (is_start and now < boundary.timestamp()) or (not is_start and now >= boundary.timestamp()):
                    raise ApiError(400, "campaign_closed", "현재 가입할 수 없는 캠페인입니다.")
        campaign = entry.get("campaign_id")
        if not isinstance(campaign, str) or not campaign.strip() or len(campaign) > 200:
            raise RuntimeError("Invalid campaign configuration")
        return code, campaign


class Accounts:
    def __init__(self, container, campaigns, clock=time.time):
        self.container, self.campaigns, self.clock = container, campaigns, clock

    def read(self, user_id):
        try:
            return self.container.read_item(user_id, partition_key=user_id)
        except CosmosResourceNotFoundError:
            return None

    def change(self, user_id, operation):
        for _ in range(8):
            doc = self.read(user_id)
            if not doc:
                raise ApiError(401, "unauthorized", "다시 로그인해주세요.")
            result = operation(doc)
            try:
                self.container.replace_item(doc["id"], doc, etag=doc["_etag"], match_condition=MatchConditions.IfNotModified)
                return result
            except CosmosHttpResponseError as exc:
                if exc.status_code != 412:
                    raise
        raise ApiError(409, "account_busy", "요청이 겹쳤습니다. 다시 시도해주세요.")

    @staticmethod
    def public(doc):
        return {"id": doc["user_id"], "nickname": doc.get("nickname", ""), "email": doc.get("email") or doc.get("login_name", ""),
                "role": doc.get("role", "user"), "campaignCode": doc.get("campaign_code", "TEST"),
                "campaign_id": doc.get("campaign_id"), "created_at": doc["created_at"],
                "department_id": doc.get("department_id"), "department_name": doc.get("department_name", ""), "campaign_joined_at": doc.get("campaign_joined_at"), "home": doc.get("home"), "work": doc.get("work")}

    def signup(self, body, *, developer=False):
        if set(body) - {"email", "password", "nickname", "campaign_code", "home", "work"}:
            raise ApiError(400, "invalid_fields", "가입 요청에 허용되지 않은 항목이 있습니다.")
        name = login_name(body.get("email"))
        if not developer and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", name):
            raise ApiError(400, "invalid_email", "이메일을 확인해주세요.")
        nickname = body.get("nickname")
        if not isinstance(nickname, str) or not 1 <= len(nickname.strip()) <= 30:
            raise ApiError(400, "invalid_nickname", "닉네임은 1자 이상 30자 이하로 입력해주세요.")
        password = valid_password(body.get("password"))
        now = self.clock()
        code, campaign = self.campaigns.resolve(body.get("campaign_code"), now)
        stamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
        uid = account_id(name)
        doc = {"id": uid, "user_id": uid, "login_name": name, "email": name if "@" in name else None,
               "nickname": nickname.strip(), "role": "developer" if developer else "user", "account_disabled": False,
               "campaign_code": code, "campaign_id": campaign, "created_at": stamp, "campaign_joined_at": stamp,
               "campaign_left_at": None, "department_id": None, "home": place(body.get("home")), "work": place(body.get("work")),
               "credentials": password_hash(password), "sessions": [], "login_failures": []}
        session = self.new_session(doc)
        try:
            self.container.create_item(doc)
        except CosmosResourceExistsError as exc:
            raise ApiError(409, "account_exists", "이미 등록된 계정입니다. 로그인해주세요.") from exc
        return {**session, "profile": self.public(doc)}

    def new_session(self, doc):
        now = self.clock()
        token = "canopy1." + doc["user_id"] + "." + secrets.token_urlsafe(32)
        # 원문 토큰 저장 제외. 만료 세션 정리 및 기기별 세션 최대 5개 유지.
        doc["sessions"] = [s for s in doc.get("sessions", []) if s["expires_at"] > now][-4:]
        expires = now + SESSION_SECONDS
        doc["sessions"].append({"sha256": hashlib.sha256(token.encode()).hexdigest(), "expires_at": expires})
        return {"access_token": token, "expires_at": expires, "token_type": "Bearer"}

    def login(self, body):
        if set(body) != {"email", "password"}:
            raise ApiError(400, "invalid_fields", "이메일과 비밀번호를 입력해주세요.")
        uid = account_id(login_name(body.get("email")))
        doc = self.read(uid)
        if not doc:
            check_password(body.get("password"), None)
            raise ApiError(401, "invalid_credentials", "이메일 또는 비밀번호를 확인해주세요.")

        def attempt(current):
            now = self.clock()
            failures = [t for t in current.get("login_failures", []) if t > now - 900]
            if len(failures) >= 10:
                raise ApiError(429, "login_limited", "로그인 시도가 많습니다. 15분 후 다시 시도해주세요.")
            if current.get("account_disabled") or not check_password(body.get("password"), current.get("credentials")):
                current["login_failures"] = failures + [now]
                return None
            current["login_failures"] = []
            return {**self.new_session(current), "profile": self.public(current)}
        result = self.change(uid, attempt)
        if not result:
            raise ApiError(401, "invalid_credentials", "이메일 또는 비밀번호를 확인해주세요.")
        return result

    def authenticated(self, token):
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != "canopy1" or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", parts[1]) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", parts[2]):
            raise ApiError(401, "unauthorized", "다시 로그인해주세요.")
        doc = self.read(parts[1])
        digest = hashlib.sha256(token.encode()).hexdigest()
        if not doc or doc.get("account_disabled") or not any(s["expires_at"] > self.clock() and hmac.compare_digest(s["sha256"], digest) for s in doc.get("sessions", [])):
            raise ApiError(401, "unauthorized", "로그인이 만료됐습니다. 다시 로그인해주세요.")
        return doc

    def logout(self, token):
        doc = self.authenticated(token)
        digest = hashlib.sha256(token.encode()).hexdigest()
        def revoke(current):
            current["sessions"] = [s for s in current.get("sessions", []) if not hmac.compare_digest(s["sha256"], digest)]
        self.change(doc["user_id"], revoke)

    def update(self, token, body):
        doc = self.authenticated(token)
        if set(body) - {"nickname", "home", "work", "department_name"}:
            raise ApiError(400, "invalid_fields", "계정과 캠페인은 프로필 수정으로 변경할 수 없습니다.")
        changes = {}
        if "department_name" in body:
            name=body["department_name"]
            if not isinstance(name,str) or len(name.strip())>50:raise ApiError(400,"invalid_department","부서명은 50자 이내로 입력해주세요.")
            name=name.strip()
            changes["department_name"]=name
            changes["department_id"]=hashlib.sha256((doc["campaign_id"]+":"+name).encode()).hexdigest()[:24] if name else None
        if "nickname" in body:
            name = body["nickname"]
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 30:
                raise ApiError(400, "invalid_nickname", "닉네임을 확인해주세요.")
            changes["nickname"] = name.strip()
        for key in ("home", "work"):
            if key in body:
                changes[key] = place(body[key])
        def apply(current):
            current.update(changes)
            return self.public(current)
        return self.change(doc["user_id"], apply)
