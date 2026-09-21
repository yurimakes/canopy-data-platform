# Canopy source-sheet 2D rig

The original 1536×1024 sheet is stored unchanged as `source.png`. SVG clipping preserves its artwork; `sheetRig.ts` defines cutouts and pivots, and `sheetMotion.ts` defines joint motion. This is a 2D cutout rig, not a reconstructed 3D model or a pre-rendered frame sequence.

## App usage

```tsx
<CanopyMascot pose="wave" expression="neutral" height={240} />
<CanopyMascot pose="walk" direction="right" />
<CanopyMascot pose="thumbsup" expression="happy" />
<CanopyMascot pose="idle" expression="love" hand="palm" />
```

Motions: `idle`, `wave`, `walk`, `run`, `jump`, `cheer`, `think`, `surprise`, `sit`, `point`, `thumbsup`, `okay`, `cycle`, `complete`. Existing aliases `start` and `garden` remain supported.

Expressions: `neutral`, `wink`, `joy`, `happy`, `surprised`, `sad`, `angry`, `calm`, `love`, `dizzy`, `disappointed`, `thinking`; `auto` follows the action. Profile travel actions retain the sheet's profile head because the supplied expression drawings are frontal. They must not be pasted onto a side-facing body.

Hand overrides: `auto`, `palm`, `fist`, `pointHand`, `thumbHand`, `okayHand`. Overrides apply to the character's selected gesture arm.

## Preview

Run `node tools/local/preview_sheet_rig.cjs` from the repository root, then serve `.local-data/rig-preview` on port 8093. Open `/sheet-2d/`. The preview contains all expressions and actions, pause/scrub controls, reflection, and a joint overlay. It imports the same motion code as the app.

Tests sample each action in both directions, checking wrist/knee/ankle attachments and finite transforms. Browser visual checks remain necessary: attachment tests do not establish artistic fidelity. iPhone device playback must be checked separately from the browser and iOS export.


2026-09-20: hello.png, walk.png, celebrate.png are static full-body cutouts from source.png. The app uses React Native Image with contain sizing; it does not reconstruct or animate separate body parts. Original pixels and proportions are preserved, with transparent silhouette masks.
