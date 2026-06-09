"""Gemini TTS backend for the agentflow GUI server.

Wraps ``google.genai`` to synthesise speech via the Gemini TTS preview model
and caches the resulting audio bytes on disk so repeated requests are served
instantly without incurring API costs.

Cache layout::

    nogit_data/tts_cache/<sha256(text|voice|lang)>.mp3

Requires:
    GEMINI_API_KEY environment variable (or loaded from ``.env`` before import).

Usage::

    from agentflow.gui.tts_service import GeminiTtsService
    service = GeminiTtsService()
    audio_bytes = await service.synthesize(text="Ahoj!", voice="Kore", lang="cs-CZ")
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File cache
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "agentflow" / "tts"


class TtsFileCache:
    """Persistent on-disk cache keyed by SHA-256 of (text, voice, lang).

    Attributes:
        cache_dir: Directory where ``.mp3`` cache files are stored.
    """

    def __init__(self, cache_dir: Path = _DEFAULT_CACHE_DIR) -> None:
        """Initialise the cache and create the cache directory if missing.

        Args:
            cache_dir: Path to the directory where audio files are stored.
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, text: str, voice: str, lang: str) -> str:
        """Return hex SHA-256 of (text, voice, lang) for use as a file stem.

        Args:
            text:  The input text to synthesise.
            voice: Gemini voice name (e.g. ``"Kore"``).
            lang:  BCP-47 language code (e.g. ``"cs-CZ"``).

        Returns:
            64-character lower-case hex string.
        """
        payload = f"{text}|{voice}|{lang}".encode()
        return hashlib.sha256(payload).hexdigest()

    def get(self, text: str, voice: str, lang: str) -> bytes | None:
        """Return cached audio bytes or ``None`` on a cache miss.

        Args:
            text:  Input text.
            voice: Gemini voice name.
            lang:  BCP-47 language code.

        Returns:
            WAV bytes if cached, else ``None``.
        """
        path = self.cache_dir / f"{self._key(text, voice, lang)}.wav"
        if path.exists():
            logger.debug("TTS cache hit path=%s", path.name)
            return path.read_bytes()
        return None

    def put(self, text: str, voice: str, lang: str, data: bytes) -> None:
        """Persist *data* to the cache.

        Args:
            text:  Input text.
            voice: Gemini voice name.
            lang:  BCP-47 language code.
            data:  WAV bytes to cache.
        """
        path = self.cache_dir / f"{self._key(text, voice, lang)}.wav"
        path.write_bytes(data)
        logger.debug("TTS cache store path=%s bytes=%d", path.name, len(data))


# ---------------------------------------------------------------------------
# Gemini TTS service
# ---------------------------------------------------------------------------

#: Gemini TTS preview model name.  Update when the GA model ships.
GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"

#: Available pre-built Gemini voices.  These names are language-neutral —
#: each voice works across all 75+ supported locales.
GEMINI_VOICES: list[dict[str, str]] = [
    {"name": "Aoede",   "label": "Aoede"},
    {"name": "Charon",  "label": "Charon"},
    {"name": "Fenrir",  "label": "Fenrir"},
    {"name": "Kore",    "label": "Kore"},
    {"name": "Leda",    "label": "Leda"},
    {"name": "Orus",    "label": "Orus"},
    {"name": "Puck",    "label": "Puck"},
    {"name": "Zephyr",  "label": "Zephyr"},
    {"name": "Algenib", "label": "Algenib"},
    {"name": "Achernar","label": "Achernar"},
    {"name": "Sadachbia","label": "Sadachbia"},
    {"name": "Umbriel", "label": "Umbriel"},
]


# ---------------------------------------------------------------------------
# Audio format helpers
# ---------------------------------------------------------------------------

import struct  # noqa: E402  (stdlib, no external dep)


def _parse_sample_rate(mime_type: str, default: int = 24000) -> int:
    """Extract the sample rate from a MIME type like ``audio/L16;rate=24000``.

    Args:
        mime_type: MIME type string, possibly containing a ``rate=`` parameter.
        default:   Fallback sample rate when none is found in the string.

    Returns:
        Integer sample rate in Hz.
    """
    for part in mime_type.split(";"):
        part = part.strip()
        if part.lower().startswith("rate="):
            try:
                return int(part.split("=", 1)[1])
            except ValueError:
                pass
    return default


