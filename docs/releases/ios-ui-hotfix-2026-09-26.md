# iOS UI hotfix — 2026-09-26

- Source: `85c9c31`, branch `feature/route-carbon-clarity`.
- Replaced measured, percentage-sized SVG speech-bubble background with a content-sized native rounded View. Tail uses fixed numeric SVG dimensions. Greeting overlay uses explicit top/right/bottom/left.
- Ranking presentation runs in the release component, not only DesignPreview. Seeded test-employee datasets receive the approved roster and distinct descending demo points. Shin Mincheol's matching row is placed first; account IDs and isMe identity remain attached to the same rows. These display values do not update accounts, wallets or reward calculations.
- Three individual podium entries; stable ordinal positions; ten-at-a-time reveal retained. Weekly and cumulative lists use the same adapter. Ordinary non-test data keeps original names and points.
- Validation: TypeScript passed; 114 tests in 24 files passed; iOS Hermes export passed (929 modules), Jua and mascot assets included.
- Limitation: in-app browser failed to initialize its runtime (missing kernel assets). No new iPhone/simulator screenshot was obtained in this Windows session. Native visual behavior needs confirmation on the installed hotfix.
- EAS production build and automatic TestFlight submission requested; status to be updated after receipt.
- Existing uncommitted API/profile changes excluded from this mobile code commit.

## Build receipt
- Version: 0.1.3 (17)
- Build: https://expo.dev/accounts/haydens2hn/projects/canopy-gps-collector/builds/4a2ef0d4-d802-418a-bf01-e472a0dafc4f
- Submission: https://expo.dev/accounts/haydens2hn/projects/canopy-gps-collector/submissions/93b5f349-5c05-4772-8e61-741740d7686f
- Initial status: build IN_PROGRESS; submission AWAITING_BUILD, no reported error.
