# Canopy UI redesign — 2026-09-21

## Scope

- Unified forest, lime and warm paper palette; consistent typography, cards, buttons, tabs and headers.
- Reworked landing/auth, home, route/baseline, active journey, result, missions, rankings, wallet, profile, history and notifications.
- Short Korean primary copy; detailed calculation rules behind disclosures.
- Real Three.js rotating coin and trophy, articulated walking mascot, reward count-up and coin-to-wallet transition with haptics. Reduced-motion preferences respected; background GPU rendering skipped.
- Journey information remains outside the map clipping area. Collapsed state retains an accessible expand control, duration, distance and speed. Active journey hides bottom tabs.
- Profile photo selection, square JPEG resizing, authenticated server validation/storage, and campaign-scoped ranking photo projection. No change to reward calculation or eligibility policy.
- Reward celebration requires a finite positive server-confirmed paid amount. Excluded/no-reduction trips show terminal explanations instead of endless pending states.

## Verification

- TypeScript typecheck passed.
- Frontend suite: 95 tests across 18 files passed, including journey toggle/small-screen regression and reward presentation states.
- API account suite: 13 tests passed, including photo update/login persistence, invalid input and removal.
- API photo validation suite: 2 tests passed.
- iOS Hermes export succeeded: 800 modules. Output is local-only at `.local-data/ui-redesign-export`.
- Browser fixture preview checked at 320×568, 390×844 and 430×932: navigation, rankings/podium, wallet filters, profile edit, reward popup/dismissal, movement collapse/reopen and horizontal overflow. These are browser checks, not physical iPhone verification.
- Preview uses clearly labelled example data and development-only entry. Mission preview actions do not write to the server.

## Release boundary

This change is local/repository implementation, not an Azure deployment or TestFlight release. Deploy the account/API changes (including Pillow dependency) before using profile photo persistence in production. Create a new EAS native build because image-picker/image-manipulator/haptics dependencies and permissions changed.

On a physical iPhone verify safe areas with large text, photo picker cancel/save/permission behavior, native map walking marker, reward animation/haptics, reduced motion, and background/resume. Do not infer GPS/Databricks runtime health from this UI preview.

## Design reference

Duolingo's milestone motion and clear primary navigation informed reward emphasis and tab hierarchy; Apple's motion guidance informed reduced-motion handling. Existing Canopy mascot art retained. No third-party brand art was copied.
