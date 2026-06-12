import os
import re
import asyncio
import logging
import unicodedata
import yaml
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger("agentkit")

# ── Cache del catálogo ────────────────────────────────────────────────────────
_catalog_cache: str = ""
_catalog_cache_at: datetime | None = None
CATALOG_TTL_SEG: int = int(os.getenv("CATALOG_TTL_SEG", 300))  # 5 min por defecto

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE", "")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN", "")


async def _resolver_admin_token() -> str:
    """Lee el Admin token preferentemente de config_value (agent_id=1) y
    fallback a env var. Permite que el OAuth en panel surta efecto sin
    reiniciar el server."""
    try:
        from agent.memory import get_config_value
        val = await get_config_value("SHOPIFY_ADMIN_TOKEN", 1)
        if val:
            return val
    except Exception:
        pass
    return SHOPIFY_ADMIN_TOKEN


async def _resolver_store() -> str:
    """Idem para SHOPIFY_STORE."""
    try:
        from agent.memory import get_config_value
        val = await get_config_value("SHOPIFY_STORE", 1)
        if val:
            return val.replace("https://", "").replace("http://", "").rstrip("/")
    except Exception:
        pass
    return SHOPIFY_STORE


async def _resolver_meta_catalog_id() -> str:
    """Lee META_CATALOG_ID preferentemente de config_value (agent_id=1) y
    fallback a env var. Permite que cambios en el panel surtan efecto sin
    reiniciar el server (importante cuando el merchant reconecta el
    catálogo Shopify↔Meta y cambia el ID)."""
    try:
        from agent.memory import get_config_value
        val = await get_config_value("META_CATALOG_ID", 1)
        if val:
            return val.strip()
    except Exception:
        pass
    return META_CATALOG_ID


async def _resolver_meta_access_token() -> str:
    """Idem para META_ACCESS_TOKEN."""
    try:
        from agent.memory import get_config_value
        val = await get_config_value("META_ACCESS_TOKEN", 1)
        if val:
            return val.strip()
    except Exception:
        pass
    return META_ACCESS_TOKEN

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_CATALOG_ID = os.getenv("META_CATALOG_ID", "")
META_API_VERSION = "v21.0"

# Queries Storefront GraphQL (SHOPIFY_GQL_QUERY, SHOPIFY_LOGO_QUERY) y la
# global SHOPIFY_STOREFRONT_TOKEN fueron eliminadas en #62. Ahora todo el
# catálogo y carrito usa Admin API via agent/shopify_admin.py.

# Colecciones que ignoramos como categoría visible (las crea Shopify por defecto)
COLECCIONES_IGNORADAS = {"home page", "frontpage", "all", "todos"}

# ── Categorías fijas de Equora ────────────────────────────────────────────────
# Orden y nombres exactos que debe mostrar Andrea.
# Clave: fragmento normalizado del título del producto → Valor: nombre de categoría.
# Si un producto no coincide con ninguna clave cae en "Otros".
CATEGORIAS_EQUORA: list[tuple[str, str]] = [
    # IMPORTANTE: orden de más específico a más general.
    # El primero que coincida gana.

    # ── Lavandería ────────────────────────────────────────────
    ("ropa blanca",                     "Lavandería"),
    ("ropa color",                      "Lavandería"),
    ("ropa delicada",                   "Lavandería"),
    ("suavizante",                      "Lavandería"),

    # ── Cocina ────────────────────────────────────────────────
    ("lavaloza",                        "Cocina"),      # cualquier lavaloza
    ("desengrasante cocina",            "Cocina"),      # específico cocina ANTES del catch-all

    # ── Hogar ─────────────────────────────────────────────────
    ("ambientador",                     "Hogar"),
    ("limpiapisos",                     "Hogar"),
    ("desmanchador",                    "Hogar"),
    ("eliminador olores",               "Hogar"),
    ("limpiador desinfectante",         "Hogar"),
    ("limpiavidrios",                   "Hogar"),
    ("multiusos",                       "Hogar"),

    # ── Talleres / Industrial ─────────────────────────────────
    # "desengrasante" solo cubre TODO lo que no sea cocina
    ("desengrasante",                   "Talleres / Industrial"),
    ("shampoo",                         "Talleres / Industrial"),

    # ── Higiene Personal ─────────────────────────────────────
    ("jabon",                           "Higiene Personal"),  # jabón de manos, líquido, etc.
]

# Orden de aparición de las categorías en el catálogo
ORDEN_CATEGORIAS = [
    "Lavandería",
    "Cocina",
    "Hogar",
    "Talleres / Industrial",
    "Higiene Personal",
    "Otros",
]


def _categoria_producto(titulo: str) -> str:
    """[LEGACY] Asigna la categoría de Equora a un producto por su título.

    Solo se usa como ÚLTIMO fallback cuando el producto de Shopify no tiene
    collections, productType, ni tags. Para Voco SaaS la fuente de verdad
    son las categorías que el cliente configura en Shopify — esta función
    se mantiene para compatibilidad con el catálogo histórico de Equora.
    """
    titulo_n = _normalizar(titulo)
    palabras_titulo = titulo_n.split()

    for fragmento, categoria in CATEGORIAS_EQUORA:
        palabras_frag = _normalizar(fragmento).split()
        if all(
            any(pt == pf or (len(pf) > 3 and pt.startswith(pf))
                for pt in palabras_titulo)
            for pf in palabras_frag
        ):
            return categoria
    return "Otros"


# Colecciones "automáticas" de Shopify que NO son categorías reales del
# negocio — Shopify las crea por defecto (incluyen todos los productos)
# o son la home page. Si las usamos como categoría, terminan tapando las
# colecciones reales del cliente (Lavandería, Cocina, etc.).
_SHOPIFY_AUTO_COLLECTIONS = {
    "página de inicio", "pagina de inicio",
    "home page", "homepage", "frontpage", "home",
    "all", "all products", "todos", "todos los productos",
}


