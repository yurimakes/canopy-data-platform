# Route quote failure — 2026-09-26

Observed 09:14–09:15 KST journey_action HTTP 503, ValueError. User document read returned 200 in the same operation. Read logs through ARM workspace query because Application Insights data-plane token issuer did not match the managed tenant.

Downloaded the current released-package.zip from the configured deployment container. Replayed its KTDB model and references: coordinates near Hongje caused `SGIS centroid 1113062 has 0 KTDB mappings`. SGIS uses 홍제1동 and KTDB uses 홍제제1동; 홍은1동/홍은제1동 has the same naming issue.

Fix: preserve direct code matches. Only when absent, compare the full administrative name and its numbered-dong 제 variant. Require exactly one candidate. Historical duplicates and unrelated districts are never guessed. Regression tests: 3 passed. Actual packaged model runs: Hongje/Hongeun, Jongno/Hongeun, and an existing Yeongdeungpo/Jongno route passed after the fix.

Deployment uses the current full package, changing only runtime-assets/reference-model/src/integration/ktdb_context.py plus release-id.txt. Previous package preserved at .local-data/route-quote-hotfix/live-before.zip outside the repo. No app rebuild, model retraining, wallet or GPS inference changes.

Remaining limitation: RoutePlanner currently treats quote failure as fatal even when TMAP succeeds. Ambiguous or still-unmapped administrative names can therefore still block the search. That broader UI fallback is not part of this narrowly scoped server patch.

Deployment verified: /api/health HTTP 200, release route-name-33e4e3a2923b8df9041e. Exact user-authenticated route request was not replayed; validation used the deployed model/reference assets and representative coordinates.
