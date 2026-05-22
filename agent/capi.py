"""
agent/capi.py — Meta Conversions API (CAPI) server-side
Envía eventos de WhatsApp a Meta para atribución de campañas.

Eventos implementados:
  Lead          → primera vez que alguien escribe a Andrea
  ViewContent   → Andrea envía link [[TIENDA:producto]]
  AddToCart     → Lovable reporta productos en el carrito
  InitiateCheckout → carrito supera el mínimo de pedido ($50.000)
"""

import os
import time
import hashlib
import logging
import httpx

logger = logging.getLogger("agentkit")

PIXEL_ID   = os.getenv("META_PIXEL_ID", "")
CAPI_TOKEN = os.getenv("META_CAPI_TOKEN", "")
API_VER    = "v21.0"
CAPI_URL   = f"https://graph.facebook.com/{API_VER}/{PIXEL_ID}/events"

# Source estándar para todos los eventos de Andrea
EVENT_SOURCE_URL = "https://wa.me/message/andrea-equora"


def _hash(valor: str) -> str:
    """SHA-256 del valor en minúsculas sin espacios (requisito de Meta)."""
    return hashlib.sha256(valor.strip().lower().encode()).hexdigest()


def _normalizar_tel(telefono: str) -> str:
    """
    Meta espera el teléfono en formato E.164 sin el '+'.
    ej: "573001234567" → "573001234567"  (ya OK)
        "+57 300 123 4567" → "573001234567"
    """
    return "".join(filter(str.isdigit, telefono))


async def enviar_evento(
    event_name: str,
    telefono: str,
    custom_data: dict | None = None,
    event_source_url: str = EVENT_SOURCE_URL,
) -> None:
    """
    Envía un evento server-side a Meta CAPI.
    Falla silenciosamente para no interrumpir el flujo de Andrea.

    Args:
        event_name      : Lead | ViewContent | AddToCart | InitiateCheckout | Purchase
        telefono        : número del cliente (se hashea antes de enviar)
        custom_data     : dict con campos opcionales (value, currency, content_name, etc.)
        event_source_url: URL de referencia del evento
    """
    if not PIXEL_ID or not CAPI_TOKEN:
        logger.debug("[capi] META_PIXEL_ID o META_CAPI_TOKEN no configurados — evento omitido")
        return

    tel_limpio = _normalizar_tel(telefono)
    payload = {
        "data": [
            {
                "event_name": event_name,
                "event_time": int(time.time()),
                "action_source": "other",          # canal WhatsApp, no web
                "event_source_url": event_source_url,
                "user_data": {
                    "ph": [_hash(tel_limpio)],     # teléfono hasheado (SHA-256)
                },
                "custom_data": custom_data or {},
            }
        ],
        "access_token": CAPI_TOKEN,
    }

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(CAPI_URL, json=payload)
            if r.status_code == 200:
                logger.info(f"[capi] {event_name} → {telefono[-4:]}**** OK")
            else:
                logger.warning(f"[capi] {event_name} error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"[capi] {event_name} excepción: {e}")


# ── Helpers por evento ───────────────────────────────────────────────────────

async def capi_lead(telefono: str) -> None:
    """Primera vez que alguien escribe a Andrea → evento Lead."""
    await enviar_evento("Lead", telefono)


async def capi_view_content(telefono: str, nombre_producto: str, url: str) -> None:
    """Andrea envía link de producto → evento ViewContent."""
    await enviar_evento(
        "ViewContent",
        telefono,
        custom_data={
            "content_name": nombre_producto,
            "content_type": "product",
        },
        event_source_url=url,
    )


async def capi_add_to_cart(telefono: str, total: int, productos: list[dict]) -> None:
    """
    Lovable reporta carrito con productos → evento AddToCart.
    total: valor en COP (ej: 58000)
    productos: lista de dicts con 'producto', 'presentacion', 'cantidad', etc.
    """
    nombres = [p.get("producto", "") for p in productos if p.get("producto")]
    await enviar_evento(
        "AddToCart",
        telefono,
        custom_data={
            "value": total,
            "currency": "COP",
            "content_type": "product",
            "content_name": ", ".join(nombres[:3]),  # primeros 3 productos
            "num_items": sum(int(p.get("cantidad", 1)) for p in productos),
        },
    )


async def capi_initiate_checkout(telefono: str, total: int) -> None:
    """Carrito supera el mínimo de pedido → evento InitiateCheckout."""
    await enviar_evento(
        "InitiateCheckout",
        telefono,
        custom_data={
            "value": total,
            "currency": "COP",
        },
    )
