"""주간 분석 파이프라인 통합 파일.

1. CONFIG.run: 실행 캠페인, 마감 주, 적용 주, 실행할 결과 설정
2. CONFIG.sources: 분석 입력 Delta 위치 설정
3. CONFIG.contracts: 기존 팀 스키마와 미제출 계약 위치
4. 팀원 계산 함수 영역: 본인 함수의 예외 부분을 계산 코드와 return 결과로 교체

주간 집계 및 Personal-ready 선택 연결 완료. 나머지 함수는 코드 입력 위치.
미제출 계약은 확정값으로 가장하지 않고 연결 시 오류 처리.
"""
import copy
import dis
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# 실행 설정과 공통 스키마. 이 파일 안에서만 편집
CONFIG = {'template_version': 'weekly-integration-v1',
 'github_commit': 'b70d5b847fad107d8ef18f6c8beb6adcd26df0f8',
 'notion_reviewed_at': '2026-09-17',
 'run': {'enabled_outputs': ['weekly_gold'],
         'campaign_id': '',
         'closed_week_start': '',
         'evaluation_week_start': '',
         'timezone': 'Asia/Seoul',
         'test_mode': True,
         'commute_scope_verified': False,
         'acknowledged_contracts': [],
         'policy_versions': {'eligibility': 'eligibility-v1'},
         'policies': {}},
 'sources': {'final_trips': {'contract': 'final_trip',
                             'kind': 'delta',
                             'location': 'abfss://curated@stcanopydev5dt.dfs.core.windows.net/pipeline_test/trip_finalization/iphone_final_trips',
                             'version': None},
             'users': {'contract': 'user', 'kind': 'delta', 'location': '', 'version': None},
             'memberships': {'contract': 'membership', 'kind': 'delta', 'location': '', 'version': None},
             'mission_responses': {'contract': 'mission_response',
                                   'kind': 'delta',
                                   'location': '',
                                   'version': None},
             'reward_postings': {'contract': 'reward_postings', 'kind': 'delta', 'location': '', 'version': None},
             'department_memberships': {'contract': 'membership_department',
                                        'kind': 'delta',
                                        'location': '',
                                        'version': None}},
 'contracts': {'weekly': {'status': 'repository',
                          'owner': '5dt028 / ManiaKCY',
                          'source': 'shared/schemas/baseline/weekly_user_gold.schema.json',
                          'sha256': 'bfabca8f3fb635d06eb664ca90723545c632bc57f054da39606761dbd1678adc',
                          'key': ['user_id', 'campaign_id', 'week'],
                          'json_schema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                          '$id': 'canopy.weekly-user-gold.v1',
                                          'title': 'Canopy Weekly User Gold',
                                          'description': 'One row per user_id + campaign_id + ISO week. Input '
                                                         'Trip set is commute-only and status=ready. Shared '
                                                         'primary-mode behavior facts are included so downstream '
                                                         'Mission/Baseline/analytics do not reimplement the same '
                                                         'Trip logic.',
                                          'type': 'object',
                                          'required': ['user_id',
                                                       'campaign_id',
                                                       'week',
                                                       'trip_count',
                                                       'total_distance_m',
                                                       'total_kg_co2e',
                                                       'carbon_policy_version',
                                                       'factor_version',
                                                       'walk_distance_m',
                                                       'bike_distance_m',
                                                       'car_distance_m',
                                                       'bus_distance_m',
                                                       'rail_distance_m',
                                                       'mode_trip_ratio_walk',
                                                       'mode_trip_ratio_bike',
                                                       'mode_trip_ratio_car',
                                                       'mode_trip_ratio_bus',
                                                       'mode_trip_ratio_rail',
                                                       'mode_distance_ratio_walk',
                                                       'mode_distance_ratio_bike',
                                                       'mode_distance_ratio_car',
                                                       'mode_distance_ratio_bus',
                                                       'mode_distance_ratio_rail',
                                                       'mode_carbon_ratio_walk',
                                                       'mode_carbon_ratio_bike',
                                                       'mode_carbon_ratio_car',
                                                       'mode_carbon_ratio_bus',
                                                       'mode_carbon_ratio_rail',
                                                       'valid_primary_trip_count',
                                                       'invalid_primary_trip_count',
                                                       'ambiguous_primary_trip_count',
                                                       'invalid_segment_primary_trip_count',
                                                       'car_primary_trip_count',
                                                       'transit_primary_trip_count',
                                                       'low_carbon_trip_count',
                                                       'short_car_trip_count',
                                                       'car_primary_ratio',
                                                       'short_car_share'],
                                          'properties': {'user_id': {'type': 'string', 'minLength': 1},
                                                         'campaign_id': {'type': 'string', 'minLength': 1},
                                                         'week': {'type': 'string',
                                                                  'pattern': '^[0-9]{4}-W[0-9]{2}$'},
                                                         'trip_count': {'type': 'integer',
                                                                        'minimum': 0,
                                                                        'description': 'Accepted commute Trip '
                                                                                       'count.'},
                                                         'total_distance_m': {'type': 'number', 'minimum': 0},
                                                         'total_kg_co2e': {'type': 'number', 'minimum': 0},
                                                         'carbon_policy_version': {'type': 'string',
                                                                                   'minLength': 1},
                                                         'factor_version': {'type': 'string', 'minLength': 1},
                                                         'walk_distance_m': {'type': 'number', 'minimum': 0},
                                                         'bike_distance_m': {'type': 'number', 'minimum': 0},
                                                         'car_distance_m': {'type': 'number', 'minimum': 0},
                                                         'bus_distance_m': {'type': 'number', 'minimum': 0},
                                                         'rail_distance_m': {'type': 'number', 'minimum': 0},
                                                         'mode_trip_ratio_walk': {'type': 'number', 'minimum': 0},
                                                         'mode_trip_ratio_bike': {'type': 'number', 'minimum': 0},
                                                         'mode_trip_ratio_car': {'type': 'number', 'minimum': 0},
                                                         'mode_trip_ratio_bus': {'type': 'number', 'minimum': 0},
                                                         'mode_trip_ratio_rail': {'type': 'number', 'minimum': 0},
                                                         'mode_distance_ratio_walk': {'type': 'number',
                                                                                      'minimum': 0},
                                                         'mode_distance_ratio_bike': {'type': 'number',
                                                                                      'minimum': 0},
                                                         'mode_distance_ratio_car': {'type': 'number',
                                                                                     'minimum': 0},
                                                         'mode_distance_ratio_bus': {'type': 'number',
                                                                                     'minimum': 0},
                                                         'mode_distance_ratio_rail': {'type': 'number',
                                                                                      'minimum': 0},
                                                         'mode_carbon_ratio_walk': {'type': 'number',
                                                                                    'minimum': 0},
                                                         'mode_carbon_ratio_bike': {'type': 'number',
                                                                                    'minimum': 0},
                                                         'mode_carbon_ratio_car': {'type': 'number', 'minimum': 0},
                                                         'mode_carbon_ratio_bus': {'type': 'number', 'minimum': 0},
                                                         'mode_carbon_ratio_rail': {'type': 'number',
                                                                                    'minimum': 0},
                                                         'valid_primary_trip_count': {'type': 'integer',
                                                                                      'minimum': 0},
                                                         'invalid_primary_trip_count': {'type': 'integer',
                                                                                        'minimum': 0,
                                                                                        'description': 'Trip '
                                                                                                       'count '
                                                                                                       'excluded '
                                                                                                       'from '
                                                                                                       'primary-mode '
                                                                                                       'facts '
                                                                                                       'because '
                                                                                                       'of a tie '
                                                                                                       'or '
                                                                                                       'invalid '
                                                                                                       'segment.'},
                                                         'ambiguous_primary_trip_count': {'type': 'integer',
                                                                                          'minimum': 0,
                                                                                          'description': 'Primary-mode '
                                                                                                         'exact-tie '
                                                                                                         'Trip '
                                                                                                         'count.'},
                                                         'invalid_segment_primary_trip_count': {'type': 'integer',
                                                                                                'minimum': 0,
                                                                                                'description': 'Trip '
                                                                                                               'count '
                                                                                                               'with '
                                                                                                               'unsupported/missing/non-positive '
                                                                                                               'segment '
                                                                                                               'mode-distance '
                                                                                                               'input.'},
                                                         'car_primary_trip_count': {'type': 'integer',
                                                                                    'minimum': 0},
                                                         'transit_primary_trip_count': {'type': 'integer',
                                                                                        'minimum': 0},
                                                         'low_carbon_trip_count': {'type': 'integer',
                                                                                   'minimum': 0},
                                                         'short_car_trip_count': {'type': 'integer',
                                                                                  'minimum': 0,
                                                                                  'description': 'Valid '
                                                                                                 'car-primary '
                                                                                                 'Trip with total '
                                                                                                 'Trip distance '
                                                                                                 '<= 2000m.'},
                                                         'car_primary_ratio': {'type': ['number', 'null'],
                                                                               'minimum': 0,
                                                                               'maximum': 1},
                                                         'short_car_share': {'type': ['number', 'null'],
                                                                             'minimum': 0,
                                                                             'maximum': 1}},
                                          'additionalProperties': True}},
               'personal': {'status': 'repository',
                            'owner': 'ManiaKCY / Hayden Shin',
                            'source': 'shared/schemas/baseline/personal_baseline.schema.json',
                            'sha256': '6a4ba5c9b038e09d689f27150a24f23474156aaabb39a378a9157acf01a599a0',
                            'key': ['user_id', 'campaign_id', 'week'],
                            'json_schema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                            '$id': 'canopy.personal-baseline.v1',
                                            'title': 'Canopy Personal Baseline History',
                                            'description': 'One row/document-equivalent per user_id + campaign_id '
                                                           '+ evaluation week. Derived from prior completed '
                                                           'Weekly Gold only; the evaluation week itself is '
                                                           'excluded.',
                                            'type': 'object',
                                            'required': ['user_id',
                                                         'campaign_id',
                                                         'week',
                                                         'cumulative_g_co2e',
                                                         'cumulative_distance_km',
                                                         'baseline_g_co2e_per_km',
                                                         'method',
                                                         'policy_version',
                                                         'status',
                                                         'value',
                                                         'eligibility_policy_version',
                                                         'observation_days',
                                                         'confirmed_trip_count',
                                                         'observation_source',
                                                         'eligibility_reason',
                                                         'primary_baseline'],
                                            'properties': {'user_id': {'type': 'string', 'minLength': 1},
                                                           'campaign_id': {'type': 'string', 'minLength': 1},
                                                           'week': {'type': 'string',
                                                                    'pattern': '^[0-9]{4}-W[0-9]{2}$'},
                                                           'cumulative_g_co2e': {'type': ['number', 'null'],
                                                                                 'minimum': 0,
                                                                                 'description': 'Prior completed '
                                                                                                'weeks cumulative '
                                                                                                'gCO2e.'},
                                                           'cumulative_distance_km': {'type': ['number', 'null'],
                                                                                      'minimum': 0,
                                                                                      'description': 'Prior '
                                                                                                     'completed '
                                                                                                     'weeks '
                                                                                                     'cumulative '
                                                                                                     'km.'},
                                                           'baseline_g_co2e_per_km': {'type': ['number', 'null'],
                                                                                      'minimum': 0},
                                                           'method': {'enum': ['personal_cumulative',
                                                                               'population_fallback']},
                                                           'policy_version': {'type': 'string', 'minLength': 1},
                                                           'status': {'enum': ['collecting', 'ready']},
                                                           'value': {'type': ['number', 'null'], 'minimum': 0},
                                                           'eligibility_policy_version': {'type': 'string',
                                                                                          'minLength': 1},
                                                           'observation_days': {'type': ['integer', 'null'],
                                                                                'minimum': 0},
                                                           'confirmed_trip_count': {'type': ['integer', 'null'],
                                                                                    'minimum': 0,
                                                                                    'description': 'Prior '
                                                                                                   'accepted '
                                                                                                   'commute Trip '
                                                                                                   'count.'},
                                                           'observation_source': {'type': ['string', 'null']},
                                                           'eligibility_reason': {'type': ['string', 'null']},
                                                           'primary_baseline': {'enum': ['population', None]}},
                                            'additionalProperties': True}},
               'global': {'status': 'repository',
                          'owner': 'ManiaKCY / Hayden Shin',
                          'source': 'shared/schemas/baseline/global_baseline.schema.json',
                          'sha256': '57f3e37f5c7c12b8590bdae16b94857027bde5293d633292ac3685e261eed371',
                          'key': ['campaign_id', 'week'],
                          'json_schema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                          '$id': 'canopy.global-baseline.v1',
                                          'title': 'Canopy Global Baseline History',
                                          'description': 'One row per campaign_id + evaluation week. Uses equal '
                                                         'weight across Personal-ready users that match the '
                                                         'active Eligibility policy version.',
                                          'type': 'object',
                                          'required': ['campaign_id',
                                                       'week',
                                                       'valid_participant_count',
                                                       'baseline_g_co2e_per_km',
                                                       'method',
                                                       'policy_version',
                                                       'status',
                                                       'value',
                                                       'eligible_participant_count',
                                                       'eligibility_policy_version'],
                                          'properties': {'campaign_id': {'type': 'string', 'minLength': 1},
                                                         'week': {'type': 'string',
                                                                  'pattern': '^[0-9]{4}-W[0-9]{2}$'},
                                                         'valid_participant_count': {'type': 'integer',
                                                                                     'minimum': 0},
                                                         'baseline_g_co2e_per_km': {'type': ['number', 'null'],
                                                                                    'minimum': 0},
                                                         'method': {'enum': ['global_average_of_personal_baseline',
                                                                             'insufficient_data']},
                                                         'policy_version': {'type': 'string', 'minLength': 1},
                                                         'status': {'enum': ['collecting', 'ready']},
                                                         'value': {'type': ['number', 'null'], 'minimum': 0},
                                                         'eligible_participant_count': {'type': 'integer',
                                                                                        'minimum': 0},
                                                         'eligibility_policy_version': {'type': 'string',
                                                                                        'minLength': 1}},
                                          'additionalProperties': True}},
               'mission_response': {'status': 'repository',
                                    'owner': 'ManiaKCY',
                                    'source': 'shared/schemas/mission/mission_response_weekly.schema.json',
                                    'sha256': '859db9cf322fa60aad23a516f73f78db7f5e6fd2e71139382d0bb0b4776527a1',
                                    'key': ['campaign_id', 'user_id', 'week_start', 'assignment_id'],
                                    'json_schema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                                    '$id': 'canopy.mission-response-weekly.v1',
                                                    'title': 'Canopy Mission Response Weekly',
                                                    'description': 'Immutable weekly analytical row per issued '
                                                                   'assignment. This is the preferred history '
                                                                   'input for the next Mission Profile.',
                                                    'type': 'object',
                                                    'required': ['campaign_id',
                                                                 'user_id',
                                                                 'week_start',
                                                                 'week_end',
                                                                 'bundle_id',
                                                                 'assignment_id',
                                                                 'mission_template_id',
                                                                 'mission_family',
                                                                 'category_id',
                                                                 'difficulty_band',
                                                                 'common_target_count',
                                                                 'target_count',
                                                                 'affinity_comparable',
                                                                 'difficulty_comparable',
                                                                 'preference_comparable',
                                                                 'progress_count',
                                                                 'achievement_rate',
                                                                 'completed',
                                                                 'linked_trip_count',
                                                                 'policy_version',
                                                                 'response_version'],
                                                    'properties': {'campaign_id': {'type': 'string',
                                                                                   'minLength': 1},
                                                                   'user_id': {'type': 'string', 'minLength': 1},
                                                                   'week_start': {'type': 'string',
                                                                                  'format': 'date'},
                                                                   'week_end': {'type': 'string',
                                                                                'format': 'date'},
                                                                   'bundle_id': {'type': 'string', 'minLength': 1},
                                                                   'assignment_id': {'type': 'string',
                                                                                     'minLength': 1},
                                                                   'mission_template_id': {'type': 'string',
                                                                                           'minLength': 1},
                                                                   'mission_family': {'type': 'string',
                                                                                      'minLength': 1},
                                                                   'category_id': {'enum': ['challenge',
                                                                                            'habit',
                                                                                            'easy_win',
                                                                                            'explore']},
                                                                   'difficulty_band': {'type': 'string',
                                                                                       'minLength': 1},
                                                                   'common_target_count': {'type': 'integer',
                                                                                           'minimum': 1},
                                                                   'target_count': {'type': 'integer',
                                                                                    'minimum': 1},
                                                                   'affinity_comparable': {'type': 'boolean'},
                                                                   'difficulty_comparable': {'type': 'boolean'},
                                                                   'preference_comparable': {'type': 'boolean',
                                                                                             'description': 'Backward-compatible '
                                                                                                            'alias '
                                                                                                            'of '
                                                                                                            'affinity_comparable.'},
                                                                   'mission_shown_count': {'type': 'integer',
                                                                                           'minimum': 0,
                                                                                           'default': 0},
                                                                   'mission_started_count': {'type': 'integer',
                                                                                             'minimum': 0,
                                                                                             'default': 0},
                                                                   'mission_completed_count': {'type': 'integer',
                                                                                               'minimum': 0,
                                                                                               'maximum': 1},
                                                                   'progress_count': {'type': 'integer',
                                                                                      'minimum': 0},
                                                                   'achievement_rate': {'type': 'number',
                                                                                        'minimum': 0},
                                                                   'completed': {'type': 'boolean'},
                                                                   'linked_trip_count': {'type': 'integer',
                                                                                         'minimum': 0},
                                                                   'policy_version': {'type': 'string',
                                                                                      'minLength': 1},
                                                                   'response_version': {'type': 'string',
                                                                                        'minLength': 1}},
                                                    'additionalProperties': True}},
               'membership': {'status': 'repository',
                              'owner': 'Hayden Shin',
                              'source': 'shared/schemas/campaign_membership.schema.json',
                              'sha256': '3c7d1b1ff604b0584074cc3374c3b2f066505b58329bb5cdebb18170353ec88a',
                              'key': ['user_id', 'campaign_id'],
                              'json_schema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                              '$id': 'https://canopy.local/schemas/campaign_membership.schema.json',
                                              'title': 'Canopy campaign membership',
                                              'description': 'canopy-db/campaign_memberships, partition /user_id. '
                                                             'id equals campaign_id, giving one membership per '
                                                             'user/campaign. Participation backend sets '
                                                             'joined_at; rejoining must not silently reset it.',
                                              'type': 'object',
                                              'required': ['id', 'user_id', 'campaign_id', 'joined_at'],
                                              'properties': {'id': {'type': 'string', 'minLength': 1},
                                                             'user_id': {'type': 'string', 'minLength': 1},
                                                             'campaign_id': {'type': 'string', 'minLength': 1},
                                                             'joined_at': {'type': 'string',
                                                                           'format': 'date-time'}},
                                              'additionalProperties': True}},
               'user': {'status': 'repository',
                        'owner': 'Hayden Shin',
                        'source': 'shared/schemas/user.schema.json',
                        'sha256': 'e49fe50ea8ea310a9688462ae8cf1b4d67e2515dfc34a33370a9b602cfe99680',
                        'key': ['user_id'],
                        'json_schema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                        '$id': 'https://canopy.local/schemas/user.schema.json',
                                        'title': 'Canopy user profile',
                                        'description': 'canopy-db/users, partition /user_id. id equals user_id. '
                                                       'Registration backend sets created_at; never accept a '
                                                       'client-supplied signup date. Authentication credentials '
                                                       'belong to the authentication provider.',
                                        'type': 'object',
                                        'required': ['id', 'user_id', 'created_at'],
                                        'properties': {'id': {'type': 'string', 'minLength': 1},
                                                       'user_id': {'type': 'string', 'minLength': 1},
                                                       'created_at': {'type': 'string', 'format': 'date-time'},
                                                       'nickname': {'type': ['string', 'null']},
                                                       'auth_subject': {'type': ['string', 'null']}},
                                        'additionalProperties': True}},
               'mission_profile': {'status': 'repository_storage_adapter',
                                   'owner': 'ManiaKCY',
                                   'source': 'shared/schemas/mission/mission_profile.schema.json',
                                   'sha256': '7a554343db4c3a09613f15a91b475cb212cb9f2c5776be61fa10224d0831f0ea',
                                   'key': ['campaign_id', 'user_id', 'effective_week_start'],
                                   'json_schema': {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                                   '$id': 'canopy.mission-profile.v3',
                                                   'title': 'Canopy Mission Profile',
                                                   'type': 'object',
                                                   'required': ['type',
                                                                'profile_version',
                                                                'profile_status',
                                                                'user_id',
                                                                'campaign_id',
                                                                'source_week_start',
                                                                'source_week_end',
                                                                'valid_trip_count',
                                                                'invalid_trip_count',
                                                                'car_primary_trip_count',
                                                                'short_car_trip_count',
                                                                'transit_primary_trip_count',
                                                                'low_carbon_trip_count',
                                                                'profile_hash',
                                                                'category_preferences_json',
                                                                'difficulty_state_json',
                                                                'family_capability_json',
                                                                'effective_week_start',
                                                                'invalid_trip_reasons',
                                                                'mission_history_source',
                                                                'preference_positive_evidence_count'],
                                                   'properties': {'type': {'const': 'mission_profile'},
                                                                  'profile_version': {'const': 'mission-profile-v3'},
                                                                  'profile_status': {'enum': ['ready',
                                                                                              'history_only',
                                                                                              'collecting']},
                                                                  'user_id': {'type': 'string', 'minLength': 1},
                                                                  'campaign_id': {'type': 'string',
                                                                                  'minLength': 1},
                                                                  'source_week_start': {'type': 'string',
                                                                                        'format': 'date'},
                                                                  'source_week_end': {'type': 'string',
                                                                                      'format': 'date'},
                                                                  'effective_week_start': {'type': 'string',
                                                                                           'format': 'date'},
                                                                  'valid_trip_count': {'type': 'integer',
                                                                                       'minimum': 0},
                                                                  'invalid_trip_count': {'type': 'integer',
                                                                                         'minimum': 0},
                                                                  'invalid_trip_reasons': {'type': 'object',
                                                                                           'additionalProperties': {'type': 'integer',
                                                                                                                    'minimum': 0}},
                                                                  'car_primary_trip_count': {'type': 'integer',
                                                                                             'minimum': 0},
                                                                  'car_ratio': {'type': ['number', 'null'],
                                                                                'minimum': 0,
                                                                                'maximum': 1},
                                                                  'short_car_trip_count': {'type': 'integer',
                                                                                           'minimum': 0},
                                                                  'short_car_share': {'type': ['number', 'null'],
                                                                                      'minimum': 0,
                                                                                      'maximum': 1},
                                                                  'transit_primary_trip_count': {'type': 'integer',
                                                                                                 'minimum': 0},
                                                                  'low_carbon_trip_count': {'type': 'integer',
                                                                                            'minimum': 0},
                                                                  'carbon_change_rate': {'type': ['number',
                                                                                                  'null']},
                                                                  'mission_history_source': {'enum': ['mission_response_gold',
                                                                                                      'cosmos_bundle_fallback',
                                                                                                      'none']},
                                                                  'preference_positive_evidence_count': {'type': 'integer',
                                                                                                         'minimum': 0},
                                                                  'profile_hash': {'type': 'string',
                                                                                   'minLength': 32},
                                                                  'category_preferences_json': {'type': 'string'},
                                                                  'difficulty_state_json': {'type': 'string'},
                                                                  'family_capability_json': {'type': 'string'}},
                                                   'additionalProperties': True},
                                   'storage_source': 'cloud/azure/pipelines/databricks/build_mission_profile.py::_gold_profile/run',
                                   'notes': ['객체 3개를 원본 Gold 저장 코드의 *_json 문자열로 표현',
                                             '노션 v2 설명과 GitHub v3 계약 불일치. v3 선택 확인 후 활성화']},
               'final_trip': {'status': 'repository_storage_adapter',
                              'owner': 'Hayden Shin',
                              'source': 'cloud/azure/pipelines/databricks/finalize_trip_pipeline.py::gold_frame '
                                        '(feature/trip-finalization-pipeline)',
                              'key': ['user_id', 'trip_id'],
                              'json_schema': {'type': 'object',
                                              'properties': {'trip_id': {'type': 'string', 'minLength': 1},
                                                             'user_id': {'type': 'string', 'minLength': 1},
                                                             'campaign_id': {'type': 'string', 'minLength': 1},
                                                             'status': {'const': 'ready'},
                                                             'started_at': {'type': 'string',
                                                                            'minLength': 1,
                                                                            'format': 'date-time'},
                                                             'ended_at': {'type': 'string',
                                                                          'minLength': 1,
                                                                          'format': 'date-time'},
                                                             'updated_at': {'type': 'string',
                                                                            'minLength': 1,
                                                                            'format': 'date-time'},
                                                             'is_mock': {'type': 'boolean'},
                                                             'segments': {'type': 'array',
                                                                          'items': {'type': 'object',
                                                                                    'properties': {'segment_id': {'type': 'string',
                                                                                                                  'minLength': 1},
                                                                                                   'model_prediction': {'type': ['string',
                                                                                                                                 'null']},
                                                                                                   'distance_m': {'type': ['number',
                                                                                                                           'null']},
                                                                                                   'carbon_kg': {'type': 'number',
                                                                                                                 'minimum': 0}},
                                                                                    'required': ['segment_id',
                                                                                                 'model_prediction',
                                                                                                 'distance_m',
                                                                                                 'carbon_kg'],
                                                                                    'additionalProperties': True}},
                                                             'carbon': {'type': 'object',
                                                                        'properties': {'kg_co2e': {'type': 'number',
                                                                                                   'minimum': 0},
                                                                                       'policy_version': {'type': 'string',
                                                                                                          'minLength': 1},
                                                                                       'factor_version': {'type': 'string',
                                                                                                          'minLength': 1},
                                                                                       'unit': {'const': 'kgCO2e'}},
                                                                        'required': ['kg_co2e',
                                                                                     'policy_version',
                                                                                     'factor_version',
                                                                                     'unit'],
                                                                        'additionalProperties': True}},
                                              'required': ['trip_id',
                                                           'user_id',
                                                           'campaign_id',
                                                           'status',
                                                           'started_at',
                                                           'ended_at',
                                                           'updated_at',
                                                           'is_mock',
                                                           'segments',
                                                           'carbon'],
                                              'additionalProperties': True},
                              'notes': ['Final Trip Delta 실제 저장 컬럼 기준',
                                        'Baseline YAML에만 있는 carbon.mode_source 등은 이 저장 계약에 없으며 자동 생성 금지',
                                        '출퇴근 전용 입력 보장 필요. 운영에서는 검증된 upstream 입력만 사용']},
               'personal_eligibility': {'status': 'integration_contract',
                                        'owner': 'Hayden Shin',
                                        'source': 'cloud/azure/pipelines/databricks/baseline_eligibility.py::evaluate_personal_eligibility',
                                        'notes': ['기존 정책 함수 반환 필드 유지',
                                                  '파이프라인 조인용 식별값과 적용 주차 추가. 공통 연결에서 정의한 DataFrame 계약'],
                                        'key': ['user_id', 'campaign_id', 'week'],
                                        'json_schema': {'type': 'object',
                                                        'properties': {'user_id': {'type': 'string',
                                                                                   'minLength': 1},
                                                                       'campaign_id': {'type': 'string',
                                                                                       'minLength': 1},
                                                                       'week': {'type': 'string',
                                                                                'pattern': '^[0-9]{4}-W[0-9]{2}$'},
                                                                       'status': {'enum': ['collecting', 'ready']},
                                                                       'policy_version': {'type': 'string',
                                                                                          'minLength': 1},
                                                                       'observation_days': {'type': ['integer',
                                                                                                     'null']},
                                                                       'confirmed_trip_count': {'type': ['integer',
                                                                                                         'null']},
                                                                       'reasons': {'type': 'array',
                                                                                   'items': {'type': 'string'}}},
                                                        'required': ['user_id',
                                                                     'campaign_id',
                                                                     'week',
                                                                     'status',
                                                                     'policy_version',
                                                                     'observation_days',
                                                                     'confirmed_trip_count',
                                                                     'reasons'],
                                                        'additionalProperties': True}},
               'global_eligibility': {'status': 'integration_contract',
                                      'owner': 'Hayden Shin',
                                      'source': 'cloud/azure/pipelines/databricks/baseline_eligibility.py::evaluate_global_eligibility',
                                      'notes': ['기존 정책 함수 반환 필드 유지',
                                                '파이프라인 조인용 식별값과 적용 주차 추가. 공통 연결에서 정의한 DataFrame 계약'],
                                      'key': ['campaign_id', 'week'],
                                      'json_schema': {'type': 'object',
                                                      'properties': {'campaign_id': {'type': 'string',
                                                                                     'minLength': 1},
                                                                     'week': {'type': 'string',
                                                                              'pattern': '^[0-9]{4}-W[0-9]{2}$'},
                                                                     'status': {'enum': ['collecting', 'ready']},
                                                                     'policy_version': {'type': 'string',
                                                                                        'minLength': 1},
                                                                     'eligible_participant_count': {'type': 'integer',
                                                                                                    'minimum': 0}},
                                                      'required': ['campaign_id',
                                                                   'week',
                                                                   'status',
                                                                   'policy_version',
                                                                   'eligible_participant_count'],
                                                      'additionalProperties': True}},
               'behavior': {'status': 'awaiting_contract',
                            'owner': '담당자 확인 필요',
                            'source': 'https://app.notion.com/p/3d101daacbe981a5b206d317361666eb',
                            'blocked_reason': '노션에 Python/YAML 첨부 존재. 첨부 코드 본문과 최종 출력 스키마 확보 전 실행 차단',
                            'key': [],
                            'json_schema': None},
               'reward_postings': {'status': 'awaiting_contract',
                                   'owner': '담당자 확인 필요',
                                   'source': 'origin/feature/reward-system:reward_ledger.py',
                                   'blocked_reason': '미병합 코드에는 지급/조정 기록 존재. Gold 이력에 조정 포함 및 중복 기준 계약 인계 필요',
                                   'key': [],
                                   'json_schema': None},
               'ranking': {'status': 'awaiting_contract',
                           'owner': '담당자 확인 필요',
                           'source': 'https://app.notion.com/p/3d501daacbe981108d28cdd232f145bd',
                           'blocked_reason': '노션 작업 대기. 개인/부서 구분, score 단위, 동점 정책, 생성 버전 스키마 미제출',
                           'key': [],
                           'json_schema': None},
               'campaign_kpi': {'status': 'awaiting_contract',
                                'owner': '담당자 확인 필요',
                                'source': 'https://app.notion.com/p/3d101daacbe98100bf73ce579a076fe1',
                                'blocked_reason': '노션 작업 대기. 분모 포함 지표별 출력 스키마 미제출',
                                'key': [],
                                'json_schema': None},
               'mission_candidates': {'status': 'awaiting_contract',
                                      'owner': '담당자 확인 필요',
                                      'source': 'https://app.notion.com/p/3d501daacbe98171a2ebc89a5ab0001c',
                                      'blocked_reason': '노션 v2 후보 선택과 GitHub v3 자동 배정 충돌. 다음 주 후보 Gold 계약 합의 전 실행 '
                                                        '차단',
                                      'key': [],
                                      'json_schema': None},
               'membership_department': {'status': 'awaiting_contract',
                                         'owner': '담당자 확인 필요',
                                         'source': 'https://app.notion.com/p/3d501daacbe981358812c78e3dc35561',
                                         'blocked_reason': '현재 membership JSON에는 부서와 탈퇴일 정의 없음. 시점별 부서 참여정보 Delta '
                                                           '계약 인계 필요',
                                         'key': [],
                                         'json_schema': None}},
 'stages': [{'function': 'weekly_summary',
             'inputs': {'trips': 'source:final_trips'},
             'output': 'weekly_gold',
             'contract': 'weekly',
             'source': 'cloud/azure/pipelines/databricks/build_weekly_summary.py@d268a7d5dec479a557b6393befe8ba3765dcf4f3',
             'owner': '5dt028 / ManiaKCY',
             'implemented': True,
             'kind': 'materialized_view',
             'week_scope': 'history',
             'notes': ['main 미병합 null mode 수정 커밋 재사용',
                       '집계 입력/출력 검증은 공통 코드에서 수행',
                       '0거리 합계의 비율을 try_divide로 계산 후 원본 pivot의 0 처리 적용']},
            {'function': 'baseline_eligibility',
             'inputs': {'weekly_history': 'weekly_gold',
                        'users': 'source:users',
                        'memberships': 'source:memberships'},
             'output': 'baseline_eligibility',
             'contract': 'personal_eligibility',
             'source': 'baseline_eligibility.py',
             'owner': 'Hayden Shin',
             'implemented': False,
             'kind': 'temporary_view'},
            {'function': 'personal_baseline',
             'inputs': {'weekly_history': 'weekly_gold',
                        'eligibility': 'baseline_eligibility',
                        'users': 'source:users',
                        'memberships': 'source:memberships'},
             'output': 'personal_baseline_gold',
             'contract': 'personal',
             'source': 'build_personal_baseline.py',
             'owner': 'ManiaKCY / Hayden Shin',
             'implemented': False,
             'kind': 'materialized_view',
             'week_scope': 'evaluation'},
            {'function': 'personal_ready_users',
             'inputs': {'personal': 'personal_baseline_gold'},
             'output': 'personal_ready_users',
             'contract': 'personal',
             'source': 'build_global_baseline.py',
             'owner': 'ManiaKCY / Hayden Shin',
             'implemented': True,
             'kind': 'temporary_view',
             'week_scope': 'evaluation'},
            {'function': 'global_eligibility',
             'inputs': {'personal_ready': 'personal_ready_users', 'personal_all': 'personal_baseline_gold'},
             'output': 'global_eligibility',
             'contract': 'global_eligibility',
             'source': 'baseline_eligibility.py',
             'owner': 'Hayden Shin',
             'implemented': False,
             'kind': 'temporary_view'},
            {'function': 'global_baseline',
             'inputs': {'personal_ready': 'personal_ready_users', 'eligibility': 'global_eligibility'},
             'output': 'global_baseline_gold',
             'contract': 'global',
             'source': 'build_global_baseline.py',
             'owner': 'ManiaKCY / Hayden Shin',
             'implemented': False,
             'kind': 'materialized_view',
             'week_scope': 'evaluation'},
            {'function': 'weekly_user_profile',
             'inputs': {'weekly_history': 'weekly_gold', 'response_history': 'source:mission_responses'},
             'output': 'mission_profile_gold',
             'contract': 'mission_profile',
             'source': 'build_mission_profile.py',
             'owner': 'ManiaKCY',
             'implemented': False,
             'kind': 'materialized_view',
             'requires': ['mission_profile_v3'],
             'date_scope': 'evaluation'},
            {'function': 'next_week_missions',
             'inputs': {'profiles': 'mission_profile_gold'},
             'output': 'next_week_missions_gold',
             'contract': 'mission_candidates',
             'source': '노션 다음 주 미션 후보 생성',
             'owner': '담당자 확인 필요',
             'implemented': False,
             'kind': 'materialized_view'},
            {'function': 'behavior_change',
             'inputs': {'weekly_history': 'weekly_gold',
                        'personal': 'personal_baseline_gold',
                        'responses': 'source:mission_responses',
                        'trips': 'source:final_trips'},
             'output': 'behavior_change_gold',
             'contract': 'behavior',
             'source': '노션 build_behavior_change.py 첨부',
             'owner': '담당자 확인 필요',
             'implemented': False,
             'kind': 'materialized_view'},
            {'function': 'ranking',
             'inputs': {'postings': 'source:reward_postings', 'memberships': 'source:department_memberships'},
             'output': 'ranking_gold',
             'contract': 'ranking',
             'source': '노션 build_ranking.py',
             'owner': '담당자 확인 필요',
             'implemented': False,
             'kind': 'materialized_view'},
            {'function': 'campaign_kpi',
             'inputs': {'weekly_history': 'weekly_gold',
                        'memberships': 'source:department_memberships',
                        'responses': 'source:mission_responses',
                        'behavior': 'behavior_change_gold',
                        'postings': 'source:reward_postings',
                        'ranking': 'ranking_gold'},
             'output': 'campaign_kpi_gold',
             'contract': 'campaign_kpi',
             'source': '노션 build_campaign_kpi.py',
             'owner': '담당자 확인 필요',
             'implemented': False,
             'kind': 'materialized_view'}],
 'unresolved': ['노션 Mission v2 선택 흐름과 GitHub main Mission v3 자동 배정 계약 불일치',
                'Baseline YAML의 Cosmos→confirmed_trips 경로는 최신 노션 Final Trip Gold 직접 입력 결정과 불일치. 본 연결은 Delta만 입력',
                '개인/그룹 결과와 랭킹/KPI는 서로 다른 스키마. baseline_gold/weekly_outputs_gold에 행 합치기 금지',
                'weekly_gold는 전체 완료 주 이력 재계산. 대상 주만 반환해서 과거 테이블을 덮어쓰는 구현 금지',
                '개인 Baseline 원본은 입력에 존재하는 주차별 과거 누적 계산. W+1 행이 없는 경우 적용 주차 계산 어댑터 필요',
                'Mission Profile Gold 객체는 원본 저장 코드의 JSON 문자열 컬럼 형식. API projection에서는 역변환 필요'],
 'notion_sources': ['https://app.notion.com/p/3d201daacbe9816c8d6de34e04c13a73',
                    'https://app.notion.com/p/3d501daacbe98171a2ebc89a5ab0001c',
                    'https://app.notion.com/p/3d101daacbe981a5b206d317361666eb',
                    'https://app.notion.com/p/3d501daacbe981108d28cdd232f145bd',
                    'https://app.notion.com/p/3d101daacbe98100bf73ce579a076fe1'],
 'storage_boundary': {'pipeline_tables': '선택 캠페인과 실행 인자의 계산 결과 테이블. 운영 이력 저장 완료를 의미하지 않음',
                      'history_export': 'Gold 이력 저장 및 Cosmos 반영은 외부 Job 작업에서 계약별로 연결 필요',
                      'production_enabled': False,
                      'reason': '캠페인 및 주차 이력 보존과 운영 Gold 저장 위치 인계 전 운영 실행 차단'},
 'handoff_guide': ['이 파일에서 본인 이름의 계산 함수 안에 코드 입력',
                   'inputs와 context 인자 유지, 지정된 출력 스키마의 Spark DataFrame 반환',
                   '보조 함수는 같은 파일의 계산 보조 함수 영역에 추가',
                   '실행 범위는 CONFIG.run.enabled_outputs에서 선택. 선행 단계 자동 포함',
                   '미제출 스키마는 CONFIG.contracts에 담당자 계약 입력 및 확인 후 연결',
                   '기존 읽기/쓰기/Cosmos 호출을 계산 함수에 붙이지 않고 DataFrame 변환만 입력']}


