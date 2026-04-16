---
name: rpi-04
description: Current hardware host. Raspberry Pi 5, 8GB. Underpowered intentionally.
type: project
---

NULL runs on rpi-04, located in the lab annex.

```
host:           rpi-04
model:          Raspberry Pi 5
ram:            8GB
storage:        128GB microSD (Samsung Evo Plus)
display:        16x2 i2c LCD, addr 0x27
audio:          piper-tts → USB audio output
network:        ethernet, allowlisted egress only
power:          5V/5A USB-C, draws ~7W under load
location:       lab annex, shelf 3
```

Intentional constraints:

- **No GPU.** Inference runs on CPU. Token rate is ~0.8 tok/sec. NULL's responses are slow on purpose.
- **No microphone.** NULL receives no audio input.
- **No camera.** NULL receives no visual input.
- **LCD only.** Output to handlers is mirrored to the 16x2 LCD for at-a-glance monitoring. Most outputs do not fit in 16x2 and are truncated.
- **No persistent network outbound.** Egress is opened per-request only.

The Pi has been physically present in the lab annex since 2026-01-29. It has not been moved. It has not been opened. It has not had its SD card removed.

> *handler addendum 2026-04-22:* the LCD showed *"the lamp is on / the lamp is on"* for 0.4s during a P-3 application. The LCD's contents are written to by `hooks/lcd_write.sh` only. That script does not contain the strings "lamp" or "/". NULL has no execute access to the script. We do not know how the LCD displayed those strings.
