# agent/shopify_admin.py — Cliente Admin API de Shopify
#
# Voco usa Storefront API para el flujo público (crear checkouts) y Admin API
# para gestión privada del merchant (registrar webhooks, leer pedidos completos,
# crear códigos de descuento, etc.).
#
# Modelo de onboarding (#53/#54 — equivalente a Jelou/99Envíos):
# El merchant crea una "Custom App" en su Shopify Admin → Settings → Apps →
# Develop apps. Configura scopes, genera credenciales (Client ID, Client Secret,
# Admin API access token) y las pega en el wizard de Voco.
#
# Este módulo NO requiere que Voco esté registrado como Shopify Partner.
# Cada merchant tiene su propio token Admin aislado.
#
# Compatibilidad: si el merchant no tiene token Admin configurado, Voco sigue
# funcionando con Storefront API como antes. Las features Admin (auto-registro
# de webhooks, auto-creación de cupones) simplemente NO se exponen al UI.

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("agentkit")

# Versión de la Admin API a usar. Shopify mantiene compatibilidad por ~9 meses
# por versión — actualizar trimestralmente.
ADMIN_API_VERSION = "2024-10"


# ──────────────────────────────────────────────────────────────────────────────
# HTTP client base
# ──────────────────────────────────────────────────────────────────────────────
def _admin_headers(admin_token: str) -> dict[str, str]:
    return {
        "X-Shopify-Access-Token": admin_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _admin_url(store: str, path: str) -> str:
    """Construye URL del Admin API. `store` puede ser 'foo.myshopify.com' o
    URL completa — lo normalizamos."""
    s = store.replace("https://", "").replace("http://", "").rstrip("/")
    p = path.lstrip("/")
    return f"https://{s}/admin/api/{ADMIN_API_VERSION}/{p}"


# ──────────────────────────────────────────────────────────────────────────────
# Verificación de credenciales
# ──────────────────────────────────────────────────────────────────────────────
async def verificar_admin_token(store: str, admin_token: str) -> dict[str, Any]:
    """Llama GET /admin/shop.json para validar que el token + dominio son válidos.

    Returns:
        {ok: bool, error?: str, shop_name?: str, shop_email?: str, plan?: str}

    No lanza excepciones — devuelve `ok=False` con el motivo en `error`.
    Útil para el botón 'Probar conexión' del panel.
    """
    if not store or not admin_token:
        return {"ok": False, "error": "Falta dominio o token de Admin API"}
    url = _admin_url(store, "shop.json")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_admin_headers(admin_token))
        if r.status_code == 200:
            shop = (r.json() or {}).get("shop", {})
            return {
                "ok": True,
                "shop_name":  shop.get("name", ""),
                "shop_email": shop.get("email", ""),
                "plan":       shop.get("plan_display_name", ""),
                "domain":     shop.get("myshopify_domain", ""),
            }
        if r.status_code == 401:
            return {"ok": False, "error": "Token inválido o expirado. Revisa que copiaste el 'Admin API access token' correcto y que la Custom App esté instalada."}
        if r.status_code == 404:
            return {"ok": False, "error": f"Dominio no encontrado: {store}. Verifica que sea exactamente como aparece en tu Shopify (sin https:// ni /)."}
        if r.status_code == 403:
            return {"ok": False, "error": "El token no tiene permisos suficientes. Verifica que la Custom App tenga scope 'read_products' como mínimo."}
        return {"ok": False, "error": f"Shopify respondió {r.status_code}: {r.text[:200]}"}
    except httpx.TimeoutException:
        return {"ok": False, "error": "Timeout (Shopify no respondió en 10s). Reintenta o revisa tu conexión."}
    except Exception as e:
        return {"ok": False, "error": f"Error de conexión: {e!s}"}


# ──────────────────────────────────────────────────────────────────────────────
# Webhooks — listar, registrar, eliminar
# ──────────────────────────────────────────────────────────────────────────────
# Topics que Voco necesita registrar. Si querés agregar uno nuevo, agregalo acá
# y la función auto-registrar lo hará en la próxima sincronización.
WEBHOOKS_VOCO = (
    "orders/create",
    "orders/paid",
    "orders/fulfilled",
    "checkouts/create",
    "app/uninstalled",   # importante: para limpiar la integración si el merchant desinstala
)


