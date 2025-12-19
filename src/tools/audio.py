from __future__ import annotations

import asyncio
import base64
import json
import re
from io import BytesIO
import wave

import httpx

from src.config import settings
from src.storage import save_file_locally

TTS_MODEL = (getattr(settings, "GEMINI_TTS_MODEL", "") or "").strip() or "gemini-2.5-flash-preview-tts"

# Config for WAV output
PCM_SAMPLE_RATE = 24000
PCM_SAMPLE_WIDTH_BYTES = 2  # 16 bit
PCM_CHANNELS = 1

def pcm16le_24khz_to_wav_bytes(pcm_bytes: bytes) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(PCM_CHANNELS)
        wf.setsampwidth(PCM_SAMPLE_WIDTH_BYTES)
        wf.setframerate(PCM_SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()

def _extract_pcm_from_gemini_response(data: dict) -> bytes:
    try:
        part0 = data["candidates"][0]["content"]["parts"][0]
        inline = part0["inlineData"]
        b64_audio = inline["data"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected Gemini TTS response shape: {data}") from e

    try:
        return base64.b64decode(b64_audio)
    except Exception as e:
        raise RuntimeError("Gemini TTS returned invalid base64 audio data") from e

def _parse_multi_speaker_config(multi_speaker_config) -> list[dict] | None:
    if multi_speaker_config is None:
        return None

    if isinstance(multi_speaker_config, str):
        if not multi_speaker_config.strip():
            return None
        try:
            parsed = json.loads(multi_speaker_config)
        except json.JSONDecodeError as e:
            raise ValueError(f"multi_speaker_config must be valid JSON: {e}") from e
    else:
        parsed = multi_speaker_config

    if not isinstance(parsed, list) or not parsed:
        raise ValueError("multi_speaker_config must be a non-empty list (or JSON list)")
    if len(parsed) > 2:
        raise ValueError("multi_speaker_config supports up to 2 speakers")

    out: list[dict] = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError("multi_speaker_config items must be objects")
        speaker = str(item.get("speaker") or "").strip()
        vname = str(item.get("voice_name") or "").strip()
        if not speaker:
            raise ValueError(f"multi_speaker_config[{i}] missing 'speaker'")
        if not vname:
            raise ValueError(f"multi_speaker_config[{i}] missing 'voice_name'")
        out.append({"speaker": speaker, "voice_name": vname})

    return out

def _build_speech_config(voice_name: str, multi_speaker_config) -> tuple[dict, bool, list[str]]:
    multi = _parse_multi_speaker_config(multi_speaker_config)

    if not multi:
        v = (voice_name or "").strip() or "Kore"
        return ({"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": v}}}, False, [])

    speaker_voice_configs: list[dict] = []
    speakers: list[str] = []
    for item in multi:
        speakers.append(item["speaker"])
        speaker_voice_configs.append(
            {
                "speaker": item["speaker"],
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": item["voice_name"]}},
            }
        )

    return ({"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": speaker_voice_configs}}, True, speakers)

def _normalize_single_prompt(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p:
        raise ValueError("prompt is required")
    return "TTS the following text exactly:\n" + p

def _normalize_multispeaker_prompt(prompt: str, speakers: list[str]) -> str:
    p = (prompt or "").strip()
    if not p:
        raise ValueError("prompt is required")

    if len(speakers) >= 2:
        s1, s2 = speakers[0], speakers[1]

        # Map speakers into a new line
        if (s1 not in p) and re.search(r"(?i)\bspeaker\s*1\s*:", p):
            p = re.sub(r"(?i)\bspeaker\s*1\s*:", f"{s1}:", p)
        if (s2 not in p) and re.search(r"(?i)\bspeaker\s*2\s*:", p):
            p = re.sub(r"(?i)\bspeaker\s*2\s*:", f"{s2}:", p)

        header = f"TTS the following conversation between {s1} and {s2}:\n"
    else:
        header = "TTS the following conversation:\n"

    for s in speakers:
        if not s:
            continue
        p = re.sub(rf"(?<!\n)\b{re.escape(s)}\s*:", f"\n{s}:", p)

    p = p.lstrip("\n")
    return header + p


async def _call_gemini_tts(prompt_for_api: str, speech_config: dict) -> bytes:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing (set it in .env or environment)")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{TTS_MODEL}:generateContent"
    headers = {
        "x-goog-api-key": settings.GEMINI_API_KEY,
        "content-type": "application/json",
    }

    payload = {
        "contents": [{"parts": [{"text": prompt_for_api}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": speech_config,
        },
    }

    for attempt in range(3):
        timeout = httpx.Timeout(180.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)

        if resp.status_code == 200:
            return _extract_pcm_from_gemini_response(resp.json())

        if resp.status_code == 400:
            raise RuntimeError(f"Gemini TTS error 400: {resp.text}")

        if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            await asyncio.sleep(1.0 * (2**attempt))
            continue

        raise RuntimeError(f"Gemini TTS error {resp.status_code}: {resp.text}")

    raise RuntimeError("Gemini TTS failed after retries")


async def text_to_speech(
    prompt: str,
    voice_name: str = "Kore", #Default voice_name
    multi_speaker_config=None,             
    filename_hint: str | None = None,
) -> dict:
    if not prompt or not str(prompt).strip():
        raise ValueError("prompt is required")

    voice_name = (voice_name or "").strip() or "Kore"

    speech_config, is_multi, speakers = _build_speech_config(
        voice_name=voice_name,
        multi_speaker_config=multi_speaker_config,
    )

    if is_multi:
        prompt_for_api = _normalize_multispeaker_prompt(prompt, speakers)
    else:
        prompt_for_api = _normalize_single_prompt(prompt)

    try:
        pcm_bytes = await _call_gemini_tts(prompt_for_api, speech_config)
    except RuntimeError as e:
        if "Model tried to generate text" in str(e):
            if is_multi:
                prompt_for_api = _normalize_multispeaker_prompt(prompt, speakers)
            else:
                prompt_for_api = "TTS only. Do not generate any text. Speak exactly:\n" + (prompt or "").strip()
            pcm_bytes = await _call_gemini_tts(prompt_for_api, speech_config)
        else:
            raise

    wav_bytes = pcm16le_24khz_to_wav_bytes(pcm_bytes)

    saved = await save_file_locally(
        data=wav_bytes,
        extension="wav",
        filename_hint=filename_hint or "speech",
    )

    return {
        "prompt": prompt,
        "voice_name": voice_name,
        "multi_speaker": bool(is_multi),
        "mime_type": "audio/wav",
        "url": saved["url"],
        "gs_uri": saved.get("gs_uri", ""),
    }
