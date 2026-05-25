import os
import re
import json
import hmac
import hashlib
import base64
import logging
import asyncio
import random
import time
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Cookie, UploadFile, File, Form
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import (
    inicializar_db, guardar_mensaje, obtener_historial,
    guardar_cliente, guardar_pedido_pendiente, limpiar_pedido_pendiente,
    guardar_carrito_activo, limpiar_carrito_activo, obtener_carrito_activo,
    registrar_mensaje_usuario, registrar_mensaje_asistente,
    marcar_followup_enviado, marcar_cierre_enviado,
    conversaciones_para_followup, conversaciones_para_cierre,
    clientes_con_carrito_abandonado,
    guardar_checkout_url, clientes_con_checkout_abandonado,
    verificar_cierre_enviado,
    get_modo_humano, set_modo_humano,
    obtener_todas_conversaciones, obtener_historial_con_timestamps,
    registrar_difusion, obtener_difusiones,
    guardar_borrador_plantilla, obtener_borradores_plantillas, eliminar_borrador_plantilla,
)
from agent.inbox import obtener_inbox_html, obtener_login_html
from agent.providers import obtener_proveedor
from agent.capi import capi_lead, capi_view_content, capi_add_to_cart, capi_initiate_checkout
from agent.tools import (
    crear_checkout_shopify,
    obtener_catalogo_shopify,
    obtener_catalogo_json,
    obtener_secciones_catalogo,
    obtener_producto_por_retailer_id,
    obtener_url_producto,
    cargar_tarifas_envio,
    obtener_costo_envio,
    obtener_umbral_envio_gratis,
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

# Monto mínimo de pedido configurado en la tienda Lovable
PEDIDO_MINIMO = int(os.getenv("PEDIDO_MINIMO", 50000))

# ── Tiempos de seguimiento — todos configurables desde Railway ───────────────
# Estado 6: follow-up genérico (sin carrito, sin checkout)
FOLLOWUP_MIN         = int(os.getenv("FOLLOWUP_MIN", 10))         # min inactivo → primer mensaje
CIERRE_MIN           = int(os.getenv("CIERRE_MIN", 5))            # min tras follow-up → cierre
FOLLOWUP_MAX_HORAS   = int(os.getenv("FOLLOWUP_MAX_HORAS", 12))   # ventana máxima

# Estado 3: carrito bajo el pedido mínimo ($50K)
CARRITO_MIN_MIN      = int(os.getenv("CARRITO_MIN_MIN", 15))      # min antes del aviso de pedido mínimo
# Estados 4-5: cross-sell (entre $50K y $80K) y carrito listo (≥$80K)
CROSSSELL_MIN_MIN    = int(os.getenv("CROSSSELL_MIN_MIN", 15))    # min antes del aviso de cross-sell/listo
# Compartidos por estados 3-5
CARRITO_MAX_MIN      = int(os.getenv("CARRITO_MAX_MIN", 120))     # min máximo de ventana
CARRITO_COOLDOWN_MIN = int(os.getenv("CARRITO_COOLDOWN_MIN", 120))# min entre avisos al mismo cliente
CARRITO_UNIF_COOLDOWN_SEG = CARRITO_COOLDOWN_MIN * 60

# Estado 2: checkout abandonado (cliente llegó a Shopify pero no terminó)
CHECKOUT_ABANDONO_MIN      = int(os.getenv("CHECKOUT_ABANDONO_MIN", 20))   # min antes del aviso
CHECKOUT_ABANDONO_MAX      = int(os.getenv("CHECKOUT_ABANDONO_MAX", 120))  # ventana máxima
CHECKOUT_COOLDOWN_MIN      = int(os.getenv("CHECKOUT_COOLDOWN_MIN", 120))  # min entre avisos
CHECKOUT_ABANDONO_COOLDOWN_SEG = CHECKOUT_COOLDOWN_MIN * 60

# Loop general
CHECK_INTERVAL_SEG   = int(os.getenv("CHECK_INTERVAL_SEG", 30))   # segundos entre cada ciclo del loop

# Legacy (no usados activamente, se conservan por compatibilidad)
ABANDONO_MIN_INACTIVO = CARRITO_MIN_MIN
ABANDONO_MAX_INACTIVO = CARRITO_MAX_MIN
_abandono_notif: dict[str, float] = {}
ABANDONO_COOLDOWN_SEG = CARRITO_UNIF_COOLDOWN_SEG
_carrito_unif_cooldown: dict[str, float] = {}
_carrito_ultimo_estado: dict[str, int] = {}   # phone → último estado enviado (3, 4 ó 5)
_checkout_abandono_notif: dict[str, float] = {}

MENSAJE_FOLLOWUP = (
    "Hola de nuevo 😊 Veo que andas un poco ocupado/a. "
    "¿Sigues por aquí o prefieres que continuemos en otro momento? "
    "No hay afán, retomamos cuando puedas."
)

MENSAJE_CIERRE = (
    "Te dejo descansar 🤗 Cuando quieras retomar, escríbeme y "
    "seguimos donde nos quedamos. ¡Que tengas un excelente día! 🌿"
)

MENSAJE_CHECKOUT_ABANDONO = (
    "Hola 👋 Vimos que iniciaste tu pedido pero no terminaste el proceso.\n\n"
    "Tu carrito está guardado — solo falta confirmar y listo 🎉\n"
    "Recuerda: *pago contraentrega*, no pagas nada online."
)

# ── Cross-selling desde mini-tienda ─────────────────────────────────────────
# Las tarifas se cargan desde Shopify Admin API al arrancar (lifespan).
# Acceder siempre via obtener_umbral_envio_gratis() y obtener_costo_envio()
# para que reflejen el valor actual (puede venir de Shopify o de env vars).
# In-memory: phone → timestamp del último cross-sell enviado (cooldown 20 min)
# _crosssell_cooldown reemplazado por _carrito_unif_cooldown (ver más abajo)
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
    try:
        costo, gratis = await cargar_tarifas_envio()
        logger.info(f"Tarifas de envío: costo=${costo:,} / gratis desde=${gratis:,} ✅")
    except Exception as e:
        logger.warning(f"No se pudieron cargar tarifas de envío: {e}")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    logger.info(
        f"Tiempos de seguimiento — "
        f"follow-up: {FOLLOWUP_MIN} min | cierre: {CIERRE_MIN} min | "
        f"carrito mínimo: {CARRITO_MIN_MIN} min | cross-sell/listo: {CROSSSELL_MIN_MIN} min | ventana max: {CARRITO_MAX_MIN} min (cooldown {CARRITO_COOLDOWN_MIN} min) | "
        f"checkout: {CHECKOUT_ABANDONO_MIN}-{CHECKOUT_ABANDONO_MAX} min (cooldown {CHECKOUT_COOLDOWN_MIN} min) | "
        f"loop cada: {CHECK_INTERVAL_SEG} seg"
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
    """Cada CHECK_INTERVAL_SEG revisa conversaciones inactivas.
    Prioridad: cierre > checkout abandonado > carrito (estados 3-5) > follow-up genérico."""
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SEG)
            await _procesar_abandono_checkout()     # prioridad 2: checkout sin completar
            await _procesar_carrito_unificado()     # prioridad 3-5: carrito activo
            await _procesar_followups()             # prioridad 6: sin carrito, sin checkout
            await _procesar_cierres()               # cierre tras follow-up genérico
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error en loop de seguimientos: {e}")


def _calcular_total_carrito(items: list[dict]) -> int:
    """Calcula el total del carrito usando subtotal o precio_unitario × cantidad."""
    total = 0
    for p in items:
        subtotal = p.get("subtotal", 0)
        if subtotal:
            total += int(subtotal)
        else:
            total += int(p.get("precio_unitario", 0)) * int(p.get("cantidad", 1))
    return total


def _sugerir_productos(nombres_en_carrito: set[str], max_items: int = 3) -> list[str]:
    """Devuelve hasta max_items productos aleatorios que no estén en el carrito.
    Las categorías y los productos dentro de cada categoría se mezclan en cada llamada
    para evitar sugerir siempre los mismos artículos."""
    catalogo = obtener_catalogo_json()
    sugeridos: list[str] = []
    vistos: set[str] = set()
    # Mezclar categorías para variar el orden en cada mensaje
    categorias = random.sample(PRODUCTOS_ESTRELLA, len(PRODUCTOS_ESTRELLA))
    for estrella in categorias:
        if len(sugeridos) >= max_items:
            break
        # Mezclar el catálogo para no elegir siempre la misma variante
        items_mezclados = random.sample(catalogo, len(catalogo))
        for item in items_mezclados:
            nombre = item.get("producto", "")
            nombre_lower = nombre.lower()
            if (estrella in nombre_lower
                    and nombre not in vistos
                    and not any(en in nombre_lower for en in nombres_en_carrito)):
                sugeridos.append(nombre)
                vistos.add(nombre)
                break
    return sugeridos


async def _procesar_carrito_unificado():
    """
    Maneja estados 3, 4 y 5 con UN solo mensaje por cliente según su total de carrito:
      Estado 3: total < PEDIDO_MINIMO  → empuja a llegar al mínimo       (CARRITO_MIN_MIN)
      Estado 4: PEDIDO_MINIMO ≤ total < ENVIO_GRATIS → cross-sell gratis  (CROSSSELL_MIN_MIN)
      Estado 5: total ≥ ENVIO_GRATIS  → recuerda confirmar                (CROSSSELL_MIN_MIN)
    Cada estado tiene su propia ventana de tiempo configurable.
    Cooldown compartido: CARRITO_COOLDOWN_MIN por cliente.
    """
    ahora = time.time()
    umbral_gratis = obtener_umbral_envio_gratis()
    minimo_fmt = f"{PEDIDO_MINIMO:,}".replace(",", ".")
    gratis_fmt = f"{umbral_gratis:,}".replace(",", ".")

    # Dos queries con tiempos distintos: estado 3 vs estados 4-5
    clientes_min   = await clientes_con_carrito_abandonado(min_inactivo=CARRITO_MIN_MIN,   max_inactivo=CARRITO_MAX_MIN)
    clientes_cross = await clientes_con_carrito_abandonado(min_inactivo=CROSSSELL_MIN_MIN, max_inactivo=CARRITO_MAX_MIN)

    # Unificar: estado 3 usa clientes_min, estados 4-5 usan clientes_cross
    # Construir dict telefono→items para cada grupo
    map_min   = {t: i for t, i in clientes_min}
    map_cross = {t: i for t, i in clientes_cross}

    # Todos los teléfonos candidatos (sin duplicados)
    todos = set(map_min) | set(map_cross)

    if todos:
        logger.info(
            f"[carrito-loop] {len(todos)} candidatos — "
            f"map_min={len(map_min)} ({CARRITO_MIN_MIN}-{CARRITO_MAX_MIN} min) | "
            f"map_cross={len(map_cross)} ({CROSSSELL_MIN_MIN}-{CARRITO_MAX_MIN} min)"
        )

    for telefono in todos:
        # No molestar si el cliente cerró la conversación explícitamente
        if await verificar_cierre_enviado(telefono):
            continue

        # Determinar items y estado según qué ventana aplica
        # Estado 3 requiere estar en map_min; estados 4-5 requieren estar en map_cross
        en_min   = telefono in map_min
        en_cross = telefono in map_cross
        items = map_min.get(telefono) or map_cross.get(telefono)
        if not items:
            continue

        total = _calcular_total_carrito(items)
        if total <= 0:
            continue

        # Verificar que el estado corresponde a la ventana de tiempo correcta
        # Estado 3 (< mínimo): solo si pasó CARRITO_MIN_MIN
        # Estados 4-5 (≥ mínimo): solo si pasó CROSSSELL_MIN_MIN
        if total < PEDIDO_MINIMO and not en_min:
            logger.info(f"Carrito {telefono}: ${total:,} < mínimo, aún no han pasado {CARRITO_MIN_MIN} min — esperando")
            continue  # Aún no es tiempo para el aviso de pedido mínimo
        if total >= PEDIDO_MINIMO and not en_cross:
            logger.info(f"Carrito {telefono}: ${total:,} ≥ mínimo, aún no han pasado {CROSSSELL_MIN_MIN} min — esperando")
            continue  # Aún no es tiempo para el cross-sell

        # Calcular estado actual para detectar cambios
        estado_actual = 3 if total < PEDIDO_MINIMO else (4 if total < umbral_gratis else 5)

        # Si el estado cambió (ej. cliente agregó productos: 3→4), resetear cooldown
        # para notificar de inmediato el nuevo estado
        estado_anterior = _carrito_ultimo_estado.get(telefono)
        if estado_anterior != estado_actual:
            _carrito_unif_cooldown[telefono] = 0
            logger.info(
                f"Carrito {telefono}: estado cambió "
                f"{estado_anterior or '—'} → {estado_actual} "
                f"(${total:,}) — cooldown reseteado"
            )
            # CAPI: InitiateCheckout — cliente alcanzó el mínimo de pedido (3→4 ó 3→5)
            if estado_anterior == 3 and estado_actual in (4, 5):
                asyncio.create_task(capi_initiate_checkout(telefono, total))

        # Cooldown: no re-notificar el mismo estado en CARRITO_COOLDOWN_MIN minutos
        elapsed_min = (ahora - _carrito_unif_cooldown.get(telefono, 0)) / 60
        if ahora - _carrito_unif_cooldown.get(telefono, 0) < CARRITO_UNIF_COOLDOWN_SEG:
            logger.info(
                f"Carrito {telefono}: estado {estado_actual} (${total:,}) — "
                f"cooldown activo ({elapsed_min:.1f}/{CARRITO_COOLDOWN_MIN} min) — saltando"
            )
            continue

        nombres_en_carrito = {p.get("producto", "").lower() for p in items}
        total_fmt = f"{total:,}".replace(",", ".")
        tienda_url = f"{EQUORA_BASE}/catalogo"

        try:
            if total < PEDIDO_MINIMO:
                # ── Estado 3: bajo el mínimo ──────────────────────────────
                falta = PEDIDO_MINIMO - total
                falta_fmt = f"{falta:,}".replace(",", ".")
                sugeridos = _sugerir_productos(nombres_en_carrito)
                lineas = "\n".join(f"✅ {s}" for s in sugeridos)
                msg = (
                    f"Hola 😊 Tienes ${total_fmt} en tu carrito, ¡casi llegas!\n\n"
                    f"Te faltan *${falta_fmt}* para el pedido mínimo de *${minimo_fmt}*."
                )
                if lineas:
                    msg += f"\n\nMuchos clientes agregan:\n{lineas}"
                enviado = False
                if hasattr(proveedor, "enviar_cta_url"):
                    try:
                        enviado = await proveedor.enviar_cta_url(
                            telefono, msg, "Ver más productos 🌿", tienda_url
                        )
                    except Exception:
                        pass
                if not enviado:
                    await proveedor.enviar_mensaje(telefono, f"{msg}\n\n👉 {tienda_url}")

            elif total < umbral_gratis:
                # ── Estado 4: sobre el mínimo, bajo envío gratis ──────────
                # Incentivo principal: agrega un poco más y el envío es gratis
                # Secundario: o ya puedes confirmar ahora (paga envío)
                falta = umbral_gratis - total
                falta_fmt = f"{falta:,}".replace(",", ".")
                costo_envio_fmt = f"{obtener_costo_envio():,}".replace(",", ".")
                sugeridos = _sugerir_productos(nombres_en_carrito)
                lineas = "\n".join(f"✅ {s}" for s in sugeridos)
                msg = (
                    f"🛒 Tienes *${total_fmt}* en tu carrito!\n\n"
                    f"Agrega *${falta_fmt}* más y el envío es *gratis* 🚚🎉"
                )
                if lineas:
                    msg += f"\n\nMuchos clientes también llevan:\n{lineas}"
                msg += (
                    f"\n\nO si prefieres, ya puedes confirmar tu pedido ahora "
                    f"(envío *${costo_envio_fmt}*) 👇"
                )
                enviado = False
                if hasattr(proveedor, "enviar_cta_url"):
                    try:
                        enviado = await proveedor.enviar_cta_url(
                            telefono, msg, "Ir al carrito 🛒", tienda_url
                        )
                    except Exception:
                        pass
                if not enviado:
                    await proveedor.enviar_mensaje(telefono, f"{msg}\n\n👉 {tienda_url}")

            else:
                # ── Estado 5: envío gratis garantizado ────────────────────
                msg = (
                    f"🎉 ¡Tu carrito tiene *${total_fmt}* con *envío gratis* incluido!\n\n"
                    f"Solo entra a la tienda, revisa tu carrito y confirma tu pedido 👇"
                )
                enviado = False
                if hasattr(proveedor, "enviar_cta_url"):
                    try:
                        enviado = await proveedor.enviar_cta_url(
                            telefono, msg, "Confirmar pedido ✅", tienda_url
                        )
                    except Exception:
                        pass
                if not enviado:
                    await proveedor.enviar_mensaje(telefono, f"{msg}\n\n👉 {tienda_url}")

            await guardar_mensaje(telefono, "assistant", msg)
            _carrito_unif_cooldown[telefono] = ahora
            _carrito_ultimo_estado[telefono] = estado_actual
            logger.info(f"Seguimiento carrito estado {estado_actual} → {telefono} (${total_fmt})")

        except Exception as e:
            logger.error(f"Error en seguimiento carrito {telefono}: {e}")


async def _procesar_followups():
    """Estado 6: sin carrito, sin checkout. Follow-up genérico una sola vez."""
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
    """Estado 6: cierre tras follow-up genérico sin respuesta."""
    telefonos = await conversaciones_para_cierre(CIERRE_MIN)
    for telefono in telefonos:
        try:
            await proveedor.enviar_mensaje(telefono, MENSAJE_CIERRE)
            await guardar_mensaje(telefono, "assistant", MENSAJE_CIERRE)
            await marcar_cierre_enviado(telefono)
            logger.info(f"Cierre enviado a {telefono}")
        except Exception as e:
            logger.error(f"Error enviando cierre a {telefono}: {e}")


async def _procesar_abandono_carrito_UNUSED():
    """REEMPLAZADO por _procesar_carrito_unificado — se deja comentado como referencia."""
    ahora = time.time()
    clientes = await clientes_con_carrito_abandonado(
        min_inactivo=ABANDONO_MIN_INACTIVO,
        max_inactivo=ABANDONO_MAX_INACTIVO,
    )
    for telefono, _ in clientes:
        ultimo = _abandono_notif.get(telefono, 0)
        if ahora - ultimo < ABANDONO_COOLDOWN_SEG:
            continue
        try:
            tienda_url = f"{EQUORA_BASE}/catalogo"
            enviado = False
            msg_abandono = _mensaje_abandono()
            if hasattr(proveedor, "enviar_cta_url"):
                try:
                    enviado = await proveedor.enviar_cta_url(
                        telefono, msg_abandono, "Ver productos 🛒", tienda_url
                    )
                except Exception:
                    pass
            if not enviado:
                texto_con_url = f"{msg_abandono}\n\n👉 {tienda_url}"
                await proveedor.enviar_mensaje(telefono, texto_con_url)
            await guardar_mensaje(telefono, "assistant", msg_abandono)
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

# CORS para que Lovable (equoradistribuciones.com) pueda llamar a /shopify/cart-update
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://equoradistribuciones.com",
        "https://www.equoradistribuciones.com",
        "https://equora-6.myshopify.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
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


def _utm_andrea(url: str, content: str = "") -> str:
    """
    Agrega parámetros UTM a cualquier URL de la tienda enviada por Andrea.
    El Pixel web de Meta los captura automáticamente en PageView / ViewContent.
      utm_source   = whatsapp
      utm_medium   = chatbot
      utm_campaign = andrea
      utm_content  = término del producto / categoría (si lo hay)
    """
    import urllib.parse
    params = {
        "utm_source": "whatsapp",
        "utm_medium": "chatbot",
        "utm_campaign": "andrea",
    }
    if content:
        params["utm_content"] = content[:100]  # truncar por seguridad
    sep = "&" if "?" in url else "?"
    return url + sep + urllib.parse.urlencode(params)


def _construir_url_tienda(query: str) -> str:
    """
    Convierte el término del marcador [[TIENDA:término]] en la URL más
    específica posible en equoradistribuciones.com:

    1. Si el término coincide exactamente con una clave de _COLECCION_MAP
       (ej. "desengrasante", "lavaloza", "combos") → abre la colección.
       Esto evita que el buscador de productos escoja mal entre variantes
       cuando Andrea usa un término genérico de categoría.
    2. Si el término es específico (ej. "desengrasante profesional" o
       "lavaloza antibacterial 500ml") → intenta URL de producto concreto.
    3. Si no hay handle, busca coincidencia parcial en _COLECCION_MAP.
    4. Fallback: /catalogo
    """
    if not query:
        return f"{EQUORA_BASE}/catalogo"

    q = query.lower().strip()

    # 1. Término genérico de categoría → colección directa (sin pasar por Jaccard)
    if q in _COLECCION_MAP:
        return _COLECCION_MAP[q]

    # 2. Término específico → buscar producto por handle (Jaccard)
    url_producto = obtener_url_producto(query)
    if url_producto:
        logger.info(f"[tienda-url] '{query}' → producto: {url_producto}")
        return url_producto
    else:
        logger.warning(f"[tienda-url] '{query}' → Jaccard no encontró handle, usando colección")

    # 3. Coincidencia parcial de categoría — solo si el query es una sola palabra
    #    (evita que "desengrasante profesional" caiga a la colección por "desengrasante")
    palabras_query = q.split()
    if len(palabras_query) == 1:
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

            # CAPI: Lead — primera vez que este número escribe a Andrea
            if not historial:
                asyncio.create_task(capi_lead(msg.telefono))

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

            # Marcador de cierre de conversación → suprime futuros seguimientos
            if '[[CIERRE_CONV:]]' in respuesta:
                respuesta = respuesta.replace('[[CIERRE_CONV:]]', '').strip()
                try:
                    await marcar_cierre_enviado(msg.telefono)
                    logger.info(f"Conversación cerrada para {msg.telefono} — seguimientos suprimidos")
                except Exception as e:
                    logger.error(f"Error marcando cierre: {e}")

            # Extraer marcadores interactivos ANTES de enviar el texto
            respuesta, datos_catalogo_cat = extraer_marcador_catalogo_cat(respuesta)
            respuesta, datos_botones = extraer_marcador_botones(respuesta)
            respuesta, datos_lista = extraer_marcador_lista(respuesta)
            respuesta, abrir_tienda, tienda_query = extraer_marcador_tienda(respuesta)

            # Enviar texto primero
            # Excepción: si hay CTA de catálogo general (sin query), el texto de Andrea
            # se fusiona como cuerpo del CTA para que quede un único mensaje de bienvenida.
            _texto_absorbido_por_cta = abrir_tienda and not tienda_query and respuesta.strip()
            if respuesta and not _texto_absorbido_por_cta:
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
                # UTMs para atribución en el Pixel web de Meta
                tienda_url = _utm_andrea(tienda_url, content=tienda_query)
                # Añadir teléfono para que Lovable pueda reportar el carrito de vuelta
                tienda_url += f"&tel={urllib.parse.quote(msg.telefono)}"
                minimo_fmt = f"{PEDIDO_MINIMO:,}".replace(",", ".")
                gratis_fmt = f"{obtener_umbral_envio_gratis():,}".replace(",", ".")
                pie_tienda = f"📦 Pedido mínimo ${minimo_fmt} | 🚚 Envío gratis > ${gratis_fmt}"
                if tienda_query:
                    texto_tienda = (
                        "🛒 *Aquí puedes ver el producto, elegir tu presentación y hacer tu pedido:*\n"
                        + pie_tienda
                    )
                    boton_label = "Ver producto 🌿"
                else:
                    # Catálogo general: fusionar el saludo de Andrea con el CTA
                    # → 1 solo mensaje en lugar de texto + CTA separados
                    if _texto_absorbido_por_cta:
                        texto_tienda = respuesta.strip() + "\n\n" + pie_tienda
                    else:
                        texto_tienda = (
                            "🛒 *Aquí puedes ver todos nuestros productos con fotos y hacer tu pedido:*\n"
                            + pie_tienda
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
                # CAPI: ViewContent — Andrea envió link de producto/catálogo
                asyncio.create_task(capi_view_content(
                    msg.telefono,
                    tienda_query or "catalogo",
                    tienda_url,
                ))

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
            # Sin teléfono no podemos asociar a una conversación
            # ADVERTENCIA: la página Lovable debe incluir siempre el teléfono en el payload
            logger.warning(
                f"[cart-update] SIN teléfono — payload ignorado. "
                f"productos={len(body.get('productos') or [])}. "
                f"Revisa que Lovable incluya 'telefono' en cada cart-update."
            )
            return JSONResponse(content={"ok": True})

        if productos:
            items_para_bd = []
            total_recibido = 0
            for p in productos:
                precio = int(float(p.get("precio_unitario") or p.get("precio") or 0))
                qty = int(p.get("cantidad") or p.get("qty") or 1)
                subtotal = precio * qty
                total_recibido += subtotal
                items_para_bd.append({
                    "producto":      p.get("producto", ""),
                    "presentacion":  p.get("presentacion", ""),
                    "cantidad":      qty,
                    "precio_unitario": precio,
                    "subtotal":      subtotal,
                })
            await guardar_carrito_activo(telefono, items_para_bd)
            logger.info(
                f"[cart-update] {telefono}: {len(productos)} productos, "
                f"total=${total_recibido:,}"
            )
            # CAPI: AddToCart — cliente agregó productos en la tienda web
            asyncio.create_task(capi_add_to_cart(telefono, total_recibido, items_para_bd))
        else:
            # Carrito vacío → limpiar
            await limpiar_carrito_activo(telefono)
            logger.info(f"[cart-update] {telefono}: carrito vaciado")

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


# ── Difusión / Broadcast ───────────────────────────────────────────────────

# Cache en memoria: {scontent_url → whatsapp_media_id}
# Se llena la primera vez que se usa cada plantilla; se pierde al reiniciar (Railway redeploy).
_header_media_cache: dict[str, str] = {}


async def _subir_imagen_whatsapp(image_url: str, access_token: str, phone_number_id: str) -> str | None:
    """
    Descarga la imagen del CDN de Meta y la sube a la WhatsApp Media API
    para obtener un media_id reutilizable en el componente header de templates.

    Returns:
        media_id  si fue exitoso, None si falló (el envío continuará sin header).
    """
    global _header_media_cache
    if image_url in _header_media_cache:
        return _header_media_cache[image_url]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Descargar la imagen (las URLs de scontent.whatsapp.net son públicas con firma)
            r_img = await client.get(image_url)
            if r_img.status_code != 200:
                logger.warning(f"[broadcast] No se pudo descargar imagen header: {r_img.status_code}")
                return None
            image_bytes = r_img.content
            content_type = r_img.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(content_type, "jpg")

            # 2. Subir a la WhatsApp Media API
            upload_url = f"https://graph.facebook.com/v21.0/{phone_number_id}/media"
            auth_headers = {"Authorization": f"Bearer {access_token}"}
            files = {
                "file": (f"header.{ext}", image_bytes, content_type),
            }
            data = {
                "messaging_product": "whatsapp",
                "type": content_type,
            }
            r_up = await client.post(upload_url, headers=auth_headers, files=files, data=data)
            if r_up.status_code == 200:
                media_id = r_up.json().get("id")
                if media_id:
                    _header_media_cache[image_url] = media_id
                    logger.info(f"[broadcast] Imagen header subida → media_id={media_id}")
                    return media_id
            logger.warning(f"[broadcast] Error subiendo imagen: {r_up.status_code} {r_up.text[:200]}")
    except Exception as e:
        logger.warning(f"[broadcast] Excepción subiendo imagen header: {e}")
    return None

@app.get("/inbox/broadcast/templates/raw")
async def inbox_broadcast_templates_raw(
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """Debug: devuelve el JSON crudo de Meta para ver cómo están registradas las variables."""
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    access_token = os.getenv("META_ACCESS_TOKEN", "")
    waba_id      = os.getenv("META_WABA_ID", "")
    api_ver = "v21.0"
    url = (
        f"https://graph.facebook.com/{api_ver}/{waba_id}"
        f"/message_templates?fields=id,name,status,components,language&limit=50"
        f"&access_token={access_token}"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        return JSONResponse(content=r.json())

@app.get("/inbox/broadcast/templates")
async def inbox_broadcast_templates(
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """Lista las plantillas aprobadas en Meta para usar en difusiones."""
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    access_token = os.getenv("META_ACCESS_TOKEN", "")
    waba_id      = os.getenv("META_WABA_ID", "")
    logger.info(f"[broadcast] access_token={'OK' if access_token else 'FALTA'} waba_id={waba_id or 'FALTA'}")

    if not access_token or not waba_id:
        return JSONResponse(content={"templates": [], "error": "META_ACCESS_TOKEN o META_WABA_ID no configurados en Railway"})

    try:
        # Las plantillas pertenecen al WhatsApp Business Account (WABA), no al número
        api_ver  = "v21.0"
        waba_url = (
            f"https://graph.facebook.com/{api_ver}/{waba_id}"
            f"/message_templates?fields=id,name,status,components,language&limit=100"
            f"&access_token={access_token}"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(waba_url)
            logger.info(f"[broadcast] Meta templates response: {r.status_code} {r.text[:300]}")
            if r.status_code != 200:
                return JSONResponse(content={"templates": [], "error": f"Meta API {r.status_code}: {r.text[:200]}"})

            data = r.json()
            # Meta a veces devuelve {"error": ...} con status 200
            if "error" in data:
                err_msg = data["error"].get("message", str(data["error"]))
                logger.error(f"[broadcast] Meta error en templates: {err_msg}")
                return JSONResponse(content={"templates": [], "error": err_msg})

            templates_raw = data.get("data", [])

            # Mostramos todas (APPROVED, PENDING, REJECTED, PAUSED)
            templates = []
            for t in templates_raw:
                # Extraer variables del body — usamos la fuente oficial de Meta:
                # 1. body_text_named_params → variables con nombre ({{nombre}})
                # 2. body_text              → variables posicionales ({{1}})
                # 3. Fallback regex
                variables = []
                named = False
                for comp in t.get("components", []):
                    if comp.get("type", "").upper() != "BODY":
                        continue
                    example = comp.get("example", {})
                    if example.get("body_text_named_params"):
                        # Plantilla con variables nombradas
                        variables = [p["param_name"] for p in example["body_text_named_params"] if p.get("param_name")]
                        named = True
                    elif example.get("body_text"):
                        # Plantilla con variables posicionales: body_text es [[val1, val2, ...]]
                        bt = example["body_text"]
                        count = len(bt[0]) if bt and bt[0] else 0
                        variables = [str(i + 1) for i in range(count)]
                    else:
                        # Fallback: regex sobre el texto de la plantilla
                        text = comp.get("text", "")
                        found = sorted(set(re.findall(r'\{\{([^}]+)\}\}', text)))
                        variables = found
                        named = any(not v.isdigit() for v in found)
                    break
                # Extraer header: tipo y URL de imagen si existe
                header_type = None
                header_url  = None
                for comp in t.get("components", []):
                    if comp.get("type", "").upper() != "HEADER":
                        continue
                    fmt = comp.get("format", "").upper()
                    header_type = fmt
                    if fmt == "IMAGE":
                        handles = comp.get("example", {}).get("header_handle", [])
                        header_url = handles[0] if handles else None
                    break

                templates.append({
                    "id":          t.get("id", ""),       # ID de la plantilla en Meta (para editar)
                    "name":        t.get("name", ""),
                    "language":    t.get("language", "es_CO"),
                    "status":      t.get("status", ""),
                    "variables":   variables,
                    "named":       named,       # True si usa {{nombre}}, False si usa {{1}}
                    "header_type": header_type, # "IMAGE", "TEXT", "VIDEO", None
                    "header_url":  header_url,  # URL de la imagen del header (si aplica)
                    "components":  t.get("components", []),  # componentes completos para edición
                    "preview":     next(
                        (c.get("text", "") for c in t.get("components", [])
                         if c.get("type", "").upper() == "BODY"),
                        ""
                    ),
                })

            logger.info(f"[broadcast] {len(templates)} plantillas APPROVED encontradas de {len(templates_raw)} totales")
            return JSONResponse(content={"templates": templates})

    except Exception as e:
        logger.error(f"[broadcast] Excepción en inbox_broadcast_templates: {e}", exc_info=True)
        return JSONResponse(content={"templates": [], "error": f"Error interno: {str(e)}"})


@app.post("/inbox/broadcast/send")
async def inbox_broadcast_send(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """
    Envía una plantilla aprobada a una lista de destinatarios personalizados.
    Body JSON:
      { "template": "nombre_plantilla",
        "language": "es_CO",
        "recipients": [
          {"phone": "573001234567", "variables": ["Juan"]},
          {"phone": "573009876543", "variables": ["María"]}
        ]
      }
    """
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    body          = await request.json()
    template_name = body.get("template", "")
    language      = body.get("language", "es_CO")
    recipients    = body.get("recipients", [])   # [{phone, variables:[]}]
    var_names     = body.get("var_names", [])    # nombres de variables, ej: ["nombre"]
    is_named      = body.get("named", False)     # True si plantilla usa {{nombre}}, False si {{1}}
    header_type   = body.get("header_type")      # "IMAGE", "TEXT", etc.
    header_url    = body.get("header_url")       # URL de imagen del header (si aplica)
    campaign_name = body.get("campaign_name", "")  # nombre de la campaña dado por el usuario
    campaign_id   = body.get("campaign_id", "")    # ID único compartido entre todos los lotes

    if not template_name or not recipients:
        return JSONResponse(content={"error": "Faltan template o recipients"}, status_code=400)

    access_token    = os.getenv("META_ACCESS_TOKEN", "")
    phone_number_id = os.getenv("META_PHONE_NUMBER_ID", "")
    if not access_token or not phone_number_id:
        return JSONResponse(content={"error": "META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados"}, status_code=500)

    api_ver = "v21.0"
    api_url = f"https://graph.facebook.com/{api_ver}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    enviados = 0
    fallidos = 0
    errores  = []

    # Si el template tiene IMAGE header, subir la imagen una sola vez y cachear el media_id
    header_media_id: str | None = None
    if header_type == "IMAGE" and header_url:
        header_media_id = await _subir_imagen_whatsapp(header_url, access_token, phone_number_id)
        if not header_media_id:
            logger.warning("[broadcast] No se pudo obtener media_id para el header — se enviará sin imagen")

    async with httpx.AsyncClient(timeout=15) as client:
        for dest in recipients:
            tel = "".join(filter(str.isdigit, str(dest.get("phone", ""))))
            if not tel or len(tel) < 10:
                fallidos += 1
                errores.append(f"Número inválido: {dest.get('phone')}")
                continue

            # Variables específicas de este destinatario
            vars_dest = dest.get("variables", [])
            components = []

            # HEADER con media_id: usamos el ID subido vía Media API (no la URL de scontent)
            if header_media_id:
                components.append({
                    "type": "header",
                    "parameters": [{"type": "image", "image": {"id": header_media_id}}],
                })

            # BODY con variables personalizadas
            if vars_dest:
                parameters = []
                for i, v in enumerate(vars_dest):
                    param = {"type": "text", "text": str(v)}
                    # parameter_name para plantillas con variables nombradas ({{nombre}})
                    if is_named and i < len(var_names) and not var_names[i].isdigit():
                        param["parameter_name"] = var_names[i]
                    parameters.append(param)
                components.append({
                    "type": "body",
                    "parameters": parameters,
                })

            payload = {
                "messaging_product": "whatsapp",
                "to": tel,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language},
                    **({"components": components} if components else {}),
                },
            }
            try:
                logger.info(f"[broadcast] named={is_named} var_names={var_names} Payload → {payload}")
                r = await client.post(api_url, json=payload, headers=headers)
                if r.status_code == 200:
                    enviados += 1
                    try:
                        resp_data = r.json()
                        wamid = resp_data.get("messages", [{}])[0].get("id", "?")
                        msg_status = resp_data.get("messages", [{}])[0].get("message_status", "?")
                    except Exception:
                        wamid, msg_status = "?", "?"
                    logger.info(f"[broadcast] Enviado a {tel[-4:]}**** wamid={wamid} status={msg_status}")
                else:
                    fallidos += 1
                    try:
                        err_data = r.json().get("error", {})
                        err_code = err_data.get("code", "")
                        err_msg  = err_data.get("message", r.text[:200])
                        err_detail = f"#{err_code} {err_msg} | payload_components={payload.get('template',{}).get('components','none')}"
                    except Exception:
                        err_detail = r.text[:300]
                    errores.append(f"{tel}: {err_detail}")
                    logger.warning(f"[broadcast] Falló {tel}: {r.status_code} — {r.text[:400]}")
            except Exception as e:
                fallidos += 1
                errores.append(f"{tel}: {e}")

            # Cadencia: 10 mensajes/segundo
            await asyncio.sleep(0.1)

    logger.info(f"[broadcast] Difusión '{template_name}': {enviados} enviados, {fallidos} fallidos")

    # Registrar resultado en BD para el historial de difusiones
    try:
        await registrar_difusion(
            template_name=template_name,
            language=language,
            destinatarios=len(recipients),
            enviados=enviados,
            fallidos=fallidos,
            errores=errores,
            campaign_name=campaign_name,
            campaign_id=campaign_id,
        )
    except Exception as e:
        logger.warning(f"[broadcast] No se pudo registrar difusión en BD: {e}")

    return JSONResponse(content={
        "enviados": enviados,
        "fallidos": fallidos,
        "errores":  errores[:20],
    })


@app.get("/inbox/difusiones/historial")
async def inbox_difusiones_historial(
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """Devuelve el historial de difusiones enviadas desde el inbox."""
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    rows = await obtener_difusiones(50)
    return JSONResponse(content={"difusiones": rows})


@app.get("/inbox/metricas/resumen")
async def inbox_metricas_resumen(
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """Métricas de WhatsApp Business: mensajes enviados, entregados, leídos (últimos 30 días)."""
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    access_token = os.getenv("META_ACCESS_TOKEN", "")
    waba_id      = os.getenv("META_WABA_ID", "")
    phone_number_id = os.getenv("META_PHONE_NUMBER_ID", "")

    if not access_token or not waba_id:
        return JSONResponse(content={"error": "META_ACCESS_TOKEN o META_WABA_ID no configurados"})

    import datetime as dt
    hoy   = dt.date.today()
    start = int((hoy - dt.timedelta(days=30)).strftime("%s") if hasattr(hoy, "strftime") else 0)
    end   = int(hoy.strftime("%s") if hasattr(hoy, "strftime") else 0)

    # Usar timestamps de época correctamente
    import time as _time
    end_ts   = int(_time.time())
    start_ts = end_ts - 30 * 86400

    api_ver = "v21.0"
    # WABA Analytics: mensajes enviados, entregados y leídos por día
    analytics_url = (
        f"https://graph.facebook.com/{api_ver}/{waba_id}/analytics"
        f"?granularity=MONTHLY&start={start_ts}&end={end_ts}"
        f"&metric_types=['SENT','DELIVERED','READ']"
        f"&access_token={access_token}"
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(analytics_url)
            data = r.json()
            if "error" in data:
                # Fallback: intentar con phone_number_id si WABA falla
                ph_url = (
                    f"https://graph.facebook.com/{api_ver}/{phone_number_id}/analytics"
                    f"?granularity=MONTHLY&start={start_ts}&end={end_ts}"
                    f"&metric_types=['SENT','DELIVERED','READ']"
                    f"&access_token={access_token}"
                )
                r2 = await client.get(ph_url)
                data = r2.json()
            if "error" in data:
                return JSONResponse(content={"error": data["error"].get("message", str(data["error"])), "raw": data})
            # Sumar totales del periodo
            puntos = data.get("data", {}).get("data_points", [])
            totales = {"sent": 0, "delivered": 0, "read": 0}
            for p in puntos:
                totales["sent"]      += p.get("sent", 0)
                totales["delivered"] += p.get("delivered", 0)
                totales["read"]      += p.get("read", 0)
            return JSONResponse(content={"resumen": totales, "puntos": puntos})
    except Exception as e:
        logger.error(f"[metricas] Error consultando Analytics API: {e}")
        return JSONResponse(content={"error": str(e)})


@app.get("/inbox/metricas/plantillas")
async def inbox_metricas_plantillas(
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """Analíticas por plantilla: enviados, entregados, leídos, clics en botón."""
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    access_token = os.getenv("META_ACCESS_TOKEN", "")
    waba_id      = os.getenv("META_WABA_ID", "")

    if not access_token or not waba_id:
        return JSONResponse(content={"error": "META_ACCESS_TOKEN o META_WABA_ID no configurados"})

    import time as _time
    end_ts   = int(_time.time())
    start_ts = end_ts - 30 * 86400
    api_ver  = "v21.0"

    url = (
        f"https://graph.facebook.com/{api_ver}/{waba_id}/template_analytics"
        f"?granularity=MONTHLY&start={start_ts}&end={end_ts}"
        f"&access_token={access_token}"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            data = r.json()
            if "error" in data:
                return JSONResponse(content={"error": data["error"].get("message", str(data["error"])), "raw": data})
            return JSONResponse(content={"analytics": data.get("data", [])})
    except Exception as e:
        logger.error(f"[metricas] Error consultando template_analytics: {e}")
        return JSONResponse(content={"error": str(e)})


@app.post("/inbox/plantillas/subir-header")
async def inbox_subir_header_media(
    file: UploadFile = File(...),
    file_type: str = Form(...),
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """
    Sube un archivo (imagen/video/doc) a Meta vía Resumable Upload API
    y retorna el handle para usar en example.header_handle al crear una plantilla.

    Flujo Meta Resumable Upload:
      1. POST /{app_id}/uploads?file_name=...&file_length=...&file_type=...
         → {"id": "upload:{session_id}"}
      2. POST /upload:{session_id}  (body = bytes del archivo, header file_offset: 0)
         → {"h": "handle_string"}
    """
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    access_token = os.getenv("META_ACCESS_TOKEN", "")
    app_id       = os.getenv("META_APP_ID", "")

    if not access_token:
        return JSONResponse(content={"error": "META_ACCESS_TOKEN no configurado"}, status_code=500)
    if not app_id:
        # Sin APP_ID no podemos usar Resumable Upload — informar al frontend
        # (la plantilla se crea sin example header, Meta igual la aprueba)
        return JSONResponse(content={"error": "META_APP_ID no configurado en Railway — la plantilla se creará sin imagen de ejemplo", "handle": None}, status_code=200)

    try:
        file_bytes = await file.read()
        file_name  = file.filename or "header_file"
        file_size  = len(file_bytes)
        mime_type  = file_type or file.content_type or "image/jpeg"

        api_ver = "v21.0"

        async with httpx.AsyncClient(timeout=60) as client:
            # 1. Iniciar sesión de upload
            init_url = (
                f"https://graph.facebook.com/{api_ver}/{app_id}/uploads"
                f"?file_name={file_name}&file_length={file_size}"
                f"&file_type={mime_type}&access_token={access_token}"
            )
            r1 = await client.post(init_url)
            data1 = r1.json()
            if "error" in data1:
                err = data1["error"]
                logger.error(f"[subir-header] Error iniciando upload: {err}")
                return JSONResponse(content={"error": err.get("message", str(err)), "handle": None})

            session_id = data1.get("id", "")
            if not session_id:
                return JSONResponse(content={"error": "No se obtuvo upload session_id de Meta", "handle": None})

            # 2. Subir el archivo
            upload_url = f"https://graph.facebook.com/{api_ver}/{session_id}"
            upload_headers = {
                "Authorization": f"OAuth {access_token}",
                "file_offset": "0",
                "Content-Type": mime_type,
            }
            r2 = await client.post(upload_url, content=file_bytes, headers=upload_headers)
            data2 = r2.json()
            if "error" in data2:
                err = data2["error"]
                logger.error(f"[subir-header] Error subiendo archivo: {err}")
                return JSONResponse(content={"error": err.get("message", str(err)), "handle": None})

            handle = data2.get("h")
            if not handle:
                return JSONResponse(content={"error": "Meta no devolvió un handle válido", "handle": None})

            logger.info(f"[subir-header] Archivo '{file_name}' subido → handle={handle[:30]}...")
            return JSONResponse(content={"ok": True, "handle": handle})

    except Exception as e:
        logger.error(f"[subir-header] Excepción: {e}", exc_info=True)
        return JSONResponse(content={"error": str(e), "handle": None}, status_code=500)


@app.post("/inbox/plantillas/crear")
async def inbox_plantillas_crear(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """Crea una nueva plantilla en Meta y la envía a revisión.
    Body JSON: { name, category, language, header_text?, body, footer?, buttons? }
    """
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    access_token = os.getenv("META_ACCESS_TOKEN", "")
    waba_id      = os.getenv("META_WABA_ID", "")
    if not access_token or not waba_id:
        return JSONResponse(content={"error": "META_ACCESS_TOKEN o META_WABA_ID no configurados"}, status_code=500)

    body = await request.json()
    nombre       = (body.get("name") or "").lower().replace(" ", "_")
    categoria    = body.get("category", "MARKETING")
    idioma       = body.get("language", "es_CO")
    cuerpo       = body.get("body", "")
    header_tipo   = (body.get("header_type") or "").upper()  # NONE|TEXT|IMAGE|VIDEO|DOCUMENT|LOCATION
    header_texto  = body.get("header_text", "")
    header_handle = body.get("header_handle")                # handle de Resumable Upload
    footer        = body.get("footer", "")
    buttons       = body.get("buttons", [])
    sub_category  = body.get("sub_category", "DEFAULT")      # DEFAULT|CATALOG_MESSAGE|CALL_PERMISSION_REQUEST
    catalog_format = body.get("catalog_format", "FULL")      # FULL | MULTI (solo para CATALOG_MESSAGE)
    var_type      = (body.get("var_type") or "").upper()     # NOMBRE | NUMERO (controla ejemplo de variables)
    ttl_activo    = body.get("ttl_activo", False)
    ttl_secs      = int(body.get("ttl", 43200))              # período de validez en segundos
    # Ubicación: campos de ejemplo para LOCATION header
    loc_lat  = body.get("loc_lat")
    loc_lng  = body.get("loc_lng")
    loc_name = body.get("loc_name", "")

    if not nombre or not cuerpo:
        return JSONResponse(content={"error": "Nombre y cuerpo son requeridos"}, status_code=400)

    componentes = []

    # ── HEADER ──
    # CATALOG_MESSAGE y CALL_PERMISSION_REQUEST no admiten encabezado multimedia
    if sub_category not in ("CATALOG_MESSAGE", "CALL_PERMISSION_REQUEST"):
        if header_tipo == "TEXT" and header_texto:
            componentes.append({"type": "HEADER", "format": "TEXT", "text": header_texto[:60]})
        elif header_tipo in ("IMAGE", "VIDEO", "DOCUMENT"):
            comp_hdr: dict = {"type": "HEADER", "format": header_tipo}
            if header_handle:
                comp_hdr["example"] = {"header_handle": [header_handle]}
            componentes.append(comp_hdr)
        elif header_tipo == "LOCATION":
            comp_hdr = {"type": "HEADER", "format": "LOCATION"}
            if loc_lat and loc_lng:
                comp_hdr["example"] = {
                    "header_location": {
                        "latitude": str(loc_lat),
                        "longitude": str(loc_lng),
                        "name": loc_name or "Ubicación de ejemplo",
                    }
                }
            componentes.append(comp_hdr)

    # ── BODY ──
    import re as _re
    vars_encontradas = _re.findall(r'\{\{([^}]+)\}\}', cuerpo)
    body_comp: dict = {"type": "BODY", "text": cuerpo}
    if vars_encontradas:
        example_vals = ["ejemplo"] * len(vars_encontradas)
        # var_type=NOMBRE fuerza named params aunque el usuario use {{1}} por error
        # var_type=NUMERO fuerza posicional aunque el usuario use {{nombre}}
        # Si no se especifica, auto-detectar
        named_vars = [v for v in vars_encontradas if not v.isdigit()]
        usar_named = (var_type == "NOMBRE") or (var_type != "NUMERO" and bool(named_vars))
        if usar_named:
            body_comp["example"] = {
                "body_text_named_params": [
                    {"param_name": v, "example": ["ejemplo"]} for v in vars_encontradas
                ]
            }
        else:
            body_comp["example"] = {"body_text": [example_vals]}
    componentes.append(body_comp)

    # ── FOOTER ──
    if footer:
        componentes.append({"type": "FOOTER", "text": footer[:60]})

    # ── BUTTONS ──
    if sub_category == "CATALOG_MESSAGE":
        # Catálogo: solo un botón fijo de tipo CATALOG (Meta lo muestra como "Ver catálogo")
        catalog_btn: dict = {"type": "CATALOG", "title": "Ver catálogo"}
        componentes.append({"type": "BUTTONS", "buttons": [catalog_btn]})
    elif sub_category == "CALL_PERMISSION_REQUEST":
        # Permisos de llamada: Meta genera los botones automáticamente, no enviamos ninguno
        pass
    elif buttons:
        btn_list = []
        for b in buttons[:10]:
            btype = b.get("type", "").upper()
            texto_btn = b.get("text", "")[:25]
            if btype == "URL":
                url_val = b.get("url", "")
                if url_val and texto_btn:
                    btn_obj = {"type": "URL", "text": texto_btn[:20], "url": url_val}
                    if "{{1}}" in url_val:
                        btn_obj["example"] = [url_val.replace("{{1}}", "ejemplo")]
                    btn_list.append(btn_obj)
            elif btype == "PHONE_NUMBER":
                phone = b.get("phone_number", "")
                if phone and texto_btn:
                    btn_list.append({"type": "PHONE_NUMBER", "text": texto_btn[:20], "phone_number": phone})
            elif btype == "QUICK_REPLY":
                if texto_btn:
                    btn_list.append({"type": "QUICK_REPLY", "text": texto_btn})
        if btn_list:
            componentes.append({"type": "BUTTONS", "buttons": btn_list})

    payload = {
        "name": nombre,
        "category": categoria,
        "language": idioma,
        "components": componentes,
    }
    # Subcategoría (solo si no es DEFAULT para evitar errores en Auth)
    if sub_category and sub_category != "DEFAULT":
        payload["sub_category"] = sub_category
    # Período de validez (solo Marketing)
    if ttl_activo and categoria == "MARKETING" and ttl_secs:
        payload["message_send_ttl_seconds"] = ttl_secs

    api_ver = "v21.0"
    url = f"https://graph.facebook.com/{api_ver}/{waba_id}/message_templates"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    logger.info(f"[plantillas] Enviando a Meta — nombre={nombre} cat={categoria} sub={sub_category} componentes={len(componentes)}")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload, headers=headers)
            # Parsear respuesta de Meta — puede no ser JSON en casos de error
            try:
                data = r.json()
            except Exception as json_err:
                raw = r.text[:600]
                logger.error(f"[plantillas] Meta devolvió respuesta no-JSON (status={r.status_code}): {raw}")
                return JSONResponse(
                    content={"error": f"Meta devolvió respuesta no válida (status {r.status_code}): {raw}"},
                    status_code=502,
                )
            if not isinstance(data, dict):
                logger.error(f"[plantillas] Respuesta inesperada de Meta (tipo={type(data).__name__}): {str(data)[:300]}")
                return JSONResponse(
                    content={"error": f"Respuesta inesperada de Meta: {str(data)[:200]}"},
                    status_code=502,
                )
            if r.status_code in (200, 201) or "id" in data:
                logger.info(f"[plantillas] Plantilla '{nombre}' creada — id={data.get('id')} status={data.get('status')}")
                return JSONResponse(content={"ok": True, "id": data.get("id"), "status": data.get("status")})
            else:
                err = data.get("error", {})
                err_msg = err.get("message", str(data)) if isinstance(err, dict) else str(err)
                err_details = err.get("error_data", {}) if isinstance(err, dict) else {}
                logger.error(f"[plantillas] Error de Meta (status={r.status_code} code={err.get('code') if isinstance(err,dict) else '?'}): {err_msg} | details={err_details}")
                return JSONResponse(content={"error": err_msg, "details": err_details}, status_code=400)
    except Exception as e:
        logger.error(f"[plantillas] Excepción ({type(e).__name__}): {e}", exc_info=True)
        return JSONResponse(content={"error": str(e) or type(e).__name__}, status_code=500)


# ── Borradores de plantillas (guardado local antes de enviar a Meta) ─────────

@app.get("/inbox/plantillas/borradores")
async def inbox_plantillas_borradores_list(
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """Lista todos los borradores de plantillas guardados localmente."""
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    borradores = await obtener_borradores_plantillas()
    return JSONResponse(content={"borradores": borradores})


@app.post("/inbox/plantillas/borrador")
async def inbox_plantillas_borrador_guardar(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """Guarda (crea o actualiza) un borrador de plantilla localmente.
    Body JSON: los mismos campos del formulario de creación.
    Si ya existe un borrador con el mismo nombre, lo sobreescribe.
    """
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    nombre    = (body.get("name") or "").strip()
    categoria = body.get("category", "MARKETING")
    idioma    = body.get("language", "es_CO")
    if not nombre:
        return JSONResponse(content={"error": "El nombre es requerido"}, status_code=400)
    bid = await guardar_borrador_plantilla(nombre, categoria, idioma, body)
    logger.info(f"[plantillas] Borrador guardado id={bid} nombre={nombre}")
    return JSONResponse(content={"ok": True, "id": bid})


@app.delete("/inbox/plantillas/borrador/{bid}")
async def inbox_plantillas_borrador_eliminar(
    bid: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """Elimina un borrador local por ID."""
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    eliminado = await eliminar_borrador_plantilla(bid)
    if not eliminado:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    return JSONResponse(content={"ok": True})


@app.post("/inbox/plantillas/editar")
async def inbox_plantillas_editar(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
):
    """Edita una plantilla existente en Meta (solo se pueden cambiar los componentes).
    Meta devuelve la plantilla a estado PENDING tras la edición.
    Body JSON: { template_id, header_type?, header_text?, header_handle?,
                 body, footer?, buttons? }
    """
    if not _verificar_admin(inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    access_token = os.getenv("META_ACCESS_TOKEN", "")
    if not access_token:
        return JSONResponse(content={"error": "META_ACCESS_TOKEN no configurado"}, status_code=500)

    body = await request.json()
    template_id   = body.get("template_id", "")
    cuerpo        = body.get("body", "")
    header_tipo   = (body.get("header_type") or "").upper()
    header_texto  = body.get("header_text", "")
    header_handle = body.get("header_handle")
    footer        = body.get("footer", "")
    buttons       = body.get("buttons", [])

    if not template_id or not cuerpo:
        return JSONResponse(content={"error": "template_id y body son requeridos"}, status_code=400)

    componentes = []

    # HEADER
    if header_tipo == "TEXT" and header_texto:
        componentes.append({"type": "HEADER", "format": "TEXT", "text": header_texto[:60]})
    elif header_tipo in ("IMAGE", "VIDEO", "DOCUMENT"):
        comp_hdr: dict = {"type": "HEADER", "format": header_tipo}
        if header_handle:
            comp_hdr["example"] = {"header_handle": [header_handle]}
        componentes.append(comp_hdr)

    # BODY
    import re as _re2
    vars_encontradas = _re2.findall(r'\{\{([^}]+)\}\}', cuerpo)
    body_comp: dict = {"type": "BODY", "text": cuerpo}
    if vars_encontradas:
        example_vals = ["ejemplo"] * len(vars_encontradas)
        named_vars = [v for v in vars_encontradas if not v.isdigit()]
        if named_vars:
            body_comp["example"] = {
                "body_text_named_params": [
                    {"param_name": v, "example": ["ejemplo"]} for v in vars_encontradas
                ]
            }
        else:
            body_comp["example"] = {"body_text": [example_vals]}
    componentes.append(body_comp)

    # FOOTER
    if footer:
        componentes.append({"type": "FOOTER", "text": footer[:60]})

    # BUTTONS
    if buttons:
        btn_list = []
        for b in buttons[:10]:
            btype = b.get("type", "").upper()
            texto_btn = b.get("text", "")[:25]
            if btype == "URL":
                url_val = b.get("url", "")
                if url_val and texto_btn:
                    btn_obj = {"type": "URL", "text": texto_btn[:20], "url": url_val}
                    if "{{1}}" in url_val:
                        btn_obj["example"] = [url_val.replace("{{1}}", "ejemplo")]
                    btn_list.append(btn_obj)
            elif btype == "PHONE_NUMBER":
                phone = b.get("phone_number", "")
                if phone and texto_btn:
                    btn_list.append({"type": "PHONE_NUMBER", "text": texto_btn[:20], "phone_number": phone})
            elif btype == "QUICK_REPLY":
                if texto_btn:
                    btn_list.append({"type": "QUICK_REPLY", "text": texto_btn})
        if btn_list:
            componentes.append({"type": "BUTTONS", "buttons": btn_list})

    api_ver = "v21.0"
    url     = f"https://graph.facebook.com/{api_ver}/{template_id}"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json={"components": componentes}, headers=headers)
            data = r.json()
            if r.status_code == 200 and data.get("success"):
                logger.info(f"[plantillas] Plantilla editada id={template_id}")
                return JSONResponse(content={"ok": True})
            else:
                err = data.get("error", {})
                logger.error(f"[plantillas] Error editando plantilla: {err}")
                return JSONResponse(content={"error": err.get("message", str(data))}, status_code=400)
    except Exception as e:
        logger.error(f"[plantillas] Excepción editando: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


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
            # Fallback: construir desde el token con formato correcto de Shopify
            token = payload.get("token") or ""
            if token:
                checkout_url = f"https://equoradistribuciones.com/checkouts/cn/{token}/es"
        # Normalizar dominio: reemplazar myshopify.com por el dominio del cliente
        # y limpiar parámetros de preview/tracking innecesarios
        if checkout_url:
            import re as _re
            checkout_url = _re.sub(
                r"https://[^/]*\.myshopify\.com/",
                "https://equoradistribuciones.com/",
                checkout_url,
            )
            # Quitar preview_theme_id (solo aparece en modo preview, confunde al cliente)
            checkout_url = _re.sub(r"[&?]preview_theme_id=[^&]*", "", checkout_url)
            checkout_url = checkout_url.rstrip("?&")
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