def _pcm_to_wav(
    pcm: bytes,
    sample_rate: int = 24000,
    channels: int = 1,
    bits_per_sample: int = 16,
) -> bytes:
    """Wrap raw signed-integer PCM bytes in a RIFF/WAV container.

    Args:
        pcm:            Raw PCM audio bytes (little-endian signed integers).
        sample_rate:    Samples per second (Hz).
        channels:       Number of audio channels (1 = mono).
        bits_per_sample: Bit depth (16 is standard for Gemini output).

    Returns:
        Complete WAV file bytes, playable by ``HTMLAudioElement`` in any browser.
    """
    byte_rate   = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size   = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,   # ChunkSize
        b"WAVE",
        b"fmt ",
        16,               # Subchunk1Size (PCM = 16)
        1,                # AudioFormat   (PCM = 1)
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm


class GeminiTtsService:
    """Synthesise speech via Gemini TTS with transparent file caching.

    Attributes:
        cache: Disk-based audio cache.
    """

    def __init__(self, cache_dir: Path = _DEFAULT_CACHE_DIR) -> None:
        """Initialise the service and validate that the API key is available.

        Args:
            cache_dir: Override the default cache directory path.

        Raises:
            RuntimeError: If neither ``GEMINI_API_KEY`` nor ``GOOGLE_API_KEY`` is set.
        """
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Neither GEMINI_API_KEY nor GOOGLE_API_KEY environment variable is set. "
                "Add one of them to your .env file to enable Gemini TTS."
            )
        self._api_key = api_key
        self.cache = TtsFileCache(cache_dir)

    async def synthesize(self, text: str, voice: str, lang: str) -> bytes:
        """Return MP3 audio bytes for *text*, served from cache if available.

        The function runs the synchronous Gemini API call in the default
        asyncio executor to avoid blocking the event loop.

        Args:
            text:  Text to synthesise (plain text; HTML/SSML not needed).
            voice: Gemini pre-built voice name (see ``GEMINI_VOICES``).
            lang:  BCP-47 language tag used as a pronunciation hint.

        Returns:
            Raw MP3 bytes suitable for sending as ``audio/mpeg``.

        Raises:
            RuntimeError: If the API returns an unexpected response structure.
            Exception:    Propagates any ``google.genai`` SDK error.
        """
        cached = self.cache.get(text, voice, lang)
        if cached is not None:
            return cached

        import asyncio
        audio_bytes = await asyncio.get_event_loop().run_in_executor(
            None, self._call_api, text, voice, lang
        )
        self.cache.put(text, voice, lang, audio_bytes)
        return audio_bytes

    def _call_api(self, text: str, voice: str, lang: str) -> bytes:
        """Perform the synchronous Gemini TTS API call.

        The Gemini TTS model returns raw PCM audio (24 kHz, 16-bit mono).
        This method wraps the PCM in a WAV container so the browser can play
        it without any additional decoding step.

        Args:
            text:  Input text.
            voice: Voice name.
            lang:  BCP-47 language tag.

        Returns:
            WAV audio bytes playable by the HTML5 Audio API.

        Raises:
            RuntimeError: If the response structure is unexpected.
        """
        from google import genai  # type: ignore[import-untyped]
        from google.genai import types  # type: ignore[import-untyped]

        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=GEMINI_TTS_MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice,
                        ),
                    ),
                ),
            ),
        )
        try:
            inline = response.candidates[0].content.parts[0].inline_data
            # The google-genai SDK returns inline_data.data as plain bytes (already decoded).
            raw: bytes = inline.data
            mime_type: str = inline.mime_type or ""
        except (IndexError, AttributeError) as exc:
            raise RuntimeError(
                f"Unexpected Gemini TTS response structure: {response}"
            ) from exc
        logger.debug("Gemini TTS raw audio: mime=%s bytes=%d", mime_type, len(raw))

        # Gemini TTS returns raw PCM (audio/L16;rate=24000 or similar).
        # Wrap it in a WAV container so HTMLAudioElement can play it.
        if mime_type.lower().startswith("audio/l16") or "pcm" in mime_type.lower() or not mime_type:
            sample_rate = _parse_sample_rate(mime_type, default=24000)
            return _pcm_to_wav(raw, sample_rate=sample_rate)
        return raw