def _categoria_desde_shopify(node: dict) -> str:
    """Determina la categoría de un producto en cascada multi-tenant:

      1. Shopify Collection REAL (saltando auto-collections de Shopify)
      2. Shopify Product Type — alternativa si no usan collections
      3. Shopify Tag (primero) — fallback liviano
      4. Keywords de Equora (legacy) — solo si el producto matchea
      5. "Catálogo" — bucket genérico cuando nada aplica

    Esta cascada permite que CUALQUIER cliente Voco funcione sin configurar
    nada: si el catálogo viene "sucio", los productos caen en una categoría
    útil — nunca en una catch-all como "Página de inicio" que esconde la
    estructura real del catálogo.
    """
    # 1. Collections REALES de Shopify (saltando "Página de inicio" y similares)
    coll_edges = (node.get("collections") or {}).get("edges") or []
    for edge in coll_edges:
        title = ((edge.get("node") or {}).get("title") or "").strip()
        if not title:
            continue
        if title.lower() in _SHOPIFY_AUTO_COLLECTIONS:
            continue  # saltar colecciones automáticas
        return title

    # 2. productType
    ptype = (node.get("productType") or "").strip()
    if ptype:
        return ptype

    # 3. Tags (el primero)
    tags = node.get("tags") or []
    if isinstance(tags, list) and tags:
        first_tag = (tags[0] or "").strip()
        if first_tag:
            return first_tag

    # 4. Keywords legacy de Equora
    titulo = node.get("title", "")
    cat_legacy = _categoria_producto(titulo)
    if cat_legacy != "Otros":
        return cat_legacy

    # 5. Bucket genérico — todo cabe sin configurar nada
    return "Catálogo"


# Mapa de variantes para resolver merchandiseId al crear el checkout
# Clave: "producto|presentacion" normalizado
# Valor: dict con "id" (variant GID) y "stock" (int o None si Storefront no expone inventario)
_variant_map: dict[str, dict] = {}

# Mapa por retailer_id (SKU o ID numérico) para procesar órdenes del catálogo nativo WhatsApp
# Clave: retailer_id (SKU del producto en Facebook/Meta Catalog)
# Valor: dict con producto, presentacion, precio_unitario, variant_id
_sku_map: dict[str, dict] = {}

# Categorías estructuradas (se llenan al cargar el catálogo) para armar secciones del catálogo nativo
# Clave: nombre de categoría → Lista de (titulo_producto, lista_variantes)
_categorias_cache: dict[str, list] = {}

# Items reales del catálogo de Facebook: [{retailer_id, name, precio, categoria}]
# Se carga consultando la Graph API — son los IDs que WhatsApp acepta en product_list
_fb_items: list[dict] = []

# Catálogo en formato JSON para la mini-tienda web
_catalog_json: list[dict] = []

# Mapa de handle Shopify por nombre de producto normalizado
# Clave: título normalizado → Valor: handle (ej. "lavaloza-antibacterial-biotu")
_handle_map: dict[str, str] = {}

# URL base de los productos en equoradistribuciones.com
EQUORA_PRODUCT_BASE = os.getenv(
    "EQUORA_PRODUCT_BASE", "https://equoradistribuciones.com/product"
)

# ── Tarifas de envío (cargadas desde Shopify Admin API o env vars) ────────────
# Se actualizan al arrancar el servidor. Sin Admin Token usan los valores de env.
_costo_envio: int = int(os.getenv("COSTO_ENVIO", 9000))
_envio_gratis: int = int(os.getenv("ENVIO_GRATIS", 80000))


def obtener_costo_envio() -> int:
    return _costo_envio


def obtener_umbral_envio_gratis() -> int:
    return _envio_gratis


async def cargar_tarifas_envio() -> tuple[int, int]:
    """
    Lee las tarifas de envío directamente de Shopify Admin API.
    Busca automáticamente:
      - La tarifa plana (precio > 0, sin mínimo) → COSTO_ENVIO
      - El umbral de envío gratis (precio = 0, con mínimo) → ENVIO_GRATIS

    Si SHOPIFY_ADMIN_TOKEN no está configurado, usa las env vars como fallback.
    Retorna (costo_envio, umbral_gratis).
    """
    global _costo_envio, _envio_gratis

    # Preferir token + store del agente conectado (post-OAuth). Fallback env vars.
    admin_token = await _resolver_admin_token()
    store_dom = await _resolver_store()

    if not admin_token:
        logger.info(
            f"SHOPIFY_ADMIN_TOKEN no configurado — tarifas de envío desde env vars: "
            f"costo=${_costo_envio}, gratis desde=${_envio_gratis}"
        )
        return _costo_envio, _envio_gratis

    try:
        url = f"https://{store_dom}/admin/api/2024-10/shipping_zones.json"
        headers = {"X-Shopify-Access-Token": admin_token}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()

        costo_nuevo: int | None = None
        gratis_nuevo: int | None = None

        for zone in data.get("shipping_zones", []):
            for rate in zone.get("price_based_shipping_rates", []):
                price = int(float(rate.get("price") or 0))
                min_sub = rate.get("min_order_subtotal")
                max_sub = rate.get("max_order_subtotal")

                if price == 0 and min_sub and not max_sub:
                    # Envío gratis desde min_sub (ej. "80000.00")
                    gratis_nuevo = int(float(min_sub))
                elif price > 0 and not min_sub:
                    # Tarifa plana sin condición de monto mínimo
                    costo_nuevo = price

        if costo_nuevo is not None:
            _costo_envio = costo_nuevo
        if gratis_nuevo is not None:
            _envio_gratis = gratis_nuevo

        logger.info(
            f"Tarifas de envío cargadas desde Shopify: "
            f"costo=${_costo_envio:,}, gratis desde=${_envio_gratis:,}"
        )

    except Exception as e:
        logger.warning(
            f"No se pudieron cargar tarifas desde Shopify Admin API: {e} "
            f"— usando valores de env vars (costo=${_costo_envio}, gratis=${_envio_gratis})"
        )

    return _costo_envio, _envio_gratis

