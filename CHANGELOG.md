# Changelog

## v0.2.0 - 2026-06-08

### Added

- Added a formal audio stability iteration for EC20 deployments.
- Added serial PCM as the recommended long-running audio path.
- Added udev stable aliases for EC20 serial ports:
  - `/dev/ec20-audio`
  - `/dev/ec20-at`
- Added Asterisk startup guard so the service waits for EC20 devices before loading.
- Added `ec20-health` for one-command diagnostics.
- Added `ec20-wait-devices` for systemd startup integration.
- Added release notes in [RELEASE-v0.2.0.md](RELEASE-v0.2.0.md).

### Changed

- Updated the verified environment from UAC audio to serial PCM audio.
- Reworked the EC20 audio chapter to make UAC a troubleshooting option rather than the default path.
- Updated install and verify scripts to support optional EC20 device guard installation.
- Updated the architecture diagram to show serial PCM audio.
- Added `.gitattributes` so shell scripts and service templates keep LF line endings.

### Fixed

- Documented and mitigated a real audio failure mode where UAC/USB Audio could enter an unstable runtime state after snapshot, restart, or USB reinitialization.
- Reduced future recovery risk by making device naming and service startup deterministic.

### Privacy

- No live domains, addresses, numbers, credentials, tokens, IMEI, or IMSI values are included.

## v0.1.0 - 2026-06-08

Initial public release:

- EC20 + Asterisk + Groundwire voice path.
- Bark encrypted SMS notification.
- Feishu SMS history and send-command workflow.
- SQLite local archive.
- DNSPod DDNS and minimal firewall templates.
- Privacy scan script and public deployment notes.
