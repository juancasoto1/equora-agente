import os
import re
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

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE", "equora-6.myshopify.com")
SHOPIFY_STOREFRONT_TOKEN = os.getenv("SHOPIFY_STOREFRONT_TOKEN", "d6fe89f265fed1b5f9572f19fc0ba3a7")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN", "")

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_CATALOG_ID = os.getenv("META_CATALOG_ID", "")
META_API_VERSION = "v21.0"

SHOPIFY_GQL_QUERY = """
{
  shop {
    brand {
      logo {
        image {
          url
        }
      }
    }
  }
  products(first: 100) {
    edges {
      node {
        title
        productType
        collections(first: 5) {
          edges {
            node {
              title
            }
          }
        }
        images(first: 1) {
          edges {
            node {
              url
            }
          }
        }
        variants(first: 10) {
          edges {
            node {
              id
              title
              sku
              price { amount }
              availableForSale
              quantityAvailable
              image {
                url
              }
            }
          }
        }
      }
    }
  }
}
"""

# Colecciones que ignoramos como categoría visible (las crea Shopify por defecto)
COLECCIONES_IGNORADAS = {"home page", "frontpage", "all", "todos"}

# ── Categorías fijas de Equora ────────────────────────────────────────────────
# Orden y nombres exactos que debe mostrar Andrea.
# Clave: fragmento normalizado del título del producto → Valor: nombre de categoría.
# Si un producto no coincide con ninguna clave cae en "Otros".
CATEGORIAS_EQUORA: list[tuple[str, str]] = [
    # (fragmento normalizado del título,  categoría visible)
    ("detergente ropa blanca",          "Lavandería"),
    ("detergente ropa color",           "Lavandería"),
    ("suavizante",                      "Lavandería"),
    ("lavaloza antibacterial",          "Cocina"),
    ("lavaloza pro max",                "Cocina"),
    ("lavaloza pro",                    "Cocina"),
    ("desengrasante de cocina",         "Cocina"),
    ("desengrasante cocina",            "Cocina"),
    ("ambientador",                     "Hogar"),
    ("limpiapisos",                     "Hogar"),
    ("desmanchador",                    "Hogar"),
    ("eliminador de olores",            "Hogar"),
    ("eliminador olores",               "Hogar"),
    ("limpiador desinfectante",         "Hogar"),
    ("limpiavidrios",                   "Hogar"),
    ("desengrasante de motor",          "Talleres / Industrial"),
    ("desengrasante motor",             "Talleres / Industrial"),
    ("desengrasante profesional",       "Talleres / Industrial"),
    ("shampoo",                         "Talleres / Industrial"),
    ("jabon liquido",                   "Higiene Personal"),
    ("jabón líquido",                   "Higiene Personal"),
    ("jabon de manos",                  "Higiene Personal"),
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
    """Asigna la categoría fija de Equora a un producto por su título."""
    titulo_n = _normalizar(titulo)
    for fragmento, categoria in CATEGORIAS_EQUORA:
        if fragmento in titulo_n:
            return categoria
    return "Otros"


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

# Logo de la tienda (obtenido de Shopify brand o configurado manualmente)
_shop_logo_url: str = ""


def obtener_logo_url() -> str:
    """Retorna la URL del logo de la tienda (desde Shopify o env var)."""
    return os.getenv("LOGO_URL", "") or _shop_logo_url


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
        url = f"https://{SHOPIFY_STORE}/api/2024-10/graphql.json"
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Storefront-Access-Token": SHOPIFY_STOREFRONT_TOKEN,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json={"query": SHOPIFY_GQL_QUERY}, headers=headers)
            r.raise_for_status()
            data = r.json()

        # Logo del shop (Shopify brand API — API 2022-04+)
        global _shop_logo_url
        try:
            logo_data = data.get("data", {}).get("shop", {}).get("brand", {}) or {}
            logo_url = logo_data.get("logo", {}).get("image", {}).get("url", "")
            if logo_url:
                _shop_logo_url = logo_url
                logger.info(f"Logo Shopify: {_shop_logo_url}")
        except Exception:
            pass

        products = data.get("data", {}).get("products", {}).get("edges", [])
        if not products:
            logger.warning("Shopify no devolvió productos")
            return "## Catálogo de productos actualizado (Shopify)\n\nNo hay productos disponibles en este momento."

        _variant_map.clear()
        _sku_map.clear()
        _categorias_cache.clear()
        _catalog_json.clear()
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

            # Categoría: siempre desde el mapa fijo de Equora (ignora colecciones Shopify)
            categoria = _categoria_producto(node["title"])
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

        # Construir texto del catálogo respetando el orden fijo de categorías Equora
        cats_con_productos = [c for c in ORDEN_CATEGORIAS if c in categorias]
        lineas = ["## Catálogo de productos actualizado (Shopify)\n"]
        lineas.append("Categorías disponibles: " + ", ".join(cats_con_productos) + "\n")
        for categoria in cats_con_productos:
            productos_cat = categorias.get(categoria, [])
            lineas.append(f"### {categoria}")
            for prod_title, variantes, _img in productos_cat:
                lineas.append(f"*{prod_title}*")
                for v in variantes:
                    precio = int(float(v["price"]["amount"]))
                    stock = v.get("quantityAvailable")
                    if isinstance(stock, int) and stock > 0:
                        lineas.append(f"  {v['title']} → ${precio:,}  ({stock} disponibles)")
                    else:
                        lineas.append(f"  {v['title']} → ${precio:,}")
                lineas.append("")
            lineas.append("")

        logger.info(f"Catálogo Shopify: {len(products)} productos, {total} variantes disponibles")

        if total == 0:
            resultado = "## Catálogo de productos actualizado (Shopify)\n\nNo hay productos con stock disponible en este momento."
        else:
            resultado = "\n".join(lineas)

        # Cargar retailer_ids reales desde el catálogo de Facebook
        # (necesario para que product_list funcione con IDs válidos)
        await _cargar_fb_catalog()

        # Guardar en cache
        _catalog_cache = resultado
        _catalog_cache_at = ahora
        return resultado

    except Exception as e:
        logger.error(f"Error obteniendo catálogo Shopify: {e}")
        return _catalog_cache  # Si falla, devuelve el último cache disponible


async def _cargar_fb_catalog():
    """Consulta la Graph API de Meta para obtener los retailer_ids reales del catálogo.
    Estos IDs son los únicos válidos para mensajes product_list de WhatsApp."""
    global _fb_items, _sku_map
    if not META_ACCESS_TOKEN or not META_CATALOG_ID:
        logger.warning("META_ACCESS_TOKEN o META_CATALOG_ID no configurados — catálogo nativo deshabilitado")
        return

    todos = []
    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_CATALOG_ID}/products"
    params = {
        "fields": "retailer_id,name,price,availability",
        "limit": 200,
        "access_token": META_ACCESS_TOKEN,
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


def obtener_secciones_catalogo(categoria: str | None = None) -> list[dict]:
    """Devuelve las secciones para un mensaje product_list de WhatsApp.
    Usa los retailer_ids REALES del catálogo de Facebook (no SKUs de Shopify).
    Si se pasa categoría filtra solo esa; si no, devuelve todas."""
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

    # Agrupar por categoría respetando el orden fijo
    por_categoria: dict[str, list[str]] = {}
    for item in items_filtrados:
        cat = item["categoria"]
        por_categoria.setdefault(cat, []).append(item["retailer_id"])

    secciones = []
    orden = [categoria] if categoria else ORDEN_CATEGORIAS
    for cat_name in orden:
        rids = por_categoria.get(cat_name, [])
        if rids:
            secciones.append({
                "title": cat_name[:24],
                "product_items": [{"product_retailer_id": r} for r in rids],
            })
    return secciones


def obtener_producto_por_retailer_id(retailer_id: str) -> dict | None:
    """Busca un producto en el mapa de SKUs para procesar órdenes del catálogo nativo."""
    return _sku_map.get(retailer_id)


def obtener_catalogo_json() -> list[dict]:
    """Retorna el catálogo completo como lista de dicts para la mini-tienda web.
    Formato: [{producto, presentacion, precio, stock, imagen, categoria}, ...]
    Se llena cuando se carga el catálogo de Shopify."""
    return list(_catalog_json)


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
                    break
        if not variante:
            no_encontrados.append(f"{p.get('producto', '')} - {p.get('presentacion', '')}")
            continue

        cantidad = int(p.get("cantidad", 1))
        stock = variante.get("stock")
        # Si Shopify expone stock y la cantidad lo excede, recortamos al stock
        if isinstance(stock, int) and stock >= 0 and cantidad > stock:
            excede_stock.append((
                f"{p.get('producto', '')} - {p.get('presentacion', '')}",
                cantidad, stock,
            ))
            cantidad = stock
        if cantidad <= 0:
            continue

        lines.append({
            "merchandiseId": variante["id"],
            "quantity": cantidad,
        })

    if no_encontrados:
        logger.warning(f"Productos no encontrados en variant_map: {no_encontrados}")
    if excede_stock:
        logger.warning(f"Cantidades recortadas por stock: {excede_stock}")
    if not lines:
        logger.error(f"Ningún producto del pedido pudo mapearse a variantes Shopify")
        return None

    telefono_e164 = telefono if telefono.startswith("+") else f"+{telefono}"

    mutation = """
    mutation cartCreate($input: CartInput!) {
      cartCreate(input: $input) {
        cart {
          id
          checkoutUrl
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    attributes = [
        {"key": "Origen", "value": "WhatsApp - Andrea Bot"},
        {"key": "Telefono WhatsApp", "value": telefono_e164},
    ]
    for k_data, k_label in [
        ("nombres", "Nombres"), ("apellidos", "Apellidos"),
        ("razon_social", "Razon Social"), ("cc_nit", "CC/NIT"),
        ("direccion", "Direccion"), ("barrio", "Barrio"),
        ("ciudad", "Ciudad"), ("departamento", "Departamento"),
    ]:
        valor = str(datos.get(k_data, "") or "").strip()
        if valor:
            attributes.append({"key": k_label, "value": valor})

    variables = {
        "input": {
            "lines": lines,
            "buyerIdentity": {
                "phone": telefono_e164,
                "countryCode": "CO",
            },
            "attributes": attributes,
            "note": f"Pedido WhatsApp de {datos.get('nombres', '')} {datos.get('apellidos', '')} ({telefono_e164})",
        }
    }

    url = f"https://{SHOPIFY_STORE}/api/2024-10/graphql.json"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Storefront-Access-Token": SHOPIFY_STOREFRONT_TOKEN,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json={"query": mutation, "variables": variables}, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Storefront cartCreate: {r.status_code} — {r.text}")
                return None
            result = r.json()
            errores = result.get("data", {}).get("cartCreate", {}).get("userErrors", [])
            if errores:
                logger.error(f"userErrors cartCreate: {errores}")
                return None
            cart = result.get("data", {}).get("cartCreate", {}).get("cart")
            if not cart:
                logger.error(f"cartCreate sin cart: {result}")
                return None
            checkout_url = cart.get("checkoutUrl")
            logger.info(f"Checkout creado para {telefono}: {checkout_url}")
            return checkout_url
    except Exception as e:
        logger.error(f"Error creando checkout en Shopify: {e}")
        return None


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