# Logo de la tienda (obtenido de Shopify brand o configurado manualmente)
_shop_logo_url: str = ""


def obtener_logo_url() -> str:
    """Retorna la URL del logo de la tienda (desde Shopify o env var)."""
    return os.getenv("LOGO_URL", "") or _shop_logo_url


async def obtener_logo_shopify() -> str:
    """Carga (si no está cacheado) y retorna el logo URL de Shopify."""
    await _cargar_logo_shopify()
    return obtener_logo_url()


def _normalizar(texto: str) -> str:
    """Normaliza para matching tolerante: minúsculas, sin acentos, separadores
    (/, -, _, comas) convertidos a espacio, espacios colapsados."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower().strip()
    texto = re.sub(r"[/\-_.,;:]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


async def obtener_catalogo_shopify() -> str:
    """Obtiene el catálogo desde Shopify. Cachea en memoria por CATALOG_TTL_SEG segundos
    para evitar una llamada HTTP en cada mensaje (mejora velocidad de respuesta ~1-2 s)."""
    global _catalog_cache, _catalog_cache_at
    ahora = datetime.utcnow()
    if (
        _catalog_cache
        and _catalog_cache_at
        and (ahora - _catalog_cache_at).total_seconds() < CATALOG_TTL_SEG
    ):
        return _catalog_cache  # Respuesta instantánea desde cache

    try:
        # Catálogo se obtiene EXCLUSIVAMENTE desde Admin GraphQL (post-OAuth).
        # El fallback Storefront fue retirado en #62 — todo cliente Voco debe
        # completar OAuth antes de operar (UX Jelou).
        admin_tok = await _resolver_admin_token()
        store_dom = await _resolver_store()
        if not (admin_tok and store_dom):
            logger.warning("[catalogo] sin SHOPIFY_ADMIN_TOKEN — completa OAuth en Configuración")
            return "## Catálogo de productos\n\nNo hay tienda Shopify conectada. Conecta tu tienda en Configuración → Shopify."
        from agent.shopify_admin import obtener_productos_admin
        data = await obtener_productos_admin(store_dom, admin_tok)
        logger.info(f"[catalogo] fuente=Admin GraphQL (store={store_dom})")

        products = data.get("data", {}).get("products", {}).get("edges", [])
        if not products:
            logger.warning("Shopify no devolvió productos")
            return "## Catálogo de productos actualizado (Shopify)\n\nNo hay productos disponibles en este momento."

        _variant_map.clear()
        _sku_map.clear()
        _categorias_cache.clear()
        _catalog_json.clear()
        _handle_map.clear()
        categorias: dict[str, list[tuple[str, list[dict], str]]] = {}
        total = 0

        for p in products:
            node = p["node"]
            variantes = [
                v["node"] for v in node["variants"]["edges"]
                if v["node"]["availableForSale"]
                and float(v["node"]["price"]["amount"]) > 0
            ]
            if not variantes:
                continue

            # Imagen principal del producto
            imgs = node.get("images", {}).get("edges", [])
            imagen = imgs[0]["node"]["url"] if imgs else ""

            # Guardar handle para construir URLs de producto específico
            # node.get("handle", "") no es suficiente: si Shopify devuelve null, .get() retorna None
            _handle_map[_normalizar(node["title"])] = node.get("handle") or ""

            # Categoría: cascada multi-tenant (Shopify-first, fallback legacy).
            # Esto reemplaza el mapa fijo de Equora — funciona para cualquier
            # cliente Voco sin configurar nada.
            categoria = _categoria_desde_shopify(node)
            categorias.setdefault(categoria, []).append((node["title"], variantes, imagen))

            for v in variantes:
                stock = v.get("quantityAvailable")
                precio = int(float(v["price"]["amount"]))

                # Imagen específica de la variante (si no tiene, hereda la del producto)
                v_img_data = v.get("image") or {}
                v_imagen = v_img_data.get("url", "") or imagen

                # Mapa para checkout Shopify
                clave = f"{_normalizar(node['title'])}|{_normalizar(v['title'])}"
                _variant_map[clave] = {
                    "id": v["id"],
                    "stock": stock if isinstance(stock, int) else None,
                }

                # Mapa por retailer_id para órdenes del catálogo nativo WhatsApp
                sku = (v.get("sku") or "").strip()
                gid = v["id"]  # gid://shopify/ProductVariant/12345678
                numeric_id = gid.split("/")[-1] if "/" in gid else gid
                # Shopify sincroniza con Facebook usando el SKU como retailer_id.
                # Si no hay SKU, usa el ID numérico de la variante.
                for rid in filter(None, [sku, numeric_id]):
                    if rid not in _sku_map:
                        _sku_map[rid] = {
                            "producto": node["title"],
                            "presentacion": v["title"],
                            "precio_unitario": precio,
                            "categoria": categoria,  # Sprint A: para fallback Shopify→_fb_items
                            "variant_id": gid,
                        }

                # JSON para mini-tienda web (imagen específica por variante)
                _catalog_json.append({
                    "producto": node["title"],
                    "presentacion": v["title"],
                    "precio": int(float(v["price"]["amount"])),
                    "stock": stock if isinstance(stock, int) else None,
                    "imagen": v_imagen,
                    "categoria": categoria,
                })

                total += 1

        # Guardar categorías para armar secciones del catálogo nativo
        _categorias_cache.update(categorias)

        # Construir texto del catálogo: respetar orden de ORDEN_CATEGORIAS para
        # categorías conocidas y agregar AL FINAL todas las categorías nuevas
        # del cliente (Combos, Más vendidos, Talleres e Industrial, etc.).
        # ANTES: solo se listaban las de ORDEN_CATEGORIAS → productos en
        # categorías nuevas quedaban INVISIBLES para Andrea y ella inventaba
        # "no está disponible" — bug critico que perdía ventas.
        ya_listadas = set(ORDEN_CATEGORIAS)
        cats_extra = sorted(c for c in categorias.keys() if c not in ya_listadas)
        cats_con_productos = [c for c in ORDEN_CATEGORIAS if c in categorias] + cats_extra

        lineas = ["## Catálogo de productos actualizado (Shopify)\n"]
        lineas.append("Categorías disponibles: " + ", ".join(cats_con_productos) + "\n")
        # Importante: indicarle a Andrea que NUNCA invente "no disponible"
        # — todo lo que esté listado abajo está vendible.
        lineas.append(
            "IMPORTANTE: TODOS los productos listados a continuación están "
            "disponibles para vender. NUNCA digas que un producto 'no está "
            "disponible' si aparece en esta lista. Si el cliente pregunta "
            "por algo de esta lista, ofrécelo activamente.\n"
        )
        for categoria in cats_con_productos:
            productos_cat = categorias.get(categoria, [])
            lineas.append(f"### {categoria}")
            for prod_title, variantes, _img in productos_cat:
                lineas.append(f"*{prod_title}*")
                for v in variantes:
                    precio = int(float(v["price"]["amount"]))
                    stock = v.get("quantityAvailable")
                    # Mostrar stock solo si es un número conocido > 0
                    # (Storefront API a veces devuelve None si el cliente no
                    # tiene activado "mostrar inventario al público")
                    if isinstance(stock, int) and stock > 0:
                        lineas.append(f"  {v['title']} → ${precio:,}  ({stock} disponibles)")
                    else:
                        # NO indicar "agotado" — el cliente puede tener
                        # "vender sin existencias=SÍ" en Shopify y igual debe venderse.
                        lineas.append(f"  {v['title']} → ${precio:,}")
                lineas.append("")
            lineas.append("")

        logger.info(f"Catálogo Shopify: {len(products)} productos, {total} variantes disponibles")

        if total == 0:
            resultado = "## Catálogo de productos actualizado (Shopify)\n\nNo hay productos con stock disponible en este momento."
        else:
            resultado = "\n".join(lineas)

        # Guardar en cache ANTES de lanzar tareas secundarias
        # (así la tienda responde de inmediato sin esperar a Facebook o logo)
        _catalog_cache = resultado
        _catalog_cache_at = ahora

        # Cargar logo y catálogo de Facebook en background (no bloquean)
        asyncio.create_task(_cargar_logo_shopify())
        asyncio.create_task(_cargar_fb_catalog())

        return resultado

    except Exception as e:
        logger.error(f"Error obteniendo catálogo Shopify: {e}")
        return _catalog_cache  # Si falla, devuelve el último cache disponible


async def _cargar_logo_shopify():
    """Obtiene el logo de la tienda desde Shopify Admin API (background task)."""
    global _shop_logo_url
    if _shop_logo_url or os.getenv("LOGO_URL"):
        return  # Ya tenemos logo
    try:
        admin_tok = await _resolver_admin_token()
        store_dom = await _resolver_store()
        if not (admin_tok and store_dom):
            return
        from agent.shopify_admin import obtener_logo_shopify_admin
        logo_url = await obtener_logo_shopify_admin(store_dom, admin_tok)
        if logo_url:
            _shop_logo_url = logo_url
            logger.info(f"Logo Shopify obtenido: {_shop_logo_url}")
    except Exception as e:
        logger.debug(f"No se pudo obtener logo Shopify: {e}")


async def _cargar_fb_catalog():
    """Consulta la Graph API de Meta para obtener los retailer_ids reales del catálogo.
    Estos IDs son los únicos válidos para mensajes product_list de WhatsApp."""
    global _fb_items, _sku_map
    # Leer dinámicamente desde config_value (panel) para que cambios surtan
    # efecto sin reiniciar — útil cuando el merchant reconecta el catálogo
    # Shopify↔Meta y obtiene un META_CATALOG_ID nuevo.
    meta_token   = await _resolver_meta_access_token()
    meta_cat_id  = await _resolver_meta_catalog_id()
    if not meta_token or not meta_cat_id:
        logger.warning("META_ACCESS_TOKEN o META_CATALOG_ID no configurados — catálogo nativo deshabilitado")
        return

    todos = []
    url = f"https://graph.facebook.com/{META_API_VERSION}/{meta_cat_id}/products"
    params = {
        "fields": "retailer_id,name,price,availability",
        "limit": 200,
        "access_token": meta_token,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            while url:
                r = await client.get(url, params=params)
                if r.status_code != 200:
                    logger.error(f"Error Graph API catálogo: {r.status_code} — {r.text}")
                    break
                data = r.json()
                todos.extend(data.get("data", []))
                # Paginación cursor-based
                url = data.get("paging", {}).get("next")
                params = {}  # next ya incluye todo en la URL

        logger.info(f"Facebook catálogo: {len(todos)} items obtenidos (IDs reales)")

        # Registrar primeros 30 para diagnóstico
        for item in todos[:30]:
            logger.info(f"  FB item: retailer_id='{item.get('retailer_id')}' name='{item.get('name')}' price='{item.get('price')}'")

        # Construir lista de items con categoría asignada
        _fb_items.clear()
        for item in todos:
            rid = item.get("retailer_id", "")
            name = item.get("name", "")
            if not rid or not name:
                continue
            categoria = _categoria_producto(name)
            precio_str = item.get("price", "0 COP").split()[0].replace(",", "").replace(".", "")
            try:
                precio = int(float(precio_str))
            except Exception:
                precio = 0

            _fb_items.append({
                "retailer_id": rid,
                "name": name,
                "precio": precio,
                "categoria": categoria,
            })

            # Actualizar _sku_map con el retailer_id real de Facebook
            # Intentamos asociarlo a la variante Shopify por nombre normalizado
            name_n = _normalizar(name)
            for clave, v_info in _variant_map.items():
                prod_n, pres_n = clave.split("|", 1)
                # Coincidencia: el nombre de FB contiene el nombre del producto
                if prod_n in name_n or name_n in prod_n:
                    existing = _sku_map.get(rid)
                    if not existing:
                        # Buscar en _sku_map existente por variant_id para obtener la presentación
                        for existing_rid, existing_info in list(_sku_map.items()):
                            if existing_info.get("variant_id") == v_info["id"]:
                                _sku_map[rid] = {**existing_info}
                                break
                        else:
                            # No se encontró — crear entrada básica
                            _sku_map[rid] = {
                                "producto": name,
                                "presentacion": "",
                                "precio_unitario": precio,
                                "variant_id": v_info["id"],
                            }
                    break

        logger.info(f"_sku_map actualizado con {len(_fb_items)} items de Facebook")

    except Exception as e:
        logger.error(f"Error cargando catálogo Facebook: {e}")

    # ──────────────────────────────────────────────────────────────────────
    # FALLBACK Shopify-only: si Graph API no devolvió items (token sin
    # permiso catalog_management, error de red, app sin App Review, etc.)
    # construimos _fb_items desde _sku_map que YA está poblado desde Shopify.
    #
    # Esto funciona porque Shopify Sales Channel sincroniza con Meta Catalog
    # usando el variant_id como retailer_id. Los IDs que pegamos al payload
    # de product_list son reconocidos por Meta sin necesitar Graph API.
    # ──────────────────────────────────────────────────────────────────────
    if not _fb_items and _sku_map:
        logger.info(
            f"_fb_items vacío de Graph API — construyendo desde _sku_map "
            f"(Shopify, {len(_sku_map)} entradas)"
        )
        # Paso 1: agrupar por variant_id (cada variante única tiene hasta
        # 2 entradas en _sku_map: una con SKU alfanumérico y otra con el
        # variant_id numérico de Shopify). Necesitamos ambas para elegir
        # el retailer_id que Meta reconoce.
        variantes_unicas: dict[str, dict] = {}
        for rid, info in _sku_map.items():
            if not rid:
                continue
            vid = info.get("variant_id", "")
            if not vid:
                continue
            entry = variantes_unicas.setdefault(vid, {
                "sku":        None,
                "numeric_id": None,
                "info":       info,
            })
            # Clasificar el rid: numérico largo = variant_id de Shopify;
            # cualquier otra cosa = SKU configurado en Shopify.
            if rid.isdigit() and len(rid) >= 8:
                entry["numeric_id"] = rid
            else:
                entry["sku"] = rid

        # Paso 2: por cada variante única, ELEGIR el retailer_id que
        # Meta reconoce. Shopify Sales Channel sincroniza con Meta usando
        # el SKU como retailer_id cuando existe; si no existe, usa el
        # variant_id numérico. Esa misma prioridad replicamos acá.
        # NOTA: si tu Meta Catalog usa otro esquema (poco común), este
        # fallback igual entrega algo y el operador puede ajustar.
        representante_por_producto: dict[str, dict] = {}
        for vid, v in variantes_unicas.items():
            info = v["info"]
            producto = info.get("producto", "")
            if not producto:
                continue
            # Preferencia: SKU > variant_id numérico
            rid_meta = v["sku"] or v["numeric_id"]
            if not rid_meta:
                continue
            precio = info.get("precio_unitario", 0) or 0
            actual = representante_por_producto.get(producto)
            # Tomar la variante más barata como representante (atrae con precio bajo)
            if actual is None or precio < actual["precio"]:
                representante_por_producto[producto] = {
                    "retailer_id": rid_meta,
                    # Solo el nombre del producto en `name` — la presentación
                    # la verá el cliente al abrir la vista nativa de Meta.
                    "name":        producto,
                    "precio":      precio,
                    # Usar la categoría que se guardó al cargar Shopify
                    # (collection > productType > tag > keyword > "Catálogo").
                    "categoria":   info.get("categoria") or _categoria_producto(producto),
                }
        _fb_items.extend(representante_por_producto.values())
        # Estadísticas para diagnóstico: cuántos usaron SKU vs numeric_id
        usaron_sku = sum(
            1 for vid, v in variantes_unicas.items()
            if v["sku"] and any(
                r["retailer_id"] == v["sku"]
                for r in representante_por_producto.values()
            )
        )
        logger.info(
            f"_fb_items construido desde Shopify: {len(_fb_items)} productos "
            f"de {len(variantes_unicas)} variantes únicas "
            f"({usaron_sku} usan SKU, {len(_fb_items) - usaron_sku} usan variant_id) ✅"
        )


async def obtener_secciones_catalogo_async(categoria: str | None = None) -> list[dict]:
    """Versión async: si _fb_items está vacío, intenta cargarlo antes de devolver.
    Útil en flujos donde queremos garantizar el product_list aunque el catálogo
    no estuviera precargado (ej: cold start, deploy reciente)."""
    if not _fb_items:
        logger.info("_fb_items vacío en runtime — cargando catálogo Facebook inline")
        try:
            await _cargar_fb_catalog()
        except Exception as e:
            logger.error(f"Fallo cargando catálogo Facebook inline: {e}")
    return obtener_secciones_catalogo(categoria)


def obtener_secciones_catalogo(categoria: str | None = None) -> list[dict]:
    """Devuelve las secciones para un mensaje product_list de WhatsApp.
    Usa los retailer_ids REALES del catálogo de Facebook (no SKUs de Shopify).
    Si se pasa categoría filtra solo esa; si no, devuelve todas.

    LÍMITES DE META: product_list admite max 30 items totales y max 10 secciones.
    Si el catálogo excede 30, se recortan: primero ORDEN_CATEGORIAS (preferencia
    Equora), luego las categorías reales que vienen de Shopify en orden alfabético.

    NOTA: Si _fb_items está vacío, esta función SINCRÓNICA no puede cargarlo.
    En ese caso, usar obtener_secciones_catalogo_async() en el caller.
    """
    if not _fb_items:
        logger.warning("_fb_items vacío — catálogo Facebook aún no cargado")
        return []

    # Filtrar por categoría si se especificó
    items_filtrados = [
        i for i in _fb_items
        if (not categoria or i["categoria"] == categoria)
    ]
    if not items_filtrados:
        logger.warning(f"Sin items de Facebook para categoría '{categoria}'")
        return []

    # Agrupar por categoría
    por_categoria: dict[str, list[str]] = {}
    for item in items_filtrados:
        cat = item["categoria"]
        por_categoria.setdefault(cat, []).append(item["retailer_id"])

    # Orden de categorías:
    #   - Si se pidió una específica → solo esa
    #   - Si no → primero las de ORDEN_CATEGORIAS (Equora), luego el resto
    #     en orden alfabético. Esto hace que un cliente Voco con colecciones
    #     custom ("Pizzas", "Bebidas", ...) vea TODAS sus categorías aunque
    #     no estén en ORDEN_CATEGORIAS.
    if categoria:
        orden = [categoria]
    else:
        ya_listadas = set(ORDEN_CATEGORIAS)
        extra = sorted(c for c in por_categoria.keys() if c not in ya_listadas)
        orden = list(ORDEN_CATEGORIAS) + extra

    META_MAX_ITEMS = 30      # Límite duro de Meta product_list
    META_MAX_SECCIONES = 10  # Límite duro de Meta product_list
    items_usados = 0
    secciones = []
    for cat_name in orden:
        if len(secciones) >= META_MAX_SECCIONES:
            break
        rids = por_categoria.get(cat_name, [])
        if not rids:
            continue
        cupo = META_MAX_ITEMS - items_usados
        if cupo <= 0:
            break
        rids_recortados = rids[:cupo]
        secciones.append({
            "title": cat_name[:24],
            "product_items": [{"product_retailer_id": r} for r in rids_recortados],
        })
        items_usados += len(rids_recortados)

    total_disponible = len(items_filtrados)
    if items_usados < total_disponible:
        logger.info(
            f"product_list recortado: {items_usados}/{total_disponible} items "
            f"({len(secciones)} secciones) — limite Meta 30 items"
        )
    return secciones


def obtener_producto_por_retailer_id(retailer_id: str) -> dict | None:
    """Busca un producto en el mapa de SKUs para procesar órdenes del catálogo nativo."""
    return _sku_map.get(retailer_id)


def obtener_catalogo_json() -> list[dict]:
    """Retorna el catálogo completo como lista de dicts para la mini-tienda web.
    Formato: [{producto, presentacion, precio, stock, imagen, categoria}, ...]
    Se llena cuando se carga el catálogo de Shopify."""
    return list(_catalog_json)


def obtener_url_producto(nombre: str) -> str | None:
    """
    Busca el handle de Shopify para el producto que coincide con `nombre`
    y retorna la URL completa en equoradistribuciones.com.

    Proceso:
    1. Normaliza el nombre de búsqueda
    2. Busca coincidencia exacta en _handle_map (título normalizado → handle)
    3. Si no hay exacta, busca coincidencia parcial
    4. Retorna None si no hay catálogo cargado aún

    Uso: llamar solo si el catálogo ya está en cache (_handle_map no vacío).
    """
    if not _handle_map:
        return None  # Catálogo aún no cargado — usar fallback de colección

    nombre_n = _normalizar(nombre)
    if not nombre_n:
        return None

    # 1. Coincidencia exacta
    handle = _handle_map.get(nombre_n)
    if handle:
        return f"{EQUORA_PRODUCT_BASE}/{handle}"

    # 2. Coincidencia parcial con scoring por palabras en común (Jaccard)
    #    Pre-filtro: al menos 1 palabra en común (tolera typos en títulos de Shopify,
    #    ej: "pofesional" vs "profesional" — ambos comparten "desengrasante").
    #    Luego el score de Jaccard elige al mejor candidato.
    palabras_busqueda = set(nombre_n.split())
    mejores: list[tuple[float, str]] = []       # (score, handle)
    mejores_sin_h: list[tuple[float, str]] = [] # (score, titulo_n) cuando handle vacío
    for titulo_n, h in _handle_map.items():
        palabras_titulo = set(titulo_n.split())
        # Pre-filtro tolerante: al menos 1 palabra en común
        if not (palabras_busqueda & palabras_titulo):
            continue
        interseccion = palabras_busqueda & palabras_titulo
        union = palabras_busqueda | palabras_titulo
        score = len(interseccion) / len(union) if union else 0
        # Umbral mínimo: descartar coincidencias muy débiles (< 15%)
        if score < 0.15:
            continue
        if h:
            mejores.append((score, h))
        else:
            # Handle vacío en Shopify — generamos uno desde el título normalizado
            mejores_sin_h.append((score, titulo_n))

    if mejores:
        mejores.sort(reverse=True)
        score_ganador, handle_ganador = mejores[0]
        logger.info(
            f"[handle-map] '{nombre}' → handle='{handle_ganador}' (score={score_ganador:.2f})"
        )
        return f"{EQUORA_PRODUCT_BASE}/{handle_ganador}"

    if mejores_sin_h:
        # Fallback: handle generado desde el título usando underscores (convención de Shopify)
        # ej. "desengrasante profesional biotu" → "desengrasante_profesional_biotu"
        mejores_sin_h.sort(reverse=True)
        score_ganador, titulo_ganador = mejores_sin_h[0]
        handle_generado = titulo_ganador.replace(" ", "_")
        logger.warning(
            f"[handle-map] '{nombre}' → handle null en API para '{titulo_ganador}' "
            f"(score={score_ganador:.2f}). Usando handle generado: '{handle_generado}'."
        )
        return f"{EQUORA_PRODUCT_BASE}/{handle_generado}"

    # Ningún candidato — log de debug
    candidatos = [k for k in _handle_map if any(p in k for p in nombre_n.split())]
    logger.warning(
        f"[handle-map] '{nombre}' (norm: '{nombre_n}') sin coincidencia. "
        f"Candidatos parciales: {candidatos[:5]}"
    )
    return None


async def crear_checkout_shopify(telefono: str, datos: dict) -> str | None:
    """Crea un cart en Shopify Storefront API y retorna el checkoutUrl listo para pagar."""
    productos = datos.get("productos", [])
    if not productos:
        logger.error("Pedido sin productos")
        return None

    # Asegurar que tengamos el mapa de variantes cargado
    if not _variant_map:
        await obtener_catalogo_shopify()

    lines = []
    no_encontrados = []
    excede_stock = []  # [(producto, pedido, disponible)]
    logger.info(f"[checkout] Procesando {len(productos)} items para {telefono}")
    for p in productos:
        clave = f"{_normalizar(p.get('producto', ''))}|{_normalizar(p.get('presentacion', ''))}"
        variante = _variant_map.get(clave)
        if not variante:
            # Fallback tolerante: misma presentación + producto contenido
            prod_norm = _normalizar(p.get('producto', ''))
            pres_norm = _normalizar(p.get('presentacion', ''))
            for k, v in _variant_map.items():
                k_prod, k_pres = k.split("|", 1)
                if pres_norm == k_pres and (prod_norm in k_prod or k_prod in prod_norm):
                    variante = v
                    logger.info(f"[checkout] Match tolerante: '{clave}' → '{k}'")
                    break
        if not variante:
            no_encontrados.append(f"{p.get('producto', '')} - {p.get('presentacion', '')}")
            logger.error(f"[checkout] Item sin match en _variant_map: clave='{clave}'")
            continue

        cantidad = int(p.get("cantidad", 1))
        stock = variante.get("stock")
        # FIX: Recortar SOLO si stock > 0 (positivo) y se excede.
        # Si stock = 0 y el producto entró al catálogo (availableForSale=True),
        # Shopify tiene "Vender sin existencias = SÍ" activado → permitir venta.
        # Si stock = None → Shopify no expone inventario → permitir venta.
        # ANTES con stock >= 0: si stock=0 recortaba cantidad a 0 → producto se
        # descartaba → "No pude procesar tu pedido" cuando el cliente SÍ puede comprar.
        if isinstance(stock, int) and stock > 0 and cantidad > stock:
            excede_stock.append((
                f"{p.get('producto', '')} - {p.get('presentacion', '')}",
                cantidad, stock,
            ))
            cantidad = stock
            logger.warning(f"[checkout] Cantidad recortada por stock real: {p.get('producto')} pidió {p.get('cantidad')} → {stock}")
        if cantidad <= 0:
            logger.warning(f"[checkout] Item descartado por cantidad <= 0: {p.get('producto')}")
            continue

        lines.append({
            "merchandiseId": variante["id"],
            "quantity": cantidad,
        })
        logger.info(f"[checkout] Item OK: {p.get('producto')} / {p.get('presentacion')} × {cantidad}")

    if no_encontrados:
        logger.error(
            f"[checkout] Productos NO encontrados en variant_map: {no_encontrados}. "
            f"Total entradas variant_map: {len(_variant_map)}. "
            f"Primeras 15 claves: {list(_variant_map.keys())[:15]}"
        )
    if excede_stock:
        logger.warning(f"[checkout] Cantidades recortadas por stock real: {excede_stock}")
    if not lines:
        logger.error(
            f"[checkout] Ningún producto mapeado. variant_map tiene {len(_variant_map)} entradas. "
            f"Pedido: {[(p.get('producto'), p.get('presentacion'), p.get('cantidad')) for p in productos]}"
        )
        return None

    # Validar si es un teléfono real (dígitos) o un placeholder como "web-tienda"
    es_tel_real = bool(telefono and telefono not in ("web-tienda",) and any(c.isdigit() for c in telefono))
    telefono_e164 = ("+" + telefono.lstrip("+")) if es_tel_real else ""

    origen = "WhatsApp - Andrea Bot" if es_tel_real else "Tienda Web"
    attributes = [{"key": "Origen", "value": origen}]
    if es_tel_real:
        attributes.append({"key": "Telefono WhatsApp", "value": telefono_e164})
    for k_data, k_label in [
        ("nombres", "Nombres"), ("apellidos", "Apellidos"),
        ("razon_social", "Razon Social"), ("cc_nit", "CC/NIT"),
        ("direccion", "Direccion"), ("barrio", "Barrio"),
        ("ciudad", "Ciudad"), ("departamento", "Departamento"),
    ]:
        valor = str(datos.get(k_data, "") or "").strip()
        if valor:
            attributes.append({"key": k_label, "value": valor})

    nota = (
        f"Pedido WhatsApp de {datos.get('nombres', '')} {datos.get('apellidos', '')} ({telefono_e164})"
        if es_tel_real else "Pedido desde Tienda Web"
    )

    # Checkout vía Admin API Draft Order (post-OAuth). Storefront cartCreate
    # fue retirado en #62 — todo cliente Voco usa Admin desde aquí.
    admin_tok = await _resolver_admin_token()
    store_dom = await _resolver_store()
    if not (admin_tok and store_dom):
        logger.error("[checkout] sin SHOPIFY_ADMIN_TOKEN — completa OAuth en Configuración")
        return None
    from agent.shopify_admin import crear_draft_order
    # Convertir merchandiseId (gid://shopify/ProductVariant/123) → variant_id numérico
    line_items_admin = []
    for ln in lines:
        gid = ln["merchandiseId"]
        variant_id = int(gid.split("/")[-1]) if "/" in gid else int(gid)
        line_items_admin.append({
            "variant_id": variant_id,
            "quantity":   ln["quantity"],
        })
    # attributes → note_attributes (Draft Order format)
    note_attrs = [{"name": a["key"], "value": a["value"]} for a in attributes]
    res = await crear_draft_order(
        store_dom, admin_tok,
        line_items=line_items_admin, note=nota, note_attributes=note_attrs,
    )
    if not res.get("ok"):
        logger.error(f"[checkout] Draft Order falló: {res.get('error')}")
        return None
    invoice_url = res["invoice_url"]
    logger.info(f"[checkout] Draft Order creado para {telefono}: {invoice_url}")
    return invoice_url


async def obtener_precios_sheet() -> list[dict]:
    """Descarga el catálogo de precios desde Google Sheets en tiempo real."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            r = await client.get(PRECIOS_SHEET_URL)
            r.raise_for_status()
            reader = csv.DictReader(io.StringIO(r.text))
            return [row for row in reader]
    except Exception as e:
        logger.error(f"Error leyendo precios desde Google Sheets: {e}")
        return []