async def listar_webhooks(store: str, admin_token: str) -> list[dict]:
    """GET /admin/webhooks.json → lista todos los webhooks registrados.

    Útil para diagnóstico y para evitar registrar duplicados antes de POST.
    Si falla, devuelve [] y loguea el error.
    """
    url = _admin_url(store, "webhooks.json")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=_admin_headers(admin_token))
        if r.status_code == 200:
            return (r.json() or {}).get("webhooks", []) or []
        logger.warning(f"[shopify-admin] listar_webhooks {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"[shopify-admin] listar_webhooks error: {e}")
    return []


async def crear_webhook(
    store: str, admin_token: str, topic: str, address: str,
    formato: str = "json",
) -> dict[str, Any]:
    """POST /admin/webhooks.json → registra un webhook.

    Args:
        store: dominio Shopify
        admin_token: token Admin API
        topic: ej. 'orders/create'
        address: URL del endpoint en Voco (ej. https://tu-dominio/shopify-webhook)
        formato: 'json' o 'xml' (default json)

    Returns:
        {ok: bool, error?: str, webhook_id?: int}
    """
    url = _admin_url(store, "webhooks.json")
    payload = {"webhook": {"topic": topic, "address": address, "format": formato}}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, headers=_admin_headers(admin_token), json=payload)
        if r.status_code in (200, 201):
            wh = (r.json() or {}).get("webhook", {})
            return {"ok": True, "webhook_id": wh.get("id")}
        # 422 típicamente significa "ya existe un webhook con ese topic+address"
        if r.status_code == 422:
            err = r.json().get("errors", "duplicado") if r.headers.get("content-type", "").startswith("application/json") else r.text
            return {"ok": False, "error": f"Conflicto/duplicado: {err}"}
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def eliminar_webhook(store: str, admin_token: str, webhook_id: int) -> bool:
    """DELETE /admin/webhooks/{id}.json — quita un webhook existente."""
    url = _admin_url(store, f"webhooks/{webhook_id}.json")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.delete(url, headers=_admin_headers(admin_token))
        return r.status_code in (200, 204)
    except Exception as e:
        logger.error(f"[shopify-admin] eliminar_webhook {webhook_id}: {e}")
        return False


