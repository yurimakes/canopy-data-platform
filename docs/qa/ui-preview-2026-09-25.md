# UI preview — 2026-09-25

Preview: http://localhost:8097/?design-preview=1
Restart using Start-UiPreview.ps1 from this worktree.
Repository: canopy-data-platform, feature/route-carbon-clarity.
No EAS build, OTA, server deployment, production data edit or main merge.

- Route cards compare route-leg carbon estimates against the distance-scaled comparison baseline. Example rail 42g versus bus 339g; comparison baseline 440g.
- Selected-route journey removes the baseline card. Native map keeps route geometry, with muted colors and rounded pins. Web is a labelled offline geometry preview, not an Apple Maps screenshot.
- Result heading: 비교 기준보다. Existing savings/excess values are preserved.
- Ranking sorts API ranks, displays the top three distinct ranks, reveals ten more entries per click. Preview contains 200 named examples; first six are 신민철, 김창연, 박준용, 김이레, 최유리, 양유진. Production accounts and scores are unchanged.
- Rewards retain product images, prices 150/200/200 T, detail -> exchange -> example barcode. No tokens deducted or real vouchers issued.
- Jua font is consistent throughout. Home greeting types on entry, respecting reduced motion.
- Profile photo field support verified. Profile PATCH HTTP limit is now 64KB for the existing 60KB image allowance; other auth requests retain 16KB limit.

Validation: TypeScript passed; 15 targeted app tests and 13 account API tests passed. Browser at 390x844 checked home typing, different route estimates, podium, ten-more pagination, example barcode and local photo selection/save. No browser console errors in those checks.

Native map rendering and live profile persistence require later device/release verification. Preview profile changes use local example state.

## Mascot update (local preview only)
- User GIFs copied unchanged to apps/ios/assets/mascot/{login,complete,processing}.gif.
- Login: image load -> 5450ms original GIF duration -> staggered canopy letters -> login form (saved profile retains welcome/continue). Load failure exits intro. Reduced-motion skips greeting animation.
- Processing uses actual journeyStage status; no timer-driven fake completion. Preview has explicit sample stage control.
- Map: 40px face-only neutral/moving assets; no arrow/body. Existing fresh GPS speed >0.5km/h controls expression, including vehicle motion. Unknown speed displays neutral expression, not a transport claim.
- Generated face prompts: exact mascot head only, transparent background; expression-only matching variant with >< eyes and open laughing mouth. Originals retained under .codex/generated_images.
- Checked 390x844 web preview: both faces, expression toggle, greeting->login, processing layout, completion GIF. TypeScript and 15 existing targeted tests pass. Native iPhone map/GIF behavior needs device verification. No build/deployment performed.

### Login flow correction
Replaced the old LandingScreen itself. Greeting GIF remains mounted at its final frame; logo and login/signup controls reveal below it in the same layout. No automatic navigation to a separate form. Form navigation only follows a button press. Typecheck passes; old landing tagline/mascot removed from this flow.

### Login garden
Added code-native decorative sun, drifting clouds and swaying grass around the supplied greeting GIF. Native-driver transform loops pause in background and respect reduced motion. Login controls use bounded logo reveal timing so background animation loops cannot delay access. No build/deploy.

### Completion dust
Added 24 small green/gold particles rising from both sides of the completion mascot and fading out, with a quiet pause between bursts. Decorations ignore touches, stay above the heading, pause in background and disable for reduced motion. Verified mobile-width browser screenshot and TypeScript/diff checks. No build/deployment.

### Login background match
Login now uses shared C.paper (#F8F9F1), identical to the main page. GIF wrapper uses multiply compositing against that same surface to blend its opaque white background without changing the source animation. TypeScript passes. Native compositing still needs device verification; no build/deploy.
