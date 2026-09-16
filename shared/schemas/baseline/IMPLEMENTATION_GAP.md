# Baseline contract implementation gap

현재 ADLS Gold의 Personal/Global schema는 Eligibility v1 메타데이터까지 포함하지만, `baseline_integration/cosmos_baseline_writer.py`의 Cosmos latest 변환은 아직 일부 필드를 누락합니다.

## 현재 누락

Personal latest에서 아직 보존하지 않는 필드:
- `eligibility_policy_version`
- `observation_days`
- `confirmed_trip_count`
- `observation_source`
- `eligibility_reason`
- `primary_baseline`

Global latest에서 아직 보존하지 않는 필드:
- `eligibility_policy_version`
- `eligible_participant_count`

또한 Cosmos latest의 `status`를 source Gold의 상태를 그대로 보존하지 않고 값 존재 여부로 다시 유도하고 있습니다. 특히 Global Gold의 `collecting`이 Cosmos latest에서는 `insufficient_data`로 변환될 수 있습니다.

## 연결 규칙

`Baseline API`, Reward, Behavior Change 담당자는 이 gap이 수정되기 전까지 Cosmos latest를 Eligibility 상태의 canonical source로 사용하지 않습니다. Eligibility 포함 canonical 상태는 ADLS Personal/Global Gold입니다.

후속 수정에서는 Cosmos publisher가 Gold의 `status`와 `eligibility_policy_version`을 그대로 보존하고, write 후 read-back 검증에서도 `week`, `policy_version`, `eligibility_policy_version`, `status`, `value`를 함께 비교해야 합니다.
