# Weekly mission personalization v2

Date: 2026-09-16
Policy: `mission-policy-v2`

## Decision

Weekly missions no longer auto-assign one mission from mobility ratios alone. The server creates a weekly **offer set**, the user selects one candidate, and only then is one active assignment created.

Personalization is split into three independent signals:

1. **Behavior fit**: mobility data such as car trips, short car trips, transit trips, and low-carbon trips decides which mission content is realistically applicable.
2. **Category preference**: repeated choices among simultaneously offered categories estimate what motivational style the user prefers.
3. **Family capability**: target count and achievement history decide the next difficulty for the same mission family.

Completion is not treated as direct preference evidence. A user can like difficult challenges and still fail them; mixing completion into preference would confuse taste with capability.

## MVP categories

- `challenge` — 도전형
- `habit` — 꾸준형
- `easy_win` — 가벼운 실천형
- `explore` — 새로운 시도형

The names and catalog are policy data, not hard-coded API branches, so the team can rename or add categories by policy version.

## Cold start

A completely new user can receive offers without a mission profile. One starter candidate is produced from each category. All categories start with the same Beta prior `Beta(1,1)`, so the first offer order falls back to policy order rather than pretending to know a preference.

`target_count=1` for starter missions is the minimum measurable behavior unit, not a population threshold or an inferred capability.

## Preference learning

For a week in which one candidate is selected:

- selected category: `alpha += 1`
- other simultaneously offered categories: `beta += 1`
- no selection that week: no preference update

`preference_score = alpha / (alpha + beta)`

This gives a transparent Bayesian estimate. The MVP keeps one candidate from every category visible and sorts them by this score; the top candidate is marked recommended. Because every category remains observable, the MVP does not need an exploration coefficient or random bandit sampling.

A later version can reduce the visible set using Thompson Sampling/UCB/contextual bandits once there is enough real interaction data.

## Difficulty personalization

Difficulty is tracked by `mission_family`, not by category. For adaptive count missions:

- no usable previous result: 1
- prior achievement >= 100%: previous target + 1
- partial achievement: keep target
- 0% achievement: previous target - 1, minimum 1
- never exceed the latest observed opportunity count when an opportunity field exists

This means a user can prefer `challenge` while still receiving a challenge target matched to their demonstrated level.

## Offer and assignment state

One `(campaign_id, user_id, week_start)` has:

- at most one deterministic `mission_offer_set`
- at most one deterministic `mission_assignment`
- assignment only after user selection
- offer set and assignment remain frozen after issue/selection

GET `/api/users/me/missions?week=...` returns either the active assignment or an `awaiting_selection` offer set. POST `/api/users/me/missions/select` selects one candidate and creates the assignment.

## Mission profile v2

The weekly profile combines:

- mobility behavior: `car_ratio`, `short_car_trip_count`, `short_car_share`, `transit_primary_trip_count`, `low_carbon_trip_count`
- preference: `category_preferences` with alpha/beta/posterior mean/observations
- capability: `family_capability` with last target and last achievement rate
- previous assignment summary and carbon-change context

A user with no Trip in the completed week can still have `profile_status=preference_only` if choice history exists. A brand-new user with no profile is handled directly by cold-start offer generation.

## Event-contract consequence

The existing analytics event contract needs one additional unambiguous choice event: `mission_selected` (or an equivalent server-side selection record). `mission_shown`/`mission_started`/`mission_completed` alone cannot reconstruct which candidate won against which alternatives.

The durable offer set itself stores all offered candidates and the selected template, so preference rebuilding does not depend only on mobile telemetry. `mission_selected` should still be kept for product analytics and event-funnel analysis.

## 20 policy scenarios covered by tests

1. cold start offers four categories
2. equal prior score for all cold-start categories
3. cold-start target is minimum measurable unit
4. stale behavior data still allows preference ranking but uses starter content
5. short-car opportunity selects challenge short-car template
6. car opportunity without short-car selects challenge transit template
7. habit category chooses maintenance template when applicable
8. easy-win category chooses low-friction short active template
9. explore category chooses applicable new-mode template
10. prior completion raises same-family target
11. partial completion holds target
12. zero completion lowers target, minimum 1
13. target escalation is capped by opportunity
14. learned preference ranks preferred category first
15. equal preference remains deterministic by policy order
16. weekly offer set is idempotent/frozen
17. user selection creates one assignment
18. later conflicting selection cannot replace assignment
19. a template not in the offer set is rejected
20. weekly retrieval returns the selected assignment after selection
