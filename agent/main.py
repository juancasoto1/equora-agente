import os
import re
import json
import hmac
import hashlib
import base64
import logging
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Cookie
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse, RedirectResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import (
    inicializar_db, guardar_mensaje, obtener_historial,
    guardar_cliente, guardar_pedido_pendiente, limpiar_pedido_pendiente,
    guardar_carrito_activo, limpiar_carrito_activo, obtener_carrito_activo,
    registrar_mensaje_usuario, registrar_mensaje_asistente,
    marcar_followup_enviado, marcar_cierre_enviado,
    conversaciones_para_followup, conversaciones_para_cierre,
    clientes_con_carrito_abandonado, clientes_para_crosssell,
    guardar_checkout_url, clientes_con_checkout_abandonado,
    get_modo_humano, set_modo_humano,
    obtener_todas_conversaciones, obtener_historial_con_timestamps,
)
from agent.inbox import obtener_inbox_html, obtener_login_html
from agent.providers import obtener_proveedor
from agent.tools import (
    crear_checkout_shopify,
    obtener_catalogo_shopify,
    obtener_catalogo_json,
    obtener_secciones_catalogo,
    obtener_producto_por_retailer_id,
)

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# URL pública del servidor (se usa para el link de la mini-tienda)
_railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
APP_URL = os.getenv("APP_URL") or (f"https://{_railway_domain}" if _railway_domain else f"http://localhost:{PORT}")

# Configuración de seguimientos automáticos (env vars opcionales)
FOLLOWUP_MIN = int(os.getenv("FOLLOWUP_MIN", 2))   # min sin respuesta del cliente
CIERRE_MIN = int(os.getenv("CIERRE_MIN", 5))       # min después del follow-up
FOLLOWUP_MAX_HORAS = int(os.getenv("FOLLOWUP_MAX_HORAS", 12))
CHECK_INTERVAL_SEG = int(os.getenv("CHECK_INTERVAL_SEG", 30))

MENSAJE_FOLLOWUP = (
    "Hola de nuevo 😊 Veo que andas un poco ocupado/a. "
    "¿Sigues por aquí o prefieres que continuemos en otro momento? "
    "No hay afán, retomamos cuando puedas."
)

MENSAJE_CIERRE = (
    "Te dejo descansar 🤗 Cuando quieras retomar, escríbeme y "
    "seguimos donde nos quedamos. ¡Que tengas un excelente día! 🌿"
)

# ── Recuperación de carrito abandonado (mini-tienda, no llegó al checkout) ──
ABANDONO_MIN_INACTIVO = int(os.getenv("ABANDONO_MIN", 10))   # min sin finalizar
ABANDONO_MAX_INACTIVO = int(os.getenv("ABANDONO_MAX", 25))   # max para no insistir
_abandono_notif: dict[str, float] = {}
ABANDONO_COOLDOWN_SEG = 3600  # No re-notificar el mismo carrito por 1 hora

MENSAJE_ABANDONO = (
    "Vi que dejaste tu pedido casi listo 😊\n"
    "¿Quieres que te ayude a finalizarlo?\n\n"
    "Recuerda: pago contraentrega y envío gratis desde $80.000 🚚"
)

# ── Recuperación de checkout abandonado (llegó al formulario Shopify pero no pagó) ──
CHECKOUT_ABANDONO_MIN = int(os.getenv("CHECKOUT_ABANDONO_MIN", 20))   # min desde que creó checkout
CHECKOUT_ABANDONO_MAX = int(os.getenv("CHECKOUT_ABANDONO_MAX", 120))  # máximo 2 horas
_checkout_abandono_notif: dict[str, float] = {}
CHECKOUT_ABANDONO_COOLDOWN_SEG = 7200  # No re-notificar por 2 horas

MENSAJE_CHECKOUT_ABANDONO = (
    "Hola 👋 Vimos que iniciaste tu pedido pero no terminaste el proceso.\n\n"
    "Tu carrito está guardado — solo falta confirmar y listo 🎉\n"
    "Recuerda: *pago contraentrega*, no pagas nada online."
)

# ── Cross-selling desde mini-tienda ─────────────────────────────────────────
ENVIO_GRATIS = 80000
COSTO_ENVIO = 7000
# In-memory: phone → timestamp del último cross-sell enviado (cooldown 20 min)
_crosssell_cooldown: dict[str, float] = {}
CROSSSELL_COOLDOWN_SEG = 1200  # 20 minutos entre mensajes de cross-sell
# Productos estrella para sugerir (se filtran los que ya están en carrito)
PRODUCTOS_ESTRELLA = [
    "lavaloza", "limpiavidrios", "limpiador", "desengrasante",
    "desmanchador", "ambientador", "multiusos", "detergente",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await inicializar_db()
    logger.info("Base de datos inicializada")
    # Pre-calentar catálogo Shopify al arrancar para que _variant_map esté listo
    # antes de que llegue cualquier petición a /tienda/confirmar
    try:
        await obtener_catalogo_shopify()
        logger.info("Catálogo Shopify pre-cargado al arrancar ✅")
    except Exception as e:
        logger.warning(f"No se pudo pre-cargar catálogo Shopify al arrancar: {e}")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    logger.info(
        f"Seguimientos: follow-up a los {FOLLOWUP_MIN} min, "
        f"cierre a los {CIERRE_MIN} min después, ventana max {FOLLOWUP_MAX_HORAS} h"
    )
    seguimiento_task = asyncio.create_task(_loop_seguimientos())
    try:
        yield
    finally:
        seguimiento_task.cancel()
        try:
            await seguimiento_task
        except asyncio.CancelledError:
            pass


async def _loop_seguimientos():
    """Cada CHECK_INTERVAL_SEG revisa conversaciones inactivas y manda
    follow-ups, cierres, cross-sell o recuperación de carrito según corresponda."""
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SEG)
            await _procesar_followups()
            await _procesar_cierres()
            await _procesar_crosssell_carrito()
            await _procesar_abandono_carrito()
            await _procesar_abandono_checkout()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error en loop de seguimientos: {e}")


