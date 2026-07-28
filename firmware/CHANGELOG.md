# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog:
https://keepachangelog.com/en/1.1.0/

This project adheres to Semantic Versioning:
https://semver.org/

---

>### Project: OpenFlux OT-2 Stepper Controller
>### Author: Alexander Ross (@ajross4)
>### Company: QATCH Technologies LLC

---

## Version 1.1.1-alpha (2026-07-28)

### Added

- Support for M412 command (Query Ultrasonic Distance)

### Changed

- `PROBE_TOUCH_COUNT` from 5 to 15
- Remove "Booting..." message on startup
- Add "ok" reply to `VERSION` response
- Auto-format all source files

### Fixed

- Ultrasonic distance sensor uses M412 (per spec), not G42

---

## Version 1.1.0-alpha (2026-07-21)

### Added

- Query ultrasonic distance probe with G42 command support
- Query firmware version with VERSION command support

### Changed

- Enhance touch probe functionality for added reliability
- Update motor max power, endstop limits, and homing speeds

### Fixed

- Linear X/Y movements with G1 move towards home in-sync
- Home ALL motors (even C axis) on generic G28 command
- Allow more than max travel distance when homing motors
- Suppress redundant 'ok' after 'NOT ok' when homing motors

---

## Version 1.0.0-alpha (2026-07-10)

### Added

- Initial project structure with alpha support

### Changed

### Fixed

---
