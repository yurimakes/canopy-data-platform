# Backpack Canopy animation assets

Character reference: `canopy-poc-archive-20260911/assets/canopy-ui/landing-mascot-point.png`.
The green tree mascot with a teal backpack replaces the robot character.

Each `*-poses.png` is a generated 6 by 6 sheet with 36 distinct chronological
poses. `tools/local/encode_backpack_gifs.py` assembles the cells in reading order,
adds optical-flow intermediates (including the last-to-first transition), and
encodes 108-frame transparent GIFs with one shared palette per action.

- `wave`: greeting on login, home, and other greeting placements.
- `walk`: movement indicator and walking map marker.
- `celebrate`: jumping and leaf confetti on journey completion.

Each loop lasts 3.6 seconds. The frame delays repeat 30/30/40 ms, averaging
30 frames per second. `manifest.json` contains decoded frame counts, unique
frame counts, loop flags, and byte sizes. A PNG poster is used for reduced
motion and when the app is in the background. Files are bundled locally;
there is no image-generation or image-download request at app runtime.

Source sheets are retained for reproducibility and are not imported by the app.
Only the three GIFs and their posters are included in the iOS asset export.