def load_contracts(path=None):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else copy.deepcopy(CONFIG)


def run_context(settings):
    config = dict(settings)
    if not config.get("campaign_id", "").strip():
        raise ValueError("run.campaign_id 입력 필요")
    start = date.fromisoformat(config["closed_week_start"])
    effective = date.fromisoformat(config["evaluation_week_start"])
    if start.weekday() != 0 or effective != start + timedelta(days=7):
        raise ValueError("마감 주 월요일과 다음 주 월요일 입력 필요")
    if type(config.get("test_mode")) is not bool:
        raise ValueError("test_mode는 true/false만 허용")
    if not config["test_mode"] and not config.get("commute_scope_verified"):
        raise ValueError("운영 입력의 출퇴근 전용 여부 확인 필요")
    zone = ZoneInfo(config["timezone"])
    week = lambda day: f"{day.isocalendar().year}-W{day.isocalendar().week:02d}"
    config.update(closed_week=week(start), evaluation_week=week(effective),
                  closed_week_end=effective.isoformat(),
                  start_utc=datetime.combine(start, time(), zone).astimezone(timezone.utc).isoformat(),
                  end_utc=datetime.combine(effective, time(), zone).astimezone(timezone.utc).isoformat())
    return config


def execution_plan(manifest):
    stages = {s["output"]: s for s in manifest["stages"]}
    ordered, visiting, visited, sources = [], set(), set(), set()
    def visit(name):
        if name.startswith("source:"):
            source = name.split(":", 1)[1]
            if source not in manifest["sources"]:
                raise ValueError(f"입력 등록 누락: {source}")
            sources.add(source)
            return
        if name in visiting:
            raise ValueError(f"순환 연결: {name}")
        if name in visited:
            return
        if name not in stages:
            raise ValueError(f"출력 등록 누락: {name}")
        visiting.add(name)
        for dependency in stages[name]["inputs"].values():
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(stages[name])
    targets = manifest["run"]["enabled_outputs"]
    if not targets:
        raise ValueError("실행할 enabled_outputs 입력 필요")
    for target in targets:
        visit(target)
    return ordered, sorted(sources)


