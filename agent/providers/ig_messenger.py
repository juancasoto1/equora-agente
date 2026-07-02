"""
providers/ig_messenger.py — Proveedor unificado Instagram DM + Facebook Messenger.

Ambos canales comparten el mismo endpoint de envío (Graph API /me/messages)
y el mismo formato de webhook `messaging`. Lo que los diferencia es el campo
`object` del payload ("instagram" vs "page") y el tipo de ID del usuario
(IGSID vs PSID) — para nuestros efectos son opacos: se tratan igual.

Config por agente (integration_configs):
  tipo="instagram" → api_token=PAGE_TOKEN, settings={"ig_account_id":"...","page_id":"..."}
  tipo="messenger" → api_token=PAGE_TOKEN, settings={"page_id":"..."}
"""
from __future__ import annotations

import logging
import httpx

logger = logging.getLogger("agentkit")

_GRAPH_VER  = "v21.0"
_GRAPH_BASE = f"https://graph.facebook.com/{_GRAPH_VER}"


def _ascii_only(s: str) -> str:
    """Elimina caracteres unicode invisibles que rompen tokens HTTP."""
    if not s:
        return ""
    for ch in ("​", "‌", "‍", "\xa0", "﻿",
               "⁠", "‪", "‬"):
        s = s.replace(ch, "")
    return "".join(c for c in s if 32 <= ord(c) < 127)


class ProveedorIGMessenger:
    """Envía y recibe mensajes de Instagram DM y Facebook Messenger."""

    def __init__(
        self,
        page_access_token: str = "",
        page_id: str = "",
        ig_account_id: str = "",
        canal: str = "instagram",   # "instagram" | "messenger"
    ):
        self.page_access_token = _ascii_only(page_access_token)
        self.page_id           = (page_id or "").strip()
        self.ig_account_id     = (ig_account_id or "").strip()
        self.canal             = canal
        self.ultimo_mid: str   = ""

    # ── Parsing ──────────────────────────────────────────────────────────────

    def parsear_body(self, body: dict) -> list[dict]:
        """
        Extrae eventos de mensajería del payload webhook.

        Retorna lista de dicts:
          sender_id, recipient_id, mid, texto, tipo, timestamp
        """
        eventos: list[dict] = []
        propios = {self.page_id, self.ig_account_id} - {""}

        for entry in body.get("entry", []):
            for evento in entry.get("messaging", []):
                sender_id    = evento.get("sender",    {}).get("id", "")
                recipient_id = evento.get("recipient", {}).get("id", "")

                # Ignorar ecos del propio bot
                if sender_id in propios:
                    continue

                msg = evento.get("message", {})
                if not msg:
                    continue

                mid       = msg.get("mid", "")
                texto     = msg.get("text", "") or ""
                adjuntos  = msg.get("attachments", [])
                reply_st  = msg.get("reply_to", {}).get("story")
                tipo      = "text"

                # Story reply sin texto adjunto
                if reply_st and not texto:
                    texto = "[respondió a tu story]"

                # Adjuntos
                for adj in adjuntos:
                    t = adj.get("type", "")
                    if t == "audio":
                        tipo = "audio"
                        if not texto:
                            texto = "[nota de voz]"
                    elif t == "image" and not texto:
                        texto = "[imagen]"
                    elif t == "video" and not texto:
                        texto = "[video]"
                    elif t == "story_mention" and not texto:
                        texto = "[te mencionó en una story]"

                if not texto:
                    continue

                eventos.append({
                    "sender_id":    sender_id,
                    "recipient_id": recipient_id,
                    "mid":          mid,
                    "texto":        texto,
                    "tipo":         tipo,
                    "timestamp":    evento.get("timestamp", 0),
                })

        return eventos

    # ── Envío ────────────────────────────────────────────────────────────────

    async def enviar_mensaje(self, recipient_id: str, texto: str) -> bool:
        """Envía texto al usuario vía Graph API. Retorna True si fue exitoso."""
        self.ultimo_mid = ""
        if not self.page_access_token or not recipient_id:
            logger.warning(f"[{self.canal}] token o recipient_id vacío — no se envía")
            return False

        # Fragmentar mensajes largos (Graph API limita a 2 000 chars por mensaje)
        chunks = [texto[i:i+1900] for i in range(0, len(texto), 1900)] or [""]
        ok = True
        for chunk in chunks:
            ok = ok and await self._post_mensaje(recipient_id, chunk)
        return ok

    async def _post_mensaje(self, recipient_id: str, texto: str) -> bool:
        url     = f"{_GRAPH_BASE}/me/messages"
        headers = {
            "Authorization": f"Bearer {self.page_access_token}",
            "Content-Type":  "application/json",
        }
        payload = {
            "recipient": {"id": recipient_id},
            "message":   {"text": texto},
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, json=payload, headers=headers)
            if r.status_code == 200:
                try:
                    self.ultimo_mid = r.json().get("message_id", "")
                except Exception:
                    pass
                return True
            logger.error(
                f"[{self.canal}] envío a {recipient_id}: "
                f"{r.status_code} — {r.text[:300]}"
            )
            return False
        except Exception as e:
            logger.error(f"[{self.canal}] excepción enviando: {e}")
            return False

    async def marcar_leido(self, sender_id: str) -> None:
        """Envía sender_action=mark_seen (equivalente a chulito azul)."""
        if not self.page_access_token or not sender_id:
            return
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{_GRAPH_BASE}/me/messages",
                    json={
                        "recipient":     {"id": sender_id},
                        "sender_action": "mark_seen",
                    },
                    headers={"Authorization": f"Bearer {self.page_access_token}"},
                )
        except Exception:
            pass

    async def enviar_typing(self, recipient_id: str) -> None:
        """Muestra indicador de escritura."""
        if not self.page_access_token or not recipient_id:
            return
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{_GRAPH_BASE}/me/messages",
                    json={
                        "recipient":     {"id": recipient_id},
                        "sender_action": "typing_on",
                    },
                    headers={"Authorization": f"Bearer {self.page_access_token}"},
                )
        except Exception:
            pass

    # ── Verificación ─────────────────────────────────────────────────────────

    async def verificar_token(self) -> dict:
        """Verifica el Page Access Token consultando /me."""
        if not self.page_access_token:
            return {"ok": False, "error": "Sin token configurado"}
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(
                    f"{_GRAPH_BASE}/me",
                    params={
                        "access_token": self.page_access_token,
                        "fields": "id,name",
                    },
                )
            if r.status_code == 200:
                d = r.json()
                return {
                    "ok":        True,
                    "page_id":   d.get("id", ""),
                    "page_name": d.get("name", ""),
                }
            err = r.json().get("error", {}).get("message", r.text[:200])
            return {"ok": False, "error": err}
        except Exception as e:
            return {"ok": False, "error": str(e)}
