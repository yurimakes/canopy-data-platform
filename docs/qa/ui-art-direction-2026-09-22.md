# Canopy illustration and motion pass

## User constraints

Keep current navigation, screen purposes, campaign rules and reward policy. Use the supplied September 22 reference for its atmosphere, not its screen layout. Replace generic feature icons with premium bespoke illustrations. Preserve Canopy mascot identity.

## Implemented

- Nine individually generated transparent icon assets: office, home, bus, mission, wallet, walking shoes, trophy, leaf and profile. Bundled locally; 320px PNGs, approximately 117–178 KB each. No asset network request is required.
- New full-bleed eco-city garden illustration for a skippable 3.2-second introductory slogan. Fade reveals the existing welcome/login choices. Intro plays once per JS session. Login and campaign validation behavior remains unchanged.
- Existing home section order preserved. Illustrated commute cards, garden-backed mascot conversation, tap-to-reveal typewriter text, soft raised surfaces and illustrated tab icons.
- Mission progress remains server driven. Claimable/completed missions get a stamp animation once per mounted application session. Claimable buttons have a travelling sheen. Successful `paid` response triggers card exit, positive reward celebration and the completed tab. Failed requests do not mark a mission complete. Claim lock prevents repeated taps in flight.
- Reduced-motion preference suppresses typing, stamping and looping sheen. Sheen stops when the app backgrounds. Existing 3D coin and articulated walking are retained.
- Semantic feature icons shared by route/baseline/history/profile/results use the new art. Standard action glyphs remain for back, close, settings, checkboxes and arrows so these controls remain recognizable.

## Map finding and change

The iPhone map is `react-native-maps` using the system Apple Maps provider. The old-looking screenshot was not proof of an outdated map dataset. Existing code explicitly requested pitch 30 and default 3D buildings.

Changed to iOS `mutedStandard`, pitch 0, buildings/POIs hidden and pitch gestures disabled; route geometry, GPS and destination markers unchanged. This is a presentation change, not a provider/data update. Android retains `standard`.

For a Korean map-provider migration, NAVER's current Maps Mobile Dynamic Map iOS SDK is a supported option. It requires a Maps application/client ID, iOS bundle configuration, native SDK integration and a new build. No provider account or paid resource was created. Do not describe the Apple styling change as a NAVER migration or guaranteed freshest road data.

Sources checked September 22:
- https://github.com/react-native-maps/react-native-maps/blob/master/docs/mapview.md
- https://developer.apple.com/documentation/mapkit/mkmapview/showsbuildings
- https://guide.ncloud-docs.com/docs/maps-ios-sdk
- https://api.ncloud-docs.com/docs/en/application-maps-dynamic

Design benchmark: Duolingo's milestone celebration and clear achievement feedback, applied to Canopy's existing flow; no copied brand assets. https://blog.duolingo.com/streak-milestone-design-animation/

## Verification

- TypeScript passed; 95 existing frontend tests passed.
- iOS Hermes export passed, 813 modules; all new images bundled.
- Browser fixture: typewriter reveal, mission progress change, stamp DOM appearance, reward claim, 5 T popup, confirmation and completed mission tab verified. No real rewards written by this fixture.
- Welcome intro disappears automatically, login CTA opens actual login form.
- Physical iPhone native map appearance, device motion and large accessibility text still require the next TestFlight build. No Azure changes made in this UI pass.

## Asset provenance and prompt set

Built-in imagegen, individually generated; originals remain under Codex generated_images. Final assets: `apps/ios/assets/canopy-ui/premium/`. PNGs resized losslessly in content (no redraw) with Sharp for app packaging.

Office prompt: premium miniature eco office building, three-quarter isometric, rounded teal glass windows, ivory facade, emerald roof garden and sculptural leaf; glazed ceramic/frosted glass, soft studio light, emerald/mint/pale blue/ivory, transparent square PNG, complete centered object, no tile/frame/text.

Home/bus/mission/wallet/walk shared prompt: "Use case: stylized-concept. Asset type: single premium mobile app illustrated icon. Subject: [subject]. Friendly miniature, sophisticated cute glazed ceramic/clay 3D rendering, subtle frosted materials, soft studio light from upper left, coherent emerald #176B50 mint pale blue warm ivory palette with small golden accents. Centered complete object, 12% margin, transparent background with very soft contact shadow. Square PNG. No tile, frame, text, watermark or extra unrelated objects. Not a flat outline symbol. Must read beautifully at 64px."

Subjects:
- Home: rounded ivory cottage, emerald pitched roof, honey-lit window, mint shrub.
- Bus: rounded sky-blue electric city bus, ivory windshield rim, emerald roof, dark glass windshield, tiny rubber wheels.
- Mission: ivory folded quest card, emerald check-mark seal, gold star and two leaf sprigs.
- Wallet: emerald leather coin purse, two golden coins, embossed leaf.
- Walk: mint and ivory walking sneakers, lime heel tab, sculpted sole.

Trophy/leaf/profile shared prompt: single premium cute mobile app icon, three-quarter isometric glazed ceramic and frosted glass, emerald/mint/ivory/gold, transparent square PNG, centered complete object, 12% padding, no text/tile/frame/watermark.
- Trophy: golden cup, round handles, emerald pedestal, embossed leaf.
- Leaf: jewel-like emerald leaf, curved midrib, clear dew drop.
- Profile: rounded ivory eco robot head, emerald faceplate, two luminous eyes and mint sprout. Decorative profile symbol, not a replacement of the brand mascot.

Scenery prompt: "Premium mobile eco mobility app full bleed portrait opening illustration, lush optimistic contemporary Korean eco city park, pale ivory and blue glass buildings, winding light stone footpath, emerald trees and foreground foliage. Polished cinematic stylized 3D render with soft morning sunlight, delicate depth of field, mint haze and blue sky. Upper 38 percent quiet pale blue sky for later slogan overlay. No text, typography, logos, UI, phones, characters, people, mascot or watermark."