async def obtener_precios_como_texto() -> str:
    """Retorna el catálogo de precios formateado como texto para el system prompt."""
    productos = await obtener_precios_sheet()
    if not productos:
        return "No se pudo cargar el catálogo de precios en este momento."
    lineas = ["## Lista de precios actualizada\n"]
    for p in productos:
        descripcion = p.get("descripcion", "")
        precio = p.get("price", "")
        if descripcion and precio:
            lineas.append(f"- {descripcion}: {precio}")
    return "\n".join(lineas)


def cargar_info_negocio() -> dict:
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    info = cargar_info_negocio()
    return {
        "horario": info.get("negocio", {}).get("horario", "No disponible"),
        "esta_abierto": True,
    }


def buscar_en_knowledge(consulta: str) -> str:
    resultados = []
    knowledge_dir = "knowledge"

    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."


# ── Calificación de leads ─────────────────────────────────────────────────────

def registrar_lead(telefono: str, tipo_cliente: str, interes: str) -> str:
    """Registra un lead nuevo con su perfil e interés."""
    logger.info(f"Lead registrado — {telefono} | tipo: {tipo_cliente} | interés: {interes}")
    return f"Lead registrado: {tipo_cliente} interesado en {interes}"


def calificar_cliente(tipo_cliente: str) -> str:
    """Devuelve el segmento de productos recomendado según el tipo de cliente."""
    segmentos = {
        "restaurante": ["Lavaloza Antibacterial PRO MAX", "Desengrasante Profesional", "Ambientador y Limpiapisos", "Jabón Manos y Cuerpo"],
        "hotel": ["Jabón Manos y Cuerpo", "Limpiavidrios", "Ambientador y Limpiapisos", "Detergente Ropa Blanca", "Suavizante"],
        "cafeteria": ["Lavaloza Antibacterial PRO MAX", "Detergente Multiusos", "Ambientador y Limpiapisos"],
        "hogar": ["Detergente Ropa Color", "Detergente Ropa Blanca", "Suavizante", "Lavaloza", "Ambientador y Limpiapisos"],
        "taller": ["Desengrasante de Motores", "Desengrasante Profesional", "Shampoo para Vehículos"],
        "industrial": ["Desengrasante Profesional", "Detergente Multiusos", "Jabón Manos y Cuerpo"],
    }
    tipo = tipo_cliente.lower()
    for key, productos in segmentos.items():
        if key in tipo:
            return f"Productos recomendados para {tipo_cliente}: {', '.join(productos)}"
    return "Contamos con líneas para hogar, restaurantes, hoteles, talleres e industria."


