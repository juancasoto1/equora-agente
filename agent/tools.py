import os
import logging
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
            lineas.append("")
            total += len(variantes)

        logger.info(f"Catálogo Shopify: {len(products)} productos, {total} variantes disponibles")

        if total == 0:
            return "## Catálogo de productos actualizado (Shopify)\n\nNo hay productos con stock disponible en este momento."

        return "\n".join(lineas)

    except Exception as e:
        logger.error(f"Error obteniendo catálogo Shopify: {e}")
        return ""


async def crear_orden_shopify(telefono: str, datos: dict) -> str | None:
    """Crea un borrador de orden en Shopify via Admin GraphQL API y lo completa."""
    if not SHOPIFY_ADMIN_TOKEN:
        logger.error("SHOPIFY_ADMIN_TOKEN no configurado")
        return None
    try:
        productos = datos.get("productos", [])
        nota = (
            f"Pedido via WhatsApp | Tel: {telefono} | "
            f"CC/NIT: {datos.get('cc_nit', '')} | "
            f"Razón Social: {datos.get('razon_social', '')} | "
            f"Barrio: {datos.get('barrio', '')} | "
            f"Dpto: {datos.get('departamento', '')}"
        )

        line_items_gql = [
            {
                "title": f"{p.get('producto', '')} - {p.get('presentacion', '')}",
                "quantity": int(p.get("cantidad", 1)),
                "originalUnitPrice": str(float(p.get("precio_unitario", 0))),
            }
            for p in productos
        ]

        mutation = """
        mutation draftOrderCreate($input: DraftOrderInput!) {
          draftOrderCreate(input: $input) {
            draftOrder {
              id
              name
              totalPrice
            }
            userErrors {
              field
              message
            }
          }
        }
        """

        variables = {
            "input": {
                "lineItems": line_items_gql,
                "shippingAddress": {
                    "firstName": datos.get("nombres", ""),
                    "lastName": datos.get("apellidos", ""),
                    "address1": datos.get("direccion", ""),
                    "city": datos.get("ciudad", ""),
                    "province": datos.get("departamento", ""),
                    "country": "CO",
                    "phone": telefono,
                },
                "note": nota,
                "tags": "whatsapp,andrea-bot",
            }
        }

        url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/graphql.json"
        headers = {
            "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json={"query": mutation, "variables": variables}, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error GraphQL Shopify: {r.status_code} — {r.text}")
                return None

            result = r.json()
            errors = result.get("data", {}).get("draftOrderCreate", {}).get("userErrors", [])
            if errors:
                logger.error(f"Errores GraphQL Shopify: {errors}")
                return None

            draft = result.get("data", {}).get("draftOrderCreate", {}).get("draftOrder")
            if not draft:
                logger.error(f"No se obtuvo draftOrder: {result}")
                return None

            draft_id = draft["id"]
            draft_name = draft.get("name", "")
            logger.info(f"Draft order creado: {draft_name} ({draft_id}) para {telefono}")

            # Completar el borrador para convertirlo en orden real
            complete_mutation = """
            mutation draftOrderComplete($id: ID!) {
              draftOrderComplete(id: $id) {
                draftOrder {
                  order {
                    id
                    name
                    orderNumber
                  }
                }
                userErrors {
                  field
                  message
                }
              }
            }
            """
            r2 = await client.post(
                url,
                json={"query": complete_mutation, "variables": {"id": draft_id}},
                headers=headers,
            )
            if r2.status_code != 200:
                logger.error(f"Error completando draft order: {r2.status_code} — {r2.text}")
                return draft_name  # devuelve el nombre del borrador al menos

            result2 = r2.json()
            errors2 = result2.get("data", {}).get("draftOrderComplete", {}).get("userErrors", [])
            if errors2:
                logger.error(f"Errores al completar draft: {errors2}")
                return draft_name

            order = (
                result2.get("data", {})
                .get("draftOrderComplete", {})
                .get("draftOrder", {})
                .get("order", {})
            )
            numero = order.get("orderNumber") or order.get("name", draft_name)
            logger.info(f"Orden Shopify creada: #{numero} para {telefono}")
            return f"#{numero}"

    except Exception as e:
        logger.error(f"Error creando orden en Shopify: {e}")
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
