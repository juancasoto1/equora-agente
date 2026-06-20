"""
agent/transcriber.py — Transcripción de mensajes de voz de WhatsApp
Flujo:
  1. Recibe el media_id del webhook de Meta
  2. Descarga el audio desde los servidores de Meta (OGG/MP4)
  3. Envía el audio a OpenAI Whisper para transcripción en español
  4. Retorna el texto transcrito

Falla silenciosamente: si algo sale mal devuelve None y el mensaje se ignora.
El resto del sistema no se ve afectado.
"""

import os
import time
import logging
import httpx
from openai import AsyncOpenAI

logger = logging.getLogger("agentkit")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
_openai_client: AsyncOpenAI | None = None
_openai_client_created_at: float = 0.0
# #78 — mismo criterio anti-stale que el cliente Anthropic (agent/brain.py).
CLIENT_MAX_AGE_SEG = int(os.getenv("AI_CLIENT_MAX_AGE_SEG", 6 * 3600))

# Tamaño máximo de audio que procesamos: 10 MB (Whisper acepta hasta 25 MB)
MAX_AUDIO_BYTES = 10 * 1024 * 1024


def _cliente_openai() -> AsyncOpenAI:
    """Retorna el cliente de OpenAI, recreándolo si pasó CLIENT_MAX_AGE_SEG."""
    global _openai_client, _openai_client_created_at
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY no configurada en .env / Railway")
    ahora = time.monotonic()
    if _openai_client is None or (ahora - _openai_client_created_at) > CLIENT_MAX_AGE_SEG:
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        _openai_client_created_at = ahora
        logger.info("[anti-stale] Cliente OpenAI (re)creado")
    return _openai_client


async def _obtener_url_audio(media_id: str, access_token: str) -> str | None:
    """
    Consulta la Graph API de Meta para obtener la URL de descarga del audio.
    Retorna la URL o None si falla.
    """
    url = f"https://graph.facebook.com/v21.0/{media_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                logger.warning(f"[transcriber] No pude obtener URL del audio {media_id}: {r.status_code}")
                return None
            data = r.json()
            return data.get("url")
    except Exception as e:
        logger.warning(f"[transcriber] Error obteniendo URL de audio: {e}")
        return None


async def _descargar_audio(url: str, access_token: str) -> bytes | None:
    """
    Descarga el archivo de audio desde Meta.
    Retorna los bytes o None si falla o excede el tamaño máximo.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                logger.warning(f"[transcriber] Error descargando audio: {r.status_code}")
                return None
            audio_bytes = r.content
            if len(audio_bytes) > MAX_AUDIO_BYTES:
                logger.warning(
                    f"[transcriber] Audio demasiado grande: {len(audio_bytes)/1024/1024:.1f} MB — ignorado"
                )
                return None
            return audio_bytes
    except Exception as e:
        logger.warning(f"[transcriber] Error en descarga de audio: {e}")
        return None


async def transcribir_audio_meta(
    media_id: str,
    access_token: str,
    mime_type: str = "audio/ogg",
) -> str | None:
    """
    Descarga el audio de Meta y lo transcribe con OpenAI Whisper.

    Args:
        media_id    : ID del media recibido en el webhook de WhatsApp
        access_token: META_ACCESS_TOKEN para autenticar con Graph API
        mime_type   : tipo MIME del audio (WhatsApp usa audio/ogg; codecs=opus)

    Returns:
        Texto transcrito, o None si algo falló (el mensaje se ignora silenciosamente)
    """
    if not OPENAI_API_KEY:
        logger.warning("[transcriber] OPENAI_API_KEY no configurada — mensajes de voz ignorados")
        return None

    # 1. Obtener URL de descarga del audio
    audio_url = await _obtener_url_audio(media_id, access_token)
    if not audio_url:
        return None

    # 2. Descargar el audio
    audio_bytes = await _descargar_audio(audio_url, access_token)
    if not audio_bytes:
        return None

    logger.info(f"[transcriber] Audio descargado: {len(audio_bytes)/1024:.0f} KB — transcribiendo...")

    # 3. Transcribir con Whisper
    # Determinar extensión desde mime_type (ogg, mp4, m4a, webm, wav, etc.)
    ext_map = {
        "audio/ogg": "ogg",
        "audio/mp4": "mp4",
        "audio/m4a": "m4a",
        "audio/mpeg": "mp3",
        "audio/webm": "webm",
        "audio/wav": "wav",
        "audio/aac": "aac",
    }
    ext = ext_map.get(mime_type.split(";")[0].strip(), "ogg")
    filename = f"audio.{ext}"

    try:
        client = _cliente_openai()
        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio_bytes, mime_type),
            language="es",   # español — más rápido y preciso que auto-detect
        )
        texto = response.text.strip()
        logger.info(f"[transcriber] Transcripción OK: '{texto[:80]}{'...' if len(texto) > 80 else ''}'")
        return texto if texto else None

    except Exception as e:
        logger.warning(f"[transcriber] Error en Whisper: {e}")
        return None
