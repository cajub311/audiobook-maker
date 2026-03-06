# Audiobook Maker - Later Phases Backlog

This file tracks larger follow-up items that are intentionally staged after the current quick-win and architecture refactors.

## Web-first expansion (planned)
- Build async cloud processing pipeline behind `POST /api/process`:
  - queue + worker lifecycle
  - `job_id` polling endpoint
  - optional webhook callback
- Add browser upload + download flow for no-install users.
- Add persistent cloud storage option for generated files and manifests.

## Android-native polish (planned)
- Material-style toast system with richer status states.
- Native share-sheet path for generated files in launcher pages.
- Gesture navigation experiments (swipe tab switch).
- Additional on-device performance tuning for low-end Android phones.

## Easy mode UX enhancements (planned)
- Add fully guided first-run screen (Easy vs Advanced entry point).
- Add optional one-voice selector in Easy mode (single dropdown).
- Add retry action cards for common failure classes.

## Accessibility and QA (planned)
- Expand ARIA labels and screen-reader narration checks.
- Manual TalkBack/VoiceOver runbook + device matrix.
- Lighthouse and Web Vitals baseline tracking in CI.

## Observability (planned)
- Persist stage timing history (parse/generate/assemble) for trend analysis.
- Add cache hit-rate telemetry summary per project.
- Add structured log export option for support diagnostics.
