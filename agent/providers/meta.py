import os
import json
import logging
import httpx
from fastapi import Request
from fastapi.responses import PlainTextResponse
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante
from agent.transcriber import transcribir_audio_meta

logger = logging.getLogger("agentkit")


class ProveedorMeta(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Meta Cloud API."""

    def __init__(
        self,
        access_token: str = "",
        phone_number_id: str = "",
        verify_token: str = "",
        catalog_id: str = "",
    ):
        # Sanitización defensiva: tokens copiados de páginas web (Meta Business)
        # vienen con caracteres unicode invisibles (zero-width space, NBSP, BOM)
        # que rompen httpx con "ascii codec can't encode" al usar como HTTP
        # header. Filtramos a solo ASCII printable acá para que no importe de
        # qué fuente venga el token (env, BD, request body).
        def _ascii_only(s: str) -> str:
            if not s:
                return ""
            # Quitar caracteres invisibles conocidos y normalizar
            for ch in ("​", "‌", "‍", " ", "﻿",
                       "⁠", " "):
                s = s.replace(ch, "")
            # Forzar ASCII printable (32-126) — quita CRLF, tabs y unicode
            return "".join(c for c in s if 32 <= ord(c) < 127)

        self.access_token = _ascii_only(access_token or os.getenv("META_ACCESS_TOKEN", ""))
        self.phone_number_id = _ascii_only(phone_number_id or os.getenv("META_PHONE_NUMBER_ID", ""))
        self.verify_token = verify_token or os.getenv("META_VERIFY_TOKEN", "equora-andrea-2024")
        self.catalog_id = _ascii_only(catalog_id or os.getenv("META_CATALOG_ID", ""))
        self.api_version = "v21.0"
        # #79 — el wamid del último mensaje enviado exitosamente. Lo callers
        # lo leen después de cada enviar_mensaje() para vincular el status
        # update con el row de mensajes en BD.
        self.ultimo_wamid: str = ""

    def _capturar_wamid(self, r: "httpx.Response") -> None:
        """Extrae el wamid de una respuesta exitosa de Meta y lo guarda en
        self.ultimo_wamid (#79 — chulitos de confirmación). Todos los métodos
        de envío pegan al mismo endpoint /messages y Meta siempre devuelve
        {"messages": [{"id": "wamid..."}]} en éxito."""
        try:
            self.ultimo_wamid = (r.json().get("messages") or [{}])[0].get("id", "")
        except Exception:
            self.ultimo_wamid = ""

    async def validar_webhook(self, request: Request):
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        if mode == "subscribe" and token == self.verify_token:
            return PlainTextResponse(content=challenge)
        return None

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea mensajes de texto e interactivos (clicks de botones y listas)."""
        body = await request.json()
        mensajes = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    telefono = msg.get("from", "")
                    msg_id = msg.get("id", "")
                    tipo = msg.get("type", "")

                    if tipo == "text":
                        texto = msg.get("text", {}).get("body", "")
                        if texto:
                            mensajes.append(MensajeEntrante(
                                telefono=telefono,
                                texto=texto,
                                mensaje_id=msg_id,
                                es_propio=False,
                            ))

                    elif tipo == "interactive":
                        interactivo = msg.get("interactive", {})
                        tipo_interactivo = interactivo.get("type", "")

                        if tipo_interactivo == "button_reply":
                            btn = interactivo.get("button_reply", {})
                            btn_id = btn.get("id", "")
                            btn_title = btn.get("title", "")
                            # Botones con id "act_*" son acciones internas de Voco
                            # — Voco los procesa sin pasar por Claude.
                            if btn_id.startswith("act_"):
                                texto = f"__ACCION_BTN__:{btn_id}"
                            else:
                                texto = btn_title
                        elif tipo_interactivo == "list_reply":
                            _lr = interactivo.get("list_reply", {})
                            texto = _lr.get("title", "")
                            _lr_id = _lr.get("id", "")
                        else:
                            texto = ""
                            _lr_id = ""

                        if texto:
                            mensajes.append(MensajeEntrante(
                                telefono=telefono,
                                texto=texto,
                                mensaje_id=msg_id,
                                es_propio=False,
                                lista_id=_lr_id if tipo_interactivo == "list_reply" else "",
                            ))

                    elif tipo == "audio":
                        # Mensaje de voz → transcribir con Whisper y tratar como texto
                        audio_data = msg.get("audio", {})
                        media_id   = audio_data.get("id", "")
                        mime_type  = audio_data.get("mime_type", "audio/ogg")
                        if media_id and self.access_token:
                            logger.info(f"[audio] Mensaje de voz de {telefono} — transcribiendo...")
                            texto = await transcribir_audio_meta(
                                media_id, self.access_token, mime_type
                            )
                            if texto:
                                mensajes.append(MensajeEntrante(
                                    telefono=telefono,
                                    texto=texto,
                                    mensaje_id=msg_id,
                                    es_propio=False,
                                ))
                            else:
                                logger.warning(
                                    f"[audio] No se pudo transcribir el audio de {telefono} — ignorado"
                                )

                    elif tipo == "order":
                        # El cliente confirmó su carrito desde el catálogo nativo de WhatsApp.
                        # Serializamos los items como texto especial para que main.py los procese
                        # directamente sin pasar por Claude.
                        order_data = msg.get("order", {})
                        items = order_data.get("product_items", [])
                        if items:
                            texto = f"__ORDEN_CATALOGO__:{json.dumps(items, ensure_ascii=False)}"
                            mensajes.append(MensajeEntrante(
                                telefono=telefono,
                                texto=texto,
                                mensaje_id=msg_id,
                                es_propio=False,
                            ))
                            logger.info(f"Orden catálogo WhatsApp de {telefono}: {len(items)} items")

                    elif tipo in ("image", "video", "document"):
                        # Media entrante: serializar como marcador para que el inbox lo renderice
                        media_data = msg.get(tipo, {})
                        media_id   = media_data.get("id", "")
                        mime_type  = media_data.get("mime_type", "")
                        caption    = media_data.get("caption", "")
                        filename   = media_data.get("filename", "") if tipo == "document" else ""
                        if media_id:
                            payload_media = {
                                "tipo":       tipo,
                                "media_id":   media_id,
                                "mime_type":  mime_type,
                                "caption":    caption,
                                "filename":   filename,
                            }
                            texto = f"__MEDIA__:{json.dumps(payload_media, ensure_ascii=False)}"
                            mensajes.append(MensajeEntrante(
                                telefono=telefono,
                                texto=texto,
                                mensaje_id=msg_id,
                                es_propio=False,
                            ))
                            logger.info(f"Media {tipo} recibido de {telefono} (media_id={media_id})")

                    elif tipo == "location":
                        loc = msg.get("location", {})
                        lat = loc.get("latitude")
                        lon = loc.get("longitude")
                        if lat is not None and lon is not None:
                            payload_loc = {
                                "tipo":      "location",
                                "latitud":   lat,
                                "longitud":  lon,
                                "nombre":    loc.get("name", ""),
                                "direccion": loc.get("address", ""),
                            }
                            texto = f"__MEDIA__:{json.dumps(payload_loc, ensure_ascii=False)}"
                            mensajes.append(MensajeEntrante(
                                telefono=telefono,
                                texto=texto,
                                mensaje_id=msg_id,
                                es_propio=False,
                            ))
                            logger.info(f"Ubicación recibida de {telefono}: {lat},{lon}")

        return mensajes

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje de texto plano. Tras éxito guarda el wamid de Meta
        en self.ultimo_wamid para que el caller pueda trackear status updates
        (sent/delivered/read) — feature #79 de chulitos de confirmación."""
        self.ultimo_wamid = ""
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "text",
            "text": {"body": mensaje},
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API texto: {r.status_code} — {r.text}")
                return False
            self._capturar_wamid(r)
            return True

    async def enviar_botones(self, telefono: str, texto: str, botones: list[str]) -> bool:
        """Envía mensaje con hasta 3 botones de respuesta rápida."""
        if not self.access_token or not self.phone_number_id:
            return False

        # WhatsApp limita títulos de botones a 20 caracteres
        botones_payload = [
            {"type": "reply", "reply": {"id": f"btn_{i}", "title": b[:20]}}
            for i, b in enumerate(botones[:3])
        ]

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": texto},
                "action": {"buttons": botones_payload},
            },
        }
        self.ultimo_wamid = ""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API botones: {r.status_code} — {r.text}")
                return False
            self._capturar_wamid(r)
            return True

    async def enviar_botones_reply(
        self, telefono: str, texto: str, botones: list[dict]
    ) -> bool:
        """Envía mensaje con botones de respuesta con IDs personalizados.
        Cada botón retorna al webhook con su ID. Máximo 3 botones.
        Útil para flujos de 2 acciones (ej: 'agregar más' vs 'confirmar pedido').

        botones: [{"id": "act_xyz", "title": "Texto visible"}, ...]
        Los IDs que empiezan con 'act_' los intercepta Voco automáticamente.
        """
        if not self.access_token or not self.phone_number_id:
            return False
        if not botones:
            return False
        botones_payload = [
            {"type": "reply", "reply": {
                "id":    b.get("id", f"btn_{i}")[:256],
                "title": b.get("title", "")[:20],
            }}
            for i, b in enumerate(botones[:3])
        ]
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": texto[:1024]},
                "action": {"buttons": botones_payload},
            },
        }
        self.ultimo_wamid = ""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta botones_reply: {r.status_code} — {r.text[:300]}")
                return False
            self._capturar_wamid(r)
            return True

    async def enviar_cta_url(self, telefono: str, texto: str, boton: str, url: str) -> bool:
        """Envía un mensaje con un botón que abre una URL (tipo CTA URL)."""
        if not self.access_token or not self.phone_number_id:
            return False
        api_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "cta_url",
                "body": {"text": texto},
                "action": {
                    "name": "cta_url",
                    "parameters": {
                        "display_text": boton[:20],
                        "url": url,
                    },
                },
            },
        }
        self.ultimo_wamid = ""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(api_url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API cta_url: {r.status_code} — {r.text}")
                return False
            self._capturar_wamid(r)
            return True

    async def enviar_lista(self, telefono: str, texto: str, boton: str, secciones: list[dict],
                           header_text: str = "") -> bool:
        """Envía mensaje con lista de opciones seleccionables.
        WhatsApp impone: máx 10 filas TOTALES entre todas las secciones,
        título de fila ≤ 24 chars, descripción ≤ 72 chars, botón ≤ 20 chars.
        `header_text` opcional añade un encabezado de texto (≤60 chars) que
        hace más prominente el botón "Ver opciones" en el cliente de WhatsApp."""
        if not self.access_token or not self.phone_number_id:
            return False

        MAX_ROWS = 10
        secciones_payload = []
        rows_acumuladas = 0
        for seccion in secciones:
            if rows_acumuladas >= MAX_ROWS:
                break
            rows = []
            for i, item in enumerate(seccion.get("items", [])):
                if rows_acumuladas >= MAX_ROWS:
                    break
                rows.append({
                    "id": str(item.get("id", f"item_{rows_acumuladas}"))[:200],
                    "title": str(item.get("titulo", ""))[:24],
                    "description": str(item.get("descripcion", ""))[:72],
                })
                rows_acumuladas += 1
            if rows:
                secciones_payload.append({
                    "title": str(seccion.get("titulo", ""))[:24],
                    "rows": rows,
                })

        if not secciones_payload:
            logger.warning("enviar_lista: sin secciones válidas — abortando")
            return False

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        interactive_payload: dict = {
            "type": "list",
            "body": {"text": texto[:1024]},
            "action": {
                "button": boton[:20] or "Ver opciones",
                "sections": secciones_payload,
            },
        }
        if header_text:
            interactive_payload["header"] = {"type": "text", "text": str(header_text)[:60]}
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "interactive",
            "interactive": interactive_payload,
        }
        self.ultimo_wamid = ""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API lista: {r.status_code} — {r.text}")
                return False
            self._capturar_wamid(r)
            return True

    async def enviar_plantilla(
        self,
        telefono: str,
        template_name: str,
        language_code: str,
        components: list[dict] | None = None,
    ) -> dict:
        """Envía una plantilla aprobada de Meta a un número.
        Retorna {"ok": True, "message_id": "..."} o {"ok": False, "error": "..."}."""
        if not self.access_token or not self.phone_number_id:
            return {"ok": False, "error": "META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados"}
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        template_obj: dict = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if components:
            template_obj["components"] = components
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "template",
            "template": template_obj,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code == 200:
                self._capturar_wamid(r)
                return {"ok": True, "message_id": self.ultimo_wamid}
            else:
                try:
                    err = r.json().get("error", {}).get("message", r.text[:200])
                except Exception:
                    err = r.text[:200]
                logger.error(f"Error Meta API enviar_plantilla: {r.status_code} — {err}")
                return {"ok": False, "error": err}

    async def enviar_catalogo_productos(
        self,
        telefono: str,
        header: str,
        cuerpo: str,
        secciones: list[dict],
    ) -> bool:
        """Envía un mensaje product_list con el catálogo nativo de WhatsApp.
        El cliente ve fotos reales, puede seleccionar cantidades y armar su carrito
        sin salir de WhatsApp. Requiere META_CATALOG_ID configurado.

        secciones: [{"title": "Lavandería", "product_items": [{"product_retailer_id": "SKU1"}]}]
        """
        if not self.access_token or not self.phone_number_id:
            return False
        if not self.catalog_id:
            logger.warning("META_CATALOG_ID no configurado — no se puede enviar catálogo nativo")
            return False
        if not secciones:
            logger.warning("enviar_catalogo_productos: sin secciones")
            return False

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "product_list",
                "header": {
                    "type": "text",
                    "text": header[:60],
                },
                "body": {"text": cuerpo[:1024]},
                "action": {
                    "catalog_id": self.catalog_id,
                    "sections": secciones,
                },
            },
        }
        # Log del payload para diagnóstico (solo IDs, no datos sensibles)
        ids_por_seccion = {s["title"]: [i["product_retailer_id"] for i in s.get("product_items", [])] for s in secciones}
        logger.info(f"product_list payload — catalog_id={self.catalog_id} secciones={ids_por_seccion}")

        self.ultimo_wamid = ""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API product_list: {r.status_code} — {r.text}")
                return False
            self._capturar_wamid(r)
            logger.info(f"Catálogo nativo enviado a {telefono} ({len(secciones)} secciones)")
            return True

    async def enviar_catalog_message(
        self, telefono: str, cuerpo: str, thumbnail_retailer_id: str = ""
    ) -> bool:
        """Envía un mensaje con un botón 'Ver catálogo' que abre el catálogo
        nativo de WhatsApp del negocio. Requiere META_CATALOG_ID configurado
        Y un thumbnail_retailer_id válido (la imagen del botón).
        Perfecto para reabrir el catálogo cuando el carrito está bajo el mínimo."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("enviar_catalog_message: credenciales Meta no configuradas")
            return False
        if not self.catalog_id:
            logger.warning("enviar_catalog_message: META_CATALOG_ID no configurado")
            return False
        # Meta requiere un retailer_id válido como thumbnail. Si no se pasó uno,
        # usamos el primero del catálogo cargado en _sku_map.
        if not thumbnail_retailer_id:
            try:
                from agent.tools import _sku_map
                # Preferir variant_id largo (mismo formato que Facebook Catalog usa)
                for rid in _sku_map.keys():
                    if rid.isdigit() and len(rid) >= 10:
                        thumbnail_retailer_id = rid
                        break
                if not thumbnail_retailer_id and _sku_map:
                    thumbnail_retailer_id = next(iter(_sku_map.keys()), "")
            except Exception as e:
                logger.warning(f"No pude obtener thumbnail_retailer_id: {e}")
        if not thumbnail_retailer_id:
            logger.warning("enviar_catalog_message: sin thumbnail_retailer_id — no se puede enviar")
            return False

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        self.ultimo_wamid = ""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "catalog_message",
                "body": {"text": cuerpo[:1024]},
                "action": {
                    "name": "catalog_message",
                    "parameters": {
                        "thumbnail_product_retailer_id": thumbnail_retailer_id,
                    },
                },
            },
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                # Log detallado para diagnóstico
                try:
                    err_data = r.json().get("error", {})
                    err_msg = err_data.get("message", r.text[:300])
                    err_code = err_data.get("code", 0)
                    logger.error(
                        f"Error Meta catalog_message: HTTP {r.status_code} "
                        f"code={err_code} thumbnail={thumbnail_retailer_id} "
                        f"catalog_id={self.catalog_id} msg={err_msg}"
                    )
                except Exception:
                    logger.error(f"Error Meta catalog_message: {r.status_code} — {r.text[:300]}")
                return False
            self._capturar_wamid(r)
            logger.info(f"catalog_message enviado a {telefono} (thumbnail={thumbnail_retailer_id})")
            return True

    # ═══════════════════════════════════════════════════════════════════════
    # SPRINT 4 — Mensajes multimedia (imagen, video, documento, ubicación)
    # ═══════════════════════════════════════════════════════════════════════

    async def subir_media(self, file_bytes: bytes, filename: str, mime_type: str) -> str | None:
        """Sube un archivo a Meta y retorna el media_id para usar en mensajes.
        Los archivos de Meta expiran a los 30 días."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("subir_media: credenciales Meta no configuradas")
            return None
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/media"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        files = {
            "file": (filename, file_bytes, mime_type),
            "messaging_product": (None, "whatsapp"),
            "type": (None, mime_type),
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(url, headers=headers, files=files)
                if r.status_code != 200:
                    logger.error(f"Error subiendo media a Meta: {r.status_code} — {r.text[:300]}")
                    return None
                media_id = r.json().get("id")
                logger.info(f"Media subida a Meta: {filename} ({mime_type}) → id={media_id}")
                return media_id
        except Exception as e:
            logger.error(f"Excepción subiendo media: {e}")
            return None

    async def obtener_url_media(self, media_id: str) -> str | None:
        """Obtiene la URL temporal de un media_id de Meta (válida ~5 min)."""
        if not self.access_token or not media_id:
            return None
        url = f"https://graph.facebook.com/{self.api_version}/{media_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    return r.json().get("url")
                logger.error(f"Error obteniendo URL media: {r.status_code}")
                return None
        except Exception as e:
            logger.error(f"Excepción obteniendo URL media: {e}")
            return None

    async def descargar_media(self, media_id: str) -> tuple[bytes, str] | None:
        """Descarga el contenido binario de un media de Meta. Retorna (bytes, mime_type)."""
        url = await self.obtener_url_media(media_id)
        if not url:
            return None
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    return r.content, r.headers.get("content-type", "application/octet-stream")
                return None
        except Exception as e:
            logger.error(f"Excepción descargando media: {e}")
            return None

    async def _enviar_media(
        self, telefono: str, tipo: str, media_id: str = "",
        link: str = "", caption: str = "", filename: str = ""
    ) -> bool:
        """Envío genérico de media (image/video/document/audio).
        Usa media_id (preferido, ya subido) o link (URL pública)."""
        if not self.access_token or not self.phone_number_id:
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        media_obj: dict = {}
        if media_id:
            media_obj["id"] = media_id
        elif link:
            media_obj["link"] = link
        else:
            logger.error(f"_enviar_media: ni media_id ni link para tipo={tipo}")
            return False
        # Caption solo aplica a image, video, document — no a audio
        if caption and tipo in ("image", "video", "document"):
            media_obj["caption"] = caption[:1024]
        if filename and tipo == "document":
            media_obj["filename"] = filename[:200]

        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": tipo,
            tipo: media_obj,
        }
        self.ultimo_wamid = ""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API {tipo}: {r.status_code} — {r.text[:300]}")
                return False
            self._capturar_wamid(r)
            return True

    async def enviar_imagen(self, telefono: str, media_id: str = "", link: str = "", caption: str = "") -> bool:
        """Envía una imagen por WhatsApp. Usa media_id (subido previamente) o link público."""
        return await self._enviar_media(telefono, "image", media_id=media_id, link=link, caption=caption)

    async def enviar_video(self, telefono: str, media_id: str = "", link: str = "", caption: str = "") -> bool:
        """Envía un video por WhatsApp."""
        return await self._enviar_media(telefono, "video", media_id=media_id, link=link, caption=caption)

    async def enviar_documento(
        self, telefono: str, media_id: str = "", link: str = "",
        caption: str = "", filename: str = ""
    ) -> bool:
        """Envía un documento (PDF, etc.) por WhatsApp."""
        return await self._enviar_media(
            telefono, "document", media_id=media_id, link=link, caption=caption, filename=filename
        )

    async def enviar_audio(self, telefono: str, media_id: str = "", link: str = "") -> bool:
        """Envía un audio/nota de voz por WhatsApp."""
        return await self._enviar_media(telefono, "audio", media_id=media_id, link=link)

    async def enviar_ubicacion(
        self, telefono: str, latitud: float, longitud: float,
        nombre: str = "", direccion: str = ""
    ) -> bool:
        """Envía una ubicación geográfica."""
        if not self.access_token or not self.phone_number_id:
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        location_obj = {"latitude": float(latitud), "longitude": float(longitud)}
        if nombre:    location_obj["name"]    = nombre[:200]
        if direccion: location_obj["address"] = direccion[:400]
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "location",
            "location": location_obj,
        }
        self.ultimo_wamid = ""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API ubicacion: {r.status_code} — {r.text[:200]}")
                return False
            self._capturar_wamid(r)
            return True

    async def enviar_producto(
        self, telefono: str, retailer_id: str, cuerpo: str = ""
    ) -> dict:
        """Envía un solo producto del catálogo (single_product). Requiere META_CATALOG_ID.
        Retorna dict: {ok: bool, error: str, code: int, catalog_id: str}"""
        if not self.access_token or not self.phone_number_id:
            return {"ok": False, "error": "META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados"}
        if not self.catalog_id:
            return {"ok": False, "error": "META_CATALOG_ID no configurado en Railway. Sin él WhatsApp no sabe en qué catálogo buscar el producto."}
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "product",
                "action": {
                    "catalog_id": self.catalog_id,
                    "product_retailer_id": retailer_id,
                },
            },
        }
        # Body es opcional, solo lo agregamos si hay texto
        if cuerpo:
            payload["interactive"]["body"] = {"text": cuerpo[:1024]}
        self.ultimo_wamid = ""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                err_msg = "Error desconocido"
                err_code = 0
                try:
                    err_data = r.json().get("error", {})
                    err_msg  = err_data.get("message", r.text[:300])
                    err_code = err_data.get("code", 0)
                except Exception:
                    err_msg = r.text[:300]
                logger.error(
                    f"Error Meta single_product: HTTP {r.status_code} code={err_code} "
                    f"catalog_id={self.catalog_id} retailer_id={retailer_id} msg={err_msg}"
                )
                return {
                    "ok": False, "error": err_msg, "code": err_code,
                    "catalog_id": self.catalog_id, "retailer_id": retailer_id,
                }
            self._capturar_wamid(r)
            return {"ok": True, "catalog_id": self.catalog_id, "retailer_id": retailer_id}