# ── Gestión de pedidos ────────────────────────────────────────────────────────

# Carrito en memoria por sesión (en producción usar base de datos)
_carritos: dict[str, list[dict]] = {}


def agregar_al_carrito(telefono: str, producto: str, cantidad: int, precio_unitario: float = 0) -> str:
    """Agrega un producto al carrito del cliente."""
    if telefono not in _carritos:
        _carritos[telefono] = []
    _carritos[telefono].append({
        "producto": producto,
        "cantidad": cantidad,
        "precio_unitario": precio_unitario,
        "subtotal": cantidad * precio_unitario,
    })
    logger.info(f"Producto agregado al carrito de {telefono}: {cantidad}x {producto}")
    return f"Agregado: {cantidad}x {producto}"


def ver_carrito(telefono: str) -> str:
    """Muestra el resumen del carrito actual."""
    carrito = _carritos.get(telefono, [])
    if not carrito:
        return "Tu carrito está vacío."
    lineas = [f"• {item['cantidad']}x {item['producto']}" for item in carrito]
    return "Tu pedido hasta ahora:\n" + "\n".join(lineas)


def limpiar_carrito(telefono: str):
    """Limpia el carrito después de confirmar el pedido."""
    _carritos.pop(telefono, None)


def confirmar_pedido(telefono: str, nombre: str, direccion: str) -> str:
    """Confirma el pedido y lo registra."""
    carrito = _carritos.get(telefono, [])
    if not carrito:
        return "No hay productos en tu pedido."
    resumen = ver_carrito(telefono)
    logger.info(f"Pedido confirmado — {nombre} ({telefono}) en {direccion}: {resumen}")
    limpiar_carrito(telefono)
    return (
        f"¡Pedido confirmado! 🎉\n\n{resumen}\n\n"
        f"📍 Dirección: {direccion}\n"
        f"👤 Nombre: {nombre}\n\n"
        "Alguien de nuestro equipo te contactará pronto para coordinar el pago y la entrega. ¡Gracias!"
    )


# ── Soporte post-venta ────────────────────────────────────────────────────────

def crear_ticket_soporte(telefono: str, problema: str) -> str:
    """Registra un ticket de soporte post-venta."""
    ticket_id = f"TKT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    logger.info(f"Ticket creado — {ticket_id} | {telefono}: {problema}")
    return (
        f"He registrado tu caso con el número *{ticket_id}*.\n"
        "Nuestro equipo lo revisará y te contactará muy pronto. "
        "Lamentamos los inconvenientes y lo resolveremos cuanto antes. 🙏"
    )


def escalar_a_equipo(telefono: str, contexto: str) -> str:
    """Escala la conversación a un agente humano."""
    logger.info(f"Escalado a equipo humano — {telefono}: {contexto}")
    return (
        "Entiendo, déjame conectarte con alguien de nuestro equipo que te pueda ayudar mejor. "
        "En breve te contactamos. ¡Gracias por tu paciencia! 😊"
    )