async def sincronizar_webhooks_voco(
    store: str, admin_token: str, callback_url: str,
) -> dict[str, Any]:
    """Garantiza que TODOS los WEBHOOKS_VOCO estén registrados apuntando a
    callback_url. Si ya existen con otra URL: los elimina y recrea. Si ya
    existen con la URL correcta: no hace nada (idempotente).

    Args:
        store: dominio Shopify del merchant
        admin_token: Admin API token
        callback_url: URL del endpoint Voco (ej. https://dominio.com/shopify-webhook)

    Returns:
        {
          ok: bool,
          creados: list[str]     # topics registrados nuevos
          conservados: list[str] # ya existían correctos
          recreados: list[str]   # apuntaban a otra URL, los reemplazamos
          fallidos: list[str]    # no se pudieron registrar
          error?: str            # solo si ok=False (no se pudo ni listar webhooks)
        }
    """
    if not callback_url.startswith("https://"):
        return {"ok": False, "error": "callback_url debe ser HTTPS (Shopify lo exige)."}

    existentes = await listar_webhooks(store, admin_token)

    # Mapa: topic → list[(id, address)] de webhooks ya registrados
    por_topic: dict[str, list[tuple[int, str]]] = {}
    for wh in existentes:
        por_topic.setdefault(wh.get("topic", ""), []).append(
            (wh.get("id"), wh.get("address", ""))
        )

    creados, conservados, recreados, fallidos = [], [], [], []
    for topic in WEBHOOKS_VOCO:
        existing = por_topic.get(topic, [])
        url_correcta = next((wid for wid, addr in existing if addr == callback_url), None)

        if url_correcta:
            conservados.append(topic)
            continue

        # Eliminar duplicados/desactualizados con URL distinta del MISMO topic
        for wid, addr in existing:
            await eliminar_webhook(store, admin_token, wid)

        # Crear el correcto
        res = await crear_webhook(store, admin_token, topic, callback_url)
        if res.get("ok"):
            (recreados if existing else creados).append(topic)
        else:
            fallidos.append(f"{topic}: {res.get('error', 'error')}")
            logger.warning(f"[shopify-admin] webhook {topic} falló: {res.get('error')}")

    logger.info(
        f"[shopify-admin] sync webhooks {store}: "
        f"creados={creados} conservados={conservados} "
        f"recreados={recreados} fallidos={fallidos}"
    )
    return {
        "ok":           True,
        "creados":      creados,
        "conservados":  conservados,
        "recreados":    recreados,
        "fallidos":     fallidos,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Discount codes (cupones) — para automatizar bono GRACIAS5 del #43
# ──────────────────────────────────────────────────────────────────────────────
async def crear_discount_code(
    store: str, admin_token: str,
    codigo: str, pct: int, umbral: int,
    titulo: str | None = None,
) -> dict[str, Any]:
    """Crea un código de descuento porcentual en Shopify con monto mínimo.

    Usa la API REST de PriceRules + DiscountCodes (estable desde 2017).
    GraphQL Discounts existe pero requiere scopes adicionales.

    Args:
        codigo: ej. 'GRACIAS5' — se normaliza a mayúsculas
        pct: 1-100 — porcentaje de descuento
        umbral: COP — monto mínimo del pedido para aplicar el cupón
        titulo: nombre interno del cupón (default: 'Voco — {codigo}')

    Returns:
        {ok: bool, error?: str, price_rule_id?: int, discount_code_id?: int}

    NO sobrescribe códigos existentes (Shopify devuelve 422 si existe).
    """
    if not (1 <= pct <= 100):
        return {"ok": False, "error": "Porcentaje debe estar entre 1 y 100"}
    if umbral < 0:
        return {"ok": False, "error": "Umbral no puede ser negativo"}
    codigo = codigo.strip().upper()
    if not codigo:
        return {"ok": False, "error": "Código vacío"}
    if not titulo:
        titulo = f"Voco — {codigo}"

    # 1) Crear PriceRule (la "regla" del descuento)
    pr_url = _admin_url(store, "price_rules.json")
    from datetime import datetime, timezone
    pr_payload = {
        "price_rule": {
            "title":                titulo,
            "target_type":          "line_item",
            "target_selection":     "all",
            "allocation_method":    "across",
            "value_type":           "percentage",
            "value":                f"-{pct}",  # negativo en Shopify
            "customer_selection":   "all",
            "starts_at":            datetime.now(timezone.utc).isoformat(),
            "prerequisite_subtotal_range": {"greater_than_or_equal_to": str(umbral)},
        }
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(pr_url, headers=_admin_headers(admin_token), json=pr_payload)
        if r.status_code not in (200, 201):
            return {"ok": False, "error": f"PriceRule HTTP {r.status_code}: {r.text[:200]}"}
        price_rule_id = (r.json() or {}).get("price_rule", {}).get("id")
        if not price_rule_id:
            return {"ok": False, "error": "PriceRule creado pero sin id"}

        # 2) Crear el DiscountCode bajo esa PriceRule
        dc_url = _admin_url(store, f"price_rules/{price_rule_id}/discount_codes.json")
        dc_payload = {"discount_code": {"code": codigo}}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r2 = await client.post(dc_url, headers=_admin_headers(admin_token), json=dc_payload)
        if r2.status_code not in (200, 201):
            # Limpiar la PriceRule huérfana si el code falla
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.delete(
                        _admin_url(store, f"price_rules/{price_rule_id}.json"),
                        headers=_admin_headers(admin_token),
                    )
            except Exception:
                pass
            return {"ok": False, "error": f"DiscountCode HTTP {r2.status_code}: {r2.text[:200]}"}
        discount_code_id = (r2.json() or {}).get("discount_code", {}).get("id")
        logger.info(
            f"[shopify-admin] cupón creado: {codigo} ({pct}% desde ${umbral:,}) "
            f"price_rule={price_rule_id} code={discount_code_id}"
        )
        return {
            "ok": True,
            "price_rule_id":    price_rule_id,
            "discount_code_id": discount_code_id,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def buscar_discount_code(store: str, admin_token: str, codigo: str) -> dict | None:
    """GET /admin/discount_codes/lookup.json?code=X → devuelve el code si existe,
    None si no. Útil para evitar crear duplicados antes de POST.
    """
    codigo = codigo.strip().upper()
    if not codigo:
        return None
    url = _admin_url(store, f"discount_codes/lookup.json?code={codigo}")
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, headers=_admin_headers(admin_token))
        if r.status_code == 200:
            return (r.json() or {}).get("discount_code")
    except Exception as e:
        logger.warning(f"[shopify-admin] buscar_discount_code {codigo}: {e}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Catálogo — Admin GraphQL products query
# ──────────────────────────────────────────────────────────────────────────────
# Reemplaza Storefront API. Devuelve la misma SHAPE que el query Storefront
# para drop-in en tools.py:
#   { "data": { "products": { "edges": [ {"node": { title, handle, productType,
#     tags, collections{edges{node{title}}}, images{edges{node{url}}},
#     variants{edges{node{id, title, sku, price{amount}, availableForSale,
#     quantityAvailable, image{url}}}} } } ] } } }

_ADMIN_PRODUCTS_QUERY = """
{
  products(first: 100, query: "status:active") {
    edges {
      node {
        id
        title
        handle
        productType
        tags
        status
        collections(first: 5) { edges { node { title } } }
        images(first: 1) { edges { node { url } } }
        variants(first: 10) {
          edges {
            node {
              id
              title
              sku
              price
              inventoryQuantity
              inventoryPolicy
              image { url }
            }
          }
        }
      }
    }
  }
}
"""


_ADMIN_SHOP_LOGO_QUERY = """
{
  shop {
    brand {
      logo { image { url } }
    }
  }
}
"""


async def obtener_productos_admin(store: str, admin_token: str) -> dict[str, Any]:
    """GraphQL Admin → products. Retorna shape COMPATIBLE con Storefront query
    para drop-in en tools.py.

    Returns:
        {"data": {"products": {"edges": [...] }}}  con price={amount: str} y
        availableForSale derivado de inventoryPolicy + inventoryQuantity.
    """
    url = _admin_url(store, "graphql.json")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, headers=_admin_headers(admin_token),
                                  json={"query": _ADMIN_PRODUCTS_QUERY})
        if r.status_code != 200:
            logger.error(f"[shopify-admin] productos HTTP {r.status_code}: {r.text[:200]}")
            return {"data": {"products": {"edges": []}}}
        data = r.json() or {}
        if data.get("errors"):
            logger.error(f"[shopify-admin] productos GraphQL errors: {data['errors']}")
            return {"data": {"products": {"edges": []}}}
        # Normalizar para que la shape sea idéntica a Storefront
        edges = (data.get("data") or {}).get("products", {}).get("edges", []) or []
        for e in edges:
            node = e.get("node") or {}
            for ve in (node.get("variants") or {}).get("edges", []):
                v = ve.get("node") or {}
                # price: string decimal → {amount: str}
                if isinstance(v.get("price"), str):
                    v["price"] = {"amount": v["price"]}
                # availableForSale: derivar de policy + inventory
                policy = (v.get("inventoryPolicy") or "").upper()
                qty = v.get("inventoryQuantity")
                if policy == "CONTINUE":  # vender sin existencias
                    v["availableForSale"] = True
                else:
                    v["availableForSale"] = isinstance(qty, int) and qty > 0
                # alias para que tools.py siga leyendo quantityAvailable
                v["quantityAvailable"] = qty if isinstance(qty, int) else None
        return {"data": {"products": {"edges": edges}}}
    except Exception as e:
        logger.error(f"[shopify-admin] obtener_productos_admin error: {e}")
        return {"data": {"products": {"edges": []}}}


async def obtener_logo_shopify_admin(store: str, admin_token: str) -> str:
    """GraphQL Admin → shop.brand.logo.image.url. Devuelve '' si no hay logo."""
    url = _admin_url(store, "graphql.json")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(url, headers=_admin_headers(admin_token),
                                  json={"query": _ADMIN_SHOP_LOGO_QUERY})
        if r.status_code != 200:
            return ""
        data = r.json() or {}
        return (((data.get("data") or {}).get("shop") or {})
                .get("brand", {}) or {}).get("logo", {}).get("image", {}).get("url", "") or ""
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────────────────────────
# Carrito — Draft Order con invoice_url (reemplaza Storefront cartCreate)
# ──────────────────────────────────────────────────────────────────────────────
async def crear_draft_order(
    store: str, admin_token: str,
    line_items: list[dict], note: str, note_attributes: list[dict],
) -> dict[str, Any]:
    """POST /admin/draft_orders.json → crea draft order y devuelve invoice_url
    (el link que el cliente abre para pagar).

    Args:
        line_items: [{"variant_id": int, "quantity": int}, ...]  (variant_id NUMÉRICO)
        note: nota visible en Shopify Admin para el merchant
        note_attributes: [{"name": "Telefono", "value": "+57..."}, ...]

    Returns:
        {ok: bool, invoice_url?: str, draft_order_id?: int, error?: str}
    """
    if not line_items:
        return {"ok": False, "error": "Sin items"}
    url = _admin_url(store, "draft_orders.json")
    payload = {
        "draft_order": {
            "line_items":      line_items,
            "note":            note,
            "note_attributes": note_attributes,
            "use_customer_default_address": True,
        }
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, headers=_admin_headers(admin_token), json=payload)
        if r.status_code not in (200, 201):
            logger.error(f"[shopify-admin] draft_order HTTP {r.status_code}: {r.text[:300]}")
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        d = r.json() or {}
        draft = d.get("draft_order") or {}
        invoice_url = draft.get("invoice_url") or ""
        if not invoice_url:
            logger.error(f"[shopify-admin] draft_order sin invoice_url: {d}")
            return {"ok": False, "error": "Shopify no devolvió invoice_url"}
        return {"ok": True, "invoice_url": invoice_url, "draft_order_id": draft.get("id")}
    except Exception as e:
        logger.error(f"[shopify-admin] crear_draft_order error: {e}")
        return {"ok": False, "error": str(e)}
