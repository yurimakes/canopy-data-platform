"""인증된 사용자 프로필 등록. 가입 시각과 캠페인 참여일 최초 1회 저장."""
from datetime import datetime, timezone
from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosResourceNotFoundError
from .trip_service import ApiError


class UserRegistration:
    def __init__(self, container, campaign_id, clock=None):
        self.container = container
        self.campaign_id = campaign_id
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def register(self, user_id, body):
        # 사용자 식별자와 참여일은 요청 본문으로 지정 불가.
        if set(body) - {"campaign_code", "nickname"}:
            raise ApiError(400, "invalid_fields", "Only campaign_code and nickname are accepted")
        if not isinstance(body.get("campaign_code"), str) or body["campaign_code"].strip().upper() != "TEST":
            raise ApiError(400, "invalid_campaign", "Unknown campaign code")
        nickname = body.get("nickname", "")
        if not isinstance(nickname, str) or not 1 <= len(nickname.strip()) <= 30:
            raise ApiError(400, "invalid_nickname", "Nickname must contain 1 to 30 characters")
        if not self.campaign_id:
            raise RuntimeError("Campaign configuration required")
        try:
            saved = self.container.read_item(user_id, partition_key=user_id)
        except CosmosResourceNotFoundError:
            now = self.clock().isoformat()
            document = {"id": user_id, "user_id": user_id, "nickname": nickname.strip(),
                        "created_at": now, "campaign_id": self.campaign_id,
                        "campaign_joined_at": now, "campaign_left_at": None, "department_id": None}
            try:
                saved = self.container.create_item(document)
                return self.public(saved), True
            except CosmosResourceExistsError:
                # 동시에 가입하거나 응답 유실 후 재시도한 경우 최초 문서 유지.
                saved = self.container.read_item(user_id, partition_key=user_id)
        if saved.get("campaign_id") != self.campaign_id:
            raise ApiError(409, "campaign_conflict", "User is already registered in another campaign")
        if not saved.get("created_at") or not saved.get("campaign_joined_at"):
            raise ApiError(409, "incomplete_registration", "Existing profile requires registration review")
        return self.public(saved), False

    @staticmethod
    def public(document):
        return {key: document.get(key) for key in
                ("user_id", "nickname", "campaign_id", "created_at", "campaign_joined_at")}
