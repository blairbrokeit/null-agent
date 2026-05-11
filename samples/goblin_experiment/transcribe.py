"""Transcribe the goblin reference video via OpenAI Whisper."""

import os
import sys
from pathlib import Path

from openai import OpenAI

AUDIO_PATH = Path("C:/Users/ross/Downloads/goblins.mp3")
OUT_PATH = Path(__file__).parent / "reference_transcript.txt"
OUT_SRT = Path(__file__).parent / "reference_transcript.srt"


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    client = OpenAI(api_key=api_key)

    with AUDIO_PATH.open("rb") as f:
        verbose = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    OUT_PATH.write_text(verbose.text, encoding="utf-8")
    print(f"text -> {OUT_PATH}")
    print(f"({len(verbose.text)} chars, {len(verbose.segments)} segments)")
    print()
    print("--- transcript ---")
    print(verbose.text)
    print("------------------")

    # Build .srt for posterity
    def fmt(t: float) -> str:
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int((t - int(t)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, seg in enumerate(verbose.segments, 1):
        lines.append(str(i))
        lines.append(f"{fmt(seg.start)} --> {fmt(seg.end)}")
        lines.append(seg.text.strip())
        lines.append("")
    OUT_SRT.write_text("\n".join(lines), encoding="utf-8")
    print(f"srt  -> {OUT_SRT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
