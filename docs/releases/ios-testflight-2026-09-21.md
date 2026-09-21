# iOS TestFlight — 2026-09-21

- 0.1.0 (2): 첫 TestFlight 배포.
- 0.1.0 (3): 가입 첫 화면에서 서버 캠페인 검증 후 다음 단계로 이동. 서버 미등록 코드 거절, 통신 실패 시 진행 차단. 빌드/Apple 업로드 완료 확인.
- 0.1.0 (4): 빌드 3 수정과 사용자 제공 Canopy 캐릭터 아이콘 포함.

아이콘 원본은 `apps/ios/assets/canopy-app-icon.png`. 제공 파일을 바이트 변경 없이 복사하고 Expo icon 설정에 연결했다. Expo의 실제 iOS 아이콘 생성기를 로컬에서 실행하여 1024×1024 RGB(불투명) 출력을 확인했다. 투명 외곽은 Expo 표준 동작에 따라 흰색으로 합성된다. 캐릭터를 재생성하거나 잘라내지 않았다.

빌드 4: 346d3e46-b9f2-4d5a-9600-aa06247a6e0f
제출 4: e1fe6e87-96de-4cb2-bb58-efbb08e4aa5f

앱 설치 후 확인: 잘못된 캠페인 코드가 첫 화면에서 차단되는지, MSDS가 장소 설정으로 진행되는지, 새 아이콘이 표시되는지. 기존 로그인/위치 권한 등은 유지한다. 빌드/업로드 성공과 Apple 처리 후 기기 설치 확인은 구분한다.

빌드 4와 EAS Submit 모두 FINISHED, 제출 오류 없음 확인. App Store Connect 업로드 완료 상태이며 Apple 처리 후 TestFlight 업데이트로 설치한다. 실기기 아이콘/가입 첫 화면 확인은 설치 후 수행한다.

## Build 6 — original frame crop

User approved the original artwork cropped to its rounded green frame, with no generated artwork and no added green background. Source: ChatGPT Image 2026년 9월 21일 오후 04_12_04.png (1254 square). Crop rectangle (122, 139, 1133, 1150), uniformly resized to 1024 square with Lanczos. The part of the leaf outside that frame is cropped as requested. Original alpha is retained in the source asset; Expo generates the opaque native icon with its standard corner matte. No outer padding was added. Actual Expo native icon output inspected locally.

Build 5 (eff4ae0b-f502-40bf-a6ab-9f1d90a3ee75) was canceled because its green backdrop was rejected. Build 6 uses only the approved frame crop. Apple upload status will be recorded after completion.

Build 6: d6c66e85-0a28-4ef7-b5a1-e4a8ddd4bc58 — FINISHED.
Submission 6: 265a8c20-6c8b-4644-9892-ca153c31b54d — FINISHED, no submission error.
Apple upload completed. TestFlight availability depends on Apple processing; device installation and icon display remain device checks.

## Build 7 — physical-phone findings

Observed phone trip 9e897cce-fee1-5a54-a37d-7c3a31c1959a: 91 expected GPS points, four output segments. Ended 08:23:30.999 UTC; Cosmos ready/updated 08:23:48.938 UTC (17.939 seconds). Databricks completed; phone screenshot still showed processing and a native fetch cancellation. Exact network cancellation trigger is not proven by the screenshot.

Changes: separate local UI refresh from serialized network work; recover lost Stop responses by reading server state before resubmitting; preserve current-trip errors separately from history errors; normalize native fetch cancellation and allow 20 seconds for requests. Keep durable retry and server idempotency. Each full-screen modal owns a SafeAreaProvider. Native map fills an explicitly bounded container so it cannot push the collapsible movement panel outside the screen. Panel remains below map with compact elapsed/distance/motion summary when folded. Long route endpoint labels and button labels can shrink/wrap.

Movement indicator: provisional GPS speed indication, explicitly labeled estimate; no claim of live bus/car/rail ML classification. Existing final ML results unchanged. No new backend or teammate pipeline changes in this release.

Validation: 84 app tests pass and TypeScript passes. Tests cover a Stop response lost after server acceptance and native cancellation before acceptance, recovering without creating another Trip. Native map bounds and modal insets require physical-device verification on the new binary; desktop tests do not establish every iPhone layout.
