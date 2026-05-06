import os
import csv
import io
import logging
import yaml
import httpx
from datetime import datetime

logger = logging.getLogger("agentkit")

PEDIDOS_SCRIPT_URL = os.getenv(
    "PEDIDOS_SCRIPT_URL",
    "https://script.google.com/macros/s/AKfycbxxieSGuKuypKgublAXFKjlnOSj5Nm7fiQDTbdPeX9zoPaR97-zgBCxW-B2ow7Sq84e/exec"
)

PRECIOS_SHEET_URL = os.getenv(
    "PRECIOS_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vSr2pT9wKPefcXti8cOQZKR-lvAHS64L8YdpT89QdNECcKSkmM8DOuuiOyLQqC9gfPC5pQfrrNd-jau/pub?gid=828131088&single=true&output=csv"
)

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE", "equora-6.myshopify.com")
SHOPIFY_STOREFRONT_TOKEN = os.getenv("SHOPIFY_STOREFRONT_TOKEN", "d6fe89f265fed1b5f9572f19fc0ba3a7")

SHOPIFY_QUERY = """
{
  products(first: 50) {
    edges {
      node {
        title
        variants(first: 10) {
          edges {
            node {
              title
              price { amount }
              availableForSale
              quantityAvailable
            }
          }
        }
      }
    }
  }
}
"""


async def obtener_catalogo_shopify() -> str:
    """Obtiene el catálogo completo de productos desde Shopify Storefront API en tiempo real."""
    try:
        url = f"https://{SHOPIFY_STORE}/api/2024-10/graphql.json"
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Storefront-Access-Token": SHOPIFY_STOREFRONT_TOKEN,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json={"query": SHOPIFY_QUERY}, headers=headers)
            r.raise_for_status()
            data = r.json()

        products = data.get("data", {}).get("products", {}).get("edges", [])
        if not products:
            return "No se pudo cargar el catálogo de Shopify."

        lineas = ["## Catálogo de productos actualizado (Shopify)\n"]
        for p in products:
            node = p["node"]
            variantes_disponibles = [
                v["node"] for v in node["variants"]["edges"]
                if v["node"]["availableForSale"] and float(v["node"]["price"]["amount"]) > 0
            ]
            if not variantes_disponibles:
                continue  # Producto completamente agotado, no lo mostramos
            lineas.append(f"*{node['title']}*")
            for vn in variantes_disponibles:
                precio = int(float(vn["price"]["amount"]))
                lineas.append(f"  {vn['title']} → ${precio:,}")
            lineas.append("")

        logger.info(f"Catálogo Shopify cargado: {len(products)} productos")
        return "\n".join(lineas)

    except Exception as e:
        logger.error(f"Error obteniendo catálogo Shopify: {e}")
        return ""


async def guardar_pedido_en_sheet(telefono: str, datos: dict) -> str | None:
    """Envía los datos del pedido al Google Sheet via Apps Script.
    Retorna el número de pedido (ej: ED-0001) o None si falló."""
    try:
        payload = {**datos, "telefono": telefono}
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            r = await client.post(PEDIDOS_SCRIPT_URL, json=payload)
            if r.status_code == 200:
                numero_pedido = r.json().get("pedido")
                logger.info(f"Pedido guardado en sheet: {numero_pedido}")
                return numero_pedido
            logger.error(f"Error sheet: {r.status_code} — {r.text}")
            return None
    except Exception as e:
        logger.error(f"Error guardando pedido en sheet: {e}")
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
