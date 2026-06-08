# v0.2.0 Audio Stability Iteration

This release turns the EC20 audio troubleshooting result into the default public deployment direction.

## What Changed

The recommended EC20 audio path is now:

```text
Groundwire -> SIP/RTP -> Asterisk -> chan_quectel -> EC20 serial PCM -> SIM/eSIM
```

UAC / USB Audio is kept only as an optional troubleshooting path. It is no longer presented as the preferred long-running setup.

## Why

In a real deployment, UAC audio could appear to work at first and later fail without a visible configuration change. The observed symptoms included:

- Call connected but the far side could not hear speech.
- Direct Asterisk playback to EC20 produced no sound, loud electrical noise, or clipping.
- SIP client echo test still worked, proving the client-to-Asterisk RTP path was not the root cause.

The practical root cause was the EC20 UAC/USB Audio runtime path, not Groundwire, SIP, RTP, IPv6, or firewall rules.

## New Files

| Path | Purpose |
| --- | --- |
| `docs/08-audio-stability-v0.2.0.md` | Public explanation of the audio stability iteration |
| `scripts/ec20-health` | One-command EC20/Asterisk health check |
| `scripts/ec20-wait-devices` | Wait for EC20 stable device aliases before Asterisk starts |
| `templates/99-ec20-quectel.rules` | udev template for stable EC20 serial aliases |
| `systemd/asterisk-ec20-devices.conf` | Asterisk systemd override template |
| `.gitattributes` | Keeps shell/service files on LF line endings |

## Recommended Config

```ini
[defaults]
rxgain=0
txgain=-5

[quectel0]
audio=/dev/ec20-audio
data=/dev/ec20-at
;quec_uac=1
;alsadev=hw:CARD=Android,DEV=0
```

`txgain=-5` is an example value from one deployment. If needed, tune around `-4`, `-5`, and `-6`.

## Upgrade Notes

1. Confirm EC20 serial interface numbers with `udevadm`.
2. Enable the device guard in `gateway.env` if desired:

   ```bash
   ENABLE_EC20_DEVICE_GUARD=yes
   ```

3. Point `/etc/asterisk/quectel.conf` to `/dev/ec20-audio` and `/dev/ec20-at`.
4. Restart Asterisk.
5. Run:

   ```bash
   sudo ec20-health
   ```

6. Test both inbound and outbound calls.

## Privacy

The release notes intentionally avoid live domains, addresses, phone numbers, device identities, tokens, and passwords.
