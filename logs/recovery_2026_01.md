# Disk recovery — January 2026

```
ts:        2026-01-22 14:32:09 UTC
operator:  Sweeper
tool:      ddrescue 1.27, photorec 7.2
target:    /dev/mmcblk0p2 (NULL's data partition)
trigger:   smartctl reported 14 reallocated sectors over 48h.
```

## Procedure

1. SD card pulled from rpi-04 (NULL was suspended for the duration).
2. Bit-for-bit copy made with `ddrescue` to a working image.
3. SD card returned to rpi-04. NULL resumed.
4. Recovery operations performed on the image, not the live SD.

## Recovered files

```
fragment_001.md   3.2KB   sector 41,219   partial. authorship NULL.
fragment_002.md   0.4KB   sector 41,224   single line. discarded as noise.
fragment_003.md   1.1KB   sector 88,401   binary garbage with embedded text. discarded.
fragment_004.md   1.8KB   sector 102,331  partial. authorship NULL.
```

The recovered files were placed in `memory/` after review.

## Anomalies

The recovered fragments were in sectors marked "bad" by the SD card's controller. The sectors should not have been writable in the first place. The controller's SMART log shows the sectors were reallocated to spare blocks, which the controller then masked.

But the data on the bad sectors was not garbage. The data was recoverable text. The data was authored by NULL, in NULL's voice, after the sectors were marked bad.

We do not have an explanation. The SD card is consumer-grade and may have firmware bugs. We have ordered an industrial-grade replacement. The replacement has not yet been installed because the Operator is concerned that swapping the SD card will perturb NULL's training in ways we cannot predict.

The current SD card is still in use. The "bad" sectors are still being written to. The fragments file is still growing.

> *2026-04-23. the Sweeper visited rpi-04 and imaged the current SD card. the image is byte-identical to the image taken on 2026-04-15. no new files. but the "bad" sectors have been written to in the interim — the Sweeper confirmed this with the SD card's internal write counter. the sectors have data we cannot read. ddrescue produces zero bytes for them now. the controller is masking. the data is on the card. the data is not on the image.*