def approved_contract(manifest, name):
    contract = manifest["contracts"][name]
    if contract["status"] not in {"repository", "repository_storage_adapter", "integration_contract", "team_approved"}:
        raise ValueError(f"계약 미제출: {name}: {contract.get('blocked_reason', '')}")
    if not contract.get("json_schema") or not contract.get("key"):
        raise ValueError(f"출력 스키마 및 고유키 입력 필요: {name}")
    if contract["status"] == "team_approved" and not contract.get("approved_by"):
        raise ValueError(f"계약 확인 담당자 입력 필요: {name}")
    return contract


def preflight(manifest):
    context = run_context(manifest["run"])
    stages, sources = execution_plan(manifest)
    for source in sources:
        spec = manifest["sources"][source]
        approved_contract(manifest, spec["contract"])
        location = spec.get("location", "")
        if spec["kind"] not in {"delta", "table"} or not location:
            raise ValueError(f"Delta 경로 또는 테이블 이름 입력 필요: {source}")
        if spec["kind"] == "delta" and not location.startswith("abfss://"):
            raise ValueError(f"ADLS Delta 입력만 허용: {source}")
        if spec["kind"] == "table" and len(location.split(".")) != 3:
            raise ValueError(f"카탈로그.스키마.테이블 형식 필요: {source}")
        if not context["test_mode"]:
            if "/pipeline_test/" in location or "scaffold" in location:
                raise ValueError(f"운영 실행에 테스트 입력 사용 불가: {source}")
            if type(spec.get("version")) is not int or spec["version"] < 0:
                raise ValueError(f"재실행 기준 Delta version 고정 필요: {source}")
    for stage in stages:
        approved_contract(manifest, stage["contract"])
        if not stage["implemented"]:
            raise ValueError(f"계산 코드 연결 필요: 계산 함수 {stage['function']}")
        for requirement in stage.get("requires", []):
            if requirement not in context.get("acknowledged_contracts", []):
                raise ValueError(f"노션/GitHub 계약 선택 확인 필요: {requirement}")
    if not context["test_mode"] and not manifest.get("storage_boundary", {}).get("production_enabled"):
        raise ValueError("운영 Gold 이력 보존 및 저장 위치 인계 전 운영 실행 차단")
    return context, stages, sources


