# Journey controls — iOS build 9

The movement panel previously lived inside the flexible, clipped map container. The phone report showed that collapsing it left no visible reopen control. The panel now belongs to the non-shrinking bottom safe-area footer with the stop button, outside the map. Global LayoutAnimation is removed from the collapse action. The toggle remains mounted; only the expanded details change. Expanded details scroll within 30% of window height.

During starting, recording and stopping, the app hides the bottom tabs and header navigation/settings. Navigation is guarded as well. Once stopping finishes, the result screen and tabs return. The footer owns the bottom safe inset while tabs are absent.

Validation:
- TypeScript check passed.
- All 17 test files / 93 tests passed using the repository Python environment for the local API integration suite.
- New React component regression tests repeat collapse/reopen five times at four simulated window heights (568, 667, 844, 932), retain the toggle and summary, and check expanded detail bounds.
- Integration component test checks the panel is a direct child of the non-shrinking bottom safe-area footer, excluded from the map component, and tabs remain hidden through stopping and return afterward.
- Component tests mock native views. They validate state and component structure, not iOS MapKit rendering or physical phone pixels. Physical TestFlight verification remains necessary.

No Azure pipeline or server changes are part of this fix.