async def _procesar_followups():
    telefonos = await conversaciones_para_followup(FOLLOWUP_MIN, FOLLOWUP_MAX_HORAS)
    for telefono in telefonos:
        try:
            await proveedor.enviar_mensaje(telefono, MENSAJE_FOLLOWUP)
            await guardar_mensaje(telefono, "assistant", MENSAJE_FOLLOWUP)
            await marcar_followup_enviado(telefono)
            logger.info(f"Follow-up enviado a {telefono}")
        except Exception as e:
            logger.error(f"Error enviando follow-up a {telefono}: {e}")


async def _procesar_cierres():
    telefonos = await conversaciones_para_cierre(CIERRE_MIN)
    for telefono in telefonos:
        try:
            await proveedor.enviar_mensaje(telefono, MENSAJE_CIERRE)
            await guardar_mensaje(telefono, "assistant", MENSAJE_CIERRE)
            await marcar_cierre_enviado(telefono)
            logger.info(f"Cierre enviado a {telefono}")
        except Exception as e:
            logger.error(f"Error enviando cierre a {telefono}: {e}")


async def _procesar_crosssell_carrito():
    """
    Detecta carritos con 2-8 minutos de antigüedad cuyo total está bajo $60.000
    y envía un mensaje de venta cruzada por WhatsApp (cooldown 20 min por cliente).
    """
    ahora = time.time()
    clientes = await clientes_para_crosssell(min_min=2, max_min=8)
    for telefono, items in clientes:
        # Respetar cooldown de 20 minutos
        ultimo = _crosssell_cooldown.get(telefono, 0)
        if ahora - ultimo < CROSSSELL_COOLDOWN_SEG:
            continue
        # Calcular total del carrito
        total = sum(p.get("precio_unitario", 0) * p.get("cantidad", 1) for p in items)
        if total <= 0 or total >= ENVIO_GRATIS:
            continue
        # Buscar productos sugeridos que no estén en el carrito
        nombres_en_carrito = {p.get("producto", "").lower() for p in items}
        catalogo = obtener_catalogo_json()
        sugeridos = []
        vistos: set[str] = set()
        for estrella in PRODUCTOS_ESTRELLA:
            if len(sugeridos) >= 3:
                break
            for item in catalogo:
                nombre = item.get("producto", "")
                nombre_lower = nombre.lower()
                if (estrella in nombre_lower
                        and nombre not in vistos
                        and not any(en in nombre_lower for en in nombres_en_carrito)):
                    sugeridos.append(nombre)
                    vistos.add(nombre)
                    break
        if not sugeridos:
            continue
        falta = ENVIO_GRATIS - total
        falta_fmt = f"{int(falta):,}".replace(",", ".")
        lineas_prod = "\n".join(f"✅ {s}" for s in sugeridos)
        msg = (
            f"Te faltan solo ${falta_fmt} para envío gratis 🚚\n\n"
            f"Muchos clientes aprovechan y agregan:\n"
            f"{lineas_prod}\n\n"
            f"¿Te envío el enlace para agregarlos al carrito? 😊"
        )
        try:
            await proveedor.enviar_mensaje(telefono, msg)
            await guardar_mensaje(telefono, "assistant", msg)
            _crosssell_cooldown[telefono] = ahora
            logger.info(f"Cross-sell enviado a {telefono} (falta ${falta_fmt})")
        except Exception as e:
            logger.error(f"Error enviando cross-sell a {telefono}: {e}")


async def _procesar_abandono_carrito():
    """Detecta carritos activos que llevan entre ABANDONO_MIN y ABANDONO_MAX min
    sin finalizar y envía un mensaje de recuperación con botón CTA a la tienda."""
    ahora = time.time()
    clientes = await clientes_con_carrito_abandonado(
        min_inactivo=ABANDONO_MIN_INACTIVO,
        max_inactivo=ABANDONO_MAX_INACTIVO,
    )
    for telefono, _ in clientes:
        # Respetar cooldown: no re-notificar si ya lo hicimos hace menos de 1 hora
        ultimo = _abandono_notif.get(telefono, 0)
        if ahora - ultimo < ABANDONO_COOLDOWN_SEG:
            continue
        try:
            tienda_url = f"{EQUORA_BASE}/catalogo"
            enviado = False
            if hasattr(proveedor, "enviar_cta_url"):
                try:
                    enviado = await proveedor.enviar_cta_url(
                        telefono, MENSAJE_ABANDONO, "Ver productos 🛒", tienda_url
                    )
                except Exception:
                    pass
            if not enviado:
                texto_con_url = f"{MENSAJE_ABANDONO}\n\n👉 {tienda_url}"
                await proveedor.enviar_mensaje(telefono, texto_con_url)
            await guardar_mensaje(telefono, "assistant", MENSAJE_ABANDONO)
            _abandono_notif[telefono] = ahora
            logger.info(f"Recuperación de carrito enviada a {telefono}")
        except Exception as e:
            logger.error(f"Error enviando recuperación de carrito a {telefono}: {e}")


async def _procesar_abandono_checkout():
    """
    Detecta clientes que iniciaron el checkout de Shopify (formulario de pago)
    pero no completaron el pedido. Reenvía el link de checkout para que terminen.
    Shopify limpia pedido_pendiente cuando dispara orders/create o orders/paid.
    """
    import urllib.parse
    ahora = time.time()
    clientes = await clientes_con_checkout_abandonado(
        min_min=CHECKOUT_ABANDONO_MIN,
        max_min=CHECKOUT_ABANDONO_MAX,
    )
    for telefono, checkout_url in clientes:
        ultimo = _checkout_abandono_notif.get(telefono, 0)
        if ahora - ultimo < CHECKOUT_ABANDONO_COOLDOWN_SEG:
            continue
        try:
            enviado = False
            if hasattr(proveedor, "enviar_cta_url"):
                try:
                    enviado = await proveedor.enviar_cta_url(
                        telefono,
                        MENSAJE_CHECKOUT_ABANDONO,
                        "Terminar pedido ✅",
                        checkout_url,
                    )
                except Exception:
                    pass
            if not enviado:
                await proveedor.enviar_mensaje(
                    telefono,
                    f"{MENSAJE_CHECKOUT_ABANDONO}\n\n👉 {checkout_url}"
                )
            await guardar_mensaje(telefono, "assistant", MENSAJE_CHECKOUT_ABANDONO)
            _checkout_abandono_notif[telefono] = ahora
            logger.info(f"Recuperación de checkout enviada a {telefono}")
        except Exception as e:
            logger.error(f"Error enviando recuperación de checkout a {telefono}: {e}")


