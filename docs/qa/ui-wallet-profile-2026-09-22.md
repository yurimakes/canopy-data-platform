# Home, wallet and profile refinement — 2026-09-22

## Implemented
- Restored original home tree scenery, increased hero space, personalized typewriter speech bubble and one journey-start action. Nunito extra bold used for token numerals.
- Origin comes from a fresh foreground GPS fix. Only destination is picked. Permission denied, stale/inaccurate fixes and timeout do not fall back to a saved address. Route quote refreshes origin after 30 seconds.
- Personalized weekly missions, no manual start action. Existing completion stamp and claim flow retained.
- Wallet shows actual loaded token balance and a clearly labeled mock redemption catalog. Starbucks coffee, CU voucher and N Pay examples open a non-transactional preview. No debit or issuance API is called.
- Reward history is its own screen, reached from profile, using existing reward data and filters.
- Profile removes duplicate balance, home/work, mission and ranking blocks. Retains history and adds settings, guide and privacy pages.
- Privacy notice is explicitly a draft. Operator, contact, retention/deletion policy, external processing contracts and effective date still require confirmation. No invented legal retention period or contact details.

## Verification
- TypeScript check passed.
- 19 test suites, 99 tests passed with CANOPY_TEST_PYTHON set to the repository Python environment. Plain npm test initially failed because the default apps/api/.venv Python path does not exist on this machine; rerun with configured interpreter passed.
- iOS Expo export passed (819 modules). This is a local bundle check, not a new TestFlight build.
- Browser preview checked at 390px and 320px: home, wallet, product preview, profile, reward history, missions and privacy screen. Document width equals viewport at 320px.
- Current-origin helper tests cover success, denied permission, stale/inaccurate/invalid coordinates and timeout. Device GPS prompts remain a real-device check.
- Catalog is demonstration only. No Azure or Databricks changes in this pass.

## Asset provenance
- reward-coffee.png: generated via built-in image generation, then resized to 384px for bundling. Neutral iced americano, no brand logo or label. Brand names in catalog are text placeholders, not official supplied artwork.
- Prompt: A single premium app reward product illustration: clear glass of iced americano with ice cubes, subtle condensation, espresso brown drink, a small neutral ivory coaster. Three-quarter studio product photograph, soft mint reflected light, appetizing polished high-end mobile shopping app art, transparent background, complete glass centered with 12 percent padding, square composition. No brand logo, no text, no labels, no watermark.
- Numeral font: @expo-google-fonts/nunito bundled dependency, SIL Open Font License.
