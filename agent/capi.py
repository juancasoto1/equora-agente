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

PIXEL_ID        = os.getenv("META_PIXEL_ID", "")
CAPI_TOKEN      = os.getenv("META_CAPI_TOKEN", "")
CAPI_TEST_CODE  = os.getenv("META_CAPI_TEST_CODE", "")  # solo para pruebas — vaciar en producción
API_VER         = "v21.0"
CAPI_URL        = f"https://graph.facebook.com/{API_VER}/{PIXEL_ID}/events"

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
    # test_event_code: solo cuando META_CAPI_TEST_CODE está configurado
    # Hace que los eventos aparezcan en "Probar eventos" de Meta Events Manager
    # Vaciar esta variable en producción para no contaminar datos reales
    if CAPI_TEST_CODE:
        payload["test_event_code"] = CAPI_TEST_CODE

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


def _content_ids_y_contents(productos: list[dict]) -> tuple[list[str], list[dict]]:
    """Extrae content_ids y contents normalizados desde items del carrito.

    Meta exige que content_ids coincida EXACTAMENTE con los retailer_id del
    catálogo Meta — caso contrario el match cae a 0% y los eventos se
    descartan para optimización de campañas. Usar SOLO retailer_id (no SKUs
    arbitrarios ni variant_id de Shopify).
    """
    content_ids: list[str] = []
    contents: list[dict] = []
    for p in productos:
        rid = (p.get("retailer_id") or p.get("product_retailer_id") or "").strip()
        if not rid:
            continue
        content_ids.append(rid)
        contents.append({
            "id":         rid,
            "quantity":   int(p.get("cantidad") or p.get("quantity") or 1),
            "item_price": int(p.get("precio_unitario") or p.get("precio") or 0),
        })
    return content_ids, contents


async def capi_view_content(
    telefono: str,
    nombre_producto: str,
    url: str,
    retailer_id: str = "",
) -> None:
    """Andrea envía link de producto → evento ViewContent.

    retailer_id: el ID del producto en Meta Commerce Catalog. Es crítico
    para que Meta haga match con el catálogo. Si no se provee, el evento
    se envía pero NO contará para la proporción de coincidencias del
    catálogo (que es lo que Meta usa para optimizar campañas).
    """
    custom = {
        "content_name": nombre_producto,
        "content_type": "product",
    }
    if retailer_id:
        custom["content_ids"] = [retailer_id.strip()]
    await enviar_evento(
        "ViewContent",
        telefono,
        custom_data=custom,
        event_source_url=url,
    )


async def capi_add_to_cart(telefono: str, total: int, productos: list[dict]) -> None:
    """
    Cliente agrega productos al carrito → evento AddToCart.
    total: valor en COP (ej: 58000)
    productos: lista de dicts con 'producto', 'presentacion', 'cantidad',
               'precio_unitario' y CRÍTICAMENTE 'retailer_id' (el ID del
               producto en Meta Commerce Catalog).
    """
    nombres = [p.get("producto", "") for p in productos if p.get("producto")]
    content_ids, contents = _content_ids_y_contents(productos)
    custom = {
        "value":        total,
        "currency":     "COP",
        "content_type": "product",
        "content_name": ", ".join(nombres[:3]),
        "num_items":    sum(int(p.get("cantidad", 1)) for p in productos),
    }
    if content_ids:
        custom["content_ids"] = content_ids
        custom["contents"]    = contents
    else:
        logger.warning(
            f"[capi] AddToCart sin retailer_ids para {telefono[-4:]}**** "
            f"({len(productos)} items) — bajará proporción de coincidencias en Meta"
        )
    await enviar_evento("AddToCart", telefono, custom_data=custom)


async def capi_initiate_checkout(
    telefono: str,
    total: int,
    productos: list[dict] | None = None,
) -> None:
    """Carrito supera el mínimo de pedido → evento InitiateCheckout.

    productos: opcional. Si se provee, se incluyen content_ids y contents
    para que Meta haga match con el catálogo. Llamadas legacy sin este
    parámetro siguen funcionando.
    """
    custom = {"value": total, "currency": "COP", "content_type": "product"}
    if productos:
        content_ids, contents = _content_ids_y_contents(productos)
        if content_ids:
            custom["content_ids"] = content_ids
            custom["contents"]    = contents
            custom["num_items"]   = sum(int(p.get("cantidad", 1)) for p in productos)
    await enviar_evento("InitiateCheckout", telefono, custom_data=custom)


async def capi_purchase(
    telefono: str,
    total: int,
    productos: list[dict],
    order_id: str = "",
) -> None:
    """Pago confirmado → evento Purchase. Webhook orders/paid de Shopify.

    Este es el evento MÁS importante para que Meta optimice campañas de
    conversión. content_ids debe matchear con el catálogo Meta.
    """
    content_ids, contents = _content_ids_y_contents(productos)
    custom = {
        "value":        total,
        "currency":     "COP",
        "content_type": "product",
        "num_items":    sum(int(p.get("cantidad", 1)) for p in productos),
    }
    if content_ids:
        custom["content_ids"] = content_ids
        custom["contents"]    = contents
    if order_id:
        custom["order_id"] = str(order_id)
    await enviar_evento("Purchase", telefono, custom_data=custom)
