# Backpack mascot and UI refinement

Changes:

- Restored the landing screen from commit `9d73705`, retaining current login
  and signup handlers. Replaced its mascot with the POC backpack character.
- Central mascot component maps greeting, walking, and completion to local GIFs.
  The 3D coin remains a coin; the old generated 3D character is no longer used.
- Home background width is the full card width. Its explicit height follows
  the measured card width to avoid React Native Web's intrinsic image height.
  Character is positioned at the bottom of the card.
- Start button uses a 24px radius without the previous bottom shadow strip.
  Token and challenge cards share `#E6F0D9`.
- Achieved mission stamp remains visible, including remounts and reduced motion.
  Completed cards render at 65% opacity. Stamp has its own space so it does not
  obscure the reward amount or claim button.
- Ranking removes both header and first-place trophies, raises/slims podiums,
  and uses distinct gold/silver/bronze SVG medals in podium and ranking rows.

Validation:

- TypeScript typecheck passed.
- Existing app tests: 19 suites, 99 tests passed.
- iOS Expo export includes all three GIFs and all three reduced-motion posters.
- All three GIFs decode to 108 unique frames, loop indefinitely, and each uses
  36 distinct source poses. Approximately 1.8 MB per GIF.
- Browser preview checked at 320px, 390px, and 430px widths: home right edge,
  bottom mascot, previous landing, podium medals, and no document overflow.
- Preview mission flow: achieve, claim, reward confirmation, completed tab.
  Completed stamp remains visible and completed card is faded.

Limits: Browser preview and iOS export are not an installed iPhone test.
No new EAS build, TestFlight upload, Azure mutation, or real reward write was
performed for this UI change.