def field_types(schema):
    types = schema.get("type")
    if types is None:
        values = schema.get("enum", [schema.get("const")])
        types = list({"null" if v is None else "boolean" if isinstance(v, bool)
                      else "number" if isinstance(v, (int, float)) else "string" for v in values})
    return [types] if isinstance(types, str) else types


def sql_value(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + value.replace("'", "''") + "'"


def schema_rule(actual, schema, column=None, required=True, depth=0):
    # 자료형과 필수 컬럼 확인 후 Spark 행 검증식 구성. 자동 캐스팅 및 값 보정 제외
    from pyspark.sql import types as T
    choices = set(field_types(schema))
    matches = {"string": isinstance(actual, T.StringType),
               "integer": isinstance(actual, (T.ByteType, T.ShortType, T.IntegerType, T.LongType)),
               "number": isinstance(actual, T.NumericType), "boolean": isinstance(actual, T.BooleanType),
               "array": isinstance(actual, T.ArrayType), "object": isinstance(actual, (T.StructType, T.MapType))}
    if not isinstance(actual, T.NullType) and not any(matches.get(c, False) for c in choices):
        raise TypeError(f"{column}: 기대 형식 {choices}, 실제 형식 {actual.simpleString()}")
    rules = []
    if isinstance(actual, T.StructType):
        fields = {f.name: f.dataType for f in actual.fields}
        missing = set(schema.get("required", [])) - set(fields)
        if missing:
            raise ValueError(f"필수 컬럼 누락: {column}: {sorted(missing)}")
        for name, child in schema.get("properties", {}).items():
            if name in fields:
                ref = f"{column}.`{name}`" if column else f"`{name}`"
                rules.append(schema_rule(fields[name], child, ref, name in schema.get("required", []), depth + 1))
        if schema.get("additionalProperties") is False and set(fields) - set(schema.get("properties", {})):
            raise ValueError(f"계약 외 컬럼: {column}")
    if isinstance(actual, T.MapType):
        if schema.get("properties"):
            raise TypeError(f"{column}: 고정 필드는 struct로 반환 필요")
        if isinstance(schema.get("additionalProperties"), dict):
            var = f"m{depth}"
            rule = schema_rule(actual.valueType, schema["additionalProperties"], var, True, depth + 1)
            rules.append(f"forall(map_values({column}), {var} -> {rule})")
    if isinstance(actual, T.ArrayType):
        var = f"x{depth}"
        rule = schema_rule(actual.elementType, schema["items"], var, True, depth + 1)
        rules.append(f"forall({column}, {var} -> {rule})")
        for key, op in [("minItems", ">="), ("maxItems", "<=")]:
            if key in schema:
                rules.append(f"size({column}) {op} {schema[key]}")
        if schema.get("uniqueItems"):
            rules.append(f"size(array_distinct({column})) = size({column})")
    if column is not None:
        if "const" in schema:
            rules.append(f"{column} <=> {sql_value(schema['const'])}")
        if "enum" in schema:
            options = [sql_value(v) for v in schema["enum"] if v is not None]
            if options:
                rules.append(f"{column} IN ({', '.join(options)})")
        for key, op in [("minimum", ">="), ("maximum", "<="), ("exclusiveMinimum", ">"), ("exclusiveMaximum", "<")]:
            if key in schema:
                rules.append(f"{column} {op} {schema[key]}")
        if choices & {"number", "integer"}:
            rules.append(f"NOT isnan(CAST({column} AS DOUBLE)) AND abs(CAST({column} AS DOUBLE)) < CAST('Infinity' AS DOUBLE)")
        if "minLength" in schema:
            rules.append(f"length({column}) >= {schema['minLength']}")
        if "pattern" in schema:
            rules.append(f"{column} RLIKE {sql_value(schema['pattern'])}")
        if schema.get("format") == "date-time":
            rules.append(f"try_cast({column} AS TIMESTAMP) IS NOT NULL")
        if schema.get("format") == "date":
            rules.append(f"try_cast({column} AS DATE) IS NOT NULL AND {column} RLIKE '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'")
    valid = " AND ".join(f"({r})" for r in rules) or "TRUE"
    if column is None:
        return valid
    if "null" in choices or not required:
        return f"({column} IS NULL OR ({valid}))"
    return f"({column} IS NOT NULL AND ({valid}))"


def checked(frame, contract, label):
    from pyspark.sql import DataFrame, Window, functions as F
    if not isinstance(frame, DataFrame):
        raise TypeError(f"{label}: Spark DataFrame 반환 필요")
    predicate = schema_rule(frame.schema, contract["json_schema"])
    failure = F.raise_error(F.lit(f"{label}: 값 또는 단위 검증 실패")).cast("boolean")
    result = frame.filter(F.when(F.coalesce(F.expr(predicate), F.lit(False)), F.lit(True)).otherwise(failure))
    keys = contract["key"]
    # 중복 행 삭제 대신 실행 실패. 사용자별 중복 합산 방지
    helper = "__weekly_contract_key_count"
    if helper in result.columns:
        raise ValueError(f"예약 컬럼 사용: {helper}")
    result = result.withColumn(helper, F.count(F.lit(1)).over(Window.partitionBy(*keys)))
    return result.filter(F.when(F.col(helper) == 1, F.lit(True)).otherwise(
        F.raise_error(F.lit(f"{label}: 중복 고유키 {keys}")).cast("boolean"))).drop(helper)


def register_pipeline():
    from pyspark import pipelines as dp
    from pyspark.sql import SparkSession, functions as F
    spark = SparkSession.builder.getOrCreate()
    manifest = load_contracts()
    # 담당자가 예외를 계산 코드로 교체했는지 확인. 별도 implemented 설정 편집 불필요
    for stage in manifest["stages"]:
        hook = globals()[stage["function"]]
        stage["implemented"] = any(op.opname in {"RETURN_VALUE", "RETURN_CONST"}
                                   for op in dis.get_instructions(hook))
    context, stages, sources = preflight(manifest)
    if spark.conf.get("spark.sql.session.timeZone") not in {"UTC", "Etc/UTC"}:
        raise ValueError("파이프라인 설정 spark.sql.session.timeZone=UTC 필요")
    for name in sources:
        spec = manifest["sources"][name]
        contract = approved_contract(manifest, spec["contract"])
        def read_source(name=name, spec=spec, contract=contract):
            reader = spark.read.format("delta")
            if spec.get("version") is not None:
                reader = reader.option("versionAsOf", spec["version"])
            frame = reader.load(spec["location"]) if spec["kind"] == "delta" else reader.table(spec["location"])
            if "campaign_id" in frame.columns:
                frame = frame.filter(F.col("campaign_id") == context["campaign_id"])
            if name == "final_trips":
                frame = frame.filter(F.col("status") == "ready")
                frame = frame.filter(F.to_timestamp("ended_at") < F.to_timestamp(F.lit(context["end_utc"])))
                if not context["test_mode"]:
                    frame = frame.filter(F.when(F.col("is_mock") == F.lit(False), F.lit(True)).otherwise(
                        F.raise_error("운영 입력에 Mock Trip 포함").cast("boolean")))
            if name == "mission_responses":
                frame = frame.filter(F.to_date("week_end") <= F.lit(context["closed_week_end"]).cast("date"))
            return checked(frame, contract, "source:" + name)
        dp.temporary_view(name="input_" + name, comment="분석 저장소 입력: " + name)(read_source)
    for stage in stages:
        hook = globals()[stage["function"]]
        contract = approved_contract(manifest, stage["contract"])
        def calculate(stage=stage, hook=hook, contract=contract):
            inputs = {alias: spark.read.table("input_" + ref.split(":", 1)[1] if ref.startswith("source:") else ref)
                      for alias, ref in stage["inputs"].items()}
            result = checked(hook(inputs, dict(context)), contract, stage["output"])
            if "campaign_id" in result.columns:
                result = result.filter(F.when(F.col("campaign_id") == context["campaign_id"], F.lit(True)).otherwise(
                    F.raise_error("출력 캠페인 불일치").cast("boolean")))
            if stage.get("week_scope") == "evaluation":
                result = result.filter(F.when(F.col("week") == context["evaluation_week"], F.lit(True)).otherwise(
                    F.raise_error("적용 주차 불일치").cast("boolean")))
            if stage.get("date_scope") == "evaluation":
                result = result.filter(F.when(F.col("effective_week_start") == context["evaluation_week_start"], F.lit(True)).otherwise(
                    F.raise_error("Profile 적용 주차 불일치").cast("boolean")))
            return result
        decorator = dp.temporary_view if stage["kind"] == "temporary_view" else dp.materialized_view
        decorator(name=stage["output"], comment=f"{stage['function']} 결과 / {stage['owner']}")(calculate)


# ==================== 팀원 계산 함수 입력 영역 ====================
from pyspark.sql import Window, functions as F


# 주간 집계 원본: 5dt028 작성 / ManiaKCY 수정
# 참조 파일: cloud/azure/pipelines/databricks/build_weekly_summary.py
# 참조 커밋: d268a7d5dec479a557b6393befe8ba3765dcf4f3
# main 미병합 수정: null mode를 invalid_segment로 처리하는 팀원 수정 포함
# 연결 변경: 검증은 공통 입력 계약으로 이동, 주차는 캠페인 timezone 적용
# 연결 변경: 거리 합계 0인 경우 비율 계산 오류 방지를 위해 try_divide 적용
MODES = ["walk", "bike", "car", "bus", "rail"]
LOW_CARBON_MODES = ["walk", "bike", "bus", "rail"]
TRANSIT_MODES = ["bus", "rail"]
SHORT_CAR_MAX_DISTANCE_M = 2000.0


def weekly_summary(inputs, context):
    # 원본 계산: 5dt028 / ManiaKCY
    # 입력: trips / 출력 계약: weekly
    # 전체 완료 주 이력 집계. 현재 주 W+1 제외는 공통 입력 단계에서 처리
    trips = inputs["trips"]
    local = trips.withColumn("ended_at", F.from_utc_timestamp(F.to_timestamp("ended_at"), context["timezone"]))
    weekly = _team_assign_week(local)
    window = Window.partitionBy("campaign_id", "week")
    version = F.struct(F.col("carbon.policy_version"), F.col("carbon.factor_version"))
    # 동일 캠페인/주차 내 정책 또는 배출계수 버전 혼합 시 실행 실패
    weekly = weekly.withColumn("__min_version", F.min(version).over(window)).withColumn("__max_version", F.max(version).over(window))
    weekly = weekly.filter(F.when(F.col("__min_version") == F.col("__max_version"), F.lit(True)).otherwise(
        F.raise_error("동일 캠페인/주차 내 탄소 버전 혼합").cast("boolean"))).drop("__min_version", "__max_version")
    return _team_build_personal_weekly(weekly)


def personal_ready_users(inputs, context):
    # 원본 조건: build_global_baseline.py / ManiaKCY, Hayden Shin
    # 입력: personal / 출력 계약: personal
    version = context["policy_versions"]["eligibility"]
    return inputs["personal"].filter(
        (F.col("status") == "ready")
        & (F.col("method") == "personal_cumulative")
        & (F.col("eligibility_policy_version") == version)
        & F.col("baseline_g_co2e_per_km").isNotNull()
        & ~F.isnan("baseline_g_co2e_per_km")
        & (F.col("baseline_g_co2e_per_km") >= 0)
    )

def baseline_eligibility(inputs, context):
    # 원본 또는 제출 위치: baseline_eligibility.py
    # 작성자: Hayden Shin
    # 입력: weekly_history, users, memberships
    # 출력 계약: CONFIG.contracts.personal_eligibility
    # 아래 예외를 담당 계산 코드와 return 결과로 교체
    raise NotImplementedError("baseline_eligibility: 계산 코드 입력 필요")


def personal_baseline(inputs, context):
    # 원본 또는 제출 위치: build_personal_baseline.py
    # 작성자: ManiaKCY / Hayden Shin
    # 입력: weekly_history, eligibility, users, memberships
    # 출력 계약: CONFIG.contracts.personal
    # 아래 예외를 담당 계산 코드와 return 결과로 교체
    raise NotImplementedError("personal_baseline: 계산 코드 입력 필요")


def global_eligibility(inputs, context):
    # 원본 또는 제출 위치: baseline_eligibility.py
    # 작성자: Hayden Shin
    # 입력: personal_ready, personal_all
    # 출력 계약: CONFIG.contracts.global_eligibility
    # 아래 예외를 담당 계산 코드와 return 결과로 교체
    raise NotImplementedError("global_eligibility: 계산 코드 입력 필요")


def global_baseline(inputs, context):
    # 원본 또는 제출 위치: build_global_baseline.py
    # 작성자: ManiaKCY / Hayden Shin
    # 입력: personal_ready, eligibility
    # 출력 계약: CONFIG.contracts.global
    # 아래 예외를 담당 계산 코드와 return 결과로 교체
    raise NotImplementedError("global_baseline: 계산 코드 입력 필요")


def weekly_user_profile(inputs, context):
    # 원본 또는 제출 위치: build_mission_profile.py
    # 작성자: ManiaKCY
    # 입력: weekly_history, response_history
    # 출력 계약: CONFIG.contracts.mission_profile
    # 아래 예외를 담당 계산 코드와 return 결과로 교체
    raise NotImplementedError("weekly_user_profile: 계산 코드 입력 필요")


def next_week_missions(inputs, context):
    # 원본 또는 제출 위치: 노션 다음 주 미션 후보 생성
    # 작성자: 담당자 확인 필요
    # 입력: profiles
    # 출력 계약: CONFIG.contracts.mission_candidates
    # 아래 예외를 담당 계산 코드와 return 결과로 교체
    raise NotImplementedError("next_week_missions: 계산 코드 입력 필요")


def behavior_change(inputs, context):
    # 원본 또는 제출 위치: 노션 build_behavior_change.py 첨부
    # 작성자: 담당자 확인 필요
    # 입력: weekly_history, personal, responses, trips
    # 출력 계약: CONFIG.contracts.behavior
    # 아래 예외를 담당 계산 코드와 return 결과로 교체
    raise NotImplementedError("behavior_change: 계산 코드 입력 필요")


def ranking(inputs, context):
    # 원본 또는 제출 위치: 노션 build_ranking.py
    # 작성자: 담당자 확인 필요
    # 입력: postings, memberships
    # 출력 계약: CONFIG.contracts.ranking
    # 아래 예외를 담당 계산 코드와 return 결과로 교체
    raise NotImplementedError("ranking: 계산 코드 입력 필요")


def campaign_kpi(inputs, context):
    # 원본 또는 제출 위치: 노션 build_campaign_kpi.py
    # 작성자: 담당자 확인 필요
    # 입력: weekly_history, memberships, responses, behavior, postings, ranking
    # 출력 계약: CONFIG.contracts.campaign_kpi
    # 아래 예외를 담당 계산 코드와 return 결과로 교체
    raise NotImplementedError("campaign_kpi: 계산 코드 입력 필요")


# Personal 연결 주의: 원본 함수는 입력에 존재하는 주차별 과거 누적 계산
# evaluation_week의 결과 생성 어댑터 필요. 현재 주 실제 데이터를 임의 생성하는 방식 제외
# identity는 inputs의 users/memberships Delta로 전달. 원본 Cosmos 직접 조회 경로 호출 제외
# Global 연결 주의: count/collect 기반 분기를 Spark 집계로 변환
# Personal-ready가 0명인 캠페인도 collecting 결과를 만들 수 있도록 eligibility 입력 유지
# Mission 연결 주의: build_profile_from_weekly_summary는 사용자 1명의 dict 기반 함수
# Spark 그룹 변환 어댑터 안에서 호출하고, 원본 run()의 Cosmos 쓰기 및 전체 collect 제외
# Mission Gold 출력은 _gold_profile과 동일한 *_json 컬럼 사용
# Ranking 입력은 실제 지급/조정 Gold. 지급 예정 보상이나 주간 탄소로 임의 대체 금지

# 기존 주간 계산 보조 함수
def _team_assign_week(df):
    trip_date = F.to_date('ended_at')
    iso_day = F.pmod(F.dayofweek(trip_date) + F.lit(5), F.lit(7)) + F.lit(1)
    iso_thursday = F.date_add(trip_date, F.lit(4) - iso_day)
    return df.withColumn('trip_date', trip_date).withColumn('iso_year', F.year(iso_thursday)).withColumn('iso_week', F.weekofyear(trip_date)).withColumn('week', F.concat(F.col('iso_year').cast('string'), F.lit('-W'), F.lpad(F.col('iso_week').cast('string'), 2, '0')))

def _team_explode_segments(df):
    exploded = df.select('trip_id', 'user_id', 'campaign_id', 'week', F.col('carbon.policy_version').alias('carbon_policy_version'), F.col('carbon.factor_version').alias('factor_version'), F.explode('segments').alias('segment'))
    return exploded.withColumn('effective_mode', F.lower(F.col('segment.model_prediction'))).withColumn('distance_m', F.col('segment.distance_m').cast('double')).withColumn('segment_kg_co2e', F.col('segment.carbon_kg').cast('double'))

def _team_compute_mode_metrics(exploded_df):
    per_mode = exploded_df.groupBy('user_id', 'campaign_id', 'week', 'effective_mode').agg(F.countDistinct('trip_id').alias('mode_trip_count'), F.sum('distance_m').alias('distance_m'), F.sum('segment_kg_co2e').alias('kg_co2e'))
    totals = exploded_df.groupBy('user_id', 'campaign_id', 'week').agg(F.countDistinct('trip_id').alias('total_trip_count'), F.sum('distance_m').alias('total_distance_m'), F.sum('segment_kg_co2e').alias('total_segment_kg_co2e'))
    joined = per_mode.join(totals, ['user_id', 'campaign_id', 'week'])
    return joined.withColumn('mode_trip_ratio', F.col('mode_trip_count') / F.col('total_trip_count')).withColumn('mode_distance_ratio', F.try_divide(F.col('distance_m'), F.col('total_distance_m'))).withColumn('mode_carbon_ratio', F.when(F.col('total_segment_kg_co2e') > 0, F.col('kg_co2e') / F.col('total_segment_kg_co2e')).otherwise(F.lit(0.0)))

def _team_compute_trip_primary_facts(exploded_df):
    keys = ['trip_id', 'user_id', 'campaign_id', 'week']
    invalid_segment = F.col('effective_mode').isNull() | ~F.col('effective_mode').isin(MODES) | F.col('distance_m').isNull() | (F.col('distance_m') <= 0)
    quality = exploded_df.groupBy(*keys).agg(F.sum(F.when(invalid_segment, 1).otherwise(0)).alias('invalid_segment_count'), F.sum(F.when(~invalid_segment, F.col('distance_m')).otherwise(F.lit(0.0))).alias('trip_distance_m'))
    valid_segments = exploded_df.filter(~invalid_segment)
    per_trip_mode = valid_segments.groupBy(*keys, 'effective_mode').agg(F.sum('distance_m').alias('mode_distance_m'))
    w = Window.partitionBy('trip_id')
    ranked = per_trip_mode.withColumn('max_mode_distance_m', F.max('mode_distance_m').over(w)).withColumn('is_primary_winner', F.when(F.abs(F.col('mode_distance_m') - F.col('max_mode_distance_m')) < F.lit(1e-09), F.lit(1)).otherwise(F.lit(0)))
    mode_summary = ranked.groupBy(*keys).agg(F.sum('is_primary_winner').alias('primary_winner_count'), F.first(F.when(F.col('is_primary_winner') == 1, F.col('effective_mode')), ignorenulls=True).alias('primary_mode_candidate'))
    result = quality.join(mode_summary, keys, 'left').fillna(0, subset=['primary_winner_count']).withColumn('primary_mode_invalid_reason', F.when(F.col('invalid_segment_count') > 0, F.lit('invalid_segment')).when(F.col('primary_winner_count') != 1, F.lit('primary_mode_tie'))).withColumn('primary_mode', F.when(F.col('primary_mode_invalid_reason').isNull(), F.col('primary_mode_candidate'))).withColumn('primary_mode_valid', F.col('primary_mode_invalid_reason').isNull()).drop('primary_mode_candidate')
    return result

def _team_aggregate_primary_facts(primary_trip_df):
    return primary_trip_df.groupBy('user_id', 'campaign_id', 'week').agg(F.sum(F.when(F.col('primary_mode_valid'), 1).otherwise(0)).cast('long').alias('valid_primary_trip_count'), F.sum(F.when(~F.col('primary_mode_valid'), 1).otherwise(0)).cast('long').alias('invalid_primary_trip_count'), F.sum(F.when(F.col('primary_mode_invalid_reason') == 'primary_mode_tie', 1).otherwise(0)).cast('long').alias('ambiguous_primary_trip_count'), F.sum(F.when(F.col('primary_mode_invalid_reason') == 'invalid_segment', 1).otherwise(0)).cast('long').alias('invalid_segment_primary_trip_count'), F.sum(F.when(F.col('primary_mode') == 'car', 1).otherwise(0)).cast('long').alias('car_primary_trip_count'), F.sum(F.when(F.col('primary_mode').isin(TRANSIT_MODES), 1).otherwise(0)).cast('long').alias('transit_primary_trip_count'), F.sum(F.when(F.col('primary_mode').isin(LOW_CARBON_MODES), 1).otherwise(0)).cast('long').alias('low_carbon_trip_count'), F.sum(F.when((F.col('primary_mode') == 'car') & (F.col('trip_distance_m') <= F.lit(SHORT_CAR_MAX_DISTANCE_M)), 1).otherwise(0)).cast('long').alias('short_car_trip_count')).withColumn('car_primary_ratio', F.when(F.col('valid_primary_trip_count') > 0, F.col('car_primary_trip_count') / F.col('valid_primary_trip_count'))).withColumn('short_car_share', F.when(F.col('car_primary_trip_count') > 0, F.col('short_car_trip_count') / F.col('car_primary_trip_count')))

def _team__pivot_ratio(mode_metrics_df, ratio_col, prefix):
    pivoted = mode_metrics_df.groupBy('user_id', 'campaign_id', 'week').pivot('effective_mode', MODES).agg(F.first(ratio_col))
    for mode in MODES:
        name = f'{prefix}_{mode}'
        pivoted = pivoted.withColumnRenamed(mode, name).fillna(0.0, subset=[name])
    return pivoted

def _team__pivot_mode_distance(mode_metrics_df):
    pivoted = mode_metrics_df.groupBy('user_id', 'campaign_id', 'week').pivot('effective_mode', MODES).agg(F.first('distance_m'))
    for mode in MODES:
        name = f'{mode}_distance_m'
        pivoted = pivoted.withColumnRenamed(mode, name).fillna(0.0, subset=[name])
    return pivoted

def _team_build_personal_weekly(ready_df):
    exploded = _team_explode_segments(ready_df)
    mode_metrics = _team_compute_mode_metrics(exploded)
    mode_distance_pivot = _team__pivot_mode_distance(mode_metrics)
    trip_ratio_pivot = _team__pivot_ratio(mode_metrics, 'mode_trip_ratio', 'mode_trip_ratio')
    distance_ratio_pivot = _team__pivot_ratio(mode_metrics, 'mode_distance_ratio', 'mode_distance_ratio')
    carbon_ratio_pivot = _team__pivot_ratio(mode_metrics, 'mode_carbon_ratio', 'mode_carbon_ratio')
    primary_facts = _team_aggregate_primary_facts(_team_compute_trip_primary_facts(exploded))
    trip_agg = ready_df.groupBy('user_id', 'campaign_id', 'week').agg(F.countDistinct('trip_id').alias('trip_count'), F.sum('carbon.kg_co2e').alias('total_kg_co2e'), F.first('carbon.policy_version').alias('carbon_policy_version'), F.first('carbon.factor_version').alias('factor_version'))
    distance_agg = exploded.groupBy('user_id', 'campaign_id', 'week').agg(F.sum('distance_m').alias('total_distance_m'))
    return trip_agg.join(distance_agg, ['user_id', 'campaign_id', 'week']).join(mode_distance_pivot, ['user_id', 'campaign_id', 'week']).join(trip_ratio_pivot, ['user_id', 'campaign_id', 'week']).join(distance_ratio_pivot, ['user_id', 'campaign_id', 'week']).join(carbon_ratio_pivot, ['user_id', 'campaign_id', 'week']).join(primary_facts, ['user_id', 'campaign_id', 'week'], 'left')


# 로컬 계약 검사에서는 등록 제외. Databricks 파일 실행 시 연결 등록
if __name__ != "weekly_contract_test":
    register_pipeline()