app = FastAPI(
    title="AgentKit — Andrea (Equora Distribuciones)",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def health_check():
    return {"status": "ok", "agente": "Andrea", "negocio": "Equora Distribuciones"}


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return resultado
    return {"status": "ok"}


def extraer_marcador_botones(respuesta: str) -> tuple[str, dict | None]:
    """Extrae datos del marcador [[BOTONES:...]] y lo elimina del texto."""
    match = re.search(r'\[\[BOTONES:(.*?)\]\]', respuesta, re.DOTALL)
    if not match:
        return respuesta, None
    try:
        datos = json.loads(match.group(1))
    except Exception:
        datos = None
    texto_limpio = re.sub(r'\s*\[\[BOTONES:.*?\]\]', '', respuesta, flags=re.DOTALL).strip()
    return texto_limpio, datos


def extraer_marcador_catalogo_cat(respuesta: str) -> tuple[str, dict | None]:
    """Extrae [[CATALOGO_CAT:{"categoria":"X"}]] — abre catálogo nativo de WhatsApp."""
    match = re.search(r'\[\[CATALOGO_CAT:(.*?)\]\]', respuesta, re.DOTALL)
    if not match:
        return respuesta, None
    try:
        datos = json.loads(match.group(1))
    except Exception:
        datos = None
    texto_limpio = re.sub(r'\s*\[\[CATALOGO_CAT:.*?\]\]', '', respuesta, flags=re.DOTALL).strip()
    return texto_limpio, datos


def extraer_marcador_carrito(respuesta: str) -> tuple[str, list | None]:
    """Extrae [[CARRITO:[...]]] — Andrea lo emite cada vez que el carrito cambia."""
    match = re.search(r'\[\[CARRITO:(\[.*?\])\]\]', respuesta, re.DOTALL)
    if not match:
        return respuesta, None
    try:
        items = json.loads(match.group(1))
    except Exception:
        items = None
    texto_limpio = re.sub(r'\s*\[\[CARRITO:\[.*?\]\]\]', '', respuesta, flags=re.DOTALL).strip()
    return texto_limpio, items


def extraer_marcador_lista(respuesta: str) -> tuple[str, dict | None]:
    """Extrae datos del marcador [[LISTA:...]] y lo elimina del texto."""
    match = re.search(r'\[\[LISTA:(.*?)\]\]', respuesta, re.DOTALL)
    if not match:
        return respuesta, None
    try:
        datos = json.loads(match.group(1))
    except Exception:
        datos = None
    texto_limpio = re.sub(r'\s*\[\[LISTA:.*?\]\]', '', respuesta, flags=re.DOTALL).strip()
    return texto_limpio, datos


EQUORA_BASE = "https://equoradistribuciones.com"

# Mapeo de términos que Andrea escribe en [[TIENDA:término]] → URL de la colección
_COLECCION_MAP: dict[str, str] = {
    # Cocina
    "lavaloza": f"{EQUORA_BASE}/coleccion/cocina",
    "cocina": f"{EQUORA_BASE}/coleccion/cocina",
    # Lavandería
    "detergente": f"{EQUORA_BASE}/coleccion/lavanderia",
    "desmanchador": f"{EQUORA_BASE}/coleccion/lavanderia",
    "lavanderia": f"{EQUORA_BASE}/coleccion/lavanderia",
    "suavizante": f"{EQUORA_BASE}/coleccion/lavanderia",
    # Baños
    "bano": f"{EQUORA_BASE}/coleccion/banos",
    "banos": f"{EQUORA_BASE}/coleccion/banos",
    "desinfectante": f"{EQUORA_BASE}/coleccion/banos",
    # Hogar
    "multiusos": f"{EQUORA_BASE}/coleccion/hogar",
    "limpiavidrios": f"{EQUORA_BASE}/coleccion/hogar",
    "ambientador": f"{EQUORA_BASE}/coleccion/hogar",
    "hogar": f"{EQUORA_BASE}/coleccion/hogar",
    # Talleres / industrial
    "desengrasante": f"{EQUORA_BASE}/coleccion/talleres-e-industrial",
    "taller": f"{EQUORA_BASE}/coleccion/talleres-e-industrial",
    "industrial": f"{EQUORA_BASE}/coleccion/talleres-e-industrial",
    # Higiene personal
    "shampoo": f"{EQUORA_BASE}/coleccion/higiene-personal",
    "higiene": f"{EQUORA_BASE}/coleccion/higiene-personal",
    # Combos
    "combo": f"{EQUORA_BASE}/coleccion/combos",
    "combos": f"{EQUORA_BASE}/coleccion/combos",
    # Más vendidos
    "mas-vendidos": f"{EQUORA_BASE}/coleccion/mas-vendidos",
    "populares": f"{EQUORA_BASE}/coleccion/mas-vendidos",
}


def _construir_url_tienda(query: str) -> str:
    """
    Convierte el término del marcador [[TIENDA:término]] en la URL
    de la colección correspondiente en equoradistribuciones.com.
    Si no hay mapeo exacto, usa /catalogo como fallback.
    """
    if not query:
        return f"{EQUORA_BASE}/catalogo"
    q = query.lower().strip()
    # Buscar coincidencia exacta primero, luego coincidencia parcial
    if q in _COLECCION_MAP:
        return _COLECCION_MAP[q]
    for clave, url in _COLECCION_MAP.items():
        if clave in q or q in clave:
            return url
    return f"{EQUORA_BASE}/catalogo"


def extraer_marcador_tienda(respuesta: str) -> tuple[str, bool, str]:
    """
    Extrae [[TIENDA:]] o [[TIENDA:término]] del texto de Andrea.
    Retorna (texto_limpio, abrir_tienda, query_busqueda).
    Si Andrea escribe [[TIENDA:lavaloza]], la tienda abre con "lavaloza" pre-buscado.
    """
    # Forma con término de búsqueda: [[TIENDA:nombre producto]]
    m = re.search(r'\[\[TIENDA:([^\]]+)\]\]', respuesta)
    if m:
        query = m.group(1).strip()
        texto_limpio = re.sub(r'\s*\[\[TIENDA:[^\]]*\]\]', '', respuesta).strip()
        return texto_limpio, True, query
    # Forma sin término: [[TIENDA:]]
    if '[[TIENDA:]]' in respuesta:
        texto_limpio = re.sub(r'\s*\[\[TIENDA:\]\]', '', respuesta).strip()
        return texto_limpio, True, ''
    return respuesta, False, ''


@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            logger.info(f"Mensaje de {msg.telefono}: {msg.texto[:80]}")

            # ── Orden directa desde catálogo nativo WhatsApp ──────────────────
            # El cliente armó su carrito en WhatsApp y confirmó — bypaseamos Claude
            # y creamos el checkout de Shopify directamente.
            if msg.texto.startswith("__ORDEN_CATALOGO__:"):
                await registrar_mensaje_usuario(msg.telefono)
                try:
                    items_raw = json.loads(msg.texto[len("__ORDEN_CATALOGO__:"):])
                    productos = []
                    no_encontrados = []
                    for item in items_raw:
                        rid = item.get("product_retailer_id", "")
                        qty = int(item.get("quantity", 1))
                        info = obtener_producto_por_retailer_id(rid)
                        if not info:
                            # Catálogo puede no estar cargado aún — recargar y reintentar
                            await obtener_catalogo_shopify()
                            info = obtener_producto_por_retailer_id(rid)
                        if info:
                            precio = info["precio_unitario"]
                            productos.append({
                                "producto": info["producto"],
                                "presentacion": info["presentacion"],
                                "cantidad": qty,
                                "precio_unitario": precio,
                                "subtotal": precio * qty,
                            })
                        else:
                            no_encontrados.append(rid)
                            logger.warning(f"retailer_id no encontrado en _sku_map: {rid}")

                    if no_encontrados:
                        logger.error(f"IDs sin mapear: {no_encontrados}. SKUs en Shopify necesarios.")

                    if productos:
                        total = sum(p["subtotal"] for p in productos)
                        datos_pedido = {"productos": productos, "total": total}
                        checkout_url = await crear_checkout_shopify(msg.telefono, datos_pedido)
                        if checkout_url:
                            await guardar_pedido_pendiente(msg.telefono, productos)
                            await limpiar_carrito_activo(msg.telefono)
                            texto_checkout = (
                                "🎉 *¡Pedido recibido!*\n\n"
                                "Toca el botón para confirmar tu dirección de entrega. "
                                "El pago es *contra entrega*. 🌿"
                            )
                            if hasattr(proveedor, "enviar_cta_url"):
                                await proveedor.enviar_cta_url(
                                    msg.telefono, texto_checkout,
                                    "Confirmar entrega", checkout_url
                                )
                            else:
                                await proveedor.enviar_mensaje(
                                    msg.telefono, f"{texto_checkout}\n\n👉 {checkout_url}"
                                )
                        else:
                            await proveedor.enviar_mensaje(
                                msg.telefono,
                                "😔 No pude procesar tu pedido. Algunos productos "
                                "pueden haberse agotado. ¿Quieres que lo revisemos juntos?"
                            )
                    else:
                        await proveedor.enviar_mensaje(
                            msg.telefono,
                            "😔 No reconocí los productos de tu pedido. "
                            "¿Puedes escribirme qué quieres y te ayudo?"
                        )
                except Exception as e:
                    logger.error(f"Error procesando orden catálogo: {e}")
                    await proveedor.enviar_mensaje(
                        msg.telefono,
                        "😔 Tuve un problema procesando tu pedido. "
                        "¿Me puedes decir qué quieres y te ayudo enseguida?"
                    )
                continue  # No pasa por Claude

            # Cliente respondió → resetea timers de seguimiento
            await registrar_mensaje_usuario(msg.telefono)

            # Modo humano: guardar mensaje pero no responder con Andrea
            if await get_modo_humano(msg.telefono):
                await guardar_mensaje(msg.telefono, "user", msg.texto)
                logger.info(f"Modo humano activo — {msg.telefono} — Andrea no responde")
                continue

            historial = await obtener_historial(msg.telefono)
            respuesta = await generar_respuesta(msg.texto, historial, msg.telefono)

            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)
            await registrar_mensaje_asistente(msg.telefono)

            # Procesar marcador de carrito → persistir estado en BD
            respuesta, items_carrito = extraer_marcador_carrito(respuesta)
            if items_carrito is not None:
                try:
                    await guardar_carrito_activo(msg.telefono, items_carrito)
                    logger.info(f"Carrito actualizado para {msg.telefono}: {len(items_carrito)} items")
                except Exception as e:
                    logger.error(f"Error guardando carrito: {e}")

            # Procesar marcador de pedido → crear checkout en Shopify
            checkout_url = None
            checkout_fallo = False
            match_pedido = re.search(r'\[\[PEDIDO:(.*?)\]\]', respuesta, re.DOTALL)
            if match_pedido:
                try:
                    datos_pedido = json.loads(match_pedido.group(1))
                    checkout_url = await crear_checkout_shopify(msg.telefono, datos_pedido)
                    if checkout_url:
                        await guardar_cliente(msg.telefono, datos_pedido)
                        # Guardamos el carrito como pendiente: lo limpia el webhook de Shopify
                        await guardar_pedido_pendiente(
                            msg.telefono, datos_pedido.get("productos", [])
                        )
                        # El carrito activo se vacía: el pedido ya fue generado
                        await limpiar_carrito_activo(msg.telefono)
                        logger.info(f"Checkout Shopify creado para {msg.telefono}")
                    else:
                        checkout_fallo = True
                        logger.error(f"No se pudo crear checkout Shopify para {msg.telefono}")
                except Exception as e:
                    checkout_fallo = True
                    logger.error(f"Error procesando pedido: {e}")
                respuesta = re.sub(r'\s*\[\[PEDIDO:.*?\]\]', '', respuesta, flags=re.DOTALL).strip()

            # Procesar marcador de escalación → notificar al equipo
            datos_escalacion = None
            match_escalar = re.search(r'\[\[ESCALAR:(.*?)\]\]', respuesta, re.DOTALL)
            if match_escalar:
                try:
                    datos_escalacion = json.loads(match_escalar.group(1))
                except Exception as e:
                    logger.error(f"Marcador ESCALAR inválido: {e}")
                respuesta = re.sub(r'\s*\[\[ESCALAR:.*?\]\]', '', respuesta, flags=re.DOTALL).strip()

            # Extraer marcadores interactivos ANTES de enviar el texto
            respuesta, datos_catalogo_cat = extraer_marcador_catalogo_cat(respuesta)
            respuesta, datos_botones = extraer_marcador_botones(respuesta)
            respuesta, datos_lista = extraer_marcador_lista(respuesta)
            respuesta, abrir_tienda, tienda_query = extraer_marcador_tienda(respuesta)

            # Enviar texto primero
            if respuesta:
                await proveedor.enviar_mensaje(msg.telefono, respuesta)

            # Catálogo nativo WhatsApp (product_list con fotos reales)
            if datos_catalogo_cat and hasattr(proveedor, "enviar_catalogo_productos"):
                categoria = datos_catalogo_cat.get("categoria")
                secciones = obtener_secciones_catalogo(categoria)
                cat_enviado = False
                if secciones:
                    header = categoria or "Catálogo Biotú 🌿"
                    cuerpo = "Selecciona los productos que quieres, ajusta las cantidades y confirma tu pedido."
                    cat_enviado = await proveedor.enviar_catalogo_productos(
                        msg.telefono, header, cuerpo, secciones
                    )
                    if cat_enviado:
                        logger.info(f"Catálogo nativo '{categoria}' enviado a {msg.telefono}")
                    else:
                        logger.warning(f"Catálogo nativo falló para {msg.telefono} — usando fallback texto")

                # Fallback: si el catálogo nativo falla (IDs no mapeados, error Meta, etc.)
                # mostramos los productos como lista interactiva de texto
                if not cat_enviado:
                    from agent.tools import _categorias_cache, ORDEN_CATEGORIAS
                    cats = {categoria: _categorias_cache[categoria]} if (
                        categoria and categoria in _categorias_cache
                    ) else {c: _categorias_cache[c] for c in ORDEN_CATEGORIAS if c in _categorias_cache}
                    lineas = []
                    for cat_name, productos_cat in cats.items():
                        lineas.append(f"*{cat_name}*")
                        for prod_title, variantes, _img in productos_cat:
                            precio_min = min(int(float(v["price"]["amount"])) for v in variantes)
                            lineas.append(f"  • {prod_title} — desde ${precio_min:,}")
                        lineas.append("")
                    if lineas:
                        await proveedor.enviar_mensaje(msg.telefono, "\n".join(lineas).strip())

            # Luego enviar mensajes interactivos
            if datos_botones and hasattr(proveedor, "enviar_botones"):
                try:
                    await proveedor.enviar_botones(
                        msg.telefono,
                        datos_botones.get("texto", ""),
                        datos_botones.get("botones", [])
                    )
                    logger.info(f"Botones enviados a {msg.telefono}")
                except Exception as e:
                    logger.error(f"Error enviando botones: {e}")

            if datos_lista and hasattr(proveedor, "enviar_lista"):
                lista_enviada = False
                try:
                    lista_enviada = await proveedor.enviar_lista(
                        msg.telefono,
                        datos_lista.get("texto", ""),
                        datos_lista.get("boton", "Ver opciones"),
                        datos_lista.get("secciones", [])
                    )
                    if lista_enviada:
                        logger.info(f"Lista enviada a {msg.telefono}")
                except Exception as e:
                    logger.error(f"Error enviando lista: {e}")
                # Fallback: si la lista interactiva falla (límites de Meta,
                # demasiados items, etc.) enviamos los productos como texto
                if not lista_enviada:
                    lineas = [datos_lista.get("texto", "")]
                    for sec in datos_lista.get("secciones", []):
                        titulo = sec.get("titulo", "")
                        if titulo:
                            lineas.append(f"\n*{titulo}*")
                        for item in sec.get("items", []):
                            t = item.get("titulo", "")
                            d = item.get("descripcion", "")
                            if t and d:
                                lineas.append(f"• *{t}* — {d}")
                            elif t:
                                lineas.append(f"• {t}")
                    fallback_text = "\n".join(l for l in lineas if l)
                    if fallback_text.strip():
                        await proveedor.enviar_mensaje(msg.telefono, fallback_text[:4000])
                        logger.info(f"Fallback texto de lista enviado a {msg.telefono}")

            # Enviar link de la tienda web si Andrea lo solicitó
            if abrir_tienda:
                import urllib.parse
                tienda_url = _construir_url_tienda(tienda_query)
                # Añadir teléfono para que Lovable pueda reportar el carrito de vuelta
                tienda_url += f"?tel={urllib.parse.quote(msg.telefono)}"
                if tienda_query:
                    texto_tienda = (
                        "🛒 *Aquí puedes ver el producto, elegir tu presentación y hacer tu pedido fácilmente:*"
                    )
                    boton_label = "Ver producto 🌿"
                else:
                    texto_tienda = (
                        "🛒 *Aquí puedes ver todos nuestros productos con fotos, "
                        "elegir cantidades y hacer tu pedido fácilmente:*"
                    )
                    boton_label = "Ver catálogo 🌿"
                enviado_tienda = False
                if hasattr(proveedor, "enviar_cta_url"):
                    try:
                        enviado_tienda = await proveedor.enviar_cta_url(
                            msg.telefono, texto_tienda, boton_label, tienda_url
                        )
                    except Exception as e:
                        logger.error(f"Error enviando link tienda: {e}")
                if not enviado_tienda:
                    await proveedor.enviar_mensaje(
                        msg.telefono, f"{texto_tienda}\n\n👉 {tienda_url}"
                    )
                logger.info(f"Link tienda enviado a {msg.telefono}: {tienda_url}")

            # Enviar link de checkout de Shopify si se generó
            if checkout_url:
                texto_checkout = (
                    "🧾 *Tu pedido está listo*\n\n"
                    "Toca el botón para confirmar tu dirección de entrega. "
                    "El pago se realiza *contra entrega*. En cuanto registres tus datos, "
                    "te confirmo aquí mismo el número de tu pedido. 🌿"
                )
                enviado_cta = False
                if hasattr(proveedor, "enviar_cta_url"):
                    try:
                        enviado_cta = await proveedor.enviar_cta_url(
                            msg.telefono, texto_checkout, "Confirmar entrega", checkout_url
                        )
                    except Exception as e:
                        logger.error(f"Error enviando cta_url: {e}")
                if not enviado_cta:
                    await proveedor.enviar_mensaje(
                        msg.telefono, f"{texto_checkout}\n\n👉 {checkout_url}"
                    )

            # Si la creación del checkout falló (stock agotado, producto no
            # mapeado, etc.) avísale al cliente en vez de quedarnos mudos
            if checkout_fallo:
                await proveedor.enviar_mensaje(
                    msg.telefono,
                    "😔 Disculpa, no pude generar tu pedido en este momento. "
                    "Es posible que algún producto del carrito se haya agotado "
                    "mientras conversábamos. ¿Quieres que revisemos juntos qué "
                    "hay disponible ahora?"
                )

            # Notificar al equipo si Andrea decidió escalar
            if datos_escalacion:
                await _notificar_escalacion(msg.telefono, datos_escalacion)

            logger.info(f"Respuesta a {msg.telefono}: {respuesta}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
#  INTEGRACIÓN LOVABLE — recibe estado del carrito desde equoradistribuciones.com
# ═══════════════════════════════════════════════════════════════

@app.post("/shopify/cart-update")
async def shopify_cart_update(request: Request):
    """
    La página de Lovable (equoradistribuciones.com) llama este endpoint
    cada vez que el carrito cambia (debounced 8 s en el cliente).
    Guarda el estado en BD para que el loop de seguimientos pueda:
      - Detectar carritos abandonados y enviar recuperación por WhatsApp
      - Disparar cross-sell si el total está bajo $80.000
    Payload esperado:
      { "telefono": "573001234567", "productos": [ { "producto": "...",
        "presentacion": "...", "cantidad": N, "precio_unitario": X } ] }
    """
    try:
        body = await request.json()
        telefono = (body.get("telefono") or "").strip()
        productos = body.get("productos") or []

        if not telefono:
            # Sin teléfono no podemos asociar a una conversación — ignoramos silenciosamente
            return JSONResponse(content={"ok": True})

        if productos:
            items_para_bd = []
            for p in productos:
                precio = int(float(p.get("precio_unitario") or p.get("precio") or 0))
                qty = int(p.get("cantidad") or p.get("qty") or 1)
                items_para_bd.append({
                    "producto":      p.get("producto", ""),
                    "presentacion":  p.get("presentacion", ""),
                    "cantidad":      qty,
                    "precio_unitario": precio,
                    "subtotal":      precio * qty,
                })
            await guardar_carrito_activo(telefono, items_para_bd)
            logger.debug(
                f"[cart-update] Carrito guardado para {telefono}: "
                f"{len(productos)} productos"
            )
        else:
            # Carrito vacío → limpiar
            await limpiar_carrito_activo(telefono)
            logger.debug(f"[cart-update] Carrito limpiado para {telefono}")

        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Error en /shopify/cart-update: {e}")
        return JSONResponse(content={"ok": True})  # siempre 200 para no bloquear al cliente




# ═══════════════════════════════════════════════════════════════
#  INBOX — Panel de administración
# ═══════════════════════════════════════════════════════════════

INBOX_COOKIE = "inbox_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 días


def _verificar_admin(token: str) -> bool:
    """Valida el token de administrador."""
    if not ADMIN_TOKEN:
        return False
    return hmac.compare_digest(token or "", ADMIN_TOKEN)


def _token_de_request(
    token: str = "",
    inbox_session: str = Cookie(default=""),
) -> str:
    """Extrae el token de la cookie o del query param."""
    return inbox_session or token


# ── Login / Logout ─────────────────────────────────────────────────────────

@app.get("/inbox/login", response_class=HTMLResponse)
async def inbox_login_page():
    return HTMLResponse(content=obtener_login_html())


@app.post("/inbox/login")
async def inbox_login(request: Request):
    form = await request.form()
    password = str(form.get("password", ""))
    if _verificar_admin(password):
        response = RedirectResponse("/inbox", status_code=302)
        response.set_cookie(
            INBOX_COOKIE, ADMIN_TOKEN,
            httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax"
        )
        return response
    return HTMLResponse(content=obtener_login_html(error=True))


@app.get("/inbox/logout")
async def inbox_logout():
    response = RedirectResponse("/inbox/login", status_code=302)
    response.delete_cookie(INBOX_COOKIE)
    return response


# ── Panel principal ────────────────────────────────────────────────────────

@app.get("/inbox", response_class=HTMLResponse)
async def inbox_panel(
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    if not _verificar_admin(inbox_session or token):
        return RedirectResponse("/inbox/login", status_code=302)
    response = HTMLResponse(content=obtener_inbox_html())
    # Si llegó por query param, guardar en cookie
    if token and _verificar_admin(token):
        response.set_cookie(
            INBOX_COOKIE, ADMIN_TOKEN,
            httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax"
        )
    return response


# ── API endpoints ──────────────────────────────────────────────────────────

@app.get("/inbox/api/conversaciones")
async def inbox_conversaciones(
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    convs = await obtener_todas_conversaciones()
    return JSONResponse(content=convs)


@app.get("/inbox/api/mensajes/{telefono}")
async def inbox_mensajes(
    telefono: str,
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    mensajes = await obtener_historial_con_timestamps(telefono, 150)
    modo = await get_modo_humano(telefono)
    return JSONResponse(content={"mensajes": mensajes, "modo_humano": modo})


@app.post("/inbox/api/responder")
async def inbox_responder(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    telefono = (body.get("telefono") or "").strip()
    mensaje = (body.get("mensaje") or "").strip()
    if not telefono or not mensaje:
        return JSONResponse(status_code=400, content={"error": "Faltan datos"})
    try:
        await proveedor.enviar_mensaje(telefono, mensaje)
        await guardar_mensaje(telefono, "assistant", mensaje)
        await registrar_mensaje_asistente(telefono)
        logger.info(f"Mensaje manual enviado a {telefono} desde inbox")
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Error enviando desde inbox a {telefono}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/inbox/api/modo/{telefono}")
async def inbox_modo(
    telefono: str,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    activo = bool(body.get("activo", False))
    await set_modo_humano(telefono, activo)
    logger.info(f"Modo cambiado a '{'humano' if activo else 'Andrea'}' para {telefono}")
    return JSONResponse(content={"ok": True, "modo_humano": activo})


SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
# Cache de deduplicación: evita procesar el mismo webhook de Shopify más de una vez
# Shopify reintenta hasta 19 veces si no recibe 200 — guardamos los procesados por 10 min
_shopify_dedup: dict[str, float] = {}
_SHOPIFY_DEDUP_TTL = 600  # segundos

ADMIN_WHATSAPP_NUMBERS = [
    n.strip() for n in os.getenv("ADMIN_WHATSAPP_NUMBERS", "").split(",") if n.strip()
]


async def _notificar_escalacion(telefono_cliente: str, datos: dict):
    """Envía un mensaje a los administradores con el contexto de la escalación."""
    if not ADMIN_WHATSAPP_NUMBERS:
        logger.warning("ADMIN_WHATSAPP_NUMBERS no configurado — escalación no se notifica")
        return

    motivo = datos.get("motivo", "sin especificar")
    contexto = datos.get("contexto", "")
    urgencia = datos.get("urgencia", "normal")
    cliente_nombre = datos.get("nombre_cliente", "")

    mensaje = (
        f"🚨 *Escalación Andrea Bot*\n\n"
        f"*Motivo:* {motivo}\n"
        f"*Urgencia:* {urgencia}\n"
        f"*Cliente:* {cliente_nombre or 'desconocido'}\n"
        f"*WhatsApp cliente:* +{telefono_cliente}\n\n"
        f"*Contexto:*\n{contexto}\n\n"
        f"Responde al cliente desde el WhatsApp Business o llámalo directamente."
    )

    for admin in ADMIN_WHATSAPP_NUMBERS:
        try:
            await proveedor.enviar_mensaje(admin, mensaje)
            logger.info(f"Escalación notificada a admin {admin}")
        except Exception as e:
            logger.error(f"Error notificando escalación a {admin}: {e}")


def _verificar_hmac_shopify(body: bytes, hmac_header: str) -> bool:
    if not SHOPIFY_WEBHOOK_SECRET:
        # Sin secret configurado, dejamos pasar (útil para pruebas iniciales)
        logger.warning("SHOPIFY_WEBHOOK_SECRET no configurado — saltando verificación HMAC")
        return True
    digest = base64.b64encode(
        hmac.new(SHOPIFY_WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(digest, hmac_header or "")


def _normalizar_telefono(valor: str | None) -> str | None:
    """Quita +, espacios, guiones — deja solo dígitos."""
    if not valor:
        return None
    digitos = re.sub(r"\D", "", str(valor))
    return digitos or None


def _extraer_telefono(payload: dict) -> str | None:
    for attr in payload.get("note_attributes", []) or []:
        if attr.get("name") in ("Telefono WhatsApp", "Telefono", "phone"):
            tel = _normalizar_telefono(attr.get("value"))
            if tel:
                return tel
    cliente = payload.get("customer") or {}
    for valor in (cliente.get("phone"), payload.get("phone"),
                  (payload.get("shipping_address") or {}).get("phone"),
                  (payload.get("billing_address") or {}).get("phone")):
        tel = _normalizar_telefono(valor)
        if tel:
            return tel
    return None


def _extraer_datos_cliente(payload: dict) -> dict:
    """Construye el dict de cliente desde la orden Shopify."""
    cliente = payload.get("customer") or {}
    envio = payload.get("shipping_address") or payload.get("billing_address") or {}
    return {
        "nombres": cliente.get("first_name") or envio.get("first_name") or "",
        "apellidos": cliente.get("last_name") or envio.get("last_name") or "",
        "email": cliente.get("email") or payload.get("email") or "",
        "direccion": envio.get("address1") or "",
        "barrio": envio.get("address2") or "",
        "ciudad": envio.get("city") or "",
        "departamento": envio.get("province") or "",
        "razon_social": envio.get("company") or "",
    }


@app.post("/shopify-webhook")
async def shopify_webhook(request: Request):
    """Recibe eventos de Shopify (orders/paid, orders/create) y notifica al cliente."""
    body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
    topic = request.headers.get("X-Shopify-Topic", "")

    if not _verificar_hmac_shopify(body, hmac_header):
        logger.error(f"HMAC inválido en shopify-webhook (topic={topic})")
        raise HTTPException(status_code=401, detail="Invalid HMAC")

    try:
        payload = json.loads(body)
    except Exception as e:
        logger.error(f"Payload Shopify inválido: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    numero = payload.get("order_number") or payload.get("name", "").lstrip("#")
    nombre_orden = payload.get("name") or (f"#{numero}" if numero else "")
    telefono = _extraer_telefono(payload)
    total = payload.get("total_price") or payload.get("current_total_price") or "0"

    logger.info(f"Shopify webhook {topic} — orden {nombre_orden}, tel {telefono}")

    # ── Deduplicación: ignorar reintentos de Shopify ──────────────────────────
    ahora_ts = time.time()
    # Limpiar entradas expiradas
    expiradas = [k for k, v in _shopify_dedup.items() if ahora_ts - v > _SHOPIFY_DEDUP_TTL]
    for k in expiradas:
        del _shopify_dedup[k]
    dedup_key = f"{numero}_{topic}"
    if dedup_key in _shopify_dedup:
        logger.warning(f"Webhook duplicado ignorado: {dedup_key}")
        return {"status": "ok"}
    _shopify_dedup[dedup_key] = ahora_ts
    # ─────────────────────────────────────────────────────────────────────────

    if not telefono or not numero:
        logger.warning(f"Sin teléfono o número de orden — no se notifica (telefono={telefono}, numero={numero})")
        return {"status": "ok"}

    try:
        total_int = int(float(total))
    except Exception:
        total_int = 0

    # Guardar/actualizar cliente con los datos que llegaron en la orden
    datos_cliente = _extraer_datos_cliente(payload)
    if any(datos_cliente.values()):
        try:
            await guardar_cliente(telefono, datos_cliente)
            logger.info(f"Cliente {telefono} guardado/actualizado desde Shopify")
        except Exception as e:
            logger.error(f"Error guardando cliente desde webhook: {e}")

    # ── checkouts/create: cliente abrió el formulario de Shopify ──────────────
    # Guardamos la checkout_url para poder reenviarla si no termina el proceso.
    # La URL del checkout viene en el campo "checkout_url" o se construye desde el token.
    if topic == "checkouts/create":
        checkout_url = (
            payload.get("checkout_url")
            or payload.get("web_url")
            or ""
        )
        if not checkout_url:
            # Fallback: construir desde el token si viene
            token = payload.get("token") or ""
            if token:
                checkout_url = f"https://equoradistribuciones.com/checkouts/{token}"
        if telefono and checkout_url:
            try:
                # Guardar carrito activo como pedido pendiente para abandono detection
                line_items = payload.get("line_items") or []
                if line_items:
                    productos = [
                        {
                            "producto": item.get("title", ""),
                            "presentacion": item.get("variant_title") or item.get("title", ""),
                            "cantidad": int(item.get("quantity", 1)),
                            "precio_unitario": int(float(item.get("price", 0))),
                            "subtotal": int(float(item.get("price", 0))) * int(item.get("quantity", 1)),
                        }
                        for item in line_items
                    ]
                    await guardar_pedido_pendiente(telefono, productos)
                await guardar_checkout_url(telefono, checkout_url)
                await limpiar_carrito_activo(telefono)
                logger.info(f"Checkout creado para {telefono}: {checkout_url}")
            except Exception as e:
                logger.error(f"Error guardando checkout create para {telefono}: {e}")
        return {"status": "ok"}

    # Cliente completó el checkout → ya no hay carrito pendiente
    if topic in ("orders/create", "orders/paid"):
        try:
            await limpiar_pedido_pendiente(telefono)
        except Exception as e:
            logger.error(f"Error limpiando pedido pendiente: {e}")

    if topic == "orders/fulfilled":
        # Shopify fulfillment puede traer tracking — si está, lo incluimos
        fulfillments = payload.get("fulfillments") or []
        tracking_num = ""
        tracking_url = ""
        if fulfillments:
            f0 = fulfillments[0]
            tracking_num = f0.get("tracking_number") or ""
            tracking_url = f0.get("tracking_url") or ""

        extra_tracking = ""
        if tracking_num:
            extra_tracking = f"\n📦 Guía: *{tracking_num}*"
        if tracking_url:
            extra_tracking += f"\n🔗 Seguimiento: {tracking_url}"

        mensaje = (
            f"🚚 *¡Tu pedido está listo y va en camino!*\n\n"
            f"Pedido *{nombre_orden}* preparado y despachado.{extra_tracking}\n\n"
            f"Recuerda tener los *${total_int:,}* listos para el pago contra entrega. "
            f"¡Gracias por confiar en Equora! 🌿"
        )
    elif topic == "orders/paid":
        mensaje = (
            f"💰 *¡Pago registrado!*\n\n"
            f"Pedido: *{nombre_orden}*  ·  Total: *${total_int:,}*\n\n"
            f"Pronto sale en camino. ¡Gracias por confiar en Equora! 🌿"
        )
    else:
        mensaje = (
            f"✅ *¡Pedido confirmado!*\n\n"
            f"🧾 Número de pedido: *{nombre_orden}*\n"
            f"💰 Total: *${total_int:,}*  (pago contra entrega)\n\n"
            f"Ya estamos preparando tu pedido. Te avisamos cuando vaya en camino. "
            f"¡Gracias por confiar en Equora! 🌿"
        )

    try:
        await proveedor.enviar_mensaje(telefono, mensaje)
        # Guardar en BD para que aparezca en el inbox
        await guardar_mensaje(telefono, "assistant", mensaje)
        # Suprimir follow-up y cierre: esta es una notificación automática,
        # no un mensaje conversacional — no debe activar los timers de seguimiento
        await marcar_followup_enviado(telefono)
        await marcar_cierre_enviado(telefono)
        logger.info(f"Confirmación {topic} enviada a {telefono} ({nombre_orden})")
    except Exception as e:
        logger.error(f"Error enviando confirmación a {telefono}: {e}")

    return {"status": "ok"}
