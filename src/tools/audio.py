from __future__ import annotations

from io import BytesIO
import wave

from src.storage import save_file_locally


async def text_to_speech(
    prompt: str,
    voice_name: str = "Kore",
    multi_speaker_config: str | None = None,
    filename_hint: str | None = None,
) -> dict:

    multi = bool(multi_speaker_config)

    sample_rate = 24000
    num_samples = sample_rate
    pcm_silence = b"\x00\x00" * num_samples

    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_silence)

    saved = await save_file_locally(buf.getvalue(), extension="wav", filename_hint=filename_hint or "speech")

    return {
        "prompt": prompt,
        "voice_name": voice_name,
        "multi_speaker": multi,
        "mime_type": "audio/wav",
        "url": saved["url"],
        "gs_uri": saved.get("gs_uri", ""),
    }
