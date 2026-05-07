import os
import re
import logging
import unicodedata
import yaml
import httpx
from datetime import datetime

logger = logging.getLogger("agentkit")

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE", "equora-6.myshopify.com")
SHOPIFY_STOREFRONT_TOKEN = os.getenv("SHOPIFY_STOREFRONT_TOKEN", "d6fe89f265fed1b5f9572f19fc0ba3a7")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN", "")

SHOPIFY_GQL_QUERY = """
{
  products(first: 100) {
    edges {
      node {
        title
        variants(first: 10) {
          edges {
            node {
              id
              title
              price { amount }
              availableForSale
            }
          }
        }
      }
    }
  }
}
"""

# Mapa de variantes para resolver merchandiseId al crear el checkout
# Clave: "producto|presentacion" normalizado | Valor: variant GID
_variant_map: dict[str, str] = {}


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
    """Obtiene el catálogo de productos disponibles desde Shopify Storefront API.
    Solo muestra variantes con availableForSale=true (requiere 'Rastrear cantidad' activado en Shopify)."""
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

        products = data.get("data", {}).get("products", {}).get("edges", [])
        if not products:
            logger.warning("Shopify no devolvió productos")
            return "## Catálogo de productos actualizado (Shopify)\n\nNo hay productos disponibles en este momento."

        lineas = ["## Catálogo de productos actualizado (Shopify)\n"]
        total = 0
        _variant_map.clear()

        for p in products:
            node = p["node"]
            variantes = [
                v["node"] for v in node["variants"]["edges"]
                if v["node"]["availableForSale"]
                and float(v["node"]["price"]["amount"]) > 0
            ]
            if not variantes:
                continue
            lineas.append(f"*{node['title']}*")
            for v in variantes:
                precio = int(float(v["price"]["amount"]))
                lineas.append(f"  {v['title']} → ${precio:,}")
                clave = f"{_normalizar(node['title'])}|{_normalizar(v['title'])}"
                _variant_map[clave] = v["id"]
            lineas.append("")
            total += len(variantes)

        logger.info(f"Catálogo Shopify: {len(products)} productos, {total} variantes disponibles")

        if total == 0:
            return "## Catálogo de productos actualizado (Shopify)\n\nNo hay productos con stock disponible en este momento."

        return "\n".join(lineas)

    except Exception as e:
        logger.error(f"Error obteniendo catálogo Shopify: {e}")
        return ""


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
    for p in productos:
        clave = f"{_normalizar(p.get('producto', ''))}|{_normalizar(p.get('presentacion', ''))}"
        variant_id = _variant_map.get(clave)
        if not variant_id:
            # Fallback: busca por presentación dentro de productos cuyo título contenga palabras clave
            prod_norm = _normalizar(p.get('producto', ''))
            pres_norm = _normalizar(p.get('presentacion', ''))
            for k, v in _variant_map.items():
                k_prod, k_pres = k.split("|", 1)
                if pres_norm == k_pres and (prod_norm in k_prod or k_prod in prod_norm):
                    variant_id = v
                    break
        if variant_id:
            lines.append({
                "merchandiseId": variant_id,
                "quantity": int(p.get("cantidad", 1)),
            })
        else:
            no_encontrados.append(f"{p.get('producto', '')} - {p.get('presentacion', '')}")

    if no_encontrados:
        logger.warning(f"Productos no encontrados en variant_map: {no_encontrados}")
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
