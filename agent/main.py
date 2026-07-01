import os
import re
import io
import csv
import json
import hmac
import hashlib
import base64
import logging
import asyncio
import random
import time
import secrets
import httpx
import bcrypt
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException, Cookie, UploadFile, File, Form
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.markers import MarkerContext, aplicar_marcadores  # noqa: F401  # registra handlers
from agent.memory import (
    inicializar_db, guardar_mensaje, obtener_historial, limpiar_historial,
    guardar_cliente, obtener_cliente, guardar_pedido_pendiente, limpiar_pedido_pendiente,
    obtener_agent_ids_por_telefono, obtener_descuento_promo, obtener_mensaje,
    construir_contexto_placeholders,
    guardar_carrito_activo, limpiar_carrito_activo, obtener_carrito_activo,
    carrito_es_fresco_para_merge,
    puede_enviar_checkout_abandono, marcar_checkout_abandono_enviado,
    registrar_mensaje_usuario, registrar_mensaje_asistente,
    marcar_followup_enviado, marcar_cierre_enviado,
    conversaciones_para_followup, conversaciones_para_cierre,
    clientes_con_carrito_abandonado,
    guardar_checkout_url, limpiar_checkout_url, clientes_con_checkout_abandonado,
    verificar_cierre_enviado,
    get_modo_humano, set_modo_humano,
    obtener_todas_conversaciones, obtener_historial_con_timestamps,
    registrar_difusion, obtener_difusiones,
    guardar_borrador_plantilla, obtener_borradores_plantillas, eliminar_borrador_plantilla,
    guardar_mensaje_difusion, actualizar_status_difusion, obtener_detalle_campana,
    actualizar_wamid_mensaje,
    obtener_metricas_internas, obtener_campana_reciente_para_telefono,
    marcar_opt_out, verificar_opt_out, revertir_opt_out, obtener_opt_outs,
    obtener_clientes_con_estado,
    get_config_value, set_config_value, get_all_config_values, cargar_config_en_env,
    guardar_cliente_import, editar_cliente,
    # Sprint 1 — SaaS multi-tenant
    crear_usuario, obtener_usuario_por_email, obtener_usuario_por_id,
    crear_sesion, verificar_sesion, cerrar_sesion,
    listar_usuarios, actualizar_usuario, obtener_agentes_de_usuario,
    # Sprint 1 — escalación multi-agente
    crear_usuario_interno, autenticar_usuario_interno, obtener_usuarios_internos,
    actualizar_usuario_interno, obtener_usuario_interno_por_id, ping_usuario_interno,
    contar_agentes_activos, obtener_o_crear_admin_interno,
    crear_ticket, obtener_tickets, contar_tickets,
    tomar_ticket, marcar_ticket_pendiente, resolver_ticket,
    obtener_ticket_activo_por_telefono, transferir_ticket,
    # Sprint 2 — notas y templates
    crear_nota_interna, obtener_notas_ticket,
    obtener_templates_rapidos, crear_template_rapido, eliminar_template_rapido,
    # Sprint 3 — auditoría, supervisor, round-robin
    registrar_evento_ticket, obtener_eventos_ticket,
    obtener_stats_equipo, obtener_siguiente_agente_roundrobin,
    # Sprint A — Pipeline
    obtener_pipeline_activo, actualizar_stages_pipeline,
    listar_deals, crear_deal, actualizar_deal, eliminar_deal,
    listar_actividades_deal, agregar_actividad_deal,
    # Pipeline Fase 2 — Calendly/integraciones
    obtener_integration_config, listar_integration_configs, guardar_integration_config,
    # Pipeline Fase 2 — flujo conversacional Calendly
    obtener_calendly_pendiente, guardar_calendly_pendiente, limpiar_calendly_pendiente,
    crear_appointment_pendiente, confirmar_appointment,
    tiene_appointment_confirmado,
)
from agent.calendly import (
    obtener_usuario as calendly_usuario,
    obtener_event_types as calendly_event_types,
    obtener_horarios_disponibles as calendly_horarios,
    crear_cita as calendly_crear_cita,
)
from agent.hubspot import obtener_portal_info as hubspot_portal_info
from agent.inbox import obtener_inbox_html, obtener_login_html, obtener_global_html, obtener_register_html
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

# ── Cache de agentes por phone_number_id ─────────────────────────────────────
# Evita consultar la BD en cada mensaje entrante para resolver el agente
_phone_agent_cache: dict[str, dict] = {}
# Sandbox hub: teléfono → agent_id del agente que validó (in-memory, se resetea al reiniciar)
_sandbox_sessions: dict[str, int] = {}


def _sandbox_code_para_agente(slug: str, agent_id: int) -> str:
    """VOCO-001 style sequential code — solo usa el agent_id como consecutivo."""
    return f"VOCO-{agent_id:03d}"


def _sandbox_codigo_a_agent_id(code: str) -> int | None:
    """'VOCO-001' → 1 (agent_id). Acepta también formato legado 'VOCO-EQ001'."""
    import re
    s = code.strip().upper().replace(" ", "")
    # Formato nuevo: VOCO-001
    m = re.match(r"^VOCO-(\d{3})$", s)
    if m:
        return int(m.group(1))
    # Formato legado: VOCO-EQ001
    m = re.match(r"^VOCO-[A-Z]{2}(\d{3})$", s)
    return int(m.group(1)) if m else None


async def _resolver_agente(phone_number_id: str) -> dict:
    """Retorna el agente para este phone_number_id. Fallback: agent_id=1 (Equora)."""
    from agent.memory import obtener_agente_por_phone_id, obtener_agente
    if phone_number_id and phone_number_id in _phone_agent_cache:
        return _phone_agent_cache[phone_number_id]
    agent = None
    if phone_number_id:
        agent = await obtener_agente_por_phone_id(phone_number_id)
        if agent:
            _phone_agent_cache[phone_number_id] = agent
    if not agent:
        agent = await obtener_agente(1)  # fallback Equora
    return agent or {"id": 1, "slug": "equora", "agent_name": "Andrea", "status": "active"}


async def _get_meta_para_agente(agent: dict) -> "ProveedorMeta":
    """Instancia ProveedorMeta con credenciales del agente (BD) o env vars (fallback)."""
    from agent.memory import get_config_value
    from agent.providers.meta import ProveedorMeta
    agent_id = agent.get("id", 1)
    access_token    = await get_config_value("META_ACCESS_TOKEN",    agent_id) or os.getenv("META_ACCESS_TOKEN", "")
    phone_number_id = await get_config_value("META_PHONE_NUMBER_ID", agent_id) or os.getenv("META_PHONE_NUMBER_ID", "")
    verify_token    = await get_config_value("META_VERIFY_TOKEN",    agent_id) or os.getenv("META_VERIFY_TOKEN", "equora-andrea-2024")
    catalog_id      = await get_config_value("META_CATALOG_ID",      agent_id) or os.getenv("META_CATALOG_ID", "")
    return ProveedorMeta(
        access_token=access_token,
        phone_number_id=phone_number_id,
        verify_token=verify_token,
        catalog_id=catalog_id,
    )


# ──────────────────────────────────────────────────────────────────────────
# #79 — Chulitos de confirmación WhatsApp (✓ enviado / ✓✓ entregado / ✓✓ leído)
#
# Bug original: el wamid (id de Meta del mensaje enviado) se leía ANTES de
# que el envío ocurriera, o se llamaba guardar_mensaje() sin pasar wamid en
# absoluto — en ~25 puntos distintos del código. Resultado: ningún mensaje
# mostraba chulitos.
#
# Para que esto NO se repita cada vez que se agregue un seguimiento, webhook
# o canal de envío nuevo, SIEMPRE usar uno de estos dos helpers en vez de
# llamar guardar_mensaje() directamente para mensajes role="assistant":
#
#   1. _guardar_con_wamid(...)        — caso normal: el envío YA ocurrió
#      (proveedor.enviar_mensaje / enviar_botones / enviar_catalogo_productos
#      / etc. ya se llamó) y ahora hay que persistir el mensaje en historial.
#
#   2. _vincular_wamid_post_envio(...) — caso especial: el mensaje ya se
#      guardó en BD ANTES del envío real (ej. el texto de Andrea se fusiona
#      con un mensaje de catálogo/CTA que se arma más abajo). Llamar esto
#      justo después del envío real para vincular el wamid al row existente.
# ──────────────────────────────────────────────────────────────────────────

async def _guardar_con_wamid(
    proveedor_local, telefono: str, contenido: str, agent_id: int = 1,
    role: str = "assistant",
) -> int:
    """Guarda un mensaje en el historial capturando el wamid del envío que
    se acaba de hacer con proveedor_local (lee proveedor_local.ultimo_wamid,
    poblado por CUALQUIER método de envío del provider — enviar_mensaje,
    enviar_botones, enviar_catalogo_productos, enviar_producto, etc.).

    Llamar SIEMPRE justo después de un envío exitoso en vez de invocar
    guardar_mensaje() a mano — evita repetir el bug de #79. Retorna el id
    de la fila guardada (útil si luego hace falta _vincular_wamid_post_envio)."""
    wamid = getattr(proveedor_local, "ultimo_wamid", "") or ""
    return await guardar_mensaje(
        telefono, role, contenido, agent_id=agent_id,
        wamid=wamid, status="sent" if wamid else "",
    )


async def _vincular_wamid_post_envio(proveedor_local, msg_id: int) -> None:
    """Vincula el wamid del último envío al row de historial que YA se
    guardó antes de que el envío ocurriera (caso: texto absorbido por un
    mensaje de catálogo/CTA armado más abajo). No hace nada si no hay
    wamid (envío falló) o msg_id es 0 (guardar_mensaje no se llamó)."""
    if not msg_id:
        return
    wamid = getattr(proveedor_local, "ultimo_wamid", "") or ""
    if wamid:
        await actualizar_wamid_mensaje(msg_id, wamid)

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
CHECKOUT_COOLDOWN_MIN      = int(os.getenv("CHECKOUT_COOLDOWN_MIN", 360))  # min entre avisos (6h)
# Nota: el cooldown vive en memoria (_checkout_abandono_notif). Si Railway
# reinicia entre avisos, el dict se borra y puede duplicar. Para evitar
# eso completamente habría que persistirlo en BD — backlog Sprint A día 2.
CHECKOUT_ABANDONO_COOLDOWN_SEG = CHECKOUT_COOLDOWN_MIN * 60

# Loop general
CHECK_INTERVAL_SEG   = int(os.getenv("CHECK_INTERVAL_SEG", 30))   # segundos entre cada ciclo del loop

# #77 — Watchdog del loop de seguimientos. Si _loop_seguimientos() no
# arranca un ciclo nuevo en WATCHDOG_UMBRAL_SEG, se asume colgado (ej. una
# llamada externa sin timeout que nunca retorna) y se fuerza un reinicio
# del proceso (Railway lo reinicia automáticamente al detectar el crash).
WATCHDOG_UMBRAL_SEG = max(300, CHECK_INTERVAL_SEG * 10)  # al menos 5 min
_ultimo_ciclo_seguimiento: float = 0.0  # time.monotonic() del último ciclo arrancado

# Legacy (no usados activamente, se conservan por compatibilidad)
ABANDONO_MIN_INACTIVO = CARRITO_MIN_MIN
ABANDONO_MAX_INACTIVO = CARRITO_MAX_MIN
_abandono_notif: dict[str, float] = {}
ABANDONO_COOLDOWN_SEG = CARRITO_UNIF_COOLDOWN_SEG
_carrito_unif_cooldown: dict[str, float] = {}
_carrito_ultimo_estado: dict[str, int] = {}   # phone → último estado enviado (3, 4 ó 5)
_checkout_abandono_notif: dict[str, float] = {}

# Mensajes del sistema — ahora configurables por agente desde el panel.
# Defaults en agent/mensajes.py:MENSAJES. Cada agente puede personalizarlos
# desde Configuración → Mensajes sin tocar código.
# Keys:
#   system.followup          ← era MENSAJE_FOLLOWUP
#   system.cierre            ← era MENSAJE_CIERRE
#   system.checkout_abandono ← era MENSAJE_CHECKOUT_ABANDONO


async def _resolver_agent_id_principal(telefono: str) -> int:
    """Resuelve el agent_id principal de un cliente para enviar mensajes.

    Si el cliente existe bajo varios agents, retorna el primero (estable
    por ID). Si no existe en BD aún, fallback a 1 (legacy/seed). En
    flujos verdaderamente multi-tenant, el caller debería pasar agent_id
    explícito en lugar de invocar este helper.
    """
    aids = await obtener_agent_ids_por_telefono(telefono)
    return aids[0] if aids else 1


async def _total_carrito_fmt(telefono: str, agent_id: int) -> str:
    """Suma los subtotales del carrito_activo del cliente y devuelve string
    formateado tipo COP ('45.700'), o vacío si no hay carrito.

    Útil para inyectar {total} en el contexto de mensajes que se envían
    desde handlers de botón (donde no tenemos el total dinámico calculado
    de antemano como sí lo tenemos en los Estados 4/5 del flujo principal).
    """
    try:
        from agent.memory import obtener_carrito_activo
        items = await obtener_carrito_activo(telefono, agent_id=agent_id)
    except Exception:
        return ""
    if not items:
        return ""
    total = 0
    for it in items:
        sub = it.get("subtotal")
        if sub is None:
            qty = int(it.get("cantidad", it.get("quantity", 1)) or 1)
            pu  = int(it.get("precio_unitario", 0) or 0)
            sub = qty * pu
        try:
            total += int(sub)
        except (TypeError, ValueError):
            pass
    if total <= 0:
        return ""
    return f"{total:,}".replace(",", ".")

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
    await cargar_config_en_env()   # carga credenciales guardadas en BD → os.environ

    # Pre-cargar defaults de tools.py en os.environ para que el panel de configuración
    # muestre el estado real aunque los valores vengan del código y no de Railway env vars
    from agent.tools import SHOPIFY_STORE
    if SHOPIFY_STORE and not os.environ.get("SHOPIFY_STORE"):
        os.environ["SHOPIFY_STORE"] = SHOPIFY_STORE
        logger.debug("[config] SHOPIFY_STORE pre-cargado desde defaults de tools.py")

    # Verificar que agente Equora (agent_id=1) existe
    from agent.memory import obtener_agente
    equora = await obtener_agente(1)
    if equora:
        logger.info(f"Agente Equora activo: {equora['agent_name']} ({equora['status']})")
    logger.info("Base de datos inicializada y configuración cargada")
    # Pre-calentar catálogo Shopify al arrancar para que _variant_map esté listo
    # antes de que llegue cualquier petición a /tienda/confirmar
    try:
        await obtener_catalogo_shopify()
        logger.info("Catálogo Shopify pre-cargado al arrancar ✅")
    except Exception as e:
        logger.warning(f"No se pudo pre-cargar catálogo Shopify al arrancar: {e}")
    # Pre-cargar SINCRÓNICAMENTE el catálogo de Facebook (retailer_ids) para
    # que product_list funcione desde el primer mensaje. Antes se lanzaba como
    # background task y la primera petición podía llegar con _fb_items vacío.
    try:
        from agent.tools import _cargar_fb_catalog, _fb_items
        await _cargar_fb_catalog()
        logger.info(f"Catálogo Facebook pre-cargado: {len(_fb_items)} items ✅")
    except Exception as e:
        logger.warning(f"No se pudo pre-cargar catálogo Facebook al arrancar: {e}")
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
    watchdog_task = asyncio.create_task(_watchdog_seguimientos())
    try:
        yield
    finally:
        seguimiento_task.cancel()
        watchdog_task.cancel()
        for t in (seguimiento_task, watchdog_task):
            try:
                await t
            except asyncio.CancelledError:
                pass


async def _loop_seguimientos():
    """Cada CHECK_INTERVAL_SEG revisa conversaciones inactivas.
    Prioridad: cierre > checkout abandonado > carrito (estados 3-5) > follow-up genérico."""
    global _ultimo_ciclo_seguimiento
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SEG)
            # Marcar el ciclo ANTES de procesar — si alguna de las 4 llamadas
            # se cuelga (ej. await sin timeout que nunca retorna), este
            # timestamp deja de avanzar y _watchdog_seguimientos lo detecta.
            _ultimo_ciclo_seguimiento = time.monotonic()
            await _procesar_abandono_checkout()     # prioridad 2: checkout sin completar
            await _procesar_carrito_unificado()     # prioridad 3-5: carrito activo
            await _procesar_followups()             # prioridad 6: sin carrito, sin checkout
            await _procesar_cierres()               # cierre tras follow-up genérico
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error en loop de seguimientos: {e}")


async def _watchdog_seguimientos():
    """#77 — vigila que _loop_seguimientos() siga ticando. Revisa cada
    minuto; si pasó WATCHDOG_UMBRAL_SEG sin que arranque un ciclo nuevo,
    el proceso se asume colgado y se fuerza su salida con os._exit(1) —
    Railway reinicia automáticamente el contenedor al detectar el crash."""
    while True:
        await asyncio.sleep(60)
        if _ultimo_ciclo_seguimiento == 0:
            continue  # aún no corrió el primer ciclo (deploy recién hecho)
        inactivo_seg = time.monotonic() - _ultimo_ciclo_seguimiento
        if inactivo_seg > WATCHDOG_UMBRAL_SEG:
            logger.critical(
                f"[watchdog] _loop_seguimientos sin ticar hace {inactivo_seg:.0f}s "
                f"(umbral {WATCHDOG_UMBRAL_SEG}s) — forzando reinicio del proceso"
            )
            os._exit(1)


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
    gratis_fmt = f"{umbral_gratis:,}".replace(",", ".")

    async def _resolver_pedido_minimo(tel: str) -> int:
        """Lee PEDIDO_MINIMO del config_value del agente principal del cliente.
        Fallback a la env var global. Esto evita usar el 50000 hardcoded
        cuando el merchant configuró otro valor en el panel."""
        try:
            from agent.memory import get_config_value
            aid = await _resolver_agent_id_principal(tel)
            raw = await get_config_value("PEDIDO_MINIMO", aid)
            if raw:
                return int(str(raw).strip() or 0) or PEDIDO_MINIMO
        except Exception:
            pass
        return PEDIDO_MINIMO

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

        # Si la conversación fue escalada a un humano (modo_humano=1), NO enviar
        # seguimientos automáticos — el agente humano se encarga.
        if await get_modo_humano(telefono):
            logger.info(f"[seguimiento-carrito] {telefono} en modo humano — saltando")
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

        # Resolver PEDIDO_MINIMO del agente (por config_value, no el global).
        # Esto fixa el bug donde el seguimiento decía "$50.000" aún cuando el
        # merchant configuró otro valor (ej. 25000) en el panel.
        pedido_minimo_local = await _resolver_pedido_minimo(telefono)
        minimo_fmt = f"{pedido_minimo_local:,}".replace(",", ".")

        # Verificar que el estado corresponde a la ventana de tiempo correcta
        # Estado 3 (< mínimo): solo si pasó CARRITO_MIN_MIN
        # Estados 4-5 (≥ mínimo): solo si pasó CROSSSELL_MIN_MIN
        if total < pedido_minimo_local and not en_min:
            logger.info(f"Carrito {telefono}: ${total:,} < mínimo ${pedido_minimo_local}, aún no han pasado {CARRITO_MIN_MIN} min — esperando")
            continue  # Aún no es tiempo para el aviso de pedido mínimo
        if total >= pedido_minimo_local and not en_cross:
            logger.info(f"Carrito {telefono}: ${total:,} ≥ mínimo ${pedido_minimo_local}, aún no han pasado {CROSSSELL_MIN_MIN} min — esperando")
            continue  # Aún no es tiempo para el cross-sell

        # Calcular estado actual para detectar cambios
        estado_actual = 3 if total < pedido_minimo_local else (4 if total < umbral_gratis else 5)

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
            # Pasamos items con retailer_id para que Meta haga match con catálogo
            if estado_anterior == 3 and estado_actual in (4, 5):
                asyncio.create_task(capi_initiate_checkout(telefono, total, productos=items))

        # Cooldown: no re-notificar el mismo estado en CARRITO_COOLDOWN_MIN minutos
        elapsed_min = (ahora - _carrito_unif_cooldown.get(telefono, 0)) / 60
        if ahora - _carrito_unif_cooldown.get(telefono, 0) < CARRITO_UNIF_COOLDOWN_SEG:
            logger.info(
                f"Carrito {telefono}: estado {estado_actual} (${total:,}) — "
                f"cooldown activo ({elapsed_min:.1f}/{CARRITO_COOLDOWN_MIN} min) — saltando"
            )
            continue

        # ── Verificación VIVA del carrito antes de mandar ───────────────
        # El loop captura items en `clientes_con_carrito_abandonado` y luego
        # los procesa. Entre esos 2 momentos el cliente puede haber vaciado
        # con [[VACIAR_CARRITO]] o confirmado pedido. Re-leer en vivo evita
        # mandar mensajes obsoletos tipo "tienes $42k" cuando ya vació.
        items_vivos = await obtener_carrito_activo(telefono)
        if not items_vivos:
            logger.info(f"[carrito-loop] {telefono} carrito vacío en BD viva — cancelando seguimiento")
            continue
        items = items_vivos
        total = _calcular_total_carrito(items)
        if total <= 0:
            continue
        # Re-calcular estado actual con el total vivo (puede haber cambiado)
        estado_actual = 3 if total < pedido_minimo_local else (4 if total < umbral_gratis else 5)

        nombres_en_carrito = {p.get("producto", "").lower() for p in items}
        total_fmt = f"{total:,}".replace(",", ".")

        # ── Detectar flujo activo del cliente ───────────────────────────
        # Si algún item tiene retailer_id, el cliente está en flujo WhatsApp
        # catálogo nativo → seguimientos deben respetar ese flujo.
        flujo_wa = any(p.get("retailer_id") for p in items)
        costo_envio_loc = obtener_costo_envio()

        # Si no es flujo_wa pero llegó hasta acá → no tiene retailer_ids,
        # probablemente carrito antiguo o de origen web. NO mandamos nada:
        # mejor silencioso que mandar link a tienda y romper la coherencia.
        if not flujo_wa:
            logger.info(f"[carrito-loop] {telefono} sin retailer_ids (no nativo) — cancelando")
            continue

        # Provider del agente real del cliente — NUNCA el singleton global
        # `proveedor` (solo tiene credenciales del agente por defecto).
        # Usarlo enviaría el seguimiento desde el número de WhatsApp
        # equivocado para cualquier otro agente (Meta acepta el envío,
        # pero el cliente nunca lo recibe en su chat real).
        proveedor = await _get_meta_para_agente({"id": await _resolver_agent_id_principal(telefono)})

        async def _crear_checkout_para_seguimiento() -> str | None:
            """Crea un checkout de Shopify a partir de los items del carrito
            y guarda la URL en el cliente. Retorna la URL o None si falla."""
            if not flujo_wa:
                return None
            try:
                productos_check = []
                for p in items:
                    qty = int(p.get("cantidad", p.get("quantity", 1)))
                    productos_check.append({
                        "producto":      p.get("producto", ""),
                        "presentacion":  p.get("presentacion", ""),
                        "cantidad":      qty,
                        "precio_unitario": p.get("precio_unitario", 0),
                        "subtotal":      p.get("subtotal", 0),
                    })
                checkout_url_seg = await crear_checkout_shopify(
                    telefono, {"productos": productos_check, "total": total}
                )
                if checkout_url_seg:
                    await guardar_checkout_url(telefono, checkout_url_seg)
                    logger.info(f"[seguimiento] Checkout creado para {telefono}: {checkout_url_seg}")
                return checkout_url_seg
            except Exception as e:
                logger.error(f"[seguimiento] No pude crear checkout: {e}")
                return None

        try:
            if total < pedido_minimo_local:
                # ── Estado 3: bajo el mínimo ──────────────────────────────
                # Texto configurable por agente (puede apagarse si el negocio
                # no maneja pedido mínimo). Si está desactivado, no enviamos
                # nada — el cliente no es interrumpido.
                falta = pedido_minimo_local - total
                falta_fmt = f"{falta:,}".replace(",", ".")
                sugeridos = _sugerir_productos(nombres_en_carrito)
                lineas = "\n".join(f"✅ {s}" for s in sugeridos)
                from agent.mensajes import format_seguro as _fmt_est3
                _aid_est3 = await _resolver_agent_id_principal(telefono)
                _ctx_est3 = await construir_contexto_placeholders(_aid_est3)
                _ctx_est3["total"]  = total_fmt
                _ctx_est3["falta"]  = falta_fmt
                _ctx_est3["minimo"] = minimo_fmt
                msg = _fmt_est3(
                    await obtener_mensaje(_aid_est3, "cart.estado3_falta_minimo"),
                    _ctx_est3,
                )
                if not msg:
                    logger.info(f"[carrito-est3] {telefono} desactivado para agent={_aid_est3} — saltando")
                    continue
                if lineas:
                    msg += f"\n\nMuchos clientes agregan:\n{lineas}"

                enviado_seg = False
                if hasattr(proveedor, "enviar_catalogo_productos"):
                    try:
                        from agent.tools import obtener_secciones_catalogo_async
                        secciones = await obtener_secciones_catalogo_async(None)
                        if secciones:
                            # TODO multi-tenant: hoy seguimiento automatico asume
                            # agent_id=1 (Equora). En Sprint B agregar agent_id a
                            # clientes_con_carrito_abandonado y propagar.
                            header_cat = await _catalogo_header_for_agent(1)
                            enviado_seg = await proveedor.enviar_catalogo_productos(
                                telefono, header_cat, msg[:1024], secciones,
                            )
                    except Exception as e:
                        logger.warning(f"[carrito-est3] product_list falló: {e}")
                if not enviado_seg:
                    # Silencio: NO mandar link a tienda web (rompe el flujo
                    # del catálogo nativo). El cliente puede seguir interactuando
                    # con Andrea por iniciativa propia.
                    logger.info(f"[carrito-est3] {telefono} product_list no disponible — cancelando silencioso")
                    continue
                # Persistir el mensaje del seguimiento (panel lo necesita).
                await _guardar_con_wamid(proveedor, telefono, msg)

                # Mensaje complementario con botones Ver/Vaciar carrito —
                # SIEMPRE accesibles para el cliente (acciones determinísticas).
                # (En Estado 3 no incluimos "Confirmar pedido" porque aún no
                # alcanza el mínimo.)
                if hasattr(proveedor, "enviar_botones_reply"):
                    try:
                        texto_botones = "¿Quieres gestionar tu carrito?"
                        await proveedor.enviar_botones_reply(
                            telefono, texto_botones,
                            _botones_carrito_estandar(ofrece_confirmar=False),
                        )
                    except Exception as e:
                        logger.warning(f"[carrito-est3] botones complementarios fallaron: {e}")

            elif total < umbral_gratis:
                # ── Estado 4 (timer seguimiento): sobre el mínimo, recordar ──
                # Mensaje configurable por agente con placeholders dinámicos.
                # Eliminamos las 3 ramas condicionales por ciudad — el cliente
                # personaliza su template según su modelo de negocio (zonas,
                # envío gratis, transportadora, etc.). El default es neutral
                # equivalente al caso "sin ciudad confirmada" del código previo.
                falta = umbral_gratis - total
                falta_fmt = f"{falta:,}".replace(",", ".")
                sugeridos = _sugerir_productos(nombres_en_carrito)
                lineas = "\n".join(f"✅ {s}" for s in sugeridos)
                from agent.mensajes import format_seguro as _fmt_est4t
                _aid_est4t = await _resolver_agent_id_principal(telefono)
                _ctx_est4t = await construir_contexto_placeholders(_aid_est4t)
                _ctx_est4t["total"] = total_fmt
                _ctx_est4t["falta_envio_gratis"] = falta_fmt
                msg = _fmt_est4t(
                    await obtener_mensaje(_aid_est4t, "cart.estado4_timer"),
                    _ctx_est4t,
                )
                if not msg:
                    logger.info(f"[carrito-est4-timer] {telefono} desactivado para agent={_aid_est4t} — saltando")
                    continue
                if lineas:
                    msg += f"\n\nMuchos clientes también llevan:\n{lineas}"

                # Solo flujo nativo (validado al inicio del loop con flujo_wa).
                # Estrategia con carrito determinístico:
                #   1) Crear checkout en Shopify para tener URL de pago lista.
                #   2) Mandar 3 reply buttons SIEMPRE iguales: Confirmar + Ver + Vaciar.
                #      (Quitamos "Envío gratis" porque "Ver carrito" da info equivalente
                #       y queremos que SIEMPRE el cliente tenga botones para operar el carrito.)
                #   3) Si fallan los botones → product_list (catálogo nativo).
                #   4) Si product_list también falla → silencio (no tienda web).
                checkout_url_seg = await _crear_checkout_para_seguimiento()
                botones_seg = False
                if checkout_url_seg and hasattr(proveedor, "enviar_botones_reply"):
                    try:
                        botones_seg = await proveedor.enviar_botones_reply(
                            telefono, msg,
                            _botones_carrito_estandar(ofrece_confirmar=True),
                        )
                    except Exception as e:
                        logger.warning(f"[carrito-est4] botones reply fallaron: {e}")
                if not botones_seg:
                    enviado_pl = False
                    if hasattr(proveedor, "enviar_catalogo_productos"):
                        try:
                            from agent.tools import obtener_secciones_catalogo_async
                            secciones = await obtener_secciones_catalogo_async(None)
                            if secciones:
                                header_cat = await _catalogo_header_for_agent(1)
                                enviado_pl = await proveedor.enviar_catalogo_productos(
                                    telefono, header_cat, msg[:1024], secciones,
                                )
                        except Exception as e:
                            logger.warning(f"[carrito-est4] product_list falló: {e}")
                    if not enviado_pl:
                        logger.info(f"[carrito-est4] {telefono} ningún canal nativo funcionó — cancelando silencioso")
                        continue
                await _guardar_con_wamid(proveedor, telefono, msg)

            else:
                # ── Estado 5 (timer de seguimiento): pedido alto, invitar a pagar ──
                # Mismo enfoque que el flujo en vivo: mensaje configurable por agente.
                # Eliminamos las 3 ramas condicionales por ciudad — el cliente personaliza
                # su template según su modelo (si quiere distinguir por zona, usa
                # placeholders en el texto; si no, mensaje único).
                from agent.mensajes import format_seguro
                aid_seg = await _resolver_agent_id_principal(telefono)
                _ctx_seg = await construir_contexto_placeholders(aid_seg)
                _ctx_seg["total"] = total_fmt
                msg = format_seguro(
                    await obtener_mensaje(aid_seg, "cart.checkout_listo_texto"),
                    _ctx_seg,
                )
                # Estado 5: cliente ya está sobre el envío gratis o ya alcanzó
                # el mínimo (no Cali). Crear checkout y mandarle el botón.
                # El checkout_url ES Shopify pago — flujo legítimo, no es "tienda web".
                checkout_url_seg = await _crear_checkout_para_seguimiento()
                if not checkout_url_seg:
                    # Sin checkout_url no podemos completar el pago — escalar
                    logger.warning(f"[carrito-est5] {telefono} no se pudo crear checkout — escalando")
                    await _escalar_meta_fallo(
                        telefono,
                        motivo_corto="no se pudo crear checkout",
                        contexto_extra=f"Cliente con carrito de ${total_fmt} listo para pagar. Shopify checkout falló.",
                    )
                    continue
                enviado_seg = False
                if hasattr(proveedor, "enviar_cta_url"):
                    try:
                        enviado_seg = await proveedor.enviar_cta_url(
                            telefono, msg, "Confirmar pedido", checkout_url_seg
                        )
                    except Exception as e:
                        logger.warning(f"[carrito-est5] cta_url falló: {e}")
                if not enviado_seg:
                    # Fallback texto con la URL del checkout (sigue siendo Shopify pago)
                    await proveedor.enviar_mensaje(telefono, f"{msg}\n\n👉 {checkout_url_seg}")

                # Persistir el mensaje del seguimiento (panel lo necesita).
                await _guardar_con_wamid(proveedor, telefono, msg)

                # Mensaje complementario con botones Ver/Vaciar — el cliente
                # SIEMPRE debe poder revisar/limpiar su carrito antes de pagar.
                if hasattr(proveedor, "enviar_botones_reply"):
                    try:
                        await proveedor.enviar_botones_reply(
                            telefono, "¿Quieres revisar antes de confirmar?",
                            _botones_carrito_estandar(ofrece_confirmar=False),
                        )
                    except Exception as e:
                        logger.warning(f"[carrito-est5] botones complementarios fallaron: {e}")

            _carrito_unif_cooldown[telefono] = ahora
            _carrito_ultimo_estado[telefono] = estado_actual
            logger.info(f"Seguimiento carrito estado {estado_actual} → {telefono} (${total_fmt})")

        except Exception as e:
            logger.error(f"Error en seguimiento carrito {telefono}: {e}")


# Keywords que indican que la conversación se cerró naturalmente. Se
# matchean SOLO contra los últimos 1-2 mensajes (no historial completo)
# para evitar falsos positivos de saludos viejos. Lowercase + sin tildes.
_CIERRE_USER_KW = (
    "gracias", "muchas gracias", "ok gracias", "perfecto", "listo",
    "vale", "ya recibí", "ya recibi", "todo bien", "nos vemos",
    "chao", "chau", "adiós", "adios", "hasta luego", "hasta pronto",
    "que tengas", "buen dia", "buena tarde", "buena noche",
)
_CIERRE_ASSISTANT_KW = (
    "que disfrutes", "estamos para servirte", "para servirte",
    "cualquier cosa", "vuelve cuando", "hasta pronto", "hasta luego",
    "que tengas", "feliz dia", "feliz día", "feliz tarde", "feliz noche",
    "un gusto", "un placer", "fue un gusto", "que tengas un",
)


def _texto_normalizado(s: str) -> str:
    """Lowercase + quita tildes para matching case/accent-insensitive."""
    import unicodedata as _u
    s = _u.normalize("NFKD", s or "")
    return "".join(c for c in s if not _u.combining(c)).lower()


async def _conversacion_cerrada_naturalmente(telefono: str, aid: int) -> bool:
    """True si los últimos mensajes indican una despedida natural — para
    NO disparar el follow-up genérico. Heurística defensiva: el backend no
    confía en que el LLM emita un marcador de cierre.

    Reglas:
      · El último mensaje es de assistant Y contiene keyword de despedida
      · El penúltimo es user con gracias/cierre Y el último es assistant
        con respuesta corta (acuse) — patrón "gracias / de nada"
    """
    try:
        hist = await obtener_historial(telefono, limite=4, agent_id=aid)
    except Exception:
        return False
    if not hist:
        return False
    ultimo = hist[-1]
    ultimo_rol = ultimo.get("role", "")
    ultimo_txt = _texto_normalizado(ultimo.get("content", ""))
    if ultimo_rol == "assistant" and any(kw in ultimo_txt for kw in _CIERRE_ASSISTANT_KW):
        return True
    # Patrón "user dice gracias → assistant responde" (sin keyword fuerte de despedida)
    if ultimo_rol == "assistant" and len(hist) >= 2:
        penultimo = hist[-2]
        if penultimo.get("role") == "user":
            pen_txt = _texto_normalizado(penultimo.get("content", ""))
            if any(kw in pen_txt for kw in _CIERRE_USER_KW):
                return True
    return False


async def _procesar_followups():
    """Estado 6: sin carrito, sin checkout. Follow-up genérico una sola vez."""
    telefonos = await conversaciones_para_followup(FOLLOWUP_MIN, FOLLOWUP_MAX_HORAS)
    for telefono in telefonos:
        # No enviar followups si la conversación está escalada a humano
        if await get_modo_humano(telefono):
            logger.info(f"[followup] {telefono} en modo humano — saltando")
            continue
        try:
            aid = await _resolver_agent_id_principal(telefono)
            # Si hay cita confirmada reciente, Calendly ya notificó al cliente —
            # no insistir con follow-up de ventas encima.
            if await tiene_appointment_confirmado(telefono, aid):
                logger.info(f"[followup] {telefono} tiene cita confirmada — saltando follow-up")
                await marcar_cierre_enviado(telefono)
                continue
            # Heurística defensiva: si la conversación cerró natural
            # (gracias / despedida) NO insistir con follow-up. Marcamos
            # como cerrado para que el timer no vuelva a evaluarlo.
            if await _conversacion_cerrada_naturalmente(telefono, aid):
                logger.info(f"[followup] {telefono} cerrada naturalmente — marcando y saltando")
                await marcar_cierre_enviado(telefono)
                continue
            texto = await obtener_mensaje(aid, "system.followup")
            if not texto:
                # El agente desactivó este mensaje desde el panel — no insistir
                logger.info(f"[followup] {telefono} mensaje desactivado para agent={aid} — saltando")
                continue
            _prov = await _get_meta_para_agente({"id": aid})
            await _prov.enviar_mensaje(telefono, texto)
            await _guardar_con_wamid(_prov, telefono, texto, agent_id=aid)
            await marcar_followup_enviado(telefono)
            logger.info(f"Follow-up enviado a {telefono}")
        except Exception as e:
            logger.error(f"Error enviando follow-up a {telefono}: {e}")


async def _procesar_cierres():
    """Estado 6: cierre tras follow-up genérico sin respuesta."""
    telefonos = await conversaciones_para_cierre(CIERRE_MIN)
    for telefono in telefonos:
        # No enviar cierres si la conversación está escalada a humano
        if await get_modo_humano(telefono):
            logger.info(f"[cierre] {telefono} en modo humano — saltando")
            continue
        try:
            aid = await _resolver_agent_id_principal(telefono)
            # Si hay cita confirmada reciente, no enviar cierre de ventas
            if await tiene_appointment_confirmado(telefono, aid):
                logger.info(f"[cierre] {telefono} tiene cita confirmada — saltando cierre")
                await marcar_cierre_enviado(telefono)
                continue
            texto = await obtener_mensaje(aid, "system.cierre")
            if not texto:
                logger.info(f"[cierre] {telefono} mensaje desactivado para agent={aid} — saltando")
                # Aún así marcar como cerrado para que el timer no vuelva a evaluarlo
                await marcar_cierre_enviado(telefono)
                continue
            _prov = await _get_meta_para_agente({"id": aid})
            await _prov.enviar_mensaje(telefono, texto)
            await _guardar_con_wamid(_prov, telefono, texto, agent_id=aid)
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
    clientes = await clientes_con_checkout_abandonado(
        min_min=CHECKOUT_ABANDONO_MIN,
        max_min=CHECKOUT_ABANDONO_MAX,
    )
    for telefono, checkout_url_raw in clientes:
        # Defensa: si el cliente ya no tiene carrito activo (vació explícito
        # o el TTL del carrito expiró), NO mandar recuperación de checkout
        # — es incoherente con su intención. Marcamos como enviado para que
        # el timer no reintente.
        carrito_vivo = await obtener_carrito_activo(telefono)
        if not carrito_vivo:
            logger.info(f"[checkout-abandono] {telefono} sin carrito activo — saltando y marcando")
            await limpiar_checkout_url(telefono)
            await marcar_checkout_abandono_enviado(telefono)
            continue

        # AUTOREPARAR si el URL guardado es corrupto (ej. solo la home).
        # Antes: saltábamos silencioso, lo que dejaba al cliente sin botón.
        # Ahora: recreamos checkout desde carrito_activo si está disponible.
        if not _es_url_checkout_valida(checkout_url_raw):
            logger.warning(
                f"[checkout-abandono] URL corrupta para {telefono} — intentando recrear"
            )
            checkout_url = await _obtener_o_recrear_checkout_url(telefono)
            if not checkout_url:
                logger.warning(f"[checkout-abandono] {telefono} sin checkout válido — saltando")
                continue
        else:
            checkout_url = checkout_url_raw
        # Cooldown PERSISTENTE (BD, no memoria) — sobrevive deploys de Railway
        if not await puede_enviar_checkout_abandono(telefono, CHECKOUT_COOLDOWN_MIN):
            continue
        try:
            aid = await _resolver_agent_id_principal(telefono)
            texto = await obtener_mensaje(aid, "system.checkout_abandono")
            if not texto:
                logger.info(f"[checkout-abandono] {telefono} mensaje desactivado para agent={aid} — saltando")
                # Marcar como enviado para evitar reintentos dentro del cooldown
                await marcar_checkout_abandono_enviado(telefono)
                continue
            _prov = await _get_meta_para_agente({"id": aid})
            enviado = False
            if hasattr(_prov, "enviar_cta_url"):
                try:
                    enviado = await _prov.enviar_cta_url(
                        telefono,
                        texto,
                        "Terminar pedido ✅",
                        checkout_url,
                    )
                except Exception:
                    pass
            if not enviado:
                await _prov.enviar_mensaje(
                    telefono,
                    f"{texto}\n\n👉 {checkout_url}"
                )
            await _guardar_con_wamid(_prov, telefono, texto, agent_id=aid)
            await marcar_checkout_abandono_enviado(telefono)
            logger.info(f"Recuperación de checkout enviada a {telefono}")
        except Exception as e:
            logger.error(f"Error enviando recuperación de checkout a {telefono}: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Helper: escalar cuando Meta product_list falla en un flujo que requiere respuesta
# ──────────────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
# Helper SaaS: header del catálogo dinámico por agente
# ──────────────────────────────────────────────────────────────────────────────
# Cache simple en memoria — el nombre del agente no cambia en runtime normal.
# Si cambia (rename desde panel), se refresca cuando el proceso se reinicia.
_catalogo_header_cache: dict[int, str] = {}

async def _catalogo_header_for_agent(agent_id: int) -> str:
    """Devuelve el texto que va en el header del product_list de WhatsApp.

    Prioridad:
      1. config_value 'CATALOGO_HEADER' del agente (si el cliente lo personalizó)
      2. Nombre del negocio del agente (Agent.name)
      3. Genérico "Catálogo 🌿"

    Esto reemplaza el "Catálogo Biotú 🌿" hardcoded que rompía SaaS multi-tenant.
    """
    if agent_id in _catalogo_header_cache:
        return _catalogo_header_cache[agent_id]
    try:
        # 1. Override explícito desde config_values
        custom = await get_config_value("CATALOGO_HEADER", agent_id)
        if custom and custom.strip():
            _catalogo_header_cache[agent_id] = custom.strip()[:60]
            return _catalogo_header_cache[agent_id]
        # 2. Nombre del negocio
        from agent.memory import obtener_agente
        agent = await obtener_agente(agent_id)
        if agent:
            nombre = (agent.get("name") or "").strip()
            if nombre:
                # "Catálogo {Nombre del negocio} 🌿" — corto a 60 chars (límite Meta)
                header = f"Catálogo {nombre} 🌿"[:60]
                _catalogo_header_cache[agent_id] = header
                return header
    except Exception as e:
        logger.warning(f"[catalogo-header] fallback genérico (error: {e})")
    # 3. Fallback genérico
    _catalogo_header_cache[agent_id] = "Catálogo 🌿"
    return "Catálogo 🌿"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de carrito determinístico (backend-managed, no LLM)
# ──────────────────────────────────────────────────────────────────────────────
def _botones_carrito_estandar(ofrece_confirmar: bool = False) -> list[dict]:
    """Devuelve los reply buttons que SIEMPRE acompañan mensajes del sistema
    cuando hay carrito activo. Garantiza que el cliente NUNCA dependa del LLM
    para ver/vaciar — son acciones determinísticas del backend.

    Si ofrece_confirmar=True (Estados 4-5) incluye el botón Confirmar pedido
    como primero (mayor visibilidad para cerrar venta). Si False (Estado 3),
    solo Ver + Vaciar.

    Meta limita a 3 reply buttons por mensaje — respetamos ese tope.
    """
    botones = []
    if ofrece_confirmar:
        botones.append({"id": "act_confirmar_pedido", "title": "Confirmar pedido ✅"})
    botones.append({"id": "act_ver_carrito",   "title": "Ver carrito 🛒"})
    botones.append({"id": "act_vaciar_carrito", "title": "Vaciar carrito 🗑"})
    return botones


def _botones_post_pedido() -> list[dict]:
    """Botones estilo Jelou que se envían cuando el cliente confirma pedido
    y el checkout está listo. 3 opciones:
      💳 Ir al pago    → enviará el invoice_url del Draft Order
      🔍 Agregar más   → reabre el catálogo para sumar productos
      🛒 Ver mi carrito → reenvía resumen del carrito actual
    """
    return [
        {"id": "act_ir_pago",      "title": "💳 Ir al pago"},
        {"id": "act_agregar_mas",  "title": "🔍 Agregar más"},
        {"id": "act_ver_carrito",  "title": "🛒 Ver mi carrito"},
    ]


async def _enviar_resumen_carrito(telefono: str, agent_id: int = 1) -> bool:
    """Lee el carrito_activo de BD y envía un resumen determinístico al cliente.
    Se llama desde el handler act_ver_carrito. NUNCA delega al LLM — el backend
    es el único source of truth del estado del carrito.

    Returns: True si envió, False si carrito vacío (manda mensaje aparte).
    """
    # Provider del agente correcto — NUNCA el singleton global `proveedor`,
    # que solo tiene las credenciales del agente por defecto (id=1). Usarlo
    # acá enviaría desde el número de WhatsApp equivocado para cualquier
    # otro agente: Meta acepta el envío (200 OK, wamid válido → chulito ✓
    # en el panel) pero el cliente nunca lo recibe en su chat real.
    proveedor = await _get_meta_para_agente({"id": agent_id})
    carrito = await obtener_carrito_activo(telefono, agent_id=agent_id)
    if not carrito:
        msg_vacio = "🛒 Tu carrito está vacío en este momento.\n\nCuando agregues productos te lo confirmo aquí."
        await proveedor.enviar_mensaje(telefono, msg_vacio)
        await _guardar_con_wamid(proveedor, telefono, msg_vacio, agent_id=agent_id)
        return False

    lineas_items = []
    total = 0
    for item in carrito:
        cantidad = int(item.get("cantidad", item.get("quantity", 1)))
        producto = item.get("producto", "Producto")
        presentacion = item.get("presentacion", "")
        subtotal = int(item.get("subtotal", 0))
        precio_u = int(item.get("precio_unitario", 0))
        total += subtotal
        if presentacion:
            lineas_items.append(f"  • {cantidad}x {producto} / {presentacion} → ${subtotal:,}".replace(",", "."))
        else:
            lineas_items.append(f"  • {cantidad}x {producto} → ${subtotal:,}".replace(",", "."))

    total_fmt = f"{total:,}".replace(",", ".")
    resumen = (
        "🛒 *Tu carrito actual:*\n\n"
        + "\n".join(lineas_items)
        + f"\n\n💰 *Total: ${total_fmt}*"
    )
    # Reply buttons (Confirmar si supera el mínimo, sino solo Ver/Vaciar)
    pedido_min = 0
    try:
        pedido_min_str = await get_config_value("PEDIDO_MINIMO", agent_id) or os.getenv("PEDIDO_MINIMO", "0")
        pedido_min = int(float(pedido_min_str)) if pedido_min_str else 0
    except Exception:
        pedido_min = 0
    ofrece_confirmar = total >= pedido_min if pedido_min > 0 else True

    enviado = False
    if hasattr(proveedor, "enviar_botones_reply"):
        try:
            # Para "Ver carrito" mostramos solo 2 botones (sin duplicar "Ver" que ya están viendo)
            botones = []
            if ofrece_confirmar:
                botones.append({"id": "act_confirmar_pedido", "title": "Confirmar pedido ✅"})
            botones.append({"id": "act_vaciar_carrito", "title": "Vaciar carrito 🗑"})
            enviado = await proveedor.enviar_botones_reply(telefono, resumen, botones)
        except Exception as e:
            logger.warning(f"[ver-carrito] botones fallaron: {e}")
    if not enviado:
        await proveedor.enviar_mensaje(telefono, resumen)
    await _guardar_con_wamid(proveedor, telefono, resumen, agent_id=agent_id)
    return True


async def _enviar_horarios_calendly(telefono: str, agent_id: int = 1) -> None:
    """Obtiene horarios reales de Calendly y los envía como lista interactiva de WA.

    Guarda el mapeo título→ISO en calendly_pendiente para que la intercepción
    del webhook pueda recuperarlo cuando el cliente seleccione un horario.
    """
    from zoneinfo import ZoneInfo
    _DIAS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    _MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    _TZ_BOGOTA = ZoneInfo("America/Bogota")

    proveedor = await _get_meta_para_agente({"id": agent_id})

    async def _fallback(msg: str) -> None:
        await proveedor.enviar_mensaje(telefono, msg)
        await _guardar_con_wamid(proveedor, telefono, msg, agent_id=agent_id)

    # 1) Obtener user_uri de Calendly (valida el token también)
    usuario = await calendly_usuario(agent_id)
    if not usuario.get("ok"):
        await _fallback(
            "Lo siento, no pude conectarme a Calendly en este momento 😔\n"
            "Por favor intenta más tarde o contáctanos directamente."
        )
        return

    user_uri = usuario["uri"]

    # 2) Obtener tipos de evento activos
    event_types = await calendly_event_types(agent_id, user_uri)
    if not event_types:
        await _fallback(
            "No encontré tipos de cita configurados en Calendly. "
            "Por favor contáctanos para coordinar tu cita."
        )
        return

    # Usar el primer tipo de evento activo
    et = event_types[0]
    event_type_uri = et["uri"]
    event_type_nombre = et["nombre"]
    duracion_min = et.get("duracion_min", 0)
    location_kinds = et.get("location_kinds", [])
    location_kind = location_kinds[0] if location_kinds else None

    # 3) Obtener horarios disponibles (próximos 7 días)
    slots = await calendly_horarios(agent_id, event_type_uri, dias=7)
    if not slots:
        await _fallback(
            "No encontré horarios disponibles para los próximos días 😔\n"
            "Por favor escríbenos para coordinar tu cita directamente."
        )
        return

    # 4) Convertir UTC → Bogota y construir filas de lista (máx 8 slots)
    opciones: dict[str, str] = {}
    filas = []
    for slot in slots[:8]:
        iso = slot.get("start_time", "")
        if not iso:
            continue
        try:
            dt_utc = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            dt = dt_utc.astimezone(_TZ_BOGOTA)
        except Exception:
            continue

        dia_abr  = _DIAS_ES[dt.weekday()]
        mes_abr  = _MESES_ES[dt.month - 1]
        hora_str = dt.strftime("%I:%M %p").lstrip("0")
        titulo = f"{dia_abr} {dt.day} {mes_abr}, {hora_str}"[:24]

        desc_parts = []
        if duracion_min:
            desc_parts.append(f"{duracion_min} min")
        if location_kind == "google_conference":
            desc_parts.append("Google Meet")
        elif location_kind == "physical":
            desc_parts.append("Presencial")
        elif location_kind:
            desc_parts.append(location_kind.replace("_", " ").title())
        descripcion = (" · ".join(desc_parts))[:72]

        if titulo not in opciones:
            _slot_id = f"slot_{len(filas)}"
            opciones[titulo] = iso
            filas.append({"id": _slot_id, "titulo": titulo, "descripcion": descripcion})

    if not filas:
        await _fallback("No pude preparar la lista de horarios. Por favor intenta más tarde.")
        return

    # id_map: slot_id → ISO (match por ID, más robusto que match por título)
    id_map = {f["id"]: opciones[f["titulo"]] for f in filas}
    titulos_map = {f["id"]: f["titulo"] for f in filas}

    # 5) Guardar estado en BD para la intercepción del webhook
    await guardar_calendly_pendiente(telefono, {
        "paso": "esperando_seleccion",
        "event_type_uri": event_type_uri,
        "event_type_nombre": event_type_nombre,
        "location_kind": location_kind,
        "opciones": opciones,
        "id_map": id_map,
        "titulos_map": titulos_map,
        "seleccion": None,
        "seleccion_titulo": None,
        "appointment_id": None,
        "intentos": 0,
    }, agent_id)

    # 6) Enviar lista interactiva
    texto_intro = (
        f"📅 *Horarios disponibles — {event_type_nombre}*\n\n"
        "Toca el horario que prefieras:"
    )
    secciones = [{"titulo": "Horarios disponibles", "items": filas}]
    enviado = False
    if hasattr(proveedor, "enviar_lista"):
        try:
            enviado = await proveedor.enviar_lista(telefono, texto_intro, "Ver horarios", secciones,
                                                header_text="📅 Elige tu horario")
        except Exception as e:
            logger.warning(f"[calendly] enviar_lista falló: {e}")
    if not enviado:
        # Fallback texto plano si el proveedor no soporta lista
        opciones_txt = "\n".join(f"• {t}" for t in opciones)
        fallback_txt = f"{texto_intro}\n\n{opciones_txt}\n\nResponde con el horario que prefieras."
        await proveedor.enviar_mensaje(telefono, fallback_txt)
        await _guardar_con_wamid(proveedor, telefono, fallback_txt, agent_id=agent_id)
    else:
        await _guardar_con_wamid(proveedor, telefono, texto_intro, agent_id=agent_id)


# ──────────────────────────────────────────────────────────────────────────────
# Helper: obtener o recrear checkout URL válido
# ──────────────────────────────────────────────────────────────────────────────
def _es_url_checkout_valida(url: str) -> bool:
    """True si la URL es un checkout real de Shopify (no la home).

    Acepta los formatos actuales del Storefront API, Admin API y webhooks:
      - '/checkouts/cn/...' y '/checkouts/...'  (webhook checkouts/create, formato clásico)
      - '/checkout/...'                          (alias usado por algunos endpoints)
      - '/cart/c/{id}?key=...&_s=...&_y=...'    (Storefront cartCreate — legacy)
      - '/invoices/...'                          (Admin Draft Order invoice_url — actual)
    """
    if not url:
        return False
    return (("/checkouts/" in url) or ("/checkout/" in url)
            or ("/cart/c/" in url) or ("/invoices/" in url))


async def _obtener_o_recrear_checkout_url(
    telefono: str, agent_id: int = 1, forzar_recrear: bool = False,
) -> str | None:
    """Devuelve un checkout_url VÁLIDO para el cliente.

    - Si forzar_recrear=True: SIEMPRE recrea desde carrito_activo actual.
      Úsalo cuando el cliente toca "Confirmar pedido" — el carrito puede
      haber cambiado desde el último checkout creado (nuevos items, etc.).
    - Si forzar_recrear=False (default): usa el URL guardado si tiene
      /checkouts/. Solo recrea si está corrupto. Úsalo en timers como el
      recordatorio de checkout abandonado.

    Returns: URL válida del checkout, o None si no se pudo (sin carrito).
    """
    cliente_data = await obtener_cliente(telefono, agent_id=agent_id)
    if not cliente_data:
        return None
    url_guardado = (cliente_data.get("pedido_checkout_url") or "").strip()

    # Si NO forzamos y el URL guardado es válido, usarlo (caso normal del timer)
    if not forzar_recrear and url_guardado and _es_url_checkout_valida(url_guardado):
        return url_guardado

    # Recrear desde carrito_activo actual:
    #   - forzar_recrear=True (cliente activamente confirmando)
    #   - O URL corrupta/vacía
    if url_guardado and not forzar_recrear:
        logger.warning(
            f"[checkout-url] URL corrupta para {telefono} ({url_guardado[:60]}) — recreando"
        )
    elif forzar_recrear:
        logger.info(
            f"[checkout-url] Recreando checkout para {telefono} (forzado por confirmación de pedido)"
        )
    carrito = await obtener_carrito_activo(telefono, agent_id=agent_id)
    if not carrito:
        logger.warning(f"[checkout-url] {telefono} sin carrito_activo — no puedo recrear checkout")
        return None
    logger.info(f"[checkout-url] carrito_activo de {telefono} tiene {len(carrito)} items")
    # Convertir items del carrito al formato esperado por crear_checkout_shopify
    productos = []
    total = 0
    descartados = []
    for item in carrito:
        producto = item.get("producto", "")
        presentacion = item.get("presentacion", "")
        cantidad = int(item.get("cantidad", item.get("quantity", 1)))
        precio_u = int(item.get("precio_unitario", 0))
        subtotal = int(item.get("subtotal") or precio_u * cantidad)
        if not producto or not precio_u:
            descartados.append(f"{producto or '?'}/{presentacion or '?'} (precio={precio_u})")
            continue
        productos.append({
            "producto": producto,
            "presentacion": presentacion,
            "cantidad": cantidad,
            "precio_unitario": precio_u,
            "subtotal": subtotal,
        })
        total += subtotal
    if descartados:
        logger.warning(f"[checkout-url] items descartados de {telefono}: {descartados}")
    logger.info(f"[checkout-url] {telefono} → {len(productos)} productos válidos, total ${total:,}")
    if not productos:
        logger.warning(f"[checkout-url] carrito_activo de {telefono} sin productos válidos")
        # Fallback: si tenemos URL guardada válida, usarla mejor que None
        if url_guardado and _es_url_checkout_valida(url_guardado):
            logger.info(f"[checkout-url] usando URL guardada como fallback")
            return url_guardado
        return None
    try:
        nuevo_url = await crear_checkout_shopify(telefono, {"productos": productos, "total": total})
        if nuevo_url and _es_url_checkout_valida(nuevo_url):
            await guardar_checkout_url(telefono, nuevo_url, agent_id=agent_id)
            logger.info(f"[checkout-url] Recreado para {telefono}: {nuevo_url[:80]}")
            return nuevo_url
        # ── Recreación falló — usar URL guardada como FALLBACK ──
        # Esto evita que el cliente quede sin botón cuando crear_checkout_shopify
        # no encuentra alguna variante (ej. "Default Title" que no matchea).
        # Mejor un checkout que ya existía con casi todos los items que NINGUNO.
        logger.error(
            f"[checkout-url] crear_checkout_shopify devolvió URL inválida: {nuevo_url} — "
            f"usando URL guardada como fallback (si existe)"
        )
        if url_guardado and _es_url_checkout_valida(url_guardado):
            logger.info(f"[checkout-url] fallback OK: {url_guardado[:80]}")
            return url_guardado
        return None
    except Exception as e:
        logger.error(f"[checkout-url] Error recreando checkout para {telefono}: {e}")
        # Mismo fallback ante excepción
        if url_guardado and _es_url_checkout_valida(url_guardado):
            logger.info(f"[checkout-url] fallback tras excepción: {url_guardado[:80]}")
            return url_guardado
        return None


async def _escalar_meta_fallo(
    telefono: str,
    motivo_corto: str,
    contexto_extra: str = "",
    agent_id: int = 1,
) -> None:
    """Escala una conversación a humano cuando el catálogo nativo de WhatsApp
    falla y el cliente está esperando una respuesta concreta AHORA.

    Hace 3 cosas:
      1. Manda mensaje cálido al cliente: 'Te conecto con un asesor...'
      2. Crea ticket via _notificar_escalacion (que también pausa el bot
         y avisa al equipo por WhatsApp + panel).
      3. Persiste el mensaje en BD para que aparezca en panel.

    Solo se usa en flujos donde NO mandar nada sería pésima UX:
      - Cliente terminó pedido nativo bajo mínimo → product_list falló
      - Andrea emitió [[TIENDA:]] → product_list falló
    NO se usa en seguimientos automáticos (timers) — esos cancelan silencioso.
    """
    try:
        # 1. Mensaje cálido al cliente
        msg_cliente = (
            "Para ayudarte mejor te conecto con un asesor "
            "que te va a mostrar los productos. Ya viene 🌿"
        )
        _prov = await _get_meta_para_agente({"id": agent_id})
        await _prov.enviar_mensaje(telefono, msg_cliente)
        await _guardar_con_wamid(_prov, telefono, msg_cliente, agent_id=agent_id)

        # 2. Obtener nombre del cliente para el ticket (mejora UX panel)
        try:
            cli = await obtener_cliente(telefono, agent_id=agent_id)
        except Exception:
            cli = None
        nombre = (cli.get("nombre") if cli else "") or ""

        # 3. Crear ticket + pausar bot + notificar equipo
        contexto_full = (
            f"Cliente esperando catálogo. {contexto_extra}".strip()
            if contexto_extra else
            "Cliente esperando catálogo de productos."
        )
        await _notificar_escalacion(
            telefono,
            {
                "motivo":         f"Catálogo no disponible — {motivo_corto}",
                "urgencia":       "normal",
                "nombre_cliente": nombre,
                "contexto":       contexto_full,
            },
            agent_id=agent_id,
        )
        logger.info(f"[escalacion-meta] {telefono} escalado por: {motivo_corto}")
    except Exception as e:
        logger.error(f"[escalacion-meta] fallo escalando {telefono}: {e}")


app = FastAPI(
    title="Voco — Plataforma multi-tenant de agentes WhatsApp",
    version="1.0.0",
    lifespan=lifespan
)

# CORS — orígenes permitidos para llamadas externas (mini-tienda Lovable,
# checkout custom, etc.). Multi-tenant: cada merchant configura sus dominios
# en CORS_ALLOWED_ORIGINS (env var, separados por coma). Fallback a Equora
# legacy mientras hay un solo tenant en producción.
_cors_env = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] or [
    "https://equoradistribuciones.com",
    "https://www.equoradistribuciones.com",
    "https://equora-6.myshopify.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
async def health_check():
    return {"status": "ok", "service": "voco"}


@app.get("/privacy", response_class=HTMLResponse)
async def pagina_privacidad():
    """Política de privacidad pública — requisito de Meta App Review (Tech
    Provider). Servida desde myvoco.ai/privacy, no requiere sitio aparte."""
    from agent.legal import politica_privacidad_html
    return HTMLResponse(content=politica_privacidad_html())


@app.get("/terms", response_class=HTMLResponse)
async def pagina_terminos():
    """Términos del servicio públicos — requisito de Meta App Review."""
    from agent.legal import terminos_html
    return HTMLResponse(content=terminos_html())


@app.get("/health")
async def health_check_deep():
    """#77 — Healthcheck profundo: verifica conexión a BD y que el loop de
    seguimientos siga ticando (no solo que el proceso responda HTTP).
    Pensado para Railway (healthcheckPath) y monitoreo externo — a
    diferencia de "/", acá un problema real devuelve 503."""
    problemas = []

    try:
        from agent.memory import obtener_agente
        await obtener_agente(1)
    except Exception as e:
        problemas.append(f"db: {e}")

    inactivo_seg = (
        round(time.monotonic() - _ultimo_ciclo_seguimiento, 1)
        if _ultimo_ciclo_seguimiento else None
    )
    # Si nunca corrió un ciclo (deploy recién hecho, aún en warm-up) no es
    # error — el primer ciclo tarda hasta CHECK_INTERVAL_SEG en arrancar.
    if inactivo_seg is not None and inactivo_seg > WATCHDOG_UMBRAL_SEG:
        problemas.append(f"loop_seguimientos sin ticar hace {inactivo_seg}s")

    if problemas:
        return JSONResponse(status_code=503, content={
            "status": "unhealthy", "service": "voco", "problemas": problemas,
        })
    return {
        "status": "ok", "service": "voco",
        "loop_seguimientos_inactivo_seg": inactivo_seg,
    }


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


def extraer_marcador_producto(respuesta: str) -> tuple[str, list[str]]:
    """Extrae uno o más [[PRODUCTO:nombre|presentacion]] — envía single_product del catálogo.
    Andrea lo usa cuando menciona un producto específico para darle al cliente
    la opción de armar carrito directo desde WhatsApp (con +/- nativos)."""
    matches = re.findall(r'\[\[PRODUCTO:([^\]]+)\]\]', respuesta)
    texto_limpio = re.sub(r'\s*\[\[PRODUCTO:[^\]]+\]\]', '', respuesta).strip()
    productos = [m.strip() for m in matches if m.strip()]
    return texto_limpio, productos


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


def extraer_marcador_vaciar_carrito(respuesta: str) -> tuple[str, bool]:
    """Extrae [[VACIAR_CARRITO]] — el agente lo emite cuando el cliente pide
    vaciar/borrar/limpiar su carrito. El parser ejecuta limpiar_carrito_activo()
    y limpia el marcador del texto que llega al cliente.

    Acepta variantes: [[VACIAR_CARRITO]], [[VACIAR CARRITO]], [[LIMPIAR_CARRITO]],
    [[LIMPIAR CARRITO]] — tolerante a errores del LLM.
    """
    patron = r'\[\[(?:VACIAR|LIMPIAR)[_ ]?CARRITO\]\]'
    if not re.search(patron, respuesta, flags=re.IGNORECASE):
        return respuesta, False
    texto_limpio = re.sub(patron, '', respuesta, flags=re.IGNORECASE).strip()
    return texto_limpio, True


def extraer_marcador_mostrar_carrito(respuesta: str) -> tuple[str, bool]:
    """Extrae [[MOSTRAR_CARRITO]] — el agente lo emite cuando el cliente pide
    ver/mostrar su carrito por TEXTO (no botón). El parser ejecuta el handler
    determinístico _enviar_resumen_carrito() que lee BD y muestra resumen +
    botones reply, garantizando consistencia. Sin esto, Andrea inventaba el
    texto del carrito basado en su contexto sin reply buttons.

    Acepta variantes: [[MOSTRAR_CARRITO]], [[VER_CARRITO]], [[VER CARRITO]].
    """
    patron = r'\[\[(?:MOSTRAR|VER)[_ ]?CARRITO\]\]'
    if not re.search(patron, respuesta, flags=re.IGNORECASE):
        return respuesta, False
    texto_limpio = re.sub(patron, '', respuesta, flags=re.IGNORECASE).strip()
    return texto_limpio, True


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


# URL base del sitio web del merchant — se usa para construir links a colecciones
# desde [[TIENDA:término]]. Multi-tenant: configurable por env var con fallback
# a Equora mientras hay un solo tenant en producción.
EQUORA_BASE = os.getenv("MERCHANT_SITE_URL", "https://equoradistribuciones.com")

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


async def _procesar_status_difusion(status: dict) -> None:
    """Procesa un status update de Meta (delivered/read/failed). Actualiza
    DOS tablas: difusion_mensajes (tracking de campañas) y mensajes (chulitos
    de confirmación en el chat — #79). Los mismos status updates aplican a
    ambos sin distinguir si fue mensaje regular o de difusión."""
    wamid      = status.get("id", "")
    status_val = status.get("status", "")   # sent | delivered | read | failed
    ts_str     = status.get("timestamp", "")
    errors     = status.get("errors", [])
    error_code = int(errors[0].get("code", 0)) if errors else None
    error_title = errors[0].get("title", "")   if errors else ""

    if not wamid or status_val not in ("sent", "delivered", "read", "failed"):
        return
    try:
        await actualizar_status_difusion(
            wamid=wamid,
            status=status_val,
            error_code=error_code,
            error_title=error_title,
            ts_str=ts_str,
        )
        if status_val == "failed":
            logger.info(f"[webhook-status] FAILED wamid={wamid[:20]} code={error_code} title={error_title}")
    except Exception as e:
        logger.debug(f"[webhook-status] Error actualizando difusion_mensajes {wamid[:20]}: {e}")

    # #79 — actualizar tabla mensajes para chulitos en el chat
    try:
        from agent.memory import actualizar_status_mensaje
        await actualizar_status_mensaje(wamid, status_val, error_code=error_code, error_title=error_title)
    except Exception as e:
        logger.debug(f"[webhook-status] Error actualizando mensajes {wamid[:20]}: {e}")


# ── Palabras clave de opt-out (baja de difusiones) ───────────────────────────
# Solo palabras con intención EXPLÍCITA de darse de baja.
# "No gracias", "No", "Cancelar" NO están aquí porque tienen otros contextos válidos.
PALABRAS_OPT_OUT: set[str] = {
    "stop",
    "baja",
    "dar de baja",
    "darme de baja",
    "dame de baja",
    "quitar de la lista",
    "quitarme de la lista",
    "no quiero más mensajes",
    "no quiero recibir más",
    "no quiero recibir más mensajes",
    "cancelar suscripción",
    "cancelar suscripcion",
    "desuscribir",
    "desuscribirme",
    "unsubscribe",
}


def _es_solicitud_opt_out(texto: str) -> bool:
    """
    Retorna True si el mensaje es una solicitud explícita de darse de baja.
    Incluye el botón 'Dar de baja' (quick reply de plantilla) y palabras clave exactas.
    """
    t = texto.strip().lower()
    # Coincidencia exacta primero (más segura — evita falsos positivos)
    if t in PALABRAS_OPT_OUT:
        return True
    # El botón quick reply de la plantilla llega exactamente como "Dar de baja"
    if t == "dar de baja":
        return True
    # Frases que contienen palabras clave de opt-out claras
    for palabra in PALABRAS_OPT_OUT:
        if len(palabra) > 6 and palabra in t:  # solo frases largas para evitar "baja" en otro contexto
            return True
    return False


def _es_respuesta_automatica(texto: str) -> bool:
    """
    Detecta si un mensaje parece ser una respuesta automática de WhatsApp Business.
    Estos mensajes no deben procesarse con Andrea para evitar conversaciones entre bots.

    Ejemplos típicos:
    - "Hola, somos Pizzería Pepito. ¿Qué deseas pedir?"
    - "Gracias por contactarnos, en breve te atendemos."
    - "Este es un mensaje automático. Estamos fuera de horario."
    """
    import re as _re
    t = texto.strip()
    if not t or len(t) > 500:  # Los mensajes reales suelen ser cortos en auto-reply
        return False

    tl = t.lower()

    # Patrones de respuesta automática
    patrones = [
        r'respuesta automát',
        r'mensaje automát',
        r'auto.?reply',
        r'bot\b',
        r'fuera de horario',
        r'fuera de servicio',
        r'no estamos disponibles',
        r'en este momento no (podemos|estamos|hay)',
        r'atenderemos (tu|su|el) (mensaje|consulta|pedido)',
        r'te (responderemos|contestaremos|atenderemos) (pronto|en breve|a la brevedad)',
        r'en breve (te|le) (atendemos|contactamos|respondemos)',
        r'gracias por (contactar|escribir|comunicarte|tu mensaje)',
        r'business hours',
        r'working hours',
        r'somos un (negocio|restaurante|empresa|tienda)',
        r'^hola[,\.]?\s+(somos|soy)\s+\w',        # "Hola, somos Pizzería..."
        r'^buenos\s+(días|tardes|noches)[,\.]?\s+(somos|soy)\s',
        r'pedido.*deseas\s+(pedir|ordenar)',
        r'(deseas|quieres)\s+(pedir|ordenar|comprar)',
        r'menú\s+(disponible|del día)',
    ]

    for patron in patrones:
        if _re.search(patron, tl):
            logger.info(f"[auto-reply] Mensaje ignorado (patrón: {patron[:30]}): {t[:60]}")
            return True

    return False


@app.post("/webhook")
async def webhook_handler(request: Request):
    # ── Extraer phone_number_id para routing multi-agente ─────────────────────
    _body_raw = {}
    try:
        _body_raw = await request.json()
    except Exception:
        pass

    _phone_id = ""
    try:
        _phone_id = _body_raw["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]
    except Exception:
        pass
    _phone_id = (_phone_id or "").strip()

    # ── Sandbox hub de Voco: el número de la plataforma se intercepta ANTES ────
    # de resolver el tenant. Ese número es propio de Voco (VOCO_SANDBOX_*), no
    # pertenece a ningún cliente; debe entrar SIEMPRE al flujo de sandbox aunque
    # exista un agente en BD reclamando ese phone_number_id (diseño viejo) o esté
    # en borrador. Antes esto vivía dentro del loop y el early-return de draft
    # más abajo mataba el mensaje antes de llegar acá.
    _voco_sb_pid = os.getenv("VOCO_SANDBOX_PHONE_NUMBER_ID", "").strip()
    _is_sandbox_msg = bool(_voco_sb_pid and _phone_id == _voco_sb_pid)
    logger.info(
        f"[sandbox] phone_id={repr(_phone_id)} sb_pid={repr(_voco_sb_pid)} "
        f"match={_is_sandbox_msg}"
    )

    _agente_actual = await _resolver_agente(_phone_id)
    _agent_id = _agente_actual.get("id", 1)

    # Si el agente está pausado o en draft, ignorar el webhook — SALVO que sea
    # un mensaje al número sandbox (ese flujo lo maneja el hub más abajo, y el
    # agente sandbox viejo suele quedar en borrador).
    if not _is_sandbox_msg and _agente_actual.get("status") in ("paused", "draft"):
        return {"status": "ok", "agente": "inactivo"}

    # Proveedor Meta específico para este agente (credenciales desde BD o env)
    _proveedor_agente = await _get_meta_para_agente(_agente_actual)

    # ── Status updates de Meta (delivery/read/failed) ─────────────────────────
    # Llegan en el mismo POST que los mensajes, en el campo "statuses"
    try:
        for entry in _body_raw.get("entry", []):
            for change in entry.get("changes", []):
                for status in change.get("value", {}).get("statuses", []):
                    asyncio.create_task(_procesar_status_difusion(status))
    except Exception:
        pass  # no interferir con el flujo normal de mensajes

    try:
        mensajes = await _proveedor_agente.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            logger.info(f"Mensaje de {msg.telefono}: {msg.texto[:80]}")

            # ── Filtro: respuestas automáticas de WhatsApp Business ───────────
            # Evita que Andrea quede atrapada respondiendo bots de otros negocios
            if _es_respuesta_automatica(msg.texto):
                continue  # ignorar silenciosamente

            # ── Sandbox hub de Voco: número central compartido entre tenants ────
            # El sandbox usa el WABA propio de Voco (VOCO_SANDBOX_*), independiente
            # del WABA de cada cliente. El código VOCO-EQ001 enruta al agente correcto.
            if _is_sandbox_msg:
                from agent.providers.meta import ProveedorMeta as _MetaProv
                _voco_sb_prov = _MetaProv(
                    access_token=os.getenv("VOCO_SANDBOX_ACCESS_TOKEN", ""),
                    phone_number_id=_voco_sb_pid,
                    verify_token=os.getenv("META_VERIFY_TOKEN", ""),
                    catalog_id="",
                )
                if msg.mensaje_id:
                    asyncio.create_task(_voco_sb_prov.marcar_leido(msg.mensaje_id))

                _sb_target_id = _sandbox_sessions.get(msg.telefono)

                # Comando SALIR: resetea la sesión para probar otro agente
                if msg.texto.strip().upper() in ("SALIR", "RESET", "CAMBIAR"):
                    _sandbox_sessions.pop(msg.telefono, None)
                    await _voco_sb_prov.enviar_mensaje(msg.telefono,
                        "🔄 Sesión reseteada. Envía un código de proyecto para conectarte a otro agente."
                    )
                    continue

                if _sb_target_id is None:
                    # Validar código de proyecto
                    _code_recv = msg.texto.strip().upper().replace(" ", "")
                    _parsed_id = _sandbox_codigo_a_agent_id(_code_recv)
                    if _parsed_id:
                        from agent.memory import obtener_agente as _get_ag_sb
                        _target_ag = await _get_ag_sb(_parsed_id)
                        if _target_ag:
                            _sandbox_sessions[msg.telefono] = _parsed_id
                            _nombre_ag = _target_ag.get("agent_name", "el agente")
                            await _voco_sb_prov.enviar_mensaje(msg.telefono,
                                f"✅ Código correcto. Ahora estás conectado con *{_nombre_ag}*.\n\n"
                                f"Escribe tu primer mensaje para empezar la prueba.\n"
                                f"_Escribe SALIR para probar otro agente._"
                            )
                        else:
                            await _voco_sb_prov.enviar_mensaje(msg.telefono,
                                f"⚠️ Código no reconocido. Verifica el código en el panel de Voco."
                            )
                    else:
                        await _voco_sb_prov.enviar_mensaje(msg.telefono,
                            f"¡Hola! 👋 Soy el sandbox de Voco.\n\n"
                            f"Envía el código de tu proyecto para comenzar la prueba.\n\n"
                            f"Ejemplo: *VOCO-001*"
                        )
                    continue

                # Código ya validado: sobreescribir agente y proveedor para el flujo normal
                _agent_id = _sb_target_id
                _proveedor_agente = _voco_sb_prov

            # ── Acción de botón interno (act_*) ───────────────────────────────
            # El cliente tocó un botón de reply con ID act_* (Voco lo procesó
            # en parsear_webhook y lo serializó como __ACCION_BTN__:act_xxx).
            # Estas acciones se procesan directo sin pasar por Claude.
            if msg.texto.startswith("__ACCION_BTN__:"):
                accion = msg.texto[len("__ACCION_BTN__:"):]
                await registrar_mensaje_usuario(msg.telefono, agent_id=_agent_id)
                # Guardamos en historial el título de la acción (más legible que el id)
                titulos = {
                    "act_envio_gratis":     "Alcanzar envío gratis",
                    "act_confirmar_pedido": "Confirmar pedido",
                    "act_ver_catalogo":     "Ver catálogo",
                }
                await guardar_mensaje(msg.telefono, "user", titulos.get(accion, accion), agent_id=_agent_id)
                logger.info(f"[accion-btn] {msg.telefono} eligió: {accion}")

                if accion == "act_envio_gratis" or accion == "act_ver_catalogo":
                    # Reabrir catálogo nativo de WhatsApp via product_list
                    # (catalog_message removido: cuelga WB mobile en algunos Android).
                    if hasattr(_proveedor_agente, "enviar_catalogo_productos"):
                        secciones = obtener_secciones_catalogo(None)
                        if secciones:
                            header_cat = await _catalogo_header_for_agent(_agent_id)
                            await _proveedor_agente.enviar_catalogo_productos(
                                msg.telefono, header_cat,
                                "Agrega los productos que quieras — se suman a tu pedido.",
                                secciones,
                            )
                    continue

                if accion == "act_confirmar_pedido":
                    # SIEMPRE recrear desde el carrito_activo actual. Equora
                    # reportó (10-jun-2026): tras "Ver carrito" + "Confirmar
                    # pedido" se reutilizaba un checkout_url viejo guardado de
                    # un pedido previo — productos del checkout no coincidían
                    # con el carrito actual (cobraba lo que NO pidió el cliente).
                    # El supuesto anterior ("__ORDEN_CATALOGO__ siempre actualiza
                    # el URL") no se cumple cuando el cliente solo navega con
                    # botones de carrito. forzar_recrear=True garantiza que el
                    # link de pago refleje EXACTAMENTE lo que está en BD ahora.
                    checkout_url = await _obtener_o_recrear_checkout_url(
                        msg.telefono, agent_id=_agent_id, forzar_recrear=True
                    )
                    if checkout_url:
                        # Mensaje y label del botón configurables por agente
                        # (#28 fase 2.6). El cliente personaliza en
                        # Configuración → Mensajes → "Flujo de compra".
                        from agent.mensajes import format_seguro
                        _ctx_ph = await construir_contexto_placeholders(_agent_id)
                        _ctx_ph["total"] = await _total_carrito_fmt(msg.telefono, _agent_id)
                        msg_checkout = format_seguro(
                            await obtener_mensaje(_agent_id, "cart.checkout_listo_texto"),
                            _ctx_ph,
                        )
                        boton_label = (await obtener_mensaje(_agent_id, "cart.checkout_listo_boton")).strip() or "Pagar ahora"
                        # Mensaje 1: CTA URL directo al checkout (1 click → pagar).
                        # WhatsApp no permite mezclar URL button + reply buttons,
                        # entonces los otros 2 (Agregar más / Ver carrito) van
                        # como mensaje complementario aparte (no obliga al cliente
                        # a 2 clicks para pagar, que es la fricción que Jelou
                        # evita).
                        ok_cta = False
                        if hasattr(_proveedor_agente, "enviar_cta_url"):
                            ok_cta = await _proveedor_agente.enviar_cta_url(
                                msg.telefono, msg_checkout, boton_label, checkout_url,
                            )
                        if not ok_cta:
                            await _proveedor_agente.enviar_mensaje(
                                msg.telefono, f"{msg_checkout}\n\n👉 {checkout_url}"
                            )
                        # Mensaje 2 (complementario): opciones de modificar antes
                        # de pagar — siempre disponibles.
                        if hasattr(_proveedor_agente, "enviar_botones_reply"):
                            try:
                                await _proveedor_agente.enviar_botones_reply(
                                    msg.telefono, "¿Quieres modificar algo antes de pagar?",
                                    [
                                        {"id": "act_agregar_mas", "title": "🔍 Agregar más"},
                                        {"id": "act_ver_carrito", "title": "🛒 Ver mi carrito"},
                                    ],
                                )
                            except Exception as _e_b:
                                logger.warning(f"[confirmar-pedido] botones complementarios fallaron: {_e_b}")
                    else:
                        _txt_no_enc = await obtener_mensaje(_agent_id, "error.checkout_no_encontrado")
                        if _txt_no_enc:
                            await _proveedor_agente.enviar_mensaje(msg.telefono, _txt_no_enc)
                            await _guardar_con_wamid(_proveedor_agente, msg.telefono, _txt_no_enc, agent_id=_agent_id)
                    continue

                if accion == "act_vaciar_carrito":
                    # El cliente tocó el botón "Vaciar carrito" del seguimiento.
                    # Vaciar directo en BD (sin depender del LLM) + confirmar.
                    try:
                        await limpiar_carrito_activo(msg.telefono, agent_id=_agent_id)
                        # Limpiar también el pedido_checkout_url para que el
                        # loop de checkout-abandonado no envíe "Vimos que
                        # iniciaste tu pedido pero no terminaste el proceso"
                        # cuando el cliente acaba de decir explícitamente
                        # que no quiere el pedido. Bug reportado por Equora.
                        await limpiar_checkout_url(msg.telefono, agent_id=_agent_id)
                        logger.info(f"[act_vaciar_carrito] carrito + checkout_url vaciados para {msg.telefono}")
                    except Exception as e:
                        logger.error(f"[act_vaciar_carrito] error vaciando: {e}")
                    msg_confirmacion = (
                        "🗑 *Listo, tu carrito quedó vacío.*\n\n"
                        "Cuando quieras armar un pedido nuevo, escríbeme qué necesitas "
                        "o pídeme el catálogo 🌿"
                    )
                    await _proveedor_agente.enviar_mensaje(msg.telefono, msg_confirmacion)
                    await _guardar_con_wamid(_proveedor_agente, msg.telefono, msg_confirmacion, agent_id=_agent_id)
                    continue

                if accion == "act_ir_pago":
                    # Botón Jelou (#61): el cliente decidió pagar — enviamos
                    # cta_url al invoice_url/checkout_url guardado en BD.
                    checkout_url = await _obtener_o_recrear_checkout_url(
                        msg.telefono, agent_id=_agent_id, forzar_recrear=False,
                    )
                    if not checkout_url:
                        _txt_no_enc = await obtener_mensaje(_agent_id, "error.checkout_no_encontrado")
                        if _txt_no_enc:
                            await _proveedor_agente.enviar_mensaje(msg.telefono, _txt_no_enc)
                            await _guardar_con_wamid(_proveedor_agente, msg.telefono, _txt_no_enc, agent_id=_agent_id)
                        continue
                    boton_label = (await obtener_mensaje(_agent_id, "cart.checkout_listo_boton")).strip() or "Pagar ahora"
                    txt = "Toca el botón para completar tu pago de forma segura 🔒"
                    ok_cta = False
                    if hasattr(_proveedor_agente, "enviar_cta_url"):
                        ok_cta = await _proveedor_agente.enviar_cta_url(
                            msg.telefono, txt, boton_label, checkout_url,
                        )
                    if not ok_cta:
                        await _proveedor_agente.enviar_mensaje(
                            msg.telefono, f"{txt}\n\n👉 {checkout_url}"
                        )
                    continue

                if accion == "act_agregar_mas":
                    # Botón Jelou (#61): cliente quiere agregar más productos —
                    # reabrimos el catálogo nativo de WhatsApp.
                    secciones = obtener_secciones_catalogo(None)
                    if secciones:
                        header_cat = await _catalogo_header_for_agent(_agent_id)
                        await _proveedor_agente.enviar_catalogo_productos(
                            msg.telefono, header_cat,
                            "Elige los productos que quieras agregar a tu pedido.",
                            secciones,
                        )
                    else:
                        await _proveedor_agente.enviar_mensaje(
                            msg.telefono,
                            "Cuéntame qué producto te gustaría agregar y te lo busco 🛒",
                        )
                    continue

                if accion == "act_ver_carrito":
                    # El cliente tocó "Ver carrito" — backend lee BD y envía resumen
                    # determinístico (NO depende de Andrea/LLM).
                    await _enviar_resumen_carrito(msg.telefono, agent_id=_agent_id)
                    continue

                # Acción desconocida: no hacer nada
                continue

            # ── Opt-out: el cliente pide darse de baja de las difusiones ──────
            if _es_solicitud_opt_out(msg.texto):
                await marcar_opt_out(msg.telefono, motivo=msg.texto.strip()[:200], agent_id=_agent_id)
                await guardar_mensaje(msg.telefono, "user", msg.texto, agent_id=_agent_id)
                respuesta_baja = (
                    "Listo ✅ Te quitamos de nuestra lista de difusiones. "
                    "No volverás a recibir mensajes masivos de nuestra parte.\n\n"
                    "Si en algún momento cambias de opinión y quieres volver a recibir "
                    "nuestras ofertas y novedades, solo escríbenos. 🌿"
                )
                await _proveedor_agente.enviar_mensaje(msg.telefono, respuesta_baja)
                await _guardar_con_wamid(_proveedor_agente, msg.telefono, respuesta_baja, agent_id=_agent_id)
                logger.info(f"[opt-out] {msg.telefono} dado de baja — motivo: {msg.texto[:50]}")
                continue  # no pasar por Claude

            # ── Flujo conversacional Calendly (agendado sin salir de WA) ─────────
            _cal_pend = await obtener_calendly_pendiente(msg.telefono, _agent_id)
            if _cal_pend:
                _paso_cal = _cal_pend.get("paso")

                if _paso_cal == "esperando_seleccion":
                    _opciones_cal  = _cal_pend.get("opciones", {})
                    _id_map_cal    = _cal_pend.get("id_map", {})
                    _titulos_map   = _cal_pend.get("titulos_map", {})
                    _texto_norm    = msg.texto.strip()
                    _iso_sel       = None
                    _titulo_sel_cal = _texto_norm

                    # 1) Match por lista_id (más fiable — evita problemas de encoding del título)
                    if msg.lista_id and msg.lista_id in _id_map_cal:
                        _iso_sel = _id_map_cal[msg.lista_id]
                        _titulo_sel_cal = _titulos_map.get(msg.lista_id, _texto_norm)
                        logger.info(f"[calendly] match por id '{msg.lista_id}' → {_iso_sel}")
                    # 2) Match por title exacto
                    elif _texto_norm in _opciones_cal:
                        _iso_sel = _opciones_cal[_texto_norm]
                        logger.info(f"[calendly] match por título exacto '{_texto_norm}'")
                    # 3) Match case-insensitive
                    else:
                        for _k_cal, _v_cal in _opciones_cal.items():
                            if _k_cal.strip().lower() == _texto_norm.lower():
                                _iso_sel = _v_cal
                                _titulo_sel_cal = _k_cal
                                logger.info(f"[calendly] match case-insensitive '{_k_cal}'")
                                break

                    if _iso_sel is None:
                        logger.warning(
                            f"[calendly] NO match: lista_id='{msg.lista_id}' "
                            f"texto='{_texto_norm}' "
                            f"opciones_keys={list(_opciones_cal.keys())[:4]} "
                            f"id_map_keys={list(_id_map_cal.keys())[:4]}"
                        )
                    if _iso_sel is not None:
                        _evt_titulo = _cal_pend.get("event_type_nombre", "Cita")
                        await guardar_mensaje(msg.telefono, "user", msg.texto, agent_id=_agent_id)
                        await registrar_mensaje_usuario(msg.telefono, agent_id=_agent_id)
                        _fecha_inicio_dt = datetime.fromisoformat(_iso_sel.replace("Z", "+00:00")).replace(tzinfo=None)
                        _appt_id = await crear_appointment_pendiente(
                            _agent_id, msg.telefono, _fecha_inicio_dt, _evt_titulo
                        )
                        _cal_pend.update({
                            "paso": "esperando_datos",
                            "seleccion": _iso_sel,
                            "seleccion_titulo": _titulo_sel_cal,
                            "appointment_id": _appt_id["id"] if isinstance(_appt_id, dict) else _appt_id,
                        })
                        await guardar_calendly_pendiente(msg.telefono, _cal_pend, _agent_id)
                        _pedir_datos = (
                            f"Perfecto, reservé el horario *{_titulo_sel_cal}* 🗓\n\n"
                            "Para confirmar necesito tu nombre completo y correo electrónico.\n"
                            "Puedes escribirlos así:\n"
                            "_Juan Pérez, juan@ejemplo.com_"
                        )
                        await _proveedor_agente.enviar_mensaje(msg.telefono, _pedir_datos)
                        await _guardar_con_wamid(_proveedor_agente, msg.telefono, _pedir_datos, agent_id=_agent_id)
                        continue
                    else:
                        # Texto no coincide — avisar sin invocar el LLM (evita bucle).
                        _cal_pend["intentos"] = _cal_pend.get("intentos", 0) + 1
                        if _cal_pend["intentos"] >= 3:
                            await limpiar_calendly_pendiente(msg.telefono, _agent_id)
                            _msg_cal_err = "No pude identificar tu selección. Escribe *agendar* para ver los horarios de nuevo."
                            await _proveedor_agente.enviar_mensaje(msg.telefono, _msg_cal_err)
                            await _guardar_con_wamid(_proveedor_agente, msg.telefono, _msg_cal_err, agent_id=_agent_id)
                        else:
                            await guardar_calendly_pendiente(msg.telefono, _cal_pend, _agent_id)
                            _msg_cal_retry = "No reconocí esa opción 🤔 Toca *Ver horarios* y elige un horario de la lista."
                            await _proveedor_agente.enviar_mensaje(msg.telefono, _msg_cal_retry)
                            await _guardar_con_wamid(_proveedor_agente, msg.telefono, _msg_cal_retry, agent_id=_agent_id)
                        continue  # nunca dejar pasar al LLM cuando hay estado Calendly activo

                elif _paso_cal == "esperando_datos":
                    _email_match = re.search(r"[\w.+\-]+@[\w\-]+\.[a-z]{2,}", msg.texto, re.IGNORECASE)
                    if _email_match:
                        await guardar_mensaje(msg.telefono, "user", msg.texto, agent_id=_agent_id)
                        await registrar_mensaje_usuario(msg.telefono, agent_id=_agent_id)
                        _email_cal = _email_match.group(0)
                        _nombre_raw = msg.texto.replace(_email_cal, "").strip(" ,.-\n")
                        _cli_cal = await obtener_cliente(msg.telefono, agent_id=_agent_id)
                        _nombre_cal = (
                            _nombre_raw
                            or (_cli_cal.get("nombres", "") if _cli_cal else "")
                            or "Cliente"
                        )
                        _cal_pend.update({
                            "paso": "esperando_asunto",
                            "nombre_cal": _nombre_cal,
                            "email_cal": _email_cal,
                        })
                        await guardar_calendly_pendiente(msg.telefono, _cal_pend, _agent_id)
                        _pedir_asunto = (
                            f"Gracias, {_nombre_cal} 👋\n\n"
                            "¿Cuál es el asunto o motivo de la cita?\n"
                            "_Ej: Consulta sobre productos de limpieza_"
                        )
                        await _proveedor_agente.enviar_mensaje(msg.telefono, _pedir_asunto)
                        await _guardar_con_wamid(_proveedor_agente, msg.telefono, _pedir_asunto, agent_id=_agent_id)
                        continue
                    # Sin email → recordar al usuario sin invocar el LLM
                    await guardar_mensaje(msg.telefono, "user", msg.texto, agent_id=_agent_id)
                    _recordatorio_cal = (
                        "Para confirmar la cita necesito tu nombre y correo 📧\n"
                        "Escríbelos así: _Juan Pérez, juan@ejemplo.com_"
                    )
                    await _proveedor_agente.enviar_mensaje(msg.telefono, _recordatorio_cal)
                    await _guardar_con_wamid(_proveedor_agente, msg.telefono, _recordatorio_cal, agent_id=_agent_id)
                    continue  # nunca dejar pasar al LLM cuando se esperan datos del invitado

                elif _paso_cal == "esperando_asunto":
                    await guardar_mensaje(msg.telefono, "user", msg.texto, agent_id=_agent_id)
                    await registrar_mensaje_usuario(msg.telefono, agent_id=_agent_id)
                    _asunto_cal = msg.texto.strip() or "Sin asunto"
                    _nombre_cal = _cal_pend.get("nombre_cal", "Cliente")
                    _email_cal  = _cal_pend.get("email_cal", "")
                    _resultado_cal = await calendly_crear_cita(
                        agent_id=_agent_id,
                        event_type_uri=_cal_pend.get("event_type_uri", ""),
                        start_time_iso=_cal_pend.get("seleccion", ""),
                        invitee_email=_email_cal,
                        invitee_nombre=_nombre_cal,
                        location_kind=_cal_pend.get("location_kind"),
                    )
                    if _resultado_cal.get("ok"):
                        _appt_id_cal = _cal_pend.get("appointment_id")
                        if _appt_id_cal:
                            await confirmar_appointment(
                                _appt_id_cal, _nombre_cal, _email_cal,
                                _resultado_cal.get("uri", ""),
                                _resultado_cal.get("cancel_url", ""),
                                _resultado_cal.get("reschedule_url", ""),
                            )
                        await limpiar_calendly_pendiente(msg.telefono, _agent_id)
                        _titulo_sel = _cal_pend.get("seleccion_titulo", "Cita agendada")
                        _msg_conf = (
                            f"✅ ¡Tu cita está confirmada!\n\n"
                            f"📅 *{_titulo_sel}*\n"
                            f"👤 {_nombre_cal}\n"
                            f"📧 {_email_cal}\n"
                            f"📝 {_asunto_cal}\n\n"
                            "Recibirás un correo de confirmación de Calendly con todos los detalles."
                        )
                        if _resultado_cal.get("reschedule_url"):
                            _msg_conf += f"\n\n🔄 Reagendar: {_resultado_cal['reschedule_url']}"
                        if _resultado_cal.get("cancel_url"):
                            _msg_conf += f"\n❌ Cancelar: {_resultado_cal['cancel_url']}"
                        await _proveedor_agente.enviar_mensaje(msg.telefono, _msg_conf)
                        await _guardar_con_wamid(_proveedor_agente, msg.telefono, _msg_conf, agent_id=_agent_id)
                        logger.info(f"[calendly] Cita confirmada para {msg.telefono} — {_email_cal} — asunto: {_asunto_cal}")
                        try:
                            from agent.memory import obtener_pipeline_activo, crear_deal
                            _pipeline_cal = await obtener_pipeline_activo(_agent_id)
                            if _pipeline_cal:
                                await crear_deal(
                                    agent_id=_agent_id,
                                    pipeline_id=_pipeline_cal["id"],
                                    cliente_telefono=msg.telefono,
                                    cliente_nombre=_nombre_cal,
                                    titulo=f"📅 {_titulo_sel} — {_asunto_cal}",
                                    stage="Calificado",
                                    source="calendly",
                                )
                        except Exception as _e_deal_cal:
                            logger.warning(f"[calendly] No se pudo crear deal en pipeline: {_e_deal_cal}")
                    else:
                        await limpiar_calendly_pendiente(msg.telefono, _agent_id)
                        _err_cal = _resultado_cal.get("error", "Error inesperado")
                        _msg_err_cal = (
                            f"Lo siento, no pude confirmar la cita: {_err_cal} 😔\n\n"
                            "Escribe *agendar* para ver otros horarios disponibles."
                        )
                        await _proveedor_agente.enviar_mensaje(msg.telefono, _msg_err_cal)
                        await _guardar_con_wamid(_proveedor_agente, msg.telefono, _msg_err_cal, agent_id=_agent_id)
                    continue

            # ── Media entrante (imagen/video/documento/ubicación) ──────────────
            # Guardamos el marcador en historial para que el inbox lo renderice,
            # y reemplazamos el texto que pasa a Claude por el caption o un placeholder
            # genérico (Andrea no procesa el contenido binario, solo responde al caption).
            if msg.texto.startswith("__MEDIA__:"):
                try:
                    media_payload = json.loads(msg.texto[len("__MEDIA__:"):])
                except Exception:
                    media_payload = {}
                # Guardamos el marcador original en BD (el inbox lo renderiza)
                await guardar_mensaje(msg.telefono, "user", msg.texto, agent_id=_agent_id)
                await registrar_mensaje_usuario(msg.telefono, agent_id=_agent_id)
                # Si hay caption, lo usamos como mensaje "real" para Claude
                caption = (media_payload.get("caption") or "").strip()
                tipo_media = media_payload.get("tipo", "media")
                tipo_legible = {
                    "image": "imagen", "video": "video",
                    "document": "documento", "location": "ubicación",
                    "audio": "audio"
                }.get(tipo_media, "archivo")
                if caption:
                    # Reescribir msg.texto para que Claude responda al caption con contexto
                    msg = type(msg)(
                        telefono=msg.telefono,
                        texto=f"[Cliente envió {tipo_legible}] {caption}",
                        mensaje_id=msg.mensaje_id,
                        es_propio=msg.es_propio,
                    )
                else:
                    # Sin caption: Andrea reconoce que llegó media pero no continúa con Claude
                    # — el operador humano debe responder. Solo registramos.
                    logger.info(f"Media {tipo_media} de {msg.telefono} sin caption — no se invoca Claude")
                    continue

            # ── Orden directa desde catálogo nativo WhatsApp ──────────────────
            # El cliente armó su carrito en WhatsApp y confirmó — bypaseamos Claude
            # y creamos el checkout de Shopify directamente.
            if msg.texto.startswith("__ORDEN_CATALOGO__:"):
                await registrar_mensaje_usuario(msg.telefono, agent_id=_agent_id)
                logger.info(f"[orden-catalogo] Recibida orden de {msg.telefono}: {msg.texto[:500]}")
                try:
                    items_raw = json.loads(msg.texto[len("__ORDEN_CATALOGO__:"):])
                    # ── Merge inteligente: solo sumar si el carrito previo está
                    # FRESCO (actividad < CARRITO_MERGE_HORAS = 2h). Si está viejo
                    # entre 2h y 4h, REEMPLAZAR — evita acumular pedidos olvidados
                    # de ayer. Si vacío o expirado (>4h), arrancar limpio.
                    carrito_previo = await obtener_carrito_activo(msg.telefono, agent_id=_agent_id)
                    es_fresco = await carrito_es_fresco_para_merge(msg.telefono, agent_id=_agent_id)
                    if carrito_previo and not es_fresco:
                        logger.info(
                            f"[orden-catalogo] Carrito previo encontrado pero NO fresco "
                            f"({len(carrito_previo)} items) — REEMPLAZANDO (no merge)"
                        )
                        # Limpiar antes para que el guardado sea solo lo nuevo
                        await limpiar_carrito_activo(msg.telefono, agent_id=_agent_id)
                        carrito_previo = []
                    # ── Construir 'productos' UNIFICANDO carrito_previo + items_raw nuevos.
                    # El método anterior descartaba la info completa del carrito_previo
                    # cuando lookup en _sku_map fallaba — por eso a veces faltaban items
                    # en el checkout. Ahora preservamos la info: si el lookup falla,
                    # usamos la info del carrito_previo que ya está completa.
                    productos = []
                    no_encontrados = []
                    ya_agregados: dict[str, dict] = {}

                    # Paso 1: items_raw (la orden NUEVA que acaba de llegar)
                    # CRÍTICO: cada item de productos lleva su retailer_id desde el inicio.
                    # Sin esto, cuando se guarde en carrito_activo el rid quedaba "" para
                    # items mergeados → siguiente merge los descartaba → bug del producto perdido.
                    for item in items_raw:
                        rid = item.get("product_retailer_id", "")
                        qty = int(item.get("quantity", 1))
                        if not rid:
                            continue
                        info = obtener_producto_por_retailer_id(rid)
                        if not info:
                            logger.warning(f"[orden-catalogo] rid '{rid}' no en _sku_map — recargando catálogo")
                            await obtener_catalogo_shopify()
                            info = obtener_producto_por_retailer_id(rid)
                        if info:
                            precio = info["precio_unitario"]
                            item_full = {
                                "producto": info["producto"],
                                "presentacion": info["presentacion"],
                                "cantidad": qty,
                                "precio_unitario": precio,
                                "subtotal": precio * qty,
                                "retailer_id": rid,   # ← clave para persistir y futuros merges
                            }
                            productos.append(item_full)
                            ya_agregados[rid] = item_full
                            logger.info(f"[orden-catalogo-nuevo] rid={rid} → {info['producto']} · {info['presentacion']} × {qty}")
                        else:
                            no_encontrados.append(rid)
                            from agent.tools import _sku_map
                            logger.error(
                                f"[orden-catalogo] rid '{rid}' NO existe en _sku_map (entradas: {len(_sku_map)})"
                            )

                    # Paso 2: carrito_previo (items del pedido anterior, info ya completa
                    # en BD). Si un rid ya viene en items_raw, sumamos cantidades. Si NO
                    # estaba, agregamos como item NUEVO usando la info persistida —
                    # crítico: aunque _sku_map ya no lo conozca, el carrito_previo SÍ tiene
                    # la info completa (producto, presentación, precio) → checkout completo.
                    if carrito_previo:
                        logger.info(f"[orden-catalogo] Mergeando con carrito previo (fresco): {len(carrito_previo)} items")
                        for prev in carrito_previo:
                            rid = prev.get("retailer_id") or prev.get("product_retailer_id") or ""
                            qty_prev = int(prev.get("quantity", prev.get("cantidad", 1)))
                            if not rid:
                                logger.warning(f"[orden-catalogo] carrito_previo item sin retailer_id — descarto: {prev}")
                                continue
                            if rid in ya_agregados:
                                # Mismo producto en orden nueva — sumar cantidades
                                ya_agregados[rid]["cantidad"] += qty_prev
                                ya_agregados[rid]["subtotal"] = (
                                    ya_agregados[rid]["cantidad"]
                                    * ya_agregados[rid]["precio_unitario"]
                                )
                            else:
                                # Item del carrito previo NO viene en la nueva orden —
                                # preservarlo (no descartar). Si tiene info completa
                                # persistida usar esa; si no, intentar lookup último recurso.
                                prod_prev = prev.get("producto", "")
                                pres_prev = prev.get("presentacion", "")
                                precio_prev = prev.get("precio_unitario", 0) or 0
                                subt_prev = prev.get("subtotal") or (precio_prev * qty_prev)
                                if not prod_prev:
                                    info_prev = obtener_producto_por_retailer_id(rid)
                                    if info_prev:
                                        prod_prev = info_prev["producto"]
                                        pres_prev = info_prev["presentacion"]
                                        precio_prev = info_prev["precio_unitario"]
                                        subt_prev = precio_prev * qty_prev
                                    else:
                                        logger.warning(
                                            f"[orden-catalogo] carrito_previo rid='{rid}' sin info — descarto"
                                        )
                                        continue
                                item_prev_full = {
                                    "producto": prod_prev,
                                    "presentacion": pres_prev,
                                    "cantidad": qty_prev,
                                    "precio_unitario": precio_prev,
                                    "subtotal": subt_prev,
                                    "retailer_id": rid,   # ← preservar para persistir
                                }
                                productos.append(item_prev_full)
                                ya_agregados[rid] = item_prev_full
                                logger.info(f"[orden-catalogo-previo] rid={rid} → {prod_prev} · {pres_prev} × {qty_prev}")
                        logger.info(f"[orden-catalogo] Total después de merge: {len(productos)} items")

                    if no_encontrados:
                        logger.error(f"[orden-catalogo] IDs sin mapear ({len(no_encontrados)}/{len(items_raw)}): {no_encontrados}")

                    if productos:
                        total = sum(p["subtotal"] for p in productos)

                        # ── Validar pedido mínimo ANTES de crear checkout ──
                        try:
                            pedido_min_str = await get_config_value("PEDIDO_MINIMO", _agent_id) or os.getenv("PEDIDO_MINIMO", "0")
                            pedido_min = int(float(pedido_min_str)) if pedido_min_str else 0
                        except Exception:
                            pedido_min = 0

                        if pedido_min > 0 and total < pedido_min:
                            falta = pedido_min - total
                            # ── Guardar items en carrito_activo con info COMPLETA ──
                            # FIX RAÍZ: usamos 'productos' (que YA tiene el merge completo
                            # con retailer_ids correctos), NO 'items_raw' (solo orden nueva).
                            # Antes, items del carrito previo se guardaban con rid="" y se
                            # perdían en el próximo merge.
                            items_para_carrito = [
                                {
                                    "retailer_id":     p.get("retailer_id", ""),
                                    "quantity":        p["cantidad"],
                                    "cantidad":        p["cantidad"],
                                    "producto":        p["producto"],
                                    "presentacion":    p["presentacion"],
                                    "precio_unitario": p["precio_unitario"],
                                    "subtotal":        p["subtotal"],
                                }
                                for p in productos
                            ]
                            try:
                                await guardar_carrito_activo(msg.telefono, items_para_carrito, agent_id=_agent_id)
                                logger.info(f"[orden-catalogo] Guardado en carrito_activo: {len(items_para_carrito)} items completos")
                            except Exception as e:
                                logger.error(f"Error guardando carrito_activo: {e}")

                            # Mensaje configurable por agente
                            lineas_pedido = "\n".join(
                                f"  • {p['producto']} {p['presentacion']} × {p['cantidad']} = ${p['subtotal']:,}".replace(",", ".")
                                for p in productos
                            )
                            msg_template = await get_config_value("PEDIDO_MIN_MSG", _agent_id) or (
                                "😊 ¡Tu pedido va muy bien! Lo que tienes:\n\n"
                                "{ITEMS}\n\n"
                                "💰 *Subtotal:* ${SUBTOTAL}\n"
                                "📦 *Pedido mínimo:* ${MINIMO}\n"
                                "➕ *Te faltan:* ${FALTA} para confirmar 🎯\n\n"
                                "✅ *No te preocupes, tu pedido quedó guardado.* "
                                "Solo agrega más productos en el catálogo de abajo "
                                "y *se sumará automáticamente* a lo que ya tenías. 🛒"
                            )
                            mensaje_minimo = (msg_template
                                .replace("{SUBTOTAL}", f"{total:,}".replace(",", "."))
                                .replace("{MINIMO}",   f"{pedido_min:,}".replace(",", "."))
                                .replace("{FALTA}",    f"{falta:,}".replace(",", "."))
                                .replace("{ITEMS}",    lineas_pedido)
                            )
                            # Enviar SIEMPRE el texto primero
                            await _proveedor_agente.enviar_mensaje(msg.telefono, mensaje_minimo)
                            # Persistir en BD para que el operador vea este mensaje
                            # en el panel de Conversaciones (antes se perdía).
                            await _guardar_con_wamid(_proveedor_agente, msg.telefono, mensaje_minimo, agent_id=_agent_id)

                            # Catalog_message removido: cuelga WhatsApp Business
                            # app en algunos Android (Meta side bug). Vamos directo
                            # al product_list que es estable en todos los devices.
                            logger.info(f"[pedido-min] Enviando product_list a {msg.telefono}")
                            cat_reabierto = False
                            tiene_metodo = hasattr(_proveedor_agente, "enviar_catalogo_productos")
                            logger.info(f"[pedido-min] tiene enviar_catalogo_productos={tiene_metodo}")
                            if tiene_metodo:
                                # Async: garantiza que _fb_items esté cargado antes
                                # de armar el payload (defensa contra cold start).
                                from agent.tools import obtener_secciones_catalogo_async, _fb_items
                                secciones = await obtener_secciones_catalogo_async(None)
                                logger.info(
                                    f"[pedido-min] _fb_items={len(_fb_items)} | secciones={len(secciones)} | "
                                    f"items_en_secciones={sum(len(s.get('product_items', [])) for s in secciones)}"
                                )
                                if secciones:
                                    try:
                                        cat_reabierto = await _proveedor_agente.enviar_catalogo_productos(
                                            msg.telefono, "Agrega más productos 🌿",
                                            "Tu carrito anterior está guardado — lo nuevo se suma automáticamente.",
                                            secciones,
                                        )
                                        logger.info(f"[pedido-min] cat_reabierto={cat_reabierto}")
                                    except Exception as e_pl:
                                        logger.error(f"[pedido-min] product_list excepción: {e_pl}", exc_info=True)
                                else:
                                    logger.warning(f"[pedido-min] secciones VACÍAS — no se mandó product_list")
                            # Mensaje de cierre — depende de si el catálogo nativo se abrió o no:
                            #   ✅ OK   → texto sugerente "escribe o explora el catálogo"
                            #   ❌ Fail → ESCALAR a humano (el cliente esperaba una respuesta
                            #             concreta; sin catálogo no podemos cerrar la venta).
                            # NUNCA mandamos link a tienda web — eso rompería el flujo del
                            # carrito nativo (universos separados que no se sincronizan).
                            if cat_reabierto:
                                texto_final = (
                                    "Escríbeme qué más quieres agregar y te ayudo, "
                                    "o explora el catálogo en *Ver artículos* 👆🌿"
                                )
                                await _proveedor_agente.enviar_mensaje(msg.telefono, texto_final)
                                await _guardar_con_wamid(_proveedor_agente, msg.telefono, texto_final, agent_id=_agent_id)
                            else:
                                # Meta nativo no disponible → escalar
                                await _escalar_meta_fallo(
                                    msg.telefono,
                                    motivo_corto="post-pedido bajo mínimo",
                                    contexto_extra=(
                                        f"Cliente cerró pedido por ${total:,} pero el mínimo es "
                                        f"${pedido_min:,} (faltan ${falta:,}). Catálogo nativo no "
                                        f"se pudo enviar para completar el pedido. Items actuales: "
                                        + ", ".join(f"{p['producto']} x{p['cantidad']}" for p in productos)
                                    ).replace(",", "."),
                                    agent_id=_agent_id,
                                )
                            logger.info(f"Pedido bajo mínimo: total={total}, min={pedido_min}, falta={falta} — items guardados para acumular")
                            continue  # No crear checkout

                        datos_pedido = {"productos": productos, "total": total}
                        checkout_url = await crear_checkout_shopify(msg.telefono, datos_pedido)
                        if checkout_url:
                            await guardar_pedido_pendiente(msg.telefono, productos, agent_id=_agent_id)
                            # IMPORTANTE: NO limpiar carrito_activo aquí — el cliente puede
                            # agregar más productos para alcanzar envío gratis. El carrito
                            # se limpia cuando llega webhook orders/paid de Shopify (pago
                            # confirmado) o cuando expira el TTL de 4h.
                            #
                            # FIX RAÍZ: 'productos' YA tiene retailer_id de cada item
                            # (paso 1 y paso 2 del merge lo agregaron). Usamos eso
                            # directamente — antes buscábamos rids en items_raw lo cual
                            # solo encontraba el rid del último pedido, dejando los items
                            # mergeados con rid="" y perdiéndolos en el siguiente pedido.
                            items_carrito_full = [
                                {
                                    "retailer_id":     p.get("retailer_id", ""),
                                    "quantity":        p["cantidad"],
                                    "cantidad":        p["cantidad"],
                                    "producto":        p["producto"],
                                    "presentacion":    p["presentacion"],
                                    "precio_unitario": p["precio_unitario"],
                                    "subtotal":        p["subtotal"],
                                }
                                for p in productos
                            ]
                            try:
                                await guardar_carrito_activo(msg.telefono, items_carrito_full, agent_id=_agent_id)
                            except Exception as e_c:
                                logger.warning(f"No pude actualizar carrito_activo: {e_c}")
                            # Guardar checkout_url para que el cliente pueda confirmar después
                            try:
                                await guardar_checkout_url(msg.telefono, checkout_url, agent_id=_agent_id)
                            except Exception as e_url:
                                logger.warning(f"No pude guardar checkout_url: {e_url}")

                            # ── Detectar si alcanzó envío gratis ──────────────
                            try:
                                umbral_gratis_local = obtener_umbral_envio_gratis()
                            except Exception:
                                umbral_gratis_local = 0
                            try:
                                costo_envio_local = obtener_costo_envio()
                            except Exception:
                                costo_envio_local = 0

                            total_fmt_loc = f"{total:,}".replace(",", ".")

                            # CASO A: alcanza mínimo PERO no envío gratis
                            # Estrategia: 2 mensajes separados — uno con botón "Ver
                            # catálogo" (para agregar más) y otro con CTA URL directo
                            # al checkout. WhatsApp no soporta 2 CTA URL en un mismo
                            # mensaje, así que es la forma más limpia.
                            # IMPORTANTE: la promesa de "envío gratis" solo aplica si
                            # el cliente está en zona local. Verificamos su ciudad.
                            if umbral_gratis_local > 0 and total < umbral_gratis_local:
                                falta_gratis = umbral_gratis_local - total
                                falta_g_fmt = f"{falta_gratis:,}".replace(",", ".")
                                envio_fmt = f"{costo_envio_local:,}".replace(",", ".") if costo_envio_local else "0"

                                # Detectar ciudad del cliente
                                try:
                                    cliente_info_a = await obtener_cliente(msg.telefono, agent_id=_agent_id)
                                except Exception:
                                    cliente_info_a = None
                                ciudad_a = (cliente_info_a.get("ciudad") if cliente_info_a else "") or ""
                                ciudad_a = ciudad_a.strip().lower()
                                ciudades_loc_raw = (
                                    await get_config_value("CIUDADES_ENVIO_PROPIO", _agent_id)
                                    or os.getenv("CIUDADES_ENVIO_PROPIO", "cali")
                                )
                                ciudades_loc = {
                                    c.strip().lower() for c in ciudades_loc_raw.split(",") if c.strip()
                                }
                                es_local_a = ciudad_a in ciudades_loc if ciudad_a else None

                                # ── Mensaje 1: invitar a agregar más (configurable por agente) ──
                                # El template del cliente decide qué decir: si quiere mencionar
                                # zonas de envío gratis, descuento, etc., usa los placeholders
                                # dinámicos {total} {falta_envio_gratis} {descuento_codigo} etc.
                                # Eliminamos la rama por "es_local_a" — el cliente personaliza
                                # su mensaje según su modelo de negocio, no asumimos nada.
                                from agent.mensajes import format_seguro
                                _ctx_estado4 = await construir_contexto_placeholders(_agent_id)
                                _ctx_estado4["total"] = total_fmt_loc
                                _ctx_estado4["falta_envio_gratis"] = falta_g_fmt if falta_g_fmt else ""
                                mensaje_agregar = format_seguro(
                                    await obtener_mensaje(_agent_id, "cart.estado4_cross_sell"),
                                    _ctx_estado4,
                                )
                                # Si el agente desactivó el cross-sell, no enviamos sugerencia ni
                                # catálogo extra — saltamos directo al CTA de pago abajo.
                                if mensaje_agregar:
                                    # catalog_message removido — directo a product_list (estable en WB).
                                    cat_btn_ok = False
                                    if hasattr(_proveedor_agente, "enviar_catalogo_productos"):
                                        secciones_loc = obtener_secciones_catalogo(None)
                                        if secciones_loc:
                                            try:
                                                await _proveedor_agente.enviar_catalogo_productos(
                                                    msg.telefono, "Agrega más productos 🌿",
                                                    mensaje_agregar[:1024], secciones_loc,
                                                )
                                                cat_btn_ok = True
                                            except Exception:
                                                pass
                                    if not cat_btn_ok:
                                        await _proveedor_agente.enviar_mensaje(msg.telefono, mensaje_agregar)
                                    # Siempre persistir el texto del mensaje (sea por product_list o por
                                    # fallback). El cuerpo del product_list NO se guarda automáticamente
                                    # — sin esto el operador NO ve el "¡Pedido confirmado!" en el panel.
                                    await _guardar_con_wamid(_proveedor_agente, msg.telefono, mensaje_agregar, agent_id=_agent_id)

                                # ── Mensaje 2: CTA al checkout (texto + botón configurables) ──
                                mensaje_confirmar = format_seguro(
                                    await obtener_mensaje(_agent_id, "cart.estado4_cta_texto"),
                                    _ctx_estado4,
                                )
                                _boton_label = (
                                    await obtener_mensaje(_agent_id, "cart.checkout_listo_boton")
                                ).strip() or "Confirmar pedido"
                                if hasattr(_proveedor_agente, "enviar_cta_url"):
                                    await _proveedor_agente.enviar_cta_url(
                                        msg.telefono, mensaje_confirmar,
                                        _boton_label, checkout_url,
                                    )
                                else:
                                    await _proveedor_agente.enviar_mensaje(
                                        msg.telefono, f"{mensaje_confirmar}\n\n👉 {checkout_url}"
                                    )
                                # Persistir el mensaje en BD (panel lo necesita).
                                await _guardar_con_wamid(_proveedor_agente, msg.telefono, mensaje_confirmar, agent_id=_agent_id)
                                # Botones determinísticos del carrito (Ver/Vaciar)
                                # — el cliente SIEMPRE debe poder gestionar antes de pagar.
                                if hasattr(_proveedor_agente, "enviar_botones_reply"):
                                    try:
                                        await _proveedor_agente.enviar_botones_reply(
                                            msg.telefono, "¿O prefieres revisar tu carrito antes?",
                                            _botones_carrito_estandar(ofrece_confirmar=False),
                                        )
                                    except Exception as e:
                                        logger.warning(f"[pedido-min] botones carrito fallaron: {e}")
                                continue  # No pasar por Claude

                            # CASO B: carrito >= umbral envío gratis (o agent que no usa zonas)
                            # Mensaje + botón 100% configurables. El cliente decide qué decir
                            # según su modelo de envío (gratis a una zona, transportadora,
                            # solo pickup, etc.). Reutilizamos los mismos mensajes que el
                            # flujo de checkout directo para mantener UX consistente.
                            from agent.mensajes import format_seguro
                            _ctx_estado5 = await construir_contexto_placeholders(_agent_id)
                            _ctx_estado5["total"] = total_fmt_loc
                            texto_checkout = format_seguro(
                                await obtener_mensaje(_agent_id, "cart.checkout_listo_texto"),
                                _ctx_estado5,
                            )
                            _boton_label_b = (
                                await obtener_mensaje(_agent_id, "cart.checkout_listo_boton")
                            ).strip() or "Confirmar pedido"
                            if hasattr(_proveedor_agente, "enviar_cta_url"):
                                await _proveedor_agente.enviar_cta_url(
                                    msg.telefono, texto_checkout,
                                    _boton_label_b, checkout_url
                                )
                            else:
                                await _proveedor_agente.enviar_mensaje(
                                    msg.telefono, f"{texto_checkout}\n\n👉 {checkout_url}"
                                )
                            # Persistir el mensaje (panel lo necesita)
                            await _guardar_con_wamid(_proveedor_agente, msg.telefono, texto_checkout, agent_id=_agent_id)
                            # Botones determinísticos del carrito
                            if hasattr(_proveedor_agente, "enviar_botones_reply"):
                                try:
                                    await _proveedor_agente.enviar_botones_reply(
                                        msg.telefono, "¿O prefieres revisar tu carrito antes?",
                                        _botones_carrito_estandar(ofrece_confirmar=False),
                                    )
                                except Exception as e:
                                    logger.warning(f"[caso-B] botones carrito fallaron: {e}")
                        else:
                            _txt_err = await obtener_mensaje(_agent_id, "error.procesar_pedido_fallo")
                            if _txt_err:
                                await _proveedor_agente.enviar_mensaje(msg.telefono, _txt_err)
                                await _guardar_con_wamid(_proveedor_agente, msg.telefono, _txt_err, agent_id=_agent_id)
                    else:
                        _txt_err2 = await obtener_mensaje(_agent_id, "error.productos_no_reconocidos")
                        if _txt_err2:
                            await _proveedor_agente.enviar_mensaje(msg.telefono, _txt_err2)
                            await _guardar_con_wamid(_proveedor_agente, msg.telefono, _txt_err2, agent_id=_agent_id)
                except Exception as e:
                    logger.error(f"Error procesando orden catálogo: {e}")
                    _txt_exc = await obtener_mensaje(_agent_id, "error.excepcion_pedido")
                    if _txt_exc:
                        await _proveedor_agente.enviar_mensaje(msg.telefono, _txt_exc)
                continue  # No pasa por Claude

            # Cliente respondió → resetea timers de seguimiento
            await registrar_mensaje_usuario(msg.telefono, agent_id=_agent_id)

            # Modo humano: guardar mensaje pero no responder con Andrea
            if await get_modo_humano(msg.telefono, agent_id=_agent_id):
                await guardar_mensaje(msg.telefono, "user", msg.texto, agent_id=_agent_id)
                logger.info(f"Modo humano activo — {msg.telefono} — Andrea no responde")
                continue

            historial = await obtener_historial(msg.telefono, agent_id=_agent_id)

            # CAPI: Lead — primera vez que este número escribe a Andrea
            if not historial:
                asyncio.create_task(capi_lead(msg.telefono))

            # ── Contexto de campaña ───────────────────────────────────────────
            # Si el cliente responde dentro de las 72 h de recibir una difusión,
            # Andrea sabe de qué producto/campaña viene y no lo pregunta de nuevo.
            contexto_campana = await obtener_campana_reciente_para_telefono(msg.telefono, agent_id=_agent_id)
            if contexto_campana:
                logger.warning(
                    f"[campaña✅] {msg.telefono} respondió a campaña "
                    f'"{contexto_campana["campaign_name"]}" '
                    f'(hace {contexto_campana["horas_ago"]}h)'
                )
            else:
                logger.warning(
                    f"[campaña❌] Sin campaña reciente en difusion_mensajes para {msg.telefono}"
                )

            # Delay natural en sandbox: hace que el agente parezca que está escribiendo
            if _is_sandbox_msg:
                await asyncio.sleep(1.5)

            respuesta = await generar_respuesta(
                msg.texto, historial, msg.telefono, contexto_campana, agent_id=_agent_id
            )

            await guardar_mensaje(msg.telefono, "user", msg.texto, agent_id=_agent_id)
            # El wamid se conoce recién tras el envío real más abajo (después
            # de procesar marcadores) — guardamos sin wamid y lo actualizamos
            # luego con actualizar_wamid_mensaje() (#79, fix: capturaba antes
            # del envío y siempre quedaba vacío).
            _msg_id_assistant = await guardar_mensaje(
                msg.telefono, "assistant", respuesta, agent_id=_agent_id,
            )
            await registrar_mensaje_asistente(msg.telefono, agent_id=_agent_id)

            # Procesar marcadores via dispatcher MARKER_HANDLERS:
            #   [[CARRITO:[...]]], [[VACIAR_CARRITO]], [[MOSTRAR_CARRITO]],
            #   [[ESCALAR:...]], [[PEDIDO:...]], [[CIERRE_CONV:]]
            #
            # Los marcadores interactivos (BOTONES, LISTA, TIENDA, PRODUCTO,
            # CATALOGO_CAT) aún se procesan inline más abajo — se migrarán
            # en la fase E del refactor.
            _marker_ctx = MarkerContext(
                respuesta=respuesta, telefono=msg.telefono, agent_id=_agent_id,
            )
            _marker_ctx = await aplicar_marcadores(_marker_ctx)
            respuesta        = _marker_ctx.respuesta
            checkout_url     = _marker_ctx.checkout_url
            checkout_fallo   = _marker_ctx.checkout_fallo
            datos_escalacion = _marker_ctx.datos_escalacion

            # [[MOSTRAR_CARRITO]] requiere envío inmediato — _enviar_resumen_carrito
            # vive en main.py (necesita acceso al proveedor de WhatsApp), por
            # eso el handler solo levanta un flag y aquí ejecutamos la acción.
            if _marker_ctx.mostrar_carrito_pendiente:
                try:
                    await _enviar_resumen_carrito(msg.telefono, agent_id=_agent_id)
                    logger.info(f"[MOSTRAR_CARRITO] resumen enviado a {msg.telefono}")
                except Exception as e:
                    logger.error(f"Error mostrando carrito de {msg.telefono}: {e}")

            if _marker_ctx.mostrar_citas_pendiente:
                try:
                    await _enviar_horarios_calendly(msg.telefono, agent_id=_agent_id)
                    respuesta = ""  # la lista interactiva ya es la respuesta; evitar doble envío
                    logger.info(f"[CITA_DISPONIBILIDAD] horarios enviados a {msg.telefono}")
                except Exception as e:
                    logger.error(f"Error enviando horarios Calendly a {msg.telefono}: {e}")

            # [[MOSTRAR_CARRITO]], [[PEDIDO:...]], [[ESCALAR:...]] y
            # [[CIERRE_CONV:]] ya fueron procesados por MARKER_HANDLERS arriba.
            # Los 5 marcadores interactivos (CATALOGO_CAT, BOTONES, LISTA,
            # TIENDA, PRODUCTO) también — solo extraemos los resultados del
            # contexto. El ENVÍO de cada uno sigue inline acá abajo porque
            # tiene dependencias de orden, fallbacks y estado local
            # (_proveedor_agente, _agent_id) que no conviene mover sin un
            # refactor mayor del bloque de envío.
            # NOTA: NO reasignar respuesta aquí — puede haber sido limpiada
            # intencionalmente (e.g. respuesta="" cuando se envió la lista de Calendly).
            datos_catalogo_cat     = _marker_ctx.datos_catalogo_cat
            datos_botones          = _marker_ctx.datos_botones
            datos_lista            = _marker_ctx.datos_lista
            abrir_tienda           = _marker_ctx.abrir_tienda
            tienda_query           = _marker_ctx.tienda_query
            productos_mencionados  = _marker_ctx.productos_mencionados

            # Enviar texto primero
            # Excepción: si hay CTA de catálogo general (sin query), el texto de Andrea
            # se fusiona como cuerpo del CTA para que quede un único mensaje de bienvenida.
            _texto_absorbido_por_cta = abrir_tienda and not tienda_query and respuesta.strip()
            if respuesta and not _texto_absorbido_por_cta:
                await _proveedor_agente.enviar_mensaje(msg.telefono, respuesta)
                # Chulitos de confirmación (#79): ahora sí el provider ya tiene
                # el wamid real de este envío — actualizamos el mensaje guardado.
                await _vincular_wamid_post_envio(_proveedor_agente, _msg_id_assistant)

            # ── [[PRODUCTO:nombre]] — enviar uno o más productos del catálogo ──
            # Andrea lo usa cuando menciona un producto específico. Por cada
            # producto: single_product (con +/- nativos al tocar "Ver") + cta_url
            # (link directo a la tienda como alternativa).
            if productos_mencionados and hasattr(_proveedor_agente, "enviar_producto"):
                from agent.tools import _sku_map, _normalizar, obtener_url_producto
                # Construir índice (producto_norm + presentacion_norm) → retailer_id largo
                _producto_idx: dict[str, str] = {}
                for rid, info in _sku_map.items():
                    if not (rid.isdigit() and len(rid) >= 10):
                        continue  # Solo variant_id largos (los que sí están en FB Catalog)
                    prod_n = _normalizar(info.get("producto", ""))
                    pres_n = _normalizar(info.get("presentacion", ""))
                    _producto_idx[f"{prod_n}|{pres_n}"] = rid
                    # También indexar solo por producto (sin presentación) → primera variante
                    if prod_n not in _producto_idx:
                        _producto_idx[prod_n] = rid

                for nombre_prod in productos_mencionados[:3]:  # max 3 productos por mensaje
                    partes = [p.strip() for p in nombre_prod.split("|", 1)]
                    nombre = partes[0]
                    presentacion = partes[1] if len(partes) > 1 else ""
                    nombre_n = _normalizar(nombre)
                    pres_n   = _normalizar(presentacion)
                    rid_match = ""
                    if pres_n:
                        rid_match = _producto_idx.get(f"{nombre_n}|{pres_n}", "")
                    if not rid_match:
                        # Buscar coincidencia parcial por nombre
                        for k, v in _producto_idx.items():
                            if "|" in k and nombre_n in k.split("|")[0]:
                                rid_match = v
                                break
                        if not rid_match:
                            rid_match = _producto_idx.get(nombre_n, "")
                    if not rid_match:
                        logger.warning(f"[PRODUCTO] No se encontró '{nombre_prod}' en _sku_map")
                        continue
                    # 1) Enviar producto del catálogo nativo
                    try:
                        await _proveedor_agente.enviar_producto(msg.telefono, rid_match)
                        logger.info(f"[PRODUCTO] single_product '{nombre_prod}' (rid={rid_match}) enviado")
                    except Exception as e:
                        logger.error(f"[PRODUCTO] Error enviando single_product: {e}")
                        # Registrar falla + alerta al admin
                        await _registrar_falla_catalogo(
                            "single_product", msg.telefono,
                            f"Producto '{nombre_prod}' (rid={rid_match}): {e}",
                            agent_id=_agent_id,
                        )
                        # Fallback: enviar URL del producto en la web
                        try:
                            url_web = obtener_url_producto(nombre)
                            if url_web and hasattr(_proveedor_agente, "enviar_cta_url"):
                                await _proveedor_agente.enviar_cta_url(
                                    msg.telefono,
                                    "Aquí está el producto 🌿",
                                    "Ver producto", url_web,
                                )
                                logger.info(f"[PRODUCTO→FALLBACK-WEB] CTA web enviado: {url_web}")
                        except Exception as e2:
                            logger.error(f"[PRODUCTO] Fallback web también falló: {e2}")
                        continue

            # Catálogo nativo WhatsApp (product_list con fotos reales)
            if datos_catalogo_cat and hasattr(_proveedor_agente, "enviar_catalogo_productos"):
                categoria = datos_catalogo_cat.get("categoria")
                secciones = obtener_secciones_catalogo(categoria)
                cat_enviado = False
                if secciones:
                    header = categoria or await _catalogo_header_for_agent(_agent_id)
                    cuerpo = "Selecciona los productos que quieres, ajusta las cantidades y confirma tu pedido."
                    cat_enviado = await _proveedor_agente.enviar_catalogo_productos(
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
                        _texto_cat_fb = "\n".join(lineas).strip()
                        await _proveedor_agente.enviar_mensaje(msg.telefono, _texto_cat_fb)
                        await _guardar_con_wamid(_proveedor_agente, msg.telefono, _texto_cat_fb, agent_id=_agent_id)

            # Luego enviar mensajes interactivos
            if datos_botones and hasattr(_proveedor_agente, "enviar_botones"):
                try:
                    await _proveedor_agente.enviar_botones(
                        msg.telefono,
                        datos_botones.get("texto", ""),
                        datos_botones.get("botones", [])
                    )
                    logger.info(f"Botones enviados a {msg.telefono}")
                except Exception as e:
                    logger.error(f"Error enviando botones: {e}")

            if datos_lista and hasattr(_proveedor_agente, "enviar_lista"):
                lista_enviada = False
                try:
                    lista_enviada = await _proveedor_agente.enviar_lista(
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
                        _txt_fb = fallback_text[:4000]
                        await _proveedor_agente.enviar_mensaje(msg.telefono, _txt_fb)
                        await _guardar_con_wamid(_proveedor_agente, msg.telefono, _txt_fb, agent_id=_agent_id)
                        logger.info(f"Fallback texto de lista enviado a {msg.telefono}")

            # Cuando Andrea usa [[TIENDA:]] PRIORIZAR catálogo nativo de WhatsApp
            # — el cliente arma su pedido sin salir de WhatsApp. Solo si el
            # catálogo nativo falla (API caída, sin catalog_id, etc.) caemos
            # al fallback de URL a la tienda web.
            if abrir_tienda:
                # Pie del catálogo — configurable por agente desde el panel
                # (Configuración → Mensajes → "Mensaje de bienvenida del catálogo").
                # Los placeholders {minimo}, {envio_gratis}, {descuento_*}, {negocio}
                # se resuelven en runtime contra la config actual del agente —
                # cuando cambia el pedido mínimo en el panel, se refleja en el
                # próximo envío sin redeploy.
                from agent.mensajes import format_seguro
                _pie_template = await obtener_mensaje(_agent_id, "cart.bienvenida_catalogo")
                _ctx_ph = await construir_contexto_placeholders(_agent_id)
                pie_tienda = format_seguro(_pie_template, _ctx_ph)

                # ── Detectar si la query es una categoría conocida ──
                # Si es categoría → product_list de esa categoría (mejor UX)
                # Si no es categoría → catalog_message (botón "Ver catálogo")
                categoria_solicitada = None
                if tienda_query:
                    from agent.tools import ORDEN_CATEGORIAS, _categorias_cache
                    q_norm = tienda_query.lower().strip()
                    # Match exacto contra términos genéricos
                    mapa_terminos = {
                        "lavaloza": "Cocina", "desengrasante": "Cocina",
                        "limpiavidrios": "Cocina", "multiusos": "Cocina",
                        "detergente": "Lavandería", "shampoo": "Lavandería",
                        "desmanchador": "Baño", "ambientador": "Baño",
                        "combos": "Combos", "combo": "Combos",
                    }
                    categoria_solicitada = mapa_terminos.get(q_norm)
                    # Verificar que la categoría exista realmente
                    if categoria_solicitada and categoria_solicitada not in _categorias_cache:
                        categoria_solicitada = None

                # Si lo que Andrea escribió en query no es categoría reconocida
                # pero suena a producto, intentar enviar single_product
                if tienda_query and not categoria_solicitada:
                    # Intentar buscar el producto específico en _sku_map
                    from agent.tools import _sku_map, _normalizar
                    q_n = _normalizar(tienda_query)
                    rid_match = ""
                    for rid, info in _sku_map.items():
                        if not (rid.isdigit() and len(rid) >= 10):
                            continue
                        prod_n = _normalizar(info.get("producto", ""))
                        if q_n in prod_n or prod_n in q_n:
                            rid_match = rid
                            break
                    if rid_match and hasattr(_proveedor_agente, "enviar_producto"):
                        try:
                            res_prod = await _proveedor_agente.enviar_producto(msg.telefono, rid_match)
                            if (isinstance(res_prod, dict) and res_prod.get("ok")) or res_prod is True:
                                logger.info(f"[TIENDA→PRODUCTO] '{tienda_query}' → producto {rid_match} enviado")
                                # Saltarse el resto del bloque tienda
                                continue
                        except Exception as e:
                            logger.warning(f"[TIENDA→PRODUCTO] error: {e}")

                # Construir texto/cuerpo del catálogo. Si el agente desactivó
                # el mensaje de bienvenida (pie_tienda == ""), se envía solo
                # la parte de invitación sin pie — limpio, sin saltos vacíos.
                _pie_sufijo = ("\n" + pie_tienda) if pie_tienda else ""
                if _texto_absorbido_por_cta:
                    cuerpo_catalogo = respuesta.strip() + ("\n\n" + pie_tienda if pie_tienda else "")
                elif tienda_query:
                    cuerpo_catalogo = "🛒 *Aquí está lo que tenemos:*" + _pie_sufijo
                else:
                    cuerpo_catalogo = (
                        "🛒 *Aquí está nuestro catálogo completo — arma tu pedido sin salir de WhatsApp:*"
                        + _pie_sufijo
                    )

                # ── INTENTO 1: product_list de la categoría (o general) ──
                enviado_catalogo_wa = False
                if hasattr(_proveedor_agente, "enviar_catalogo_productos"):
                    try:
                        secciones = obtener_secciones_catalogo(categoria_solicitada)
                        if secciones:
                            header_cat = categoria_solicitada or await _catalogo_header_for_agent(_agent_id)
                            enviado_catalogo_wa = await _proveedor_agente.enviar_catalogo_productos(
                                msg.telefono, header_cat,
                                cuerpo_catalogo[:1024],
                                secciones,
                            )
                            if enviado_catalogo_wa:
                                logger.info(f"[TIENDA→catalogo-WA] product_list enviado a {msg.telefono} (cat={categoria_solicitada})")
                                # #79 — si el texto de Andrea se fusionó en este
                                # mensaje (_texto_absorbido_por_cta), el row de
                                # historial guardado antes (_msg_id_assistant)
                                # aún no tiene wamid: actualizarlo ahora.
                                if _texto_absorbido_por_cta:
                                    await _vincular_wamid_post_envio(_proveedor_agente, _msg_id_assistant)
                    except Exception as e:
                        logger.warning(f"[TIENDA] product_list falló: {e}")

                # ── FALLBACK: ESCALAR a humano ────────────────────────────
                # Si product_list falla, NO mandamos link a tienda web — eso
                # rompe el flujo del carrito nativo (universos separados que
                # no se sincronizan). Escalar es mejor UX: un humano abre el
                # catálogo manualmente con el cliente y cierra la venta.
                if not enviado_catalogo_wa:
                    await _registrar_falla_catalogo(
                        "tienda_catalogo_wa", msg.telefono,
                        f"product_list falló (query='{tienda_query}')",
                        agent_id=_agent_id,
                    )
                    logger.info(f"[TIENDA→ESCALAR] catálogo WA no disponible para {msg.telefono}")
                    await _escalar_meta_fallo(
                        msg.telefono,
                        motivo_corto=f"[[TIENDA:{tienda_query or 'completo'}]] fallido",
                        contexto_extra=(
                            f"Cliente pidió ver catálogo "
                            f"({'categoría: ' + tienda_query if tienda_query else 'general'}). "
                            f"product_list nativo falló — necesita asesor para mostrar productos."
                        ),
                        agent_id=_agent_id,
                    )

            # Enviar link de checkout de Shopify si se generó Y es válido
            # (con /checkouts/ — no la home). Si es inválido, intentar
            # autoreparar antes de mandar al cliente un botón muerto.
            if checkout_url and not _es_url_checkout_valida(checkout_url):
                logger.warning(f"[PEDIDO] checkout_url corrupto: {checkout_url[:60]} — intentando recrear")
                checkout_url = await _obtener_o_recrear_checkout_url(msg.telefono, agent_id=_agent_id)
            if checkout_url:
                # Mensaje y label del botón configurables por agente (#28 fase 2.6)
                from agent.mensajes import format_seguro
                _ctx_ph = await construir_contexto_placeholders(_agent_id)
                # Inyectar {total} — primero intentamos del carrito_activo
                # (autoridad de la verdad). Si está vacío, fallback a 0.
                _ctx_ph["total"] = await _total_carrito_fmt(msg.telefono, _agent_id)
                texto_checkout = format_seguro(
                    await obtener_mensaje(_agent_id, "cart.checkout_listo_texto"),
                    _ctx_ph,
                )
                boton_label = (await obtener_mensaje(_agent_id, "cart.checkout_listo_boton")).strip() or "Confirmar pedido"
                enviado_cta = False
                if hasattr(_proveedor_agente, "enviar_cta_url"):
                    try:
                        enviado_cta = await _proveedor_agente.enviar_cta_url(
                            msg.telefono, texto_checkout, boton_label, checkout_url
                        )
                    except Exception as e:
                        logger.error(f"Error enviando cta_url: {e}")
                if not enviado_cta:
                    await _proveedor_agente.enviar_mensaje(
                        msg.telefono, f"{texto_checkout}\n\n👉 {checkout_url}"
                    )

            # Si la creación del checkout falló (stock agotado, producto no
            # mapeado, etc.) avísale al cliente en vez de quedarnos mudos
            if checkout_fallo:
                _txt_chk_fail = await obtener_mensaje(_agent_id, "error.checkout_no_generado")
                if _txt_chk_fail:
                    await _proveedor_agente.enviar_mensaje(msg.telefono, _txt_chk_fail)

            # Notificar al equipo si Andrea decidió escalar
            if datos_escalacion:
                await _notificar_escalacion(msg.telefono, datos_escalacion, agent_id=_agent_id)

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
                    # retailer_id es CRÍTICO para que el evento CAPI
                    # AddToCart matchee con el catálogo Meta (sin esto
                    # la proporción de coincidencias cae <90% y los
                    # eventos no optimizan campañas)
                    "retailer_id":   (p.get("retailer_id")
                                      or p.get("product_retailer_id")
                                      or p.get("sku") or ""),
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
VOCO_COOKIE = "voco_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 días


def _verificar_admin(token: str) -> bool:
    """Valida el token de administrador (legacy sync — mantiene compatibilidad con 47 call sites)."""
    if not ADMIN_TOKEN:
        return False
    return hmac.compare_digest(token or "", ADMIN_TOKEN)


async def _obtener_sesion_usuario(token: str) -> dict | None:
    """Retorna el dict del usuario autenticado por token de sesión, o None.
    Prueba primero el nuevo sistema de sesiones; fallback al ADMIN_TOKEN legacy."""
    if not token:
        return None
    # Nuevo sistema: sesión de usuario registrado en BD
    try:
        user = await verificar_sesion(token)
        if user:
            return user
    except Exception as e:
        logger.warning(f"[sesion] Error verificando sesión DB: {e}")
    # Fallback legacy: ADMIN_TOKEN para compatibilidad con setup de Railway existente
    if ADMIN_TOKEN and hmac.compare_digest(token, ADMIN_TOKEN):
        return {"id": 0, "email": "admin@voco.local", "rol": "admin", "nombre": "Admin", "plan": "admin"}
    # Sin ADMIN_TOKEN configurado → cualquier acceso directo es admin (solo dev)
    if not ADMIN_TOKEN:
        return {"id": 0, "email": "admin@voco.local", "rol": "admin", "nombre": "Admin", "plan": "admin"}
    return None


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
    email = str(form.get("email", "")).strip().lower()

    # Intento 1: login con email + contraseña (nuevo sistema)
    if email:
        user_data = await obtener_usuario_por_email(email)
        if user_data and user_data.get("is_active"):
            try:
                pw_match = bcrypt.checkpw(password.encode(), user_data["password_hash"].encode())
            except Exception:
                pw_match = False
            if pw_match:
                token = await crear_sesion(user_data["id"])
                response = RedirectResponse("/inbox", status_code=302)
                response.set_cookie(
                    VOCO_COOKIE, token,
                    httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax"
                )
                # Compatibilidad con endpoints legacy que leen inbox_session
                if ADMIN_TOKEN:
                    response.set_cookie(
                        INBOX_COOKIE, ADMIN_TOKEN,
                        httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax"
                    )
                return response
        return HTMLResponse(content=obtener_login_html(error=True))

    # Intento 2: login legacy con ADMIN_TOKEN (campo password)
    if _verificar_admin(password):
        response = RedirectResponse("/inbox", status_code=302)
        response.set_cookie(
            INBOX_COOKIE, ADMIN_TOKEN,
            httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax"
        )
        return response
    return HTMLResponse(content=obtener_login_html(error=True))


@app.get("/inbox/logout")
async def inbox_logout(
    voco_session: str = Cookie(default=""),
    inbox_session: str = Cookie(default=""),
):
    if voco_session:
        await cerrar_sesion(voco_session)
    response = RedirectResponse("/inbox/login", status_code=302)
    response.delete_cookie(INBOX_COOKIE)
    response.delete_cookie(VOCO_COOKIE)
    return response


# ── Registro de usuarios (Sprint 1) ─────────────────────────────────────────

@app.get("/auth/register", response_class=HTMLResponse)
async def auth_register_page():
    return HTMLResponse(content=obtener_register_html())


@app.post("/auth/register")
async def auth_register(request: Request):
    form = await request.form()
    nombre   = str(form.get("nombre", "")).strip()
    email    = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    confirm  = str(form.get("confirm_password", ""))

    # Validaciones
    if not nombre or not email or not password:
        return HTMLResponse(content=obtener_register_html(error="Todos los campos son obligatorios"))
    if len(password) < 8:
        return HTMLResponse(content=obtener_register_html(error="La contraseña debe tener al menos 8 caracteres"))
    if password != confirm:
        return HTMLResponse(content=obtener_register_html(error="Las contraseñas no coinciden"))

    # Verificar que el email no exista ya
    existente = await obtener_usuario_por_email(email)
    if existente:
        return HTMLResponse(content=obtener_register_html(error="Este email ya está registrado"))

    # Crear usuario
    try:
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = await crear_usuario(email=email, password_hash=pw_hash, nombre=nombre)
        token = await crear_sesion(user["id"])
        response = RedirectResponse("/inbox", status_code=302)
        response.set_cookie(
            VOCO_COOKIE, token,
            httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax"
        )
        return response
    except Exception as e:
        logger.error(f"[auth/register] Error: {e}")
        return HTMLResponse(content=obtener_register_html(error="Error al crear la cuenta. Intenta de nuevo."))


@app.post("/auth/logout")
async def auth_logout(
    voco_session: str = Cookie(default=""),
    inbox_session: str = Cookie(default=""),
):
    if voco_session:
        await cerrar_sesion(voco_session)
    response = RedirectResponse("/inbox/login", status_code=302)
    response.delete_cookie(INBOX_COOKIE)
    response.delete_cookie(VOCO_COOKIE)
    return response


# ── OAuth Social Login ────────────────────────────────────────────────────

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
FACEBOOK_APP_ID      = os.getenv("FACEBOOK_APP_ID", "")
FACEBOOK_APP_SECRET  = os.getenv("FACEBOOK_APP_SECRET", "")
APP_BASE_URL         = os.getenv("APP_BASE_URL", "https://tienda.equoradistribuciones.com")


@app.get("/auth/google")
async def auth_google():
    """Redirige al flujo OAuth de Google."""
    if not GOOGLE_CLIENT_ID:
        return RedirectResponse("/inbox/login?error=google_not_configured", status_code=302)
    params = (
        f"client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={APP_BASE_URL}/auth/google/callback"
        "&response_type=code"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}", status_code=302)


@app.get("/auth/google/callback")
async def auth_google_callback(code: str = "", error: str = ""):
    """Callback OAuth de Google — intercambia code por token y crea sesión."""
    if error or not code:
        return RedirectResponse("/inbox/login?error=google_cancelled", status_code=302)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Intercambiar code por access_token
            r = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": f"{APP_BASE_URL}/auth/google/callback",
                "grant_type": "authorization_code",
            })
            tokens = r.json()
            access_token = tokens.get("access_token")
            if not access_token:
                raise ValueError(f"No access_token: {tokens}")
            # Obtener perfil del usuario
            profile = (await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )).json()
        email  = (profile.get("email") or "").lower().strip()
        nombre = profile.get("name") or profile.get("given_name") or email
        if not email:
            return RedirectResponse("/inbox/login?error=google_no_email", status_code=302)
        # Buscar o crear usuario
        user_data = await obtener_usuario_por_email(email)
        if not user_data:
            pw_hash = bcrypt.hashpw(secrets.token_urlsafe(24).encode(), bcrypt.gensalt()).decode()
            user_data = await crear_usuario(email=email, password_hash=pw_hash, nombre=nombre)
        if not user_data.get("is_active", True):
            return RedirectResponse("/inbox/login?error=cuenta_inactiva", status_code=302)
        token = await crear_sesion(user_data["id"])
        response = RedirectResponse("/inbox", status_code=302)
        response.set_cookie(VOCO_COOKIE, token, httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax")
        if ADMIN_TOKEN:
            response.set_cookie(INBOX_COOKIE, ADMIN_TOKEN, httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax")
        return response
    except Exception as e:
        logger.error(f"[OAuth Google] {e}")
        return RedirectResponse("/inbox/login?error=google_error", status_code=302)


@app.get("/auth/facebook")
async def auth_facebook():
    """Redirige al flujo OAuth de Facebook."""
    if not FACEBOOK_APP_ID:
        return RedirectResponse("/inbox/login?error=facebook_not_configured", status_code=302)
    params = (
        f"client_id={FACEBOOK_APP_ID}"
        f"&redirect_uri={APP_BASE_URL}/auth/facebook/callback"
        "&scope=email,public_profile"
        "&response_type=code"
    )
    return RedirectResponse(f"https://www.facebook.com/v21.0/dialog/oauth?{params}", status_code=302)


@app.get("/auth/facebook/callback")
async def auth_facebook_callback(code: str = "", error: str = ""):
    """Callback OAuth de Facebook — intercambia code por token y crea sesión."""
    if error or not code:
        return RedirectResponse("/inbox/login?error=facebook_cancelled", status_code=302)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Intercambiar code por access_token
            r = await client.get("https://graph.facebook.com/v21.0/oauth/access_token", params={
                "client_id": FACEBOOK_APP_ID,
                "client_secret": FACEBOOK_APP_SECRET,
                "redirect_uri": f"{APP_BASE_URL}/auth/facebook/callback",
                "code": code,
            })
            tokens = r.json()
            access_token = tokens.get("access_token")
            if not access_token:
                raise ValueError(f"No access_token: {tokens}")
            # Obtener perfil
            profile = (await client.get(
                "https://graph.facebook.com/me",
                params={"fields": "id,name,email", "access_token": access_token},
            )).json()
        email  = (profile.get("email") or "").lower().strip()
        nombre = profile.get("name") or email
        if not email:
            return RedirectResponse("/inbox/login?error=facebook_no_email", status_code=302)
        user_data = await obtener_usuario_por_email(email)
        if not user_data:
            pw_hash = bcrypt.hashpw(secrets.token_urlsafe(24).encode(), bcrypt.gensalt()).decode()
            user_data = await crear_usuario(email=email, password_hash=pw_hash, nombre=nombre)
        if not user_data.get("is_active", True):
            return RedirectResponse("/inbox/login?error=cuenta_inactiva", status_code=302)
        token = await crear_sesion(user_data["id"])
        response = RedirectResponse("/inbox", status_code=302)
        response.set_cookie(VOCO_COOKIE, token, httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax")
        if ADMIN_TOKEN:
            response.set_cookie(INBOX_COOKIE, ADMIN_TOKEN, httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax")
        return response
    except Exception as e:
        logger.error(f"[OAuth Facebook] {e}")
        return RedirectResponse("/inbox/login?error=facebook_error", status_code=302)


# ── Gestión de agentes (Voco platform) ────────────────────────────────────

@app.get("/inbox/api/agents")
async def inbox_listar_agentes(
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Lista agentes: admin ve todos, usuario solo los suyos."""
    effective_token = voco_session or inbox_session or token
    current_user = await _obtener_sesion_usuario(effective_token)
    if not current_user:
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import obtener_todos_agentes, obtener_agentes_de_usuario
    if current_user.get("rol") == "admin":
        agentes = await obtener_todos_agentes()
    else:
        agentes = await obtener_agentes_de_usuario(current_user["id"])
    return JSONResponse(content={"agents": agentes})


@app.post("/inbox/api/agents")
async def inbox_crear_agente(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Crea un nuevo agente en la plataforma. Asigna owner_id al usuario actual."""
    effective_token = voco_session or inbox_session or token
    current_user = await _obtener_sesion_usuario(effective_token)
    if not current_user:
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import crear_agente
    body = await request.json()
    slug         = (body.get("slug") or "").strip().lower().replace(" ", "-")
    name         = (body.get("name") or "").strip()
    agent_name   = (body.get("agent_name") or "Agente").strip()
    business_type = (body.get("business_type") or "productos").strip()
    phone_number_id = (body.get("phone_number_id") or "").strip()
    waba_id      = (body.get("waba_id") or "").strip()
    color        = (body.get("color") or "#6366f1").strip()
    emoji        = (body.get("emoji") or "🤖").strip()

    if not slug or not name:
        return JSONResponse(status_code=400, content={"error": "slug y name son requeridos"})

    # Admin (id=0 legacy o rol=admin) → owner_id=None (admin-owned)
    # Usuario regular → owner_id = su id
    user_id = current_user.get("id", 0)
    owner_id = None if (current_user.get("rol") == "admin" or user_id == 0) else user_id

    try:
        agente = await crear_agente(
            slug=slug, name=name, agent_name=agent_name,
            business_type=business_type, phone_number_id=phone_number_id,
            waba_id=waba_id, color=color, emoji=emoji,
            owner_id=owner_id,
        )
        return JSONResponse(content={"ok": True, "agent": agente})
    except Exception as e:
        logger.error(f"[agents] Error creando agente: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.patch("/inbox/api/agents/{agent_id_param}")
async def inbox_actualizar_agente(
    agent_id_param: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Actualiza campos de un agente existente."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import actualizar_agente, obtener_agente
    body = await request.json()
    try:
        ok = await actualizar_agente(agent_id_param, **body)
        if not ok:
            return JSONResponse(status_code=404, content={"error": "Agente no encontrado"})
        # Invalidar cache de phone_number_id para que el webhook lo recargue
        if "phone_number_id" in body:
            for key in list(_phone_agent_cache.keys()):
                if _phone_agent_cache[key].get("id") == agent_id_param:
                    del _phone_agent_cache[key]
        agente_actualizado = await obtener_agente(agent_id_param)
        return JSONResponse(content={"ok": True, "agent": agente_actualizado})
    except Exception as e:
        logger.error(f"[agents] Error actualizando agente {agent_id_param}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/inbox/api/agents/{agent_id_param}/activate")
async def inbox_activar_agente(
    agent_id_param: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Activa un agente (status → active)."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import actualizar_agente
    await actualizar_agente(agent_id_param, status="active")
    return JSONResponse(content={"ok": True})


# ──────────────────────────────────────────────────────────────────────────────
# #43 — Promoción post-venta (código descuento tras pago)
# ──────────────────────────────────────────────────────────────────────────────
async def _verificar_acceso_agente(user: dict, agent_id: int) -> bool:
    """True si el usuario puede modificar este agente.

    Permitido: admin (todos) o owner del agente. Usuarios internos sin
    rol admin solo pueden tocar el agente que poseen.
    """
    if not user:
        return False
    if user.get("rol") == "admin" or user.get("id", 0) == 0:
        return True  # admins ven/editan todo
    from agent.memory import obtener_agente
    agente = await obtener_agente(agent_id)
    if not agente:
        return False
    # owner_id None = admin-owned (legacy); owner_id == user.id = suyo
    return agente.get("owner_id") in (None, user.get("id"))


@app.get("/inbox/api/agents/{agent_id_param}/descuento")
async def api_obtener_descuento(
    agent_id_param: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Devuelve la config de descuento post-venta del agente.

    Siempre retorna el shape completo (activo + 4 campos), aunque esté
    desactivado — el form del panel necesita rellenar los inputs.
    """
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    if not await _verificar_acceso_agente(user, agent_id_param):
        raise HTTPException(status_code=403, detail="Sin acceso a este agente")
    from agent.memory import obtener_descuento_promo_config, DESCUENTO_MENSAJE_DEFAULT
    config = await obtener_descuento_promo_config(agent_id_param)
    # Exponemos también el default para que la UI pueda mostrarlo como placeholder
    config["mensaje_default"] = DESCUENTO_MENSAJE_DEFAULT
    return JSONResponse(content=config)


# ──────────────────────────────────────────────────────────────────────────────
# #28 — Mensajes del sistema configurables por agente
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/inbox/api/agents/{agent_id_param}/mensajes")
async def api_listar_mensajes(
    agent_id_param: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Devuelve el catálogo COMPLETO de mensajes con el valor actual de cada
    uno y la metadata para que la UI lo pueda renderizar agrupado por
    categoría sin hacer queries adicionales.

    Response shape:
      {
        "categorias": {<slug>: {<label>, <descripcion>, <orden>}, ...},
        "mensajes":   [{<key>, <categoria>, <titulo>, <descripcion>, <cuando>,
                        <default>, <placeholders>, <content>, <personalizado>,
                        <updated_at>}, ...]
      }
    """
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    if not await _verificar_acceso_agente(user, agent_id_param):
        raise HTTPException(status_code=403, detail="Sin acceso a este agente")
    from agent.memory import listar_mensajes_agente
    from agent.mensajes import CATEGORIAS
    mensajes = await listar_mensajes_agente(agent_id_param)
    return JSONResponse(content={
        "categorias": CATEGORIAS,
        "mensajes":   mensajes,
    })


@app.put("/inbox/api/agents/{agent_id_param}/mensajes/{key}")
async def api_guardar_mensaje(
    agent_id_param: int,
    key: str,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Guarda el override del mensaje. Body: {"content": "..."}.

    Validaciones en memory.guardar_mensaje_agente: key del catálogo,
    no vacío, <=4000 chars, placeholders requeridos presentes.
    """
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    if not await _verificar_acceso_agente(user, agent_id_param):
        raise HTTPException(status_code=403, detail="Sin acceso a este agente")
    from agent.memory import guardar_mensaje_agente
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "JSON inválido"})
    content = str(body.get("content") or "")
    ok, error = await guardar_mensaje_agente(agent_id_param, key, content)
    if not ok:
        return JSONResponse(status_code=400, content={"ok": False, "error": error})
    logger.info(
        f"[mensajes] agent_id={agent_id_param} actualizó {key!r} "
        f"({len(content)} chars) — user={user.get('id')}"
    )
    return JSONResponse(content={"ok": True})


@app.patch("/inbox/api/agents/{agent_id_param}/mensajes/{key}/activo")
async def api_set_mensaje_activo(
    agent_id_param: int,
    key: str,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Activa o desactiva un mensaje sin modificar su contenido.

    Body: {"activo": bool}
    Si el mensaje del catálogo está marcado como esencial (puede_desactivarse=False),
    se rechaza con 400.
    """
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    if not await _verificar_acceso_agente(user, agent_id_param):
        raise HTTPException(status_code=403, detail="Sin acceso a este agente")
    from agent.memory import set_mensaje_activo
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "JSON inválido"})
    activo = bool(body.get("activo"))
    ok, error = await set_mensaje_activo(agent_id_param, key, activo)
    if not ok:
        return JSONResponse(status_code=400, content={"ok": False, "error": error})
    logger.info(
        f"[mensajes] agent_id={agent_id_param} {key!r} → activo={activo} "
        f"— user={user.get('id')}"
    )
    return JSONResponse(content={"ok": True, "activo": activo})


@app.delete("/inbox/api/agents/{agent_id_param}/mensajes/{key}")
async def api_restaurar_mensaje(
    agent_id_param: int,
    key: str,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Restaura el mensaje al default — borra el override del agente.

    Idempotente: si no había override, devuelve ok=true sin cambios.
    """
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    if not await _verificar_acceso_agente(user, agent_id_param):
        raise HTTPException(status_code=403, detail="Sin acceso a este agente")
    from agent.memory import restaurar_mensaje_agente
    existia = await restaurar_mensaje_agente(agent_id_param, key)
    logger.info(
        f"[mensajes] agent_id={agent_id_param} restauró {key!r} "
        f"(habia_override={existia}) — user={user.get('id')}"
    )
    return JSONResponse(content={"ok": True, "habia_override": existia})


@app.put("/inbox/api/agents/{agent_id_param}/descuento")
async def api_guardar_descuento(
    agent_id_param: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Guarda la config de descuento post-venta del agente.

    Body esperado:
      {
        "activo":  bool,
        "umbral":  int,    # COP, sin envío
        "codigo":  str,    # se normaliza a MAYÚSCULAS
        "pct":     int,    # 1-100
        "mensaje": str     # template con {codigo} {pct} {umbral} — opcional
      }

    Validaciones en memory.guardar_descuento_promo(): umbral >= 1000,
    código [A-Z0-9_-]{2,30}, pct 1-100, mensaje debe contener {codigo}.
    Si activo=false, los demás campos se persisten igual para permitir
    reactivar más tarde sin perder la configuración.
    """
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    if not await _verificar_acceso_agente(user, agent_id_param):
        raise HTTPException(status_code=403, detail="Sin acceso a este agente")
    from agent.memory import guardar_descuento_promo
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "JSON inválido"})

    activo  = bool(body.get("activo"))
    try:
        umbral = int(body.get("umbral") or 0)
        pct    = int(body.get("pct") or 0)
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"ok": False, "error": "umbral y pct deben ser números enteros"})
    codigo  = str(body.get("codigo") or "").strip()
    mensaje = str(body.get("mensaje") or "").strip()

    ok, error = await guardar_descuento_promo(
        agent_id_param, activo, umbral, codigo, pct, mensaje,
    )
    if not ok:
        return JSONResponse(status_code=400, content={"ok": False, "error": error})
    logger.info(
        f"[descuento] agent_id={agent_id_param} actualizado por user={user.get('id')} "
        f"(activo={activo}, codigo={codigo}, umbral={umbral}, pct={pct})"
    )

    # ── #54 fase 3 — Auto-crear cupón en Shopify si hay Admin API ─────────────
    # Si el agente activó la promo Y tiene SHOPIFY_ADMIN_TOKEN configurado,
    # intentamos crear el discount code automáticamente en Shopify. Esto evita
    # que el merchant tenga que duplicar el código en 2 lugares (Voco + Shopify).
    # Es best-effort: si Shopify falla (ya existe, scope faltante, etc.) la
    # respuesta al panel sigue ok=True pero incluye `shopify_setup` con detalle.
    respuesta_extra: dict = {}
    if activo and codigo:
        from agent.memory import get_config_value
        store_raw = (await get_config_value("SHOPIFY_STORE", agent_id_param)
                     or os.getenv("SHOPIFY_STORE", "")).strip()
        admin_tok = (await get_config_value("SHOPIFY_ADMIN_TOKEN", agent_id_param)
                     or os.getenv("SHOPIFY_ADMIN_TOKEN", "")).strip()
        if store_raw and admin_tok:
            from agent.shopify_admin import buscar_discount_code, crear_discount_code
            store = store_raw.replace("https://", "").replace("http://", "").rstrip("/")
            try:
                existente = await buscar_discount_code(store, admin_tok, codigo)
                if existente:
                    respuesta_extra["shopify_setup"] = {
                        "ok": True,
                        "estado": "ya_existe",
                        "mensaje": f"El código '{codigo}' ya existe en Shopify — Voco lo anunciará tal como esté configurado allá.",
                    }
                    logger.info(f"[descuento] '{codigo}' ya existe en Shopify para agent {agent_id_param} — no recreo")
                else:
                    res = await crear_discount_code(store, admin_tok, codigo, pct, umbral)
                    if res.get("ok"):
                        respuesta_extra["shopify_setup"] = {
                            "ok": True,
                            "estado": "creado",
                            "mensaje": f"Cupón '{codigo}' creado automáticamente en Shopify ({pct}% desde ${umbral:,}).",
                            "price_rule_id":    res.get("price_rule_id"),
                            "discount_code_id": res.get("discount_code_id"),
                        }
                        logger.info(f"[descuento] cupón '{codigo}' creado en Shopify para agent {agent_id_param}")
                    else:
                        respuesta_extra["shopify_setup"] = {
                            "ok": False,
                            "estado": "error",
                            "mensaje": f"No pude crear el cupón en Shopify: {res.get('error', 'error desconocido')}. Créalo manualmente en Shopify Admin → Discounts.",
                        }
                        logger.warning(f"[descuento] crear cupón '{codigo}' falló: {res.get('error')}")
            except Exception as e:
                logger.error(f"[descuento] error con Shopify Admin: {e}")
                respuesta_extra["shopify_setup"] = {
                    "ok": False,
                    "estado": "error",
                    "mensaje": f"Error contactando Shopify: {e!s}. Créalo manualmente.",
                }
        # Si no hay Admin token configurado, simplemente no intentamos —
        # la respuesta normal (ok=True) sigue. El cliente puede crear el
        # cupón a mano en Shopify Admin como hasta ahora.

    return JSONResponse(content={"ok": True, **respuesta_extra})


# ──────────────────────────────────────────────────────────────────────────────
# Sprint A — Módulos por agente (modules_json)
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/inbox/api/agents/{agent_id_param}/modules")
async def inbox_obtener_modulos_agente(
    agent_id_param: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Devuelve el dict de módulos activos para un agente. Defaults seguros."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import get_agent_modules
    modules = await get_agent_modules(agent_id_param)
    return JSONResponse(content={"ok": True, "modules": modules})


@app.post("/inbox/api/agents/{agent_id_param}/modules")
async def inbox_guardar_modulos_agente(
    agent_id_param: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Guarda los módulos del agente. Espera body JSON con claves válidas.

    Solo procesa claves en DEFAULT_MODULES; el resto se ignora silenciosamente.
    """
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import set_agent_modules
    try:
        body = await request.json()
    except Exception:
        body = {}
    modules_in = body.get("modules", body) if isinstance(body, dict) else {}
    saved = await set_agent_modules(agent_id_param, modules_in)
    return JSONResponse(content={"ok": True, "modules": saved})


@app.post("/inbox/api/agents/{agent_id_param}/pause")
async def inbox_pausar_agente(
    agent_id_param: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Pausa un agente (status → paused). No afecta al agente Equora (id=1)."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    if agent_id_param == 1:
        return JSONResponse(status_code=400, content={"error": "El agente Equora no puede pausarse desde la API"})
    from agent.memory import actualizar_agente
    await actualizar_agente(agent_id_param, status="paused")
    return JSONResponse(content={"ok": True})


@app.post("/inbox/api/agents/{agent_id_param}/clone")
async def inbox_clonar_agente(
    agent_id_param: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Clona un agente existente con un nuevo slug."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import obtener_agente, crear_agente, get_config_value, set_config_value
    body = await request.json()
    nuevo_slug = (body.get("slug") or "").strip().lower().replace(" ", "-")
    nuevo_name = (body.get("name") or "").strip()
    if not nuevo_slug:
        return JSONResponse(status_code=400, content={"error": "slug requerido"})

    original = await obtener_agente(agent_id_param)
    if not original:
        return JSONResponse(status_code=404, content={"error": "Agente no encontrado"})

    try:
        nuevo = await crear_agente(
            slug=nuevo_slug,
            name=nuevo_name or f"{original.get('name', '')} (copia)",
            agent_name=original.get("agent_name", "Agente"),
            business_type=original.get("business_type", "productos"),
            phone_number_id="",  # El nuevo agente empieza sin número asignado
            waba_id="",
            color=original.get("color", "#6366f1"),
            emoji=original.get("emoji", "🤖"),
        )
        # Clonar config_values del agente original (prompt, vars, etc.)
        nuevo_id = nuevo.get("id")
        for clave in ("SYSTEM_PROMPT", "BUSINESS_VARS", "BUSINESS_TYPE", "ACTIVE_MODULES"):
            valor = await get_config_value(clave, agent_id_param)
            if valor:
                await set_config_value(clave, valor, nuevo_id)
        return JSONResponse(content={"ok": True, "agent": nuevo})
    except Exception as e:
        logger.error(f"[agents] Error clonando agente {agent_id_param}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/inbox/api/agents/{agent_id_param}/sandbox")
async def inbox_sandbox_info(
    agent_id_param: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Retorna la configuración del sandbox hub de Voco para este agente."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import obtener_agente

    # El sandbox usa el WABA propio de Voco — credenciales a nivel de plataforma
    voco_sb_phone_id = os.getenv("VOCO_SANDBOX_PHONE_NUMBER_ID", "")
    voco_sb_phone    = os.getenv("VOCO_SANDBOX_PHONE_NUMBER", "")

    if not voco_sb_phone_id or not voco_sb_phone:
        return JSONResponse(content={"configured": False, "phone_number": "", "phone_number_id": ""})

    # Código de proyecto específico para este agente (VOCO-EQ001)
    _src_agent = await obtener_agente(agent_id_param)
    _src_slug  = _src_agent.get("slug", "agente") if _src_agent else "agente"
    _sandbox_code = _sandbox_code_para_agente(_src_slug, agent_id_param)

    return JSONResponse(content={
        "configured": True,
        "phone_number": voco_sb_phone,
        "phone_number_id": voco_sb_phone_id,
        "active": True,
        "code": _sandbox_code,
    })


@app.get("/inbox/api/qr")
async def generar_qr(data: str = ""):
    """Genera un QR code como SVG a partir del parámetro ?data= ."""
    if not data:
        return Response(content="<svg/>", media_type="image/svg+xml")
    try:
        import qrcode
        import qrcode.image.svg as _svg
        from io import BytesIO
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(image_factory=_svg.SvgPathImage)
        buf = BytesIO()
        img.save(buf)
        buf.seek(0)
        return Response(content=buf.read(), media_type="image/svg+xml")
    except Exception as e:
        logger.error(f"[qr] Error generando QR: {e}")
        return Response(content="<svg/>", media_type="image/svg+xml")


@app.post("/inbox/api/agents/{agent_id_param}/sandbox/activar")
async def inbox_sandbox_activar(
    agent_id_param: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Crea el agente sandbox copiando credenciales del agente origen."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import (
        obtener_agente, crear_agente, obtener_agente_por_phone_id,
        get_config_value, set_config_value,
    )

    body = await request.json()
    sandbox_phone_id = (body.get("phone_number_id") or os.getenv("META_SANDBOX_PHONE_NUMBER_ID", "")).strip()
    sandbox_phone_number = (body.get("phone_number") or os.getenv("META_SANDBOX_PHONE_NUMBER", "")).strip()

    if not sandbox_phone_id:
        return JSONResponse(status_code=400, content={"error": "phone_number_id requerido"})

    # Si ya existe un agente con ese phone_number_id no crear duplicado
    existing = await obtener_agente_por_phone_id(sandbox_phone_id)
    if existing:
        return JSONResponse(content={"ok": True, "sandbox": existing, "created": False})

    original = await obtener_agente(agent_id_param)
    if not original:
        return JSONResponse(status_code=404, content={"error": "Agente origen no encontrado"})

    access_token   = await get_config_value("META_ACCESS_TOKEN",  agent_id_param) or os.getenv("META_ACCESS_TOKEN", "")
    verify_token   = await get_config_value("META_VERIFY_TOKEN",  agent_id_param) or os.getenv("META_VERIFY_TOKEN", "")
    system_prompt  = await get_config_value("SYSTEM_PROMPT",      agent_id_param) or ""
    active_modules = await get_config_value("ACTIVE_MODULES",     agent_id_param) or ""
    business_vars  = await get_config_value("BUSINESS_VARS",      agent_id_param) or ""

    try:
        sandbox = await crear_agente(
            name=f"{original.get('name', 'Agente')} (Sandbox)",
            slug=f"{original.get('slug', 'agente')}-sandbox",
            agent_name=original.get("agent_name", "Agente"),
            business_type=original.get("business_type", "productos"),
            phone_number_id=sandbox_phone_id,
            waba_id="",
            color=original.get("color", "#6366f1"),
            emoji="🧪",
        )
        sid = sandbox["id"]
        await set_config_value("META_ACCESS_TOKEN",  access_token,   sid)
        await set_config_value("META_PHONE_NUMBER_ID", sandbox_phone_id, sid)
        await set_config_value("META_VERIFY_TOKEN",  verify_token,   sid)
        if system_prompt:
            await set_config_value("SYSTEM_PROMPT",  system_prompt,  sid)
        if active_modules:
            await set_config_value("ACTIVE_MODULES", active_modules, sid)
        if business_vars:
            await set_config_value("BUSINESS_VARS",  business_vars,  sid)

        # Guardar referencia en el agente origen para que la UI la encuentre
        await set_config_value("SANDBOX_PHONE_NUMBER_ID", sandbox_phone_id,   agent_id_param)
        await set_config_value("SANDBOX_PHONE_NUMBER",    sandbox_phone_number, agent_id_param)

        # Limpiar caché de routing para que el webhook reconozca el nuevo número
        _phone_agent_cache.pop(sandbox_phone_id, None)

        logger.info(f"[sandbox] Agente sandbox creado (id={sid}) para agent_id={agent_id_param}")
        return JSONResponse(content={"ok": True, "sandbox": sandbox, "created": True})
    except Exception as e:
        logger.error(f"[sandbox] Error activando sandbox para agente {agent_id_param}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/inbox/api/agents/{agent_id_param}/sandbox/invite")
async def inbox_sandbox_invite(
    agent_id_param: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Envía hello_world template al número indicado para iniciar conversación de prueba."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import get_config_value
    import httpx as _httpx

    body = await request.json()
    to_phone = re.sub(r"[^\d]", "", body.get("to", ""))
    if not to_phone:
        return JSONResponse(status_code=400, content={"error": "Número de teléfono requerido"})

    sandbox_phone_id = (
        os.getenv("META_SANDBOX_PHONE_NUMBER_ID")
        or await get_config_value("SANDBOX_PHONE_NUMBER_ID", agent_id_param)
        or ""
    )
    access_token = (
        await get_config_value("META_ACCESS_TOKEN", agent_id_param)
        or os.getenv("META_ACCESS_TOKEN", "")
    )
    if not sandbox_phone_id or not access_token:
        return JSONResponse(status_code=400, content={"error": "Sandbox no configurado (falta phone_number_id o access_token)"})

    url = f"https://graph.facebook.com/v21.0/{sandbox_phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {"name": "hello_world", "language": {"code": "en_US"}},
    }
    try:
        async with _httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload, headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            })
        if r.status_code == 200:
            logger.info(f"[sandbox] Invitación enviada a {to_phone} desde sandbox {sandbox_phone_id}")
            return JSONResponse(content={"ok": True})
        else:
            err = r.json().get("error", {}).get("message", r.text)
            logger.warning(f"[sandbox] Error Meta API al invitar {to_phone}: {err}")
            return JSONResponse(status_code=400, content={"error": err})
    except Exception as e:
        logger.error(f"[sandbox] Excepción al enviar invitación: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/inbox/api/agents/{agent_id_param}/stats")
async def inbox_stats_agente(
    agent_id_param: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Estadísticas básicas de un agente: conversaciones, mensajes."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import obtener_metricas_internas
    try:
        data = await obtener_metricas_internas(dias=30, agent_id=agent_id_param)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"[agents] Error obteniendo stats del agente {agent_id_param}: {e}")
        return JSONResponse(content={"error": str(e)})


# ── Panel principal ────────────────────────────────────────────────────────

@app.get("/inbox", response_class=HTMLResponse)
async def inbox_panel(
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    # Resolver token efectivo: voco_session > inbox_session > query param
    effective_token = voco_session or inbox_session or token

    # Intentar autenticación con nuevo sistema de sesiones primero
    current_user = await _obtener_sesion_usuario(effective_token)

    if not current_user:
        return RedirectResponse("/inbox/login", status_code=302)

    from agent.memory import obtener_todos_agentes, obtener_agentes_de_usuario
    if current_user.get("rol") == "admin":
        agentes = await obtener_todos_agentes()
    else:
        agentes = await obtener_agentes_de_usuario(current_user["id"])

    response = HTMLResponse(content=obtener_global_html(agentes, user=current_user))

    # Si llegó por query param con ADMIN_TOKEN legacy, persistir en cookie legacy
    if token and _verificar_admin(token):
        response.set_cookie(
            INBOX_COOKIE, ADMIN_TOKEN,
            httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax"
        )
    return response


# ── Admin: gestión de usuarios (Sprint 1) ───────────────────────────────────

@app.get("/inbox/api/admin/users")
async def admin_listar_usuarios(
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Lista todos los usuarios registrados. Solo accesible por administradores."""
    effective_token = voco_session or inbox_session or token
    current_user = await _obtener_sesion_usuario(effective_token)
    if not current_user or current_user.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Acceso restringido a administradores")
    usuarios = await listar_usuarios()
    return JSONResponse(content={"users": usuarios})


@app.post("/inbox/api/admin/users/{user_id_param}")
async def admin_actualizar_usuario(
    user_id_param: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Actualiza datos de un usuario (plan, is_active, rol). Solo para administradores."""
    effective_token = voco_session or inbox_session or token
    current_user = await _obtener_sesion_usuario(effective_token)
    if not current_user or current_user.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Acceso restringido a administradores")
    body = await request.json()
    # Solo campos seguros
    campos_seguros = {k: v for k, v in body.items() if k in ("plan", "is_active", "rol", "nombre")}
    ok = await actualizar_usuario(user_id_param, **campos_seguros)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
    return JSONResponse(content={"ok": True})


# ── API endpoints ──────────────────────────────────────────────────────────

@app.get("/inbox/api/conversaciones")
async def inbox_conversaciones(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    convs = await obtener_todas_conversaciones(agent_id=agent_id)
    return JSONResponse(content=convs)


@app.get("/inbox/api/mensajes/{telefono}")
async def inbox_mensajes(
    telefono: str,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    mensajes = await obtener_historial_con_timestamps(telefono, 150, agent_id=agent_id)
    modo = await get_modo_humano(telefono, agent_id=agent_id)
    return JSONResponse(content={"mensajes": mensajes, "modo_humano": modo})


@app.post("/inbox/api/responder")
async def inbox_responder(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    telefono  = (body.get("telefono") or "").strip()
    mensaje   = (body.get("mensaje") or "").strip()
    agent_id  = int(body.get("agent_id") or 1)
    if not telefono or not mensaje:
        return JSONResponse(status_code=400, content={"error": "Faltan datos"})
    try:
        # Usar el proveedor del agente correcto
        from agent.memory import obtener_agente
        _agente = await obtener_agente(agent_id) or {"id": 1}
        _prov = await _get_meta_para_agente(_agente)
        # DIAGNÓSTICO: loguear qué credenciales se están usando (sin exponer
        # token completo). Útil para detectar config_value en BD que difiere
        # de env vars de Railway tras cambios recientes.
        _pn = (_prov.phone_number_id or "")
        _tk = (_prov.access_token or "")
        logger.info(
            f"[responder] agent_id={agent_id} → phone_number_id={_pn} "
            f"(len={len(_pn)}) · access_token={_tk[:12]}…{_tk[-4:] if len(_tk)>4 else ''} "
            f"(len={len(_tk)})"
        )
        ok = await _prov.enviar_mensaje(telefono, mensaje)
        if not ok:
            logger.error(f"[responder] enviar_mensaje devolvió False para {telefono} (agent_id={agent_id})")
            return JSONResponse(status_code=502, content={
                "ok": False,
                "error": f"WhatsApp rechazó el envío.\n\n"
                         f"Phone Number ID usado: {_pn}\n"
                         f"Token (primeros chars): {_tk[:8]}…\n\n"
                         f"Causas típicas: token expirado, Phone Number ID incorrecto, "
                         f"ventana de 24h cerrada, o scope insuficiente. Logs de Railway "
                         f"tienen la respuesta exacta de Meta."
            })
        await _guardar_con_wamid(_prov, telefono, mensaje, agent_id=agent_id)
        await registrar_mensaje_asistente(telefono)
        logger.info(f"Mensaje manual enviado a {telefono} desde inbox (agent_id={agent_id})")
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Error enviando desde inbox a {telefono}: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 4 — Mensajes multimedia desde el inbox
# ══════════════════════════════════════════════════════════════════════════════

# Límites Meta WhatsApp Cloud API
_MEDIA_LIMITS = {
    "image":    5  * 1024 * 1024,   # 5 MB
    "video":    16 * 1024 * 1024,   # 16 MB
    "audio":    16 * 1024 * 1024,   # 16 MB
    "document": 100 * 1024 * 1024,  # 100 MB
}

_MEDIA_MIME_TIPO = {
    "image/jpeg":  "image",   "image/png":  "image",   "image/webp": "image",
    "video/mp4":   "video",   "video/3gpp": "video",
    "audio/mpeg":  "audio",   "audio/ogg":  "audio",   "audio/mp4":  "audio",   "audio/amr": "audio",
    "application/pdf": "document",
}


def _detectar_tipo_media(mime_type: str) -> str:
    """Detecta el tipo de media según el MIME type. Default = document."""
    mime = (mime_type or "").lower().split(";")[0].strip()
    if mime in _MEDIA_MIME_TIPO:
        return _MEDIA_MIME_TIPO[mime]
    if mime.startswith("image/"):    return "image"
    if mime.startswith("video/"):    return "video"
    if mime.startswith("audio/"):    return "audio"
    return "document"


@app.post("/inbox/api/responder/media")
async def inbox_responder_media(
    file: UploadFile = File(...),
    telefono: str = Form(...),
    caption: str = Form(""),
    agent_id: int = Form(1),
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Envía un archivo multimedia (imagen/video/documento/audio) por WhatsApp.
    El frontend sube el archivo aquí, lo subimos a Meta y enviamos el mensaje."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    telefono = telefono.strip()
    if not telefono:
        return JSONResponse(content={"ok": False, "error": "Teléfono requerido"}, status_code=400)

    contenido = await file.read()
    if not contenido:
        return JSONResponse(content={"ok": False, "error": "Archivo vacío"}, status_code=400)

    mime_type = file.content_type or "application/octet-stream"
    tipo      = _detectar_tipo_media(mime_type)

    limite = _MEDIA_LIMITS.get(tipo, 5 * 1024 * 1024)
    if len(contenido) > limite:
        mb = round(limite / 1024 / 1024)
        return JSONResponse(content={
            "ok": False,
            "error": f"Archivo demasiado grande. Máximo {mb} MB para {tipo}"
        }, status_code=400)

    try:
        from agent.memory import obtener_agente
        _agente = await obtener_agente(agent_id) or {"id": 1}
        _prov = await _get_meta_para_agente(_agente)

        # 1. Subir el archivo a Meta
        media_id = await _prov.subir_media(contenido, file.filename or "archivo", mime_type)
        if not media_id:
            return JSONResponse(content={
                "ok": False, "error": "No se pudo subir el archivo a Meta"
            }, status_code=500)

        # 2. Enviar el mensaje según el tipo
        cap = caption.strip()
        ok = False
        if tipo == "image":
            ok = await _prov.enviar_imagen(telefono, media_id=media_id, caption=cap)
        elif tipo == "video":
            ok = await _prov.enviar_video(telefono, media_id=media_id, caption=cap)
        elif tipo == "audio":
            ok = await _prov.enviar_audio(telefono, media_id=media_id)
        else:  # document
            ok = await _prov.enviar_documento(
                telefono, media_id=media_id, caption=cap, filename=file.filename or ""
            )

        if not ok:
            return JSONResponse(content={
                "ok": False, "error": "Meta rechazó el envío del mensaje"
            }, status_code=500)

        # 3. Guardar marcador en historial — wamid ya disponible (#79, se envió arriba)
        marcador = json.dumps({
            "tipo":      tipo,
            "media_id":  media_id,
            "mime_type": mime_type,
            "filename":  file.filename or "",
            "caption":   cap,
        }, ensure_ascii=False)
        await _guardar_con_wamid(_prov, telefono, f"__MEDIA__:{marcador}", agent_id=agent_id)
        await registrar_mensaje_asistente(telefono)
        logger.info(f"Media {tipo} enviada a {telefono} desde inbox")
        return JSONResponse(content={
            "ok": True, "tipo": tipo, "media_id": media_id, "filename": file.filename or ""
        })
    except Exception as e:
        logger.error(f"Error enviando media a {telefono}: {e}", exc_info=True)
        return JSONResponse(content={"ok": False, "error": str(e)[:300]}, status_code=500)


@app.get("/inbox/api/media/{media_id}")
async def inbox_obtener_media(
    media_id: str,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Proxy que descarga el media de Meta y lo sirve al frontend.
    Necesario porque las URLs scontent.whatsapp.net requieren auth header."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from fastapi.responses import Response
    try:
        from agent.memory import obtener_agente
        _agente = await obtener_agente(agent_id) or {"id": 1}
        _prov = await _get_meta_para_agente(_agente)
        result = await _prov.descargar_media(media_id)
        if not result:
            raise HTTPException(status_code=404, detail="Media no encontrada o expirada")
        contenido, mime = result
        return Response(content=contenido, media_type=mime,
                        headers={"Cache-Control": "private, max-age=3600"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo media {media_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@app.post("/inbox/api/responder/ubicacion")
async def inbox_responder_ubicacion(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Envía una ubicación geográfica al cliente."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    telefono  = (body.get("telefono") or "").strip()
    latitud   = body.get("latitud")
    longitud  = body.get("longitud")
    nombre    = (body.get("nombre")    or "").strip()
    direccion = (body.get("direccion") or "").strip()
    agent_id  = int(body.get("agent_id") or 1)
    if not telefono or latitud is None or longitud is None:
        return JSONResponse(content={"ok": False, "error": "Faltan datos"}, status_code=400)
    try:
        from agent.memory import obtener_agente
        _agente = await obtener_agente(agent_id) or {"id": 1}
        _prov = await _get_meta_para_agente(_agente)
        ok = await _prov.enviar_ubicacion(telefono, float(latitud), float(longitud), nombre, direccion)
        if not ok:
            return JSONResponse(content={"ok": False, "error": "Meta rechazó la ubicación"}, status_code=500)
        marcador = json.dumps({
            "tipo":      "location",
            "latitud":   latitud,
            "longitud":  longitud,
            "nombre":    nombre,
            "direccion": direccion,
        }, ensure_ascii=False)
        await _guardar_con_wamid(_prov, telefono, f"__MEDIA__:{marcador}", agent_id=agent_id)
        await registrar_mensaje_asistente(telefono)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Error enviando ubicación: {e}")
        return JSONResponse(content={"ok": False, "error": str(e)[:300]}, status_code=500)


@app.post("/inbox/api/responder/producto")
async def inbox_responder_producto(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Envía un producto del catálogo de Shopify al cliente."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    telefono     = (body.get("telefono") or "").strip()
    retailer_id  = (body.get("retailer_id") or "").strip()
    cuerpo       = (body.get("cuerpo") or "").strip()
    agent_id     = int(body.get("agent_id") or 1)
    if not telefono or not retailer_id:
        return JSONResponse(content={"ok": False, "error": "Faltan datos"}, status_code=400)
    try:
        from agent.memory import obtener_agente
        _agente = await obtener_agente(agent_id) or {"id": 1}
        _prov = await _get_meta_para_agente(_agente)
        resultado = await _prov.enviar_producto(telefono, retailer_id, cuerpo)
        if not resultado.get("ok"):
            err_msg = resultado.get("error", "Meta rechazó el producto")
            err_code = resultado.get("code", 0)
            # Mensajes más amigables según el código de Meta
            if "Object with ID" in err_msg or err_code == 100:
                err_msg = f"El SKU '{retailer_id}' no existe en tu catálogo de Meta (CATALOG_ID: {resultado.get('catalog_id','')}). Verifica que el producto esté sincronizado desde Shopify a Facebook Catalog."
            elif "catalog" in err_msg.lower():
                err_msg = f"Problema con el catálogo de Meta: {err_msg}"
            return JSONResponse(content={
                "ok": False, "error": err_msg, "detail": resultado
            }, status_code=500)
        marcador = json.dumps({
            "tipo":        "product",
            "retailer_id": retailer_id,
            "cuerpo":      cuerpo,
        }, ensure_ascii=False)
        await _guardar_con_wamid(_prov, telefono, f"__MEDIA__:{marcador}", agent_id=agent_id)
        await registrar_mensaje_asistente(telefono)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Error enviando producto: {e}")
        return JSONResponse(content={"ok": False, "error": str(e)[:300]}, status_code=500)


@app.get("/inbox/api/catalogo/buscar")
async def inbox_buscar_catalogo(
    q: str = "",
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Busca productos en el catálogo de Shopify por nombre (para enviar desde el inbox)."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    try:
        # Asegurar que el catálogo esté cargado en cache
        await obtener_catalogo_shopify()
        catalogo = obtener_catalogo_json() or []
        # _sku_map mapea: retailer_id → {producto, presentacion, precio_unitario, variant_id}
        # Construimos el reverso: (producto_norm, presentacion_norm) → retailer_id
        # PRIORIZAR el variant_id largo (numeric_id de Shopify) sobre SKUs cortos,
        # porque Facebook Catalog usa el variant_id como retailer_id real al sincronizar.
        from agent.tools import _sku_map, _normalizar
        rev_sku = {}
        for rid, info in _sku_map.items():
            clave = (_normalizar(info.get("producto", "")), _normalizar(info.get("presentacion", "")))
            existente = rev_sku.get(clave, "")
            # Un rid es "variant_id" si es numérico y largo (>=10 dígitos)
            es_variant_id        = rid.isdigit() and len(rid) >= 10
            existente_es_variant = existente.isdigit() and len(existente) >= 10
            # Reemplazar si: no había, o el actual es variant_id y el existente no
            if not existente or (es_variant_id and not existente_es_variant):
                rev_sku[clave] = rid

        # Construir mapa de SKU "humano" para mostrar en la UI (cuando exista)
        sku_humano = {}
        for rid, info in _sku_map.items():
            clave = (_normalizar(info.get("producto", "")), _normalizar(info.get("presentacion", "")))
            # SKU humano = el corto, no-numérico o numérico corto (<10 dígitos)
            if not (rid.isdigit() and len(rid) >= 10):
                if clave not in sku_humano:
                    sku_humano[clave] = rid

        q_norm = q.strip().lower()
        resultados = []
        for item in catalogo:
            titulo       = (item.get("producto") or "").strip()
            presentacion = (item.get("presentacion") or "").strip()
            if q_norm and q_norm not in (titulo + " " + presentacion).lower():
                continue
            clave = (_normalizar(titulo), _normalizar(presentacion))
            retailer_id = rev_sku.get(clave, "")
            sku_legible = sku_humano.get(clave, "")
            resultados.append({
                "retailer_id": retailer_id,
                "sku_legible": sku_legible or retailer_id,  # para mostrar al usuario
                "title":       titulo,
                "variant":     presentacion,
                "price":       item.get("precio", 0),
                "image":       item.get("imagen", ""),
                "categoria":   item.get("categoria", ""),
            })
            if len(resultados) >= 50:
                break
        return JSONResponse(content={"productos": resultados})
    except Exception as e:
        logger.error(f"Error buscando catálogo: {e}", exc_info=True)
        return JSONResponse(content={"productos": [], "error": str(e)[:200]})


# ── Carrito omnichannel — un agente humano arma/edita el carrito de un ──────
# cliente desde el panel (clientes con dificultad para usar el catálogo
# nativo de WhatsApp). Reusa el mismo carrito_activo que ya usa Andrea, así
# que lo que arma el humano se ve y se puede confirmar igual que un carrito
# armado por el bot.

@app.get("/inbox/api/carrito/{telefono}")
async def inbox_obtener_carrito(
    telefono: str,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    items = await obtener_carrito_activo(telefono, agent_id=agent_id)
    total = sum(int(it.get("subtotal", 0)) for it in items)
    return JSONResponse(content={"items": items, "total": total})


@app.post("/inbox/api/carrito/{telefono}")
async def inbox_guardar_carrito(
    telefono: str,
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Reemplaza el carrito activo del cliente con la lista de items recibida
    desde el panel. No se setea retailer_id aunque el producto venga del
    catálogo nativo — este carrito lo arma un humano, no es un checkout
    nativo de WhatsApp, y el prompt de Andrea usa retailer_id para decidir
    si está "en medio de un checkout nativo" (ver brain.py)."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    items_raw = body.get("items") or []
    if not isinstance(items_raw, list):
        return JSONResponse(status_code=400, content={"error": "items debe ser una lista"})

    items = []
    for it in items_raw:
        try:
            cantidad = int(it.get("cantidad", 1))
            precio_unitario = int(it.get("precio_unitario", 0))
        except (TypeError, ValueError):
            return JSONResponse(status_code=400, content={"error": "cantidad o precio_unitario inválido"})
        if cantidad <= 0 or not (it.get("producto") or "").strip():
            continue
        items.append({
            "retailer_id":     "",
            "quantity":        cantidad,
            "cantidad":        cantidad,
            "producto":        (it.get("producto") or "").strip(),
            "presentacion":    (it.get("presentacion") or "").strip(),
            "precio_unitario": precio_unitario,
            "subtotal":        precio_unitario * cantidad,
        })

    if items:
        await guardar_carrito_activo(telefono, items, agent_id=agent_id)
    else:
        await limpiar_carrito_activo(telefono, agent_id=agent_id)

    logger.info(f"[carrito-manual] Carrito de {telefono} actualizado desde inbox (agent_id={agent_id}, {len(items)} items)")

    # Avisar al cliente — mismo resumen + botón "Confirmar pedido ✅" que
    # recibiría si hubiera armado el carrito él mismo (ver _enviar_resumen_carrito,
    # llamada también desde act_ver_carrito y [[MOSTRAR_CARRITO]]). Si Meta
    # rechaza el envío (ej. ventana de 24h cerrada), el mensaje queda marcado
    # como "failed" en el chat con el motivo real — no rompemos el guardado
    # del carrito por un fallo de notificación.
    notificado = False
    try:
        notificado = await _enviar_resumen_carrito(telefono, agent_id=agent_id)
    except Exception as e:
        logger.error(f"[carrito-manual] Error notificando a {telefono}: {e}")

    total = sum(it["subtotal"] for it in items)
    return JSONResponse(content={"ok": True, "items": items, "total": total, "cliente_notificado": notificado})


@app.post("/inbox/api/modo/{telefono}")
async def inbox_modo(
    telefono: str,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    activo = bool(body.get("activo", False))
    await set_modo_humano(telefono, activo)
    logger.info(f"Modo cambiado a '{'humano' if activo else 'Andrea'}' para {telefono}")
    return JSONResponse(content={"ok": True, "modo_humano": activo})


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 1 — API de Tickets de Escalación
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/inbox/api/tickets")
async def api_listar_tickets(
    estado: str = "",
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Lista tickets filtrados por estado (sin_asignar|activo|pendiente|resuelto|todos)."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    tickets = await obtener_tickets(agent_id, estado=estado or None)
    return JSONResponse(content={"tickets": tickets})


@app.get("/inbox/api/tickets/counts")
async def api_contar_tickets(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Conteos por estado para los badges del panel."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    counts = await contar_tickets(agent_id)
    return JSONResponse(content=counts)


@app.post("/inbox/api/tickets/{ticket_id}/tomar")
async def api_tomar_ticket(
    ticket_id: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """El agente humano toma un ticket (sin_asignar o pendiente → activo).
    Si quien toma es el admin SaaS (no un UsuarioInterno explícito), se
    crea/usa automáticamente un usuario interno con rol 'admin' para que
    el ticket quede registrado con nombre + rol."""
    sesion = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not sesion:
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    agente_humano_id = int(body.get("agente_humano_id") or 0)

    # Si el frontend no pasó un usuario interno explícito (= 0), significa que
    # está actuando el admin SaaS o un usuario sin perfil de equipo interno.
    # Buscamos/creamos un usuario interno tipo admin para él.
    if not agente_humano_id:
        # agent_id del ticket (lo necesitamos para crear el admin en el negocio correcto)
        from agent.memory import Ticket as _T, async_session as _AS
        from sqlalchemy import select as _sel
        async with _AS() as _s:
            _r = await _s.execute(_sel(_T).where(_T.id == ticket_id))
            _tk = _r.scalar_one_or_none()
        if _tk:
            try:
                admin_ui = await obtener_o_crear_admin_interno(
                    agent_id=_tk.agent_id,
                    email=sesion.get("email", "admin@voco.local"),
                    nombre=sesion.get("nombre", "") or sesion.get("email", "Administrador"),
                )
                agente_humano_id = admin_ui["id"]
            except Exception as e:
                logger.warning(f"No pude obtener/crear admin interno: {e}")

    ticket = await tomar_ticket(ticket_id, agente_humano_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    # Activar modo humano para esta conversación. Sin esto Andrea sigue
    # respondiendo al cliente mientras el humano lo atiende — el cliente
    # ve respuestas duplicadas/contradictorias. La creación via escalación
    # ya lo activa, pero si el humano toma un ticket que no pasó por esa
    # ruta (ej: reabierto manualmente, o quedó con modo humano apagado por
    # algún cambio anterior), aquí lo forzamos.
    try:
        await set_modo_humano(ticket["telefono_cliente"], True, agent_id=ticket["agent_id"])
    except Exception as e:
        logger.warning(f"No pude activar modo humano al tomar ticket {ticket_id}: {e}")
    await registrar_evento_ticket(ticket_id, "tomado", ticket.get("agente_nombre","Agente"),
                                  "Tomó la conversación")
    _push_evento_ticket(ticket["agent_id"], "ticket_tomado", ticket)
    return JSONResponse(content={"ok": True, "ticket": ticket})


@app.post("/inbox/api/tickets/{ticket_id}/pendiente")
async def api_ticket_pendiente(
    ticket_id: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Marca el ticket como pendiente (agente necesita más info)."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    ticket = await marcar_ticket_pendiente(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    await registrar_evento_ticket(ticket_id, "pendiente",
                                  ticket.get("agente_nombre","Agente"), "Marcó como pendiente")
    _push_evento_ticket(ticket["agent_id"], "ticket_pendiente", ticket)
    return JSONResponse(content={"ok": True, "ticket": ticket})


@app.post("/inbox/api/tickets/{ticket_id}/resolver")
async def api_resolver_ticket(
    ticket_id: int,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Resuelve el ticket y reactiva el bot automáticamente."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    ticket = await resolver_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    # Reactivar bot para este cliente
    try:
        await set_modo_humano(ticket["telefono_cliente"], False, agent_id=agent_id)
        logger.info(f"Bot reactivado para {ticket['telefono_cliente']} al resolver ticket {ticket_id}")
    except Exception as e:
        logger.error(f"Error reactivando bot: {e}")
    await registrar_evento_ticket(ticket_id, "resuelto",
                                  ticket.get("agente_nombre","Agente"),
                                  "Resolvió el ticket — bot reactivado")
    _push_evento_ticket(ticket["agent_id"], "ticket_resuelto", ticket)
    return JSONResponse(content={"ok": True, "ticket": ticket})


@app.get("/inbox/api/tickets/{ticket_id}/eventos")
async def api_eventos_ticket(
    ticket_id: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Auditoría: historial de eventos de un ticket."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    eventos = await obtener_eventos_ticket(ticket_id)
    return JSONResponse(content={"eventos": eventos})


@app.get("/inbox/api/sistema/capi-status")
async def api_capi_status(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Diagnostica el estado del Conversions API (CAPI) token de Meta.
    Verifica si el token está configurado, si es válido contra la API de Meta,
    y a qué pixel/dataset tiene acceso."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    pixel_id   = await get_config_value("META_PIXEL_ID", agent_id=agent_id) or ""
    capi_token = await get_config_value("META_CAPI_TOKEN", agent_id=agent_id) or ""
    test_code  = await get_config_value("META_CAPI_TEST_CODE", agent_id=agent_id) or ""
    if agent_id == 1:  # solo para el agente primario, caer a env vars como fallback
        pixel_id   = pixel_id or os.getenv("META_PIXEL_ID", "").strip()
        capi_token = capi_token or os.getenv("META_CAPI_TOKEN", "").strip()
        test_code  = test_code or os.getenv("META_CAPI_TEST_CODE", "").strip()
    api_ver     = "v21.0"

    resultado = {
        "pixel_id_configurado":   bool(pixel_id),
        "capi_token_configurado": bool(capi_token),
        "modo_prueba_activo":     bool(test_code),
        "pixel_id_partial":       f"{pixel_id[:6]}...{pixel_id[-4:]}" if len(pixel_id) > 10 else pixel_id,
        "token_partial":          f"{capi_token[:8]}...{capi_token[-4:]}" if len(capi_token) > 16 else "(vacío)",
        "estado":                 "desconocido",
        "mensaje":                "",
        "pixel_info":             {},
    }

    if not pixel_id:
        resultado["estado"] = "no_configurado"
        resultado["mensaje"] = "Falta META_PIXEL_ID en variables de entorno"
        return JSONResponse(content=resultado)
    if not capi_token:
        resultado["estado"] = "no_configurado"
        resultado["mensaje"] = "Falta META_CAPI_TOKEN en variables de entorno"
        return JSONResponse(content=resultado)

    # 1) Validar token contra /me — devuelve la app/usuario al que pertenece
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r_me = await cli.get(
                f"https://graph.facebook.com/{api_ver}/me",
                headers={"Authorization": f"Bearer {capi_token}"},
            )
            if r_me.status_code != 200:
                err_data = {}
                try:
                    err_data = r_me.json().get("error", {})
                except Exception:
                    pass
                resultado["estado"] = "token_invalido"
                resultado["mensaje"] = (
                    f"Token rechazado por Meta — code={err_data.get('code', r_me.status_code)} "
                    f"msg={err_data.get('message', r_me.text[:200])}"
                )
                resultado["error_code"] = err_data.get("code")
                if err_data.get("code") == 190:
                    resultado["sugerencia"] = (
                        "Token expirado. Genera uno nuevo en Meta Business Manager → "
                        "Pixel → Configuración → Conversions API → Generate Access Token"
                    )
                return JSONResponse(content=resultado)
            me_data = r_me.json()
            resultado["token_owner"] = {
                "id":   me_data.get("id", ""),
                "name": me_data.get("name", ""),
            }
    except Exception as e:
        resultado["estado"] = "error_red"
        resultado["mensaje"] = f"No pude contactar Meta API: {str(e)[:200]}"
        return JSONResponse(content=resultado)

    # 2) Validar capacidad de enviar eventos al pixel
    # En vez de hacer GET (requiere ads_management), hacemos un POST de test event
    # que es exactamente para lo que sirve el token CAPI. Si Meta acepta el envío,
    # el token funciona para CAPI aunque no tenga permisos de lectura.
    # Usamos test_event_code para no contaminar el pixel real con eventos de prueba.
    try:
        url_eventos = f"https://graph.facebook.com/{api_ver}/{pixel_id}/events"
        # Evento de test mínimo (no se atribuye, solo valida que el token funciona)
        import hashlib
        test_payload = {
            "data": [{
                "event_name":   "VocoDiagnostico",
                "event_time":   int(datetime.utcnow().timestamp()),
                "action_source": "system_generated",
                "user_data":    {
                    "external_id": [hashlib.sha256(b"voco_diagnostic").hexdigest()],
                },
            }],
            "test_event_code": "TEST_VOCO_DIAGNOSTIC",  # marca como test, no afecta métricas
        }
        async with httpx.AsyncClient(timeout=10) as cli:
            r_ev = await cli.post(
                url_eventos,
                params={"access_token": capi_token},
                json=test_payload,
            )
            if r_ev.status_code == 200:
                ev_data = r_ev.json()
                resultado["estado"]   = "ok_activo"
                resultado["mensaje"]  = "✅ Token válido — Meta aceptó evento de prueba"
                resultado["eventos_recibidos"] = ev_data.get("events_received", 0)
                resultado["fbtrace_id"] = ev_data.get("fbtrace_id", "")
            else:
                err_data_p = {}
                try:
                    err_data_p = r_ev.json().get("error", {})
                except Exception:
                    pass
                err_code = err_data_p.get("code", 0)
                err_msg  = err_data_p.get("message", r_ev.text[:200])
                if err_code == 190:
                    resultado["estado"]  = "token_invalido"
                    resultado["mensaje"] = f"Token expirado/inválido: {err_msg}"
                    resultado["sugerencia"] = (
                        "Regenera el token en Events Manager → Equora Pixel → "
                        "Configuración → API de conversiones → Generar token de acceso"
                    )
                elif err_code in (100, 200, 803):
                    resultado["estado"]  = "sin_acceso_pixel"
                    resultado["mensaje"] = (
                        f"Token sin permiso sobre el pixel {pixel_id}: {err_msg}"
                    )
                    resultado["sugerencia"] = (
                        "Verifica que el token fue generado DESDE el panel del pixel "
                        "Equora Pixel en Events Manager (no desde otro pixel). "
                        "Confirma también que META_PIXEL_ID en Railway coincida con el "
                        "pixel para el que generaste el token."
                    )
                else:
                    resultado["estado"]  = "error"
                    resultado["mensaje"] = f"Meta respondió HTTP {r_ev.status_code} code={err_code}: {err_msg}"
                resultado["error_code"] = err_code
    except Exception as e:
        resultado["estado"]  = "error_red"
        resultado["mensaje"] = f"Error enviando evento de test: {str(e)[:200]}"

    return JSONResponse(content=resultado)


@app.get("/inbox/api/sistema/webhook-suscripcion")
async def api_webhook_suscripcion_status(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Verifica si nuestra app está suscrita al webhook de la WABA del agente.
    Sin esta suscripción Meta no envía los mensajes entrantes al backend, los
    clientes escriben y Andrea nunca se entera (token funciona OK pero no
    recibe nada). Pasa después de re-activar números o cambios en la WABA."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    waba_id = await get_config_value("META_WABA_ID", agent_id=agent_id) or (os.getenv("META_WABA_ID", "") if agent_id == 1 else "")
    tok     = await get_config_value("META_ACCESS_TOKEN", agent_id=agent_id) or (os.getenv("META_ACCESS_TOKEN", "") if agent_id == 1 else "")
    if not waba_id or not tok:
        return JSONResponse({"ok": False, "error": "Falta META_WABA_ID o META_ACCESS_TOKEN"})
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://graph.facebook.com/v21.0/{waba_id}/subscribed_apps",
                params={"access_token": tok},
            )
            if r.status_code != 200:
                return JSONResponse({"ok": False, "error": f"Meta API {r.status_code}: {r.text[:200]}"})
            data = r.json() or {}
            apps = data.get("data", []) or []
            return JSONResponse({
                "ok":         True,
                "suscrito":   len(apps) > 0,
                "total_apps": len(apps),
                "apps":       apps,
            })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/inbox/api/sistema/webhook-suscribir")
async def api_webhook_suscribir(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Suscribe la app Voco al webhook de la WABA. Reemplaza el paso manual
    que antes había que hacer en developers.facebook.com → WhatsApp → Configuration."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    waba_id = await get_config_value("META_WABA_ID", agent_id=agent_id) or (os.getenv("META_WABA_ID", "") if agent_id == 1 else "")
    tok     = await get_config_value("META_ACCESS_TOKEN", agent_id=agent_id) or (os.getenv("META_ACCESS_TOKEN", "") if agent_id == 1 else "")
    if not waba_id or not tok:
        return JSONResponse({"ok": False, "error": "Falta META_WABA_ID o META_ACCESS_TOKEN"})
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://graph.facebook.com/v21.0/{waba_id}/subscribed_apps",
                params={"access_token": tok},
            )
            ok = r.status_code == 200
            return JSONResponse({"ok": ok, "status": r.status_code, "detalle": r.text[:300]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@app.get("/inbox/api/sistema/fallas-catalogo")
async def api_fallas_catalogo(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Devuelve las últimas fallas del catálogo nativo de WhatsApp.
    Útil para diagnosticar problemas de sincronización con Meta."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    # Filtrar las últimas 24 horas
    hace_un_dia = datetime.utcnow() - timedelta(hours=24)
    recientes = [
        f for f in _catalogo_fallas
        if datetime.fromisoformat(f["at"]) > hace_un_dia
    ]
    # Contar por tipo
    por_tipo: dict[str, int] = {}
    for f in recientes:
        por_tipo[f["tipo"]] = por_tipo.get(f["tipo"], 0) + 1
    # Flag de "configurado" por agente — sin esto el panel mostraba "Catálogo funcionando"
    # para agentes nuevos que NO tienen META_CATALOG_ID, usando el catalog de otro agente.
    meta_cat_id = await get_config_value("META_CATALOG_ID", agent_id=agent_id) or ""
    if not meta_cat_id and agent_id == 1:
        meta_cat_id = os.getenv("META_CATALOG_ID", "")
    configurado = bool(meta_cat_id.strip())
    return JSONResponse(content={
        "configurado": configurado,
        "total_24h":  len(recientes),
        "por_tipo":   por_tipo,
        "ultimas":    list(recientes)[-20:],   # las 20 más recientes
        "cooldown_alerta_seg": _CATALOGO_ALERTA_COOLDOWN_SEG,
    })


@app.get("/inbox/api/equipo/stats")
async def api_stats_equipo(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Dashboard supervisor: métricas por agente."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    stats = await obtener_stats_equipo(agent_id)
    return JSONResponse(content={"stats": stats})


@app.post("/inbox/api/config/auto-asignar")
async def api_toggle_autoasignar(
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Activa/desactiva la asignación automática round-robin."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    activo = "1" if body.get("activo") else "0"
    await set_config_value("AUTO_ASIGNAR", activo, agent_id)
    return JSONResponse(content={"ok": True, "auto_asignar": activo == "1"})


@app.get("/inbox/api/tickets/{ticket_id}/historial")
async def api_historial_ticket(
    ticket_id: int,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Historial completo de mensajes del ticket (Andrea + humano) para el panel."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    ticket = await obtener_ticket_activo_por_telefono(agent_id, "")
    # Buscar por ticket_id directamente
    from agent.memory import Ticket as _TicketModel, async_session as _as
    from sqlalchemy import select as _sel
    async with _as() as sess:
        r = await sess.execute(_sel(_TicketModel).where(_TicketModel.id == ticket_id))
        t = r.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    mensajes = await obtener_historial_con_timestamps(t.telefono_cliente, 150, agent_id=t.agent_id)
    return JSONResponse(content={"mensajes": mensajes, "telefono": t.telefono_cliente})


# ══════════════════════════════════════════════════════════════════════════════
# Item #3 del backlog — Pipeline. Las tablas (Pipeline/Deal/DealActivity)
# existían desde Sprint A pero sin ningún endpoint que las usara — el módulo
# vivía como placeholder "en construcción" en el panel. Estos son los
# primeros endpoints CRUD.
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/inbox/api/pipeline")
async def api_obtener_pipeline(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Pipeline activo del agente (se crea con stages default si no existe)
    + todos sus deals. Pensado para cargar el kanban en una sola llamada."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    pipeline = await obtener_pipeline_activo(agent_id)
    deals = await listar_deals(agent_id, pipeline_id=pipeline["id"])
    return JSONResponse(content={"pipeline": pipeline, "deals": deals})


@app.post("/inbox/api/pipeline/{pipeline_id}/stages")
async def api_actualizar_stages_pipeline(
    pipeline_id: int,
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    stages = body.get("stages") or []
    if not isinstance(stages, list):
        return JSONResponse(status_code=400, content={"error": "stages debe ser una lista"})
    pipeline = await actualizar_stages_pipeline(pipeline_id, agent_id, [str(s) for s in stages])
    if not pipeline:
        return JSONResponse(status_code=400, content={"error": "Pipeline no encontrado o lista de stages vacía"})
    return JSONResponse(content={"ok": True, "pipeline": pipeline})


@app.post("/inbox/api/deals")
async def api_crear_deal(
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    telefono = (body.get("cliente_telefono") or "").strip()
    if not telefono:
        return JSONResponse(status_code=400, content={"error": "cliente_telefono es requerido"})
    pipeline = await obtener_pipeline_activo(agent_id)
    stages = pipeline["stages"] or ["Nuevo"]
    stage_inicial = body.get("stage") or stages[0]
    deal = await crear_deal(
        agent_id=agent_id,
        pipeline_id=pipeline["id"],
        cliente_telefono=telefono,
        cliente_nombre=(body.get("cliente_nombre") or "").strip(),
        titulo=(body.get("titulo") or "").strip(),
        valor_cop=body.get("valor_cop") or 0,
        source=(body.get("source") or "manual").strip(),
        stage=stage_inicial,
        autor_nombre=user.get("nombre") or user.get("email") or "Sistema",
    )
    return JSONResponse(content={"ok": True, "deal": deal})


@app.patch("/inbox/api/deals/{deal_id}")
async def api_actualizar_deal(
    deal_id: int,
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    campos = {k: body[k] for k in
              ("titulo", "stage", "valor_cop", "source", "owner_id", "notas", "cliente_nombre", "cliente_email")
              if k in body}
    deal = await actualizar_deal(deal_id, agent_id, autor_nombre=user.get("nombre") or user.get("email") or "Sistema", **campos)
    if not deal:
        return JSONResponse(status_code=404, content={"error": "Deal no encontrado o sin cambios válidos"})
    return JSONResponse(content={"ok": True, "deal": deal})


@app.delete("/inbox/api/deals/{deal_id}")
async def api_eliminar_deal(
    deal_id: int,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    ok = await eliminar_deal(deal_id, agent_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "Deal no encontrado"})
    return JSONResponse(content={"ok": True})


@app.get("/inbox/api/deals/{deal_id}/actividades")
async def api_listar_actividades_deal(
    deal_id: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    actividades = await listar_actividades_deal(deal_id)
    return JSONResponse(content={"actividades": actividades})


@app.post("/inbox/api/deals/{deal_id}/actividades")
async def api_crear_actividad_deal(
    deal_id: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    contenido = (body.get("contenido") or "").strip()
    if not contenido:
        return JSONResponse(status_code=400, content={"error": "contenido es requerido"})
    actividad = await agregar_actividad_deal(
        deal_id, tipo="note", contenido=contenido,
        autor_nombre=user.get("nombre") or user.get("email") or "Sistema",
    )
    return JSONResponse(content={"ok": True, "actividad": actividad})


# ══════════════════════════════════════════════════════════════════════════════
# Pipeline Fase 2 — Integraciones externas (Calendly, HubSpot, ...). CRUD
# genérico sobre IntegrationConfig — la tabla existía desde Sprint A sin
# ningún endpoint que la usara. Un (agent_id, tipo) por integración.
# ══════════════════════════════════════════════════════════════════════════════

TIPOS_INTEGRACION_VALIDOS = {"calendly", "hubspot", "sendgrid", "pipedrive"}


def _integracion_para_frontend(config: dict) -> dict:
    """Nunca devolvemos el token real al frontend — mismo patrón que ya usa
    Configuración para META_ACCESS_TOKEN/SHOPIFY_ADMIN_TOKEN (_ofuscar_secreto)."""
    config = dict(config)
    config["tiene_token"] = bool(config.get("api_token"))
    config["api_token"] = _ofuscar_secreto(config["api_token"]) if config.get("api_token") else ""
    return config


@app.get("/inbox/api/agents/{agent_id_param}/integrations")
async def api_listar_integraciones(
    agent_id_param: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    configs = await listar_integration_configs(agent_id_param)
    return JSONResponse(content={"integraciones": [_integracion_para_frontend(c) for c in configs]})


@app.get("/inbox/api/agents/{agent_id_param}/integrations/hubspot/verify")
async def api_verificar_hubspot(
    agent_id_param: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Llama a HubSpot /account-info/v3/details para confirmar qué portal está conectado."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    resultado = await hubspot_portal_info(agent_id_param)
    return JSONResponse(content=resultado)


@app.get("/inbox/api/agents/{agent_id_param}/integrations/calendly/verify")
async def api_verificar_calendly(
    agent_id_param: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Llama a Calendly /users/me para confirmar qué cuenta está conectada."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    resultado = await calendly_usuario(agent_id_param)
    return JSONResponse(content=resultado)


@app.get("/inbox/api/agents/{agent_id_param}/integrations/{tipo}")
async def api_obtener_integracion(
    agent_id_param: int,
    tipo: str,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    config = await obtener_integration_config(agent_id_param, tipo)
    if not config:
        return JSONResponse(content={
            "tipo": tipo, "configurado": False, "settings": {}, "activo": False,
            "tiene_token": False, "api_token": "",
        })
    config = _integracion_para_frontend(config)
    config["configurado"] = True
    return JSONResponse(content=config)


@app.post("/inbox/api/agents/{agent_id_param}/integrations/{tipo}")
async def api_guardar_integracion(
    agent_id_param: int,
    tipo: str,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    if tipo not in TIPOS_INTEGRACION_VALIDOS:
        return JSONResponse(status_code=400, content={"error": f"tipo inválido: {tipo}"})
    body = await request.json()

    api_token = body.get("api_token")
    if isinstance(api_token, str):
        api_token = api_token.strip()
        # Mismo saneo de caracteres invisibles que ya existe para tokens de
        # Meta/Shopify (bug real reportado al pegar tokens copiados de una web).
        for ch in ("​", "‌", "‍", "\xa0", "﻿", "‪", "‬"):
            api_token = api_token.replace(ch, "")
        if not api_token:
            api_token = None  # vacío = no tocar el token ya guardado, mismo patrón que Configuración
    elif api_token is not None:
        return JSONResponse(status_code=400, content={"error": "api_token debe ser texto"})

    settings = body.get("settings")
    if settings is not None and not isinstance(settings, dict):
        return JSONResponse(status_code=400, content={"error": "settings debe ser un objeto"})

    activo = body.get("activo")
    if activo is not None and not isinstance(activo, bool):
        return JSONResponse(status_code=400, content={"error": "activo debe ser booleano"})

    config = await guardar_integration_config(
        agent_id_param, tipo, api_token=api_token, settings=settings, activo=activo,
    )
    logger.info(f"[integraciones] '{tipo}' actualizado para agent_id={agent_id_param}")
    return JSONResponse(content={"ok": True, "integracion": _integracion_para_frontend(config)})


# ── API de Equipo (Usuarios Internos) ─────────────────────────────────────────

@app.get("/inbox/api/equipo")
async def api_listar_equipo(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Lista los agentes humanos de soporte del negocio."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    usuarios = await obtener_usuarios_internos(agent_id)
    return JSONResponse(content={"equipo": usuarios})


@app.post("/inbox/api/equipo")
async def api_crear_agente_equipo(
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Crea un nuevo agente humano de soporte. Respeta límites por plan."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    body = await request.json()
    nombre   = (body.get("nombre") or "").strip()
    email    = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    rol      = body.get("rol", "agente")

    if not nombre or not email or not password:
        return JSONResponse(content={"ok": False, "error": "nombre, email y password son requeridos"})
    if rol not in ("agente", "supervisor", "admin"):
        return JSONResponse(content={"ok": False, "error": "Rol inválido"})

    # Verificar límite de agentes según plan del agente
    from agent.memory import Agent as _AgentModel, async_session as _as
    from sqlalchemy import select as _sel
    async with _as() as sess:
        r = await sess.execute(_sel(_AgentModel).where(_AgentModel.id == agent_id))
        agente_cfg = r.scalar_one_or_none()
    max_permitidos = getattr(agente_cfg, "max_agentes", 2) if agente_cfg else 2
    actuales = await contar_agentes_activos(agent_id)
    if actuales >= max_permitidos:
        return JSONResponse(content={
            "ok": False,
            "error": f"Límite de {max_permitidos} agentes alcanzado. Actualiza tu plan para agregar más."
        })

    try:
        nuevo = await crear_usuario_interno(agent_id, nombre, email, password, rol)
        return JSONResponse(content={"ok": True, "usuario": nuevo})
    except Exception as e:
        return JSONResponse(content={"ok": False, "error": str(e)[:200]})


@app.put("/inbox/api/equipo/{ui_id}")
async def api_actualizar_agente_equipo(
    ui_id: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Actualiza nombre, rol, activo o password de un agente interno."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    # Whitelist de campos editables. #52 agrega notif_escalaciones_wa y telefono_wa.
    campos = {k: v for k, v in body.items() if k in (
        "nombre", "rol", "activo", "password",
        "notif_escalaciones_wa", "telefono_wa",
    )}
    # Normalizar el teléfono a solo dígitos (sin '+' ni espacios) si viene
    if "telefono_wa" in campos:
        digitos = re.sub(r"\D", "", str(campos["telefono_wa"] or ""))
        campos["telefono_wa"] = digitos
    if "notif_escalaciones_wa" in campos:
        campos["notif_escalaciones_wa"] = bool(campos["notif_escalaciones_wa"])
    ok = await actualizar_usuario_interno(ui_id, **campos)
    return JSONResponse(content={"ok": ok})


@app.delete("/inbox/api/equipo/{ui_id}")
async def api_desactivar_agente_equipo(
    ui_id: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Desactiva (soft-delete) un agente interno."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    ok = await actualizar_usuario_interno(ui_id, activo=False)
    return JSONResponse(content={"ok": ok})


@app.post("/inbox/api/equipo/ping")
async def api_ping_agente(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Heartbeat del agente para marcar que está online."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    ui_id = body.get("usuario_interno_id")
    if ui_id:
        await ping_usuario_interno(ui_id)
    return JSONResponse(content={"ok": True})


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 2 — SSE (Server-Sent Events) para notificaciones en tiempo real
# ══════════════════════════════════════════════════════════════════════════════

import asyncio as _asyncio
from fastapi.responses import StreamingResponse

# { agent_id → [Queue, Queue, ...] }  — una queue por pestaña/agente conectado
_sse_queues: dict[int, list[_asyncio.Queue]] = {}


def _push_evento_ticket(agent_id: int, tipo: str, ticket: dict) -> None:
    """Envía un evento SSE a todos los suscriptores del agent_id."""
    payload = json.dumps({"tipo": tipo, "ticket": ticket})
    for q in _sse_queues.get(agent_id, []):
        try:
            q.put_nowait(payload)
        except _asyncio.QueueFull:
            pass


async def _sse_stream(agent_id: int, q: _asyncio.Queue):
    """Generador SSE con keepalive cada 25 segundos."""
    try:
        while True:
            try:
                data = await _asyncio.wait_for(q.get(), timeout=25)
                yield f"data: {data}\n\n"
            except _asyncio.TimeoutError:
                yield ": keepalive\n\n"
    except _asyncio.CancelledError:
        pass
    finally:
        # Limpiar queue al desconectar
        qs = _sse_queues.get(agent_id, [])
        if q in qs:
            qs.remove(q)


@app.get("/inbox/api/eventos")
async def api_eventos_sse(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """SSE stream de eventos de tickets para el panel de escalaciones."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    q: _asyncio.Queue = _asyncio.Queue(maxsize=50)
    _sse_queues.setdefault(agent_id, []).append(q)

    return StreamingResponse(
        _sse_stream(agent_id, q),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",   # Nginx: deshabilitar buffer
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Transferir ticket entre agentes ───────────────────────────────────────────

@app.post("/inbox/api/tickets/{ticket_id}/transferir")
async def api_transferir_ticket(
    ticket_id: int,
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Transfiere un ticket a otro agente humano."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    nuevo_agente_id = body.get("agente_humano_id")
    if not nuevo_agente_id:
        return JSONResponse(content={"ok": False, "error": "agente_humano_id requerido"})
    ticket = await transferir_ticket(ticket_id, nuevo_agente_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    _push_evento_ticket(agent_id, "ticket_transferido", ticket)
    return JSONResponse(content={"ok": True, "ticket": ticket})


# ── Notas internas ────────────────────────────────────────────────────────────

@app.get("/inbox/api/tickets/{ticket_id}/notas")
async def api_listar_notas(
    ticket_id: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    notas = await obtener_notas_ticket(ticket_id)
    return JSONResponse(content={"notas": notas})


@app.post("/inbox/api/tickets/{ticket_id}/notas")
async def api_crear_nota(
    ticket_id: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    contenido        = (body.get("contenido") or "").strip()
    agente_humano_id = body.get("agente_humano_id", 0)
    agente_nombre    = (body.get("agente_nombre") or "Agente").strip()
    if not contenido:
        return JSONResponse(content={"ok": False, "error": "Nota vacía"})
    nota = await crear_nota_interna(ticket_id, agente_humano_id, agente_nombre, contenido)
    return JSONResponse(content={"ok": True, "nota": nota})


# ── Templates rápidos ─────────────────────────────────────────────────────────

@app.get("/inbox/api/templates")
async def api_listar_templates(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    templates = await obtener_templates_rapidos(agent_id)
    return JSONResponse(content={"templates": templates})


@app.post("/inbox/api/templates")
async def api_crear_template(
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body     = await request.json()
    titulo   = (body.get("titulo")   or "").strip()
    contenido = (body.get("contenido") or "").strip()
    orden    = int(body.get("orden", 0))
    if not titulo or not contenido:
        return JSONResponse(content={"ok": False, "error": "titulo y contenido requeridos"})
    tpl = await crear_template_rapido(agent_id, titulo, contenido, orden)
    return JSONResponse(content={"ok": True, "template": tpl})


@app.delete("/inbox/api/templates/{tpl_id}")
async def api_eliminar_template(
    tpl_id: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    ok = await eliminar_template_rapido(tpl_id)
    return JSONResponse(content={"ok": ok})


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
    voco_session: str = Cookie(default=""),
):
    """Debug: devuelve el JSON crudo de Meta para ver cómo están registradas las variables."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
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
    voco_session: str = Cookie(default=""),
):
    """Lista las plantillas aprobadas en Meta para usar en difusiones."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
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
    voco_session: str = Cookie(default=""),
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
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
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
    # Texto del body del template — el frontend lo manda para que podamos
    # guardarlo en el historial del cliente con variables sustituidas (#71).
    # Si no viene, usamos un fallback descriptivo.
    body_text     = body.get("body_text", "")

    if not template_name or not recipients:
        return JSONResponse(content={"error": "Faltan template o recipients"}, status_code=400)

    access_token    = os.getenv("META_ACCESS_TOKEN", "")
    phone_number_id = os.getenv("META_PHONE_NUMBER_ID", "")
    if not access_token or not phone_number_id:
        return JSONResponse(content={"error": "META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados"}, status_code=500)

    api_ver = "v21.0"
    api_url = f"https://graph.facebook.com/{api_ver}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    enviados   = 0
    fallidos   = 0
    opt_outs   = 0
    errores    = []

    # Pre-cargar lista de opt-outs para filtrar sin consulta por cada destinatario
    opt_out_set: set[str] = {r["telefono"] for r in await obtener_opt_outs()}
    if opt_out_set:
        logger.info(f"[broadcast] {len(opt_out_set)} números en opt-out — serán saltados")

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

            # Saltar números dados de baja
            if tel in opt_out_set:
                opt_outs += 1
                logger.info(f"[broadcast] {tel[-4:]}**** saltado — opt-out")
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
                        resp_data  = r.json()
                        wamid      = resp_data.get("messages", [{}])[0].get("id", "")
                        msg_status = resp_data.get("messages", [{}])[0].get("message_status", "?")
                    except Exception:
                        wamid, msg_status = "", "?"
                    logger.info(f"[broadcast] Enviado a {tel[-4:]}**** wamid={wamid[:20] if wamid else '?'} status={msg_status}")
                    # Guardar wamid para tracking de delivery/lectura
                    if wamid and campaign_id:
                        try:
                            await guardar_mensaje_difusion(
                                wamid=wamid,
                                campaign_id=campaign_id,
                                campaign_name=campaign_name,
                                telefono=tel,
                            )
                            logger.warning(f"[broadcast✅] wamid guardado para {tel[-4:]}**** campaign={campaign_id[:20]}")
                        except Exception as _e:
                            logger.warning(f"[broadcast⚠️] No se guardó wamid en difusion_mensajes: {_e}")
                    elif not campaign_id:
                        logger.warning(f"[broadcast⚠️] campaign_id vacío — no se guarda wamid para {tel[-4:]}****")

                    # #71 — Guardar el mensaje en historial de Conversaciones para
                    # que el merchant vea la difusión enviada en el chat del cliente.
                    # Renderizamos el body sustituyendo variables ({{1}}, {{nombre}}, etc).
                    try:
                        texto_render = body_text or ""
                        if texto_render and vars_dest:
                            for i, val in enumerate(vars_dest, start=1):
                                # Sustituir tanto posicionales {{1}} como nombradas {{nombre}}
                                texto_render = texto_render.replace("{{" + str(i) + "}}", str(val))
                                if is_named and i - 1 < len(var_names):
                                    texto_render = texto_render.replace("{{" + var_names[i-1] + "}}", str(val))
                        # Si no llegó body_text, marcador descriptivo
                        if not texto_render:
                            texto_render = f"[Plantilla: {template_name}]"
                        # Prefijo 📣 para distinguir visualmente del chat orgánico
                        texto_para_historial = f"📣 {texto_render}"
                        await guardar_mensaje(tel, "assistant", texto_para_historial, agent_id=1,
                                              wamid=wamid, status="sent" if wamid else "")
                    except Exception as _e:
                        logger.warning(f"[broadcast⚠️] No se guardó en historial mensajes: {_e}")
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

    logger.info(
        f"[broadcast] Difusión '{template_name}': "
        f"{enviados} enviados, {fallidos} fallidos, {opt_outs} opt-outs saltados"
    )

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
        "enviados":  enviados,
        "fallidos":  fallidos,
        "opt_outs":  opt_outs,
        "errores":   errores[:20],
    })


@app.get("/inbox/difusiones/historial")
async def inbox_difusiones_historial(
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Devuelve el historial de difusiones enviadas desde el inbox."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    try:
        rows = await obtener_difusiones(100)
        return JSONResponse(content={"difusiones": rows})
    except Exception as e:
        logger.error(f"[historial-dif] Error: {e}", exc_info=True)
        return JSONResponse(content={"difusiones": [], "error": str(e)[:300]})


@app.get("/inbox/difusiones/campana/{campaign_id:path}")
async def inbox_difusion_detalle(
    campaign_id: str,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Detalle de una campaña: breakdown de entregados, leídos, fallidos con motivo de error."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    data = await obtener_detalle_campana(campaign_id)
    return JSONResponse(content=data)


# ══════════════════════════════════════════════════════════════════════════════
# #51 — Wizard onboarding Meta WhatsApp (8 pasos guiados)
# ══════════════════════════════════════════════════════════════════════════════

# El progreso se persiste en un único registro ConfigValue como JSON,
# scopeado por agent_id — así cada agente (cada tenant) tiene su propio
# estado del wizard. Cuando cambian de usuario, ven el progreso de SU agente,
# no el de otro.
_ONBOARDING_KEY = "ONBOARDING_META_PROGRESS"
# 6 pasos en total:
#   1 Crear Business Manager
#   2 Verificar negocio
#   3 Crear WABA + agregar número (Meta lo combina en un solo modal)
#   4 Invitar Voco como socio
#   5 Generar token System User
#   6 Conectar Voco (valida + registra número + suscribe webhook automático)
_ONBOARDING_TOTAL_PASOS = 6
# Camino corto = solo 2 pasos NUEVOS (3 = crear WABA+número, 6 = conectar).
_ONBOARDING_TOTAL_PASOS_CORTO = 2


async def _resolver_agent_id_para_user(user: dict) -> int | None:
    """Devuelve el agent_id activo del usuario para el wizard.

    Estrategia: primer agente del que el user es owner. Si el user no tiene
    agentes propios (ej: cuenta recién creada), retorna None — el handler
    debe redirigir a Mis Agentes para crear uno.
    """
    if not user or not user.get("id"):
        return None
    from agent.memory import obtener_agentes_de_usuario
    agentes = await obtener_agentes_de_usuario(int(user["id"]))
    if not agentes:
        return None
    return int(agentes[0]["id"])


async def _leer_onboarding_estado(agent_id: int = 1) -> dict:
    raw = await get_config_value(_ONBOARDING_KEY, agent_id) or ""
    if not raw:
        return {"pasos": {}}
    try:
        import json as _json
        data = _json.loads(raw)
        if not isinstance(data, dict) or "pasos" not in data:
            return {"pasos": {}}
        return data
    except Exception:
        return {"pasos": {}}


async def _guardar_onboarding_estado(estado: dict, agent_id: int = 1, user: dict | None = None) -> None:
    import json as _json
    await set_config_value(
        _ONBOARDING_KEY,
        _json.dumps(estado),
        agent_id=agent_id,
        usuario_id=(user or {}).get("id"),
        usuario_email=(user or {}).get("email", ""),
    )


@app.get("/inbox/api/onboarding/estado")
async def api_onboarding_estado(
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Devuelve el estado del wizard del agente del usuario actual + flag
    `tiene_meta_previo` para que el frontend muestre la bifurcación si aplica."""
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    agent_id = await _resolver_agent_id_para_user(user)
    if agent_id is None:
        return JSONResponse({"pasos": {}, "completados": 0, "total": _ONBOARDING_TOTAL_PASOS,
                             "porcentaje": 0, "sin_agente": True})
    from agent.memory import usuario_tiene_meta_configurado
    estado = await _leer_onboarding_estado(agent_id)
    # tiene_meta_previo: el user ya completó el wizard largo en OTRO agente.
    # Si esto es true Y este agente todavía no eligió camino, mostramos
    # la pantalla de bifurcación.
    tiene_previo = await usuario_tiene_meta_configurado(int(user["id"]))
    # Es "el agente actual ya completó algo" si tiene cualquier paso marcado
    actual_tiene_progreso = any(p.get("completado") for p in estado["pasos"].values())
    # Es propiamente "otro agente" si tiene_previo Y el agente activo no es
    # el que tiene el paso 8 — chequeo simple: si este mismo tiene paso 8, no
    # es escenario de "segundo agente"
    este_ya_termino = estado["pasos"].get("8", {}).get("completado", False)
    mostrar_bifurcacion = bool(tiene_previo and not este_ya_termino and not actual_tiene_progreso)

    # Camino del wizard que el merchant eligió para ESTE agente — guardado
    # como una clave especial dentro del propio JSON de progreso.
    camino = estado.get("_camino") or ""

    completados = sum(1 for p in estado["pasos"].values() if p.get("completado"))
    total = _ONBOARDING_TOTAL_PASOS_CORTO if camino == "corto" else _ONBOARDING_TOTAL_PASOS
    return JSONResponse({
        "agent_id": agent_id,
        "pasos": estado["pasos"],
        "completados": completados,
        "total": total,
        "porcentaje": round((completados / total) * 100) if total else 0,
        "mostrar_bifurcacion": mostrar_bifurcacion,
        "camino": camino,  # '' / 'corto' / 'completo'
    })


@app.post("/inbox/api/onboarding/reset")
async def api_onboarding_reset(
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Borra TODO el progreso del wizard para el agente actual. Útil cuando el
    merchant quiere recomenzar (cambió de número, se equivocó de cuenta, etc).
    El historial de cambios queda registrado vía set_config_value."""
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    agent_id = await _resolver_agent_id_para_user(user)
    if agent_id is None:
        return JSONResponse({"ok": False, "error": "Sin agente"}, status_code=400)
    await _guardar_onboarding_estado({"pasos": {}}, agent_id, user)
    logger.info(f"[onboarding] Wizard reiniciado para agent_id={agent_id} por user={user.get('email')}")
    return JSONResponse({"ok": True})


@app.post("/inbox/api/onboarding/camino/{nombre}")
async def api_onboarding_set_camino(
    nombre: str,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Marca qué camino eligió el merchant: 'corto' (reusa BM) o 'completo'.
    Esto define qué pasos rendea el wizard a partir de ahora para este agente."""
    if nombre not in ("corto", "completo"):
        return JSONResponse({"ok": False, "error": "Camino inválido"}, status_code=400)
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    agent_id = await _resolver_agent_id_para_user(user)
    if agent_id is None:
        return JSONResponse({"ok": False, "error": "Sin agente"}, status_code=400)
    estado = await _leer_onboarding_estado(agent_id)
    estado["_camino"] = nombre
    # Si eligió camino corto, marcamos automáticamente los pasos heredados
    # del BM existente: 1 (BM creado), 2 (verificado), 5 (Voco invitado),
    # 6 (token generado), 8 (webhook activo a nivel app)
    if nombre == "corto":
        ahora = datetime.utcnow().isoformat()
        # 1=BM, 2=verificación, 4=socio invitado, 5=token generado — todos
        # heredables del primer agente. Paso 6 (conectar+webhook+registro) sí
        # toca hacerlo de nuevo porque el número y WABA son nuevos.
        for paso_n in ("1", "2", "4", "5"):
            estado["pasos"][paso_n] = {
                "completado": True,
                "datos": {"_heredado": True},
                "fecha": ahora,
                "usuario_email": user.get("email", ""),
            }
    await _guardar_onboarding_estado(estado, agent_id, user)
    return JSONResponse({"ok": True, "camino": nombre})


@app.post("/inbox/api/onboarding/paso/{n}/completar")
async def api_onboarding_completar(
    n: int,
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Marca un paso como completado. Body opcional: {"datos": {...}} con campos
    capturados en ese paso (Business Manager ID, número de teléfono, etc)."""
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    if n < 0 or n > _ONBOARDING_TOTAL_PASOS:
        return JSONResponse({"ok": False, "error": f"Paso {n} fuera de rango"}, status_code=400)
    agent_id = await _resolver_agent_id_para_user(user)
    if agent_id is None:
        return JSONResponse({"ok": False, "error": "Primero crea un agente"}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    datos = body.get("datos") or {}
    estado = await _leer_onboarding_estado(agent_id)
    estado["pasos"][str(n)] = {
        "completado": True,
        "datos": datos,
        "fecha": datetime.utcnow().isoformat(),
        "usuario_email": user.get("email", ""),
    }
    await _guardar_onboarding_estado(estado, agent_id, user)
    return JSONResponse({"ok": True})


@app.post("/inbox/api/onboarding/paso/{n}/reabrir")
async def api_onboarding_reabrir(
    n: int,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Reabre un paso (desmarca como completado). Útil si el merchant quiere
    volver a revisar algo."""
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    agent_id = await _resolver_agent_id_para_user(user)
    if agent_id is None:
        return JSONResponse({"ok": False, "error": "Sin agente"}, status_code=400)
    estado = await _leer_onboarding_estado(agent_id)
    if str(n) in estado["pasos"]:
        estado["pasos"][str(n)]["completado"] = False
        await _guardar_onboarding_estado(estado, agent_id, user)
    return JSONResponse({"ok": True})


@app.post("/inbox/api/onboarding/validar-meta")
async def api_onboarding_validar_meta(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Valida credenciales Meta haciendo 3 llamadas reales: /me, /{phone_id},
    /{waba_id}/templates. Devuelve qué pasó con cada una para feedback claro."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    body = await request.json()
    tok      = (body.get("access_token") or "").strip()
    phone_id = (body.get("phone_number_id") or "").strip()
    waba_id  = (body.get("waba_id") or "").strip()
    if not tok or not phone_id:
        return JSONResponse({"ok": False, "error": "Faltan access_token y/o phone_number_id"})

    resultados = {"me": None, "phone": None, "waba": None}
    api_ver = "v21.0"
    async with httpx.AsyncClient(timeout=10) as client:
        # /me — token válido?
        try:
            r = await client.get(f"https://graph.facebook.com/{api_ver}/me",
                                 params={"access_token": tok})
            resultados["me"] = {"ok": r.status_code == 200, "detalle": r.json() if r.status_code == 200 else r.text[:200]}
        except Exception as e:
            resultados["me"] = {"ok": False, "detalle": str(e)}
        # /{phone_id} — token tiene acceso al número?
        try:
            r = await client.get(f"https://graph.facebook.com/{api_ver}/{phone_id}",
                                 params={"access_token": tok})
            resultados["phone"] = {"ok": r.status_code == 200, "detalle": r.json() if r.status_code == 200 else r.text[:200]}
        except Exception as e:
            resultados["phone"] = {"ok": False, "detalle": str(e)}
        # /{waba_id}/message_templates — token tiene scope whatsapp_business_management?
        if waba_id:
            try:
                r = await client.get(f"https://graph.facebook.com/{api_ver}/{waba_id}/message_templates",
                                     params={"access_token": tok, "limit": 1})
                resultados["waba"] = {"ok": r.status_code == 200, "detalle": r.json() if r.status_code == 200 else r.text[:200]}
            except Exception as e:
                resultados["waba"] = {"ok": False, "detalle": str(e)}

    todo_ok = resultados["me"]["ok"] and resultados["phone"]["ok"] and (not waba_id or resultados["waba"]["ok"])

    # Si las 3 validaciones pasaron, ejecutamos lo que el merchant antes hacía
    # MANUALMENTE en API Setup → "Enviar mensaje": registrar el número para
    # Cloud API (sin esto Meta no enruta los mensajes al webhook) + suscribir
    # nuestra app a los webhooks de la WABA. Todo en backend, sin que el
    # merchant tenga que entrar a developers.facebook.com.
    registro_numero = None
    webhook_subscrito = None
    if todo_ok:
        # PIN para 2FA del número. Default '000000' — Meta lo acepta como nuevo
        # PIN si el número aún no tiene 2FA. El merchant puede cambiarlo después
        # desde WhatsApp Manager si quiere.
        pin = (body.get("pin") or "000000").strip()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                rr = await client.post(
                    f"https://graph.facebook.com/{api_ver}/{phone_id}/register",
                    headers={"Authorization": f"Bearer {tok}"},
                    json={"messaging_product": "whatsapp", "pin": pin},
                )
                # Códigos comunes:
                # 200 → registro exitoso
                # 400 con "already registered" → ya estaba registrado, OK
                # 400 con "pin mismatch" → ya tiene 2FA con otro PIN
                resp_text = rr.text[:300]
                ok = rr.status_code == 200 or "already" in resp_text.lower()
                registro_numero = {
                    "ok":      ok,
                    "status":  rr.status_code,
                    "detalle": resp_text,
                }
        except Exception as e:
            registro_numero = {"ok": False, "detalle": str(e)}

        if waba_id:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    rs = await client.post(
                        f"https://graph.facebook.com/{api_ver}/{waba_id}/subscribed_apps",
                        params={"access_token": tok},
                    )
                    webhook_subscrito = {"ok": rs.status_code == 200,
                                         "detalle": rs.json() if rs.status_code == 200 else rs.text[:200]}
            except Exception as e:
                webhook_subscrito = {"ok": False, "detalle": str(e)}

    return JSONResponse({
        "ok": todo_ok,
        "resultados": resultados,
        "registro_numero":   registro_numero,
        "webhook_subscrito": webhook_subscrito,
    })


# Página del wizard (HTML standalone, fuera del panel principal)
@app.get("/inbox/onboarding-meta", response_class=HTMLResponse)
async def inbox_onboarding_meta(
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Página del wizard de onboarding Meta WhatsApp.
    Standalone — no usa el shell del panel para foco total en la tarea."""
    user = await _obtener_sesion_usuario(voco_session or inbox_session)
    if not user:
        return HTMLResponse(status_code=302, headers={"Location": "/inbox/login"}, content="")
    # Si el usuario no tiene agentes, no tiene sentido abrir el wizard.
    # Lo enviamos a Mis Agentes para que cree uno primero.
    agent_id = await _resolver_agent_id_para_user(user)
    if agent_id is None:
        return HTMLResponse(status_code=302, headers={"Location": "/inbox"}, content="")
    from agent.inbox import HTML_WIZARD_ONBOARDING
    webhook_url = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/") + "/webhook"
    return HTMLResponse(content=HTML_WIZARD_ONBOARDING.replace("__WEBHOOK_URL__", webhook_url))


@app.get("/inbox/api/metricas/operacion")
async def inbox_metricas_operacion(
    dias: int = 7,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Dashboard de salud del flujo (#47): tráfico + conversión + escalación.
    Devuelve métricas del período actual vs período anterior para detectar
    tendencias. agent_name viene incluido para que la UI no hardcodee 'Andrea'."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import obtener_metricas_operacion, obtener_agente
    dias = max(1, min(int(dias or 7), 90))
    data = await obtener_metricas_operacion(agent_id=agent_id, dias=dias)
    ag = await obtener_agente(agent_id) or {}
    data["agent_name"]    = ag.get("agent_name") or "Bot"
    data["agent_business"] = ag.get("name") or ""
    return JSONResponse(content=data)


@app.get("/inbox/metricas/resumen")
async def inbox_metricas_resumen(
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Métricas de WhatsApp Business: mensajes enviados, entregados, leídos (últimos 30 días)."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
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
    voco_session: str = Cookie(default=""),
):
    """Analíticas por plantilla: enviados, entregados, leídos, clics en botón."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
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


@app.get("/inbox/metricas/interno")
async def inbox_metricas_interno(
    dias: int = 30,
    desde: str = "",        # ISO date opcional: "2025-05-01"
    hasta: str = "",        # ISO date opcional: "2025-05-31"
    granularidad: str = "dia",   # dia | semana | mes (para series temporales)
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Métricas calculadas desde la base de datos interna.
    Acepta rango específico con `desde`/`hasta` (formato ISO YYYY-MM-DD) o
    fallback a últimos `dias` días. Incluye series temporales con la granularidad."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    try:
        # Parsear rango de fechas si vino explícito
        desde_dt = None
        hasta_dt = None
        if desde:
            try:
                desde_dt = datetime.fromisoformat(desde.replace("Z", ""))
            except Exception:
                logger.warning(f"[metricas] 'desde' inválido: {desde}")
        if hasta:
            try:
                hasta_dt = datetime.fromisoformat(hasta.replace("Z", ""))
                # Si solo es fecha (YYYY-MM-DD), incluir hasta el final del día
                if len(hasta) <= 10:
                    hasta_dt = hasta_dt.replace(hour=23, minute=59, second=59)
            except Exception:
                logger.warning(f"[metricas] 'hasta' inválido: {hasta}")

        # Métricas agregadas
        data = await obtener_metricas_internas(
            dias=dias, desde=desde_dt, hasta=hasta_dt, agent_id=agent_id,
        )
        # Series temporales (usar fechas efectivas calculadas)
        from agent.memory import obtener_series_metricas
        desde_eff = datetime.fromisoformat(data["desde"])
        hasta_eff = datetime.fromisoformat(data["hasta"])
        series = await obtener_series_metricas(
            desde=desde_eff, hasta=hasta_eff,
            granularidad=granularidad, agent_id=agent_id,
        )
        data["series"]       = series
        data["granularidad"] = granularidad
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"[metricas-interno] Error: {e}", exc_info=True)
        return JSONResponse(content={"error": str(e) or type(e).__name__})


@app.get("/inbox/api/opt-outs")
async def inbox_opt_outs(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Lista de números dados de baja de difusiones masivas."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    rows = await obtener_opt_outs(agent_id=agent_id)
    return JSONResponse(content={"opt_outs": rows, "total": len(rows)})


@app.get("/inbox/api/clientes")
async def inbox_clientes(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Base de clientes con estado de engagement (activo/tibio/frío/baja)."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    clientes = await obtener_clientes_con_estado(agent_id=agent_id)
    resumen = {"total": len(clientes), "activo": 0, "tibio": 0, "frio": 0, "baja": 0}
    for c in clientes:
        resumen[c["estado"]] = resumen.get(c["estado"], 0) + 1
    return JSONResponse(content={"clientes": clientes, "resumen": resumen})


@app.post("/inbox/api/clientes/edit")
async def inbox_editar_cliente(
    request: Request,
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Edita nombre/teléfono/ciudad de un cliente desde el panel.
    Si cambia el teléfono, migra todas las referencias (mensajes, escalaciones, etc).
    """
    if not await _obtener_sesion_usuario(voco_session or inbox_session):
        raise HTTPException(status_code=401, detail="No autorizado")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    telefono_original = (body.get("telefono_original") or "").strip()
    if not telefono_original:
        return JSONResponse({"ok": False, "error": "Falta telefono_original"}, status_code=400)

    datos = {
        "nombres":  (body.get("nombres") or "").strip(),
        "apellidos": (body.get("apellidos") or "").strip(),
        "ciudad":   (body.get("ciudad") or "").strip(),
    }

    agent_id = int(body.get("agent_id") or 1)
    telefono_nuevo_raw = (body.get("telefono") or "").strip()
    telefono_nuevo: str | None = None
    if telefono_nuevo_raw:
        telefono_nuevo = _normalizar_telefono(telefono_nuevo_raw)
        if not telefono_nuevo:
            return JSONResponse(
                {"ok": False, "error": "Teléfono inválido"},
                status_code=400,
            )

    resultado = await editar_cliente(
        telefono_original=telefono_original,
        datos=datos,
        agent_id=agent_id,
        telefono_nuevo=telefono_nuevo,
    )
    status = 200 if resultado["ok"] else 409
    return JSONResponse(resultado, status_code=status)


def _normalizar_telefono(raw: str) -> str | None:
    """Normaliza un número de teléfono para WhatsApp.
    Acepta formatos con espacios, guiones, signos +.
    Si comienza con 3 y tiene 10 dígitos, antepone código país 57 (Colombia)."""
    digits = re.sub(r'[^0-9]', '', str(raw))
    if not digits:
        return None
    if digits.startswith('57') and len(digits) == 12:
        return digits
    if digits.startswith('3') and len(digits) == 10:
        return '57' + digits
    if len(digits) >= 7:
        return digits  # aceptar tal cual para internacionales
    return None


@app.get("/inbox/api/clientes/import/template")
async def inbox_plantilla_csv(
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Descarga la plantilla CSV con las columnas correctas y ejemplos."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from fastapi.responses import Response
    contenido = (
        "telefono,nombres,apellidos,ciudad,departamento,email,cc_nit\n"
        "3001234567,Juan,Pérez,Bogotá,Cundinamarca,juan@email.com,12345678\n"
        "3159876543,María,López,Medellín,Antioquia,maria@email.com,87654321\n"
        "573201112233,Carlos,García,Cali,Valle del Cauca,,\n"
    )
    return Response(
        content=contenido.encode("utf-8-sig"),  # BOM para Excel en español
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=plantilla_clientes.csv"},
    )


@app.post("/inbox/api/clientes/import")
async def inbox_importar_clientes(
    request: Request,
    file: UploadFile = File(...),
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Importa clientes masivamente desde un archivo CSV (campo 'file' en multipart/form-data).
    Columnas requeridas: telefono, nombres, apellidos. Opcionales: ciudad, departamento, email, cc_nit."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    contenido = await file.read()
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = contenido.decode("latin-1", errors="replace")

    reader = csv.DictReader(io.StringIO(texto))

    CAMPOS_OPCIONALES = {"nombres", "apellidos", "ciudad", "departamento", "email", "cc_nit"}

    total = 0
    insertados = 0
    actualizados = 0
    errores = 0
    filas_error: list[dict] = []

    for i, fila in enumerate(reader, start=2):  # start=2: fila 1 es cabecera
        total += 1
        fila_norm = {k.strip().lower(): (v or "").strip() for k, v in fila.items()}
        raw_tel = fila_norm.get("telefono", "")
        if not raw_tel:
            errores += 1
            filas_error.append({"fila": i, "razon": "columna 'telefono' vacía", "datos": fila_norm})
            continue

        tel = _normalizar_telefono(raw_tel)
        if not tel:
            errores += 1
            filas_error.append({"fila": i, "razon": f"número inválido: {raw_tel}", "datos": fila_norm})
            continue

        # nombres y apellidos son obligatorios
        if not fila_norm.get("nombres") or not fila_norm.get("apellidos"):
            errores += 1
            filas_error.append({"fila": i, "razon": "nombres y apellidos son obligatorios", "datos": fila_norm})
            continue

        datos = {campo: fila_norm[campo] for campo in CAMPOS_OPCIONALES if fila_norm.get(campo)}
        try:
            resultado = await guardar_cliente_import(tel, datos, agent_id)
            if resultado == "inserted":
                insertados += 1
            else:
                actualizados += 1
        except Exception as e:
            errores += 1
            filas_error.append({"fila": i, "razon": str(e), "datos": fila_norm})

    logger.info(f"[import-clientes] total={total} insertados={insertados} actualizados={actualizados} errores={errores}")
    return JSONResponse(content={
        "ok": True,
        "total": total,
        "inserted": insertados,
        "updated": actualizados,
        "errors": errores,
        "error_rows": filas_error[:20],  # máximo 20 ejemplos de errores
    })


@app.get("/inbox/api/clientes/templates")
async def inbox_listar_templates_clientes(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Lista plantillas aprobadas de Meta para enviar a clientes individuales."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    access_token = await get_config_value("META_ACCESS_TOKEN", agent_id) or os.getenv("META_ACCESS_TOKEN", "")
    waba_id      = await get_config_value("META_WABA_ID", agent_id)      or os.getenv("META_WABA_ID", "")

    if not access_token or not waba_id:
        return JSONResponse(content={"templates": [], "error": "META_ACCESS_TOKEN o META_WABA_ID no configurados"})

    api_ver = "v21.0"
    url = (
        f"https://graph.facebook.com/{api_ver}/{waba_id}"
        f"/message_templates?fields=id,name,status,components,language&limit=100"
        f"&access_token={access_token}"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return JSONResponse(content={"templates": [], "error": f"Meta API {r.status_code}: {r.text[:200]}"})
        data = r.json()
        if "error" in data:
            return JSONResponse(content={"templates": [], "error": data["error"].get("message", str(data["error"]))})

        templates = []
        for t in data.get("data", []):
            if (t.get("status", "")).upper() != "APPROVED":
                continue
            body_text = next(
                (c.get("text", "") for c in t.get("components", []) if c.get("type", "").upper() == "BODY"),
                ""
            )
            templates.append({
                "name":     t.get("name", ""),
                "language": t.get("language", "es_CO"),
                "category": t.get("category", ""),
                "preview":  body_text,
                "components": t.get("components", []),
            })
        return JSONResponse(content={"templates": templates})
    except Exception as e:
        logger.error(f"[clientes/templates] Error: {e}", exc_info=True)
        return JSONResponse(content={"templates": [], "error": str(e)})


@app.post("/inbox/api/clientes/message")
async def inbox_enviar_mensaje_cliente(
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Envía una plantilla aprobada de Meta a un cliente específico.
    Body JSON: {telefono, template_name, language_code, components?}"""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    body          = await request.json()
    telefono      = str(body.get("telefono", "")).strip()
    template_name = str(body.get("template_name", "")).strip()
    language_code = str(body.get("language_code", "es_CO")).strip()
    components    = body.get("components")  # lista de componentes, puede ser None

    tel = _normalizar_telefono(telefono)
    if not tel:
        return JSONResponse(content={"ok": False, "error": f"Número inválido: {telefono}"}, status_code=400)
    if not template_name:
        return JSONResponse(content={"ok": False, "error": "template_name es requerido"}, status_code=400)

    access_token    = await get_config_value("META_ACCESS_TOKEN", agent_id)    or os.getenv("META_ACCESS_TOKEN", "")
    phone_number_id = await get_config_value("META_PHONE_NUMBER_ID", agent_id) or os.getenv("META_PHONE_NUMBER_ID", "")

    from agent.providers.meta import ProveedorMeta
    meta = ProveedorMeta(
        access_token=access_token,
        phone_number_id=phone_number_id,
    )
    resultado = await meta.enviar_plantilla(
        telefono=tel,
        template_name=template_name,
        language_code=language_code,
        components=components,
    )
    if resultado.get("ok"):
        # Registrar en historial
        try:
            _w = resultado.get("message_id") or ""
            await guardar_mensaje(tel, "assistant", f"[Plantilla: {template_name}]", agent_id=agent_id,
                                  wamid=_w, status="sent" if _w else "")
        except Exception:
            pass
        logger.info(f"[clientes/message] Plantilla '{template_name}' enviada a {tel[-4:]}**** message_id={resultado.get('message_id','?')}")
    else:
        logger.warning(f"[clientes/message] Fallo enviando plantilla a {tel[-4:]}****: {resultado.get('error')}")

    return JSONResponse(content=resultado)


@app.delete("/inbox/api/opt-outs/{telefono}")
async def inbox_revertir_opt_out(
    telefono: str,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Reactiva un número para recibir difusiones (el cliente cambió de opinión)."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    await revertir_opt_out(telefono)
    logger.info(f"[opt-out] {telefono} reactivado desde inbox")
    return JSONResponse(content={"ok": True})


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DINÁMICA — guardar credenciales en BD + probar conexiones
# ══════════════════════════════════════════════════════════════════════════════

_CONFIG_KEYS_ALLOWED = {
    "META_ACCESS_TOKEN", "META_PHONE_NUMBER_ID", "META_WABA_ID", "META_VERIFY_TOKEN",
    "META_CATALOG_ID",
    # Conversions API (Pixel server-side) — antes solo en Railway env vars
    "META_PIXEL_ID", "META_CAPI_TOKEN", "META_CAPI_TEST_CODE",
    "ANTHROPIC_API_KEY", "AI_MODEL",
    # Shopify post-#62: solo OAuth (modelo Jelou). El cliente entrega Client
    # ID + Client Secret; Voco hace el OAuth dance y obtiene ADMIN_TOKEN
    # automáticamente. STOREFRONT_TOKEN y WEBHOOK_SECRET fueron retirados.
    "SHOPIFY_STORE", "SHOPIFY_ADMIN_TOKEN",
    "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET",
    # Sprint 4 — reglas del negocio configurables por agente
    "PEDIDO_MINIMO", "PEDIDO_MIN_MSG",
}

_CONFIG_META = {
    "META_ACCESS_TOKEN":       {"label": "Token de acceso",    "tipo": "secret"},
    "META_PHONE_NUMBER_ID":    {"label": "Phone Number ID",    "tipo": "plain"},
    "META_WABA_ID":            {"label": "WABA ID",            "tipo": "plain"},
    "META_VERIFY_TOKEN":       {"label": "Verify Token",       "tipo": "plain"},
    "META_CATALOG_ID":         {"label": "Catalog ID",         "tipo": "plain"},
    "META_PIXEL_ID":           {"label": "Pixel ID (CAPI)",    "tipo": "plain"},
    "META_CAPI_TOKEN":         {"label": "Token CAPI",         "tipo": "secret"},
    "META_CAPI_TEST_CODE":     {"label": "Test Event Code",    "tipo": "plain"},
    "ANTHROPIC_API_KEY":       {"label": "API Key",            "tipo": "secret"},
    "AI_MODEL":                {"label": "Modelo IA",          "tipo": "plain"},
    "SHOPIFY_STORE":           {"label": "Dominio tienda",   "tipo": "plain"},
    "SHOPIFY_ADMIN_TOKEN":     {"label": "Admin API Token",  "tipo": "secret"},
    "SHOPIFY_CLIENT_ID":       {"label": "Client ID (OAuth)",     "tipo": "plain"},
    "SHOPIFY_CLIENT_SECRET":   {"label": "Client Secret (OAuth)", "tipo": "secret"},
    "PEDIDO_MINIMO":           {"label": "Pedido mínimo (COP)", "tipo": "plain"},
    "PEDIDO_MIN_MSG":          {"label": "Mensaje pedido mínimo", "tipo": "plain"},
}


@app.get("/inbox/api/config")
async def inbox_get_config(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Devuelve el estado de cada clave de configuración (sin exponer valores secretos)."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    resultado = {}
    for clave, meta in _CONFIG_META.items():
        db_val  = await get_config_value(clave, agent_id=agent_id)
        # Env vars son globales de la plataforma; solo se muestran para el
        # agente primario (id=1). Los demás tenants solo ven sus propios valores de BD.
        env_val = os.getenv(clave, "") if agent_id == 1 else ""
        valor   = db_val if db_val else env_val
        if valor:
            display = "•" * 8 if meta["tipo"] == "secret" else valor
            resultado[clave] = {"configurado": True, "display": display,
                                "fuente": "db" if db_val else "env"}
        else:
            resultado[clave] = {"configurado": False, "display": "", "fuente": None}

    return JSONResponse(content=resultado)


@app.post("/inbox/api/config/save")
async def inbox_save_config(
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Guarda credenciales en la BD y las inyecta en el entorno actual."""
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")

    body = await request.json()
    # Claves que permiten valor vacío (para resetear) — el resto solo guarda si no está vacío
    _PERMITE_VACIO = {"PEDIDO_MIN_MSG", "META_CAPI_TEST_CODE"}
    saved = []
    for clave, valor in body.items():
        if clave in _CONFIG_KEYS_ALLOWED and isinstance(valor, str):
            valor = valor.strip()
            # Sanitizar caracteres invisibles que se copian de páginas web
            # (zero-width space, non-breaking space, BOM, etc.). Estos rompen
            # httpx con 'ascii codec can't encode' al usar el valor como header.
            # Bug reportado por Equora 13-jun al pegar token de Meta Business.
            for ch in ("​", "‌", "‍", " ", "﻿", " ", " "):
                valor = valor.replace(ch, "")
            # Para campos que van como HTTP header (tokens), forzar ASCII
            if clave in {"META_ACCESS_TOKEN", "META_CAPI_TOKEN",
                         "SHOPIFY_ADMIN_TOKEN", "SHOPIFY_CLIENT_SECRET",
                         "ANTHROPIC_API_KEY"}:
                try:
                    valor.encode("ascii")
                except UnicodeEncodeError:
                    # Filtrar a solo ASCII printable
                    valor = "".join(c for c in valor if 32 <= ord(c) < 127)
                    logger.warning(f"[config] {clave} tenía caracteres no-ASCII — filtrados")
            if valor or clave in _PERMITE_VACIO:
                # Pasamos contexto de usuario para que el historial (#48) sepa quién cambió qué.
                await set_config_value(
                    clave, valor,
                    agent_id=agent_id,
                    usuario_id=user.get("id"),
                    usuario_email=user.get("email", ""),
                )
                os.environ[clave] = valor   # actualizar en tiempo real
                saved.append(clave)

    # Si se actualizó META_CATALOG_ID o META_ACCESS_TOKEN, invalidar el
    # cache del catálogo y forzar recarga inmediata desde Meta. Evita que
    # el cliente tenga que esperar el TTL (5 min) o reiniciar el server.
    if "META_CATALOG_ID" in saved or "META_ACCESS_TOKEN" in saved:
        try:
            from agent import tools as _tools
            _tools._catalog_cache = ""
            _tools._catalog_cache_at = None
            _tools._fb_items.clear()
            _tools._sku_map.clear()
            asyncio.create_task(_tools._cargar_fb_catalog())
            # También recargar catálogo Shopify para reconstruir _sku_map
            asyncio.create_task(_tools.obtener_catalogo_shopify())
            logger.info(f"[config] {saved} actualizado(s) — cache invalidado, catálogo recargando")
        except Exception as e:
            logger.error(f"[config] error invalidando cache: {e}")

    return JSONResponse(content={"ok": True, "saved": saved})


# ── #48 — Historial + restore de configuración por agente ──────────────────────

# Claves consideradas sensibles — al exponer historial, ofuscamos sus valores
# para no leakear tokens completos en una UI accesible a múltiples usuarios.
# El valor real se preserva en BD intacto, listo para el restore.
_CLAVES_SENSIBLES = {
    "META_ACCESS_TOKEN", "META_CAPI_TOKEN", "META_VERIFY_TOKEN",
    "SHOPIFY_ADMIN_TOKEN", "SHOPIFY_CLIENT_SECRET", "SHOPIFY_WEBHOOK_SECRET",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
}


def _ofuscar_secreto(v: str) -> str:
    """Muestra solo los últimos 4 caracteres. Vacío → '(vacío)'."""
    if not v:
        return "(vacío)"
    if len(v) <= 8:
        return "•" * len(v)
    return "•" * 8 + v[-4:]


@app.get("/inbox/api/config/historial")
async def inbox_historial_config(
    clave: str = "",
    limite: int = 100,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Lista cambios de configuración del más reciente al más viejo, opcionalmente
    filtrados por clave. Valores de claves sensibles vienen ofuscados (••••XXXX).
    """
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import obtener_historial_config
    entries = await obtener_historial_config(
        agent_id=agent_id,
        clave=clave or None,
        limite=max(1, min(limite, 500)),
    )
    # Ofuscar tokens en la respuesta
    for e in entries:
        if e["clave"] in _CLAVES_SENSIBLES:
            e["valor_antes_display"]   = _ofuscar_secreto(e["valor_antes"])
            e["valor_despues_display"] = _ofuscar_secreto(e["valor_despues"])
        else:
            e["valor_antes_display"]   = e["valor_antes"]
            e["valor_despues_display"] = e["valor_despues"]
        # Eliminar valores crudos para no leakearlos a la UI
        e.pop("valor_antes", None)
        e.pop("valor_despues", None)
    return JSONResponse(content={"historial": entries})


@app.post("/inbox/api/config/historial/{historial_id}/restore")
async def inbox_restore_config(
    historial_id: int,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Restaura el valor_antes de una entrada de historial. Crea un nuevo entry
    de tipo 'restore' para mantener trazabilidad — no se borra el historial."""
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    from agent.memory import restaurar_config_desde_historial
    res = await restaurar_config_desde_historial(
        historial_id=historial_id,
        agent_id=agent_id,
        usuario_id=user.get("id"),
        usuario_email=user.get("email", ""),
    )
    if not res["ok"]:
        return JSONResponse(status_code=404, content={"ok": False, "error": res["error"]})
    # Sincronizar os.environ + invalidar cache catálogo si aplica (mismo pattern
    # que /config/save, sin duplicar logica)
    clave = res["clave"]
    valor_restaurado = await get_config_value(clave, agent_id=agent_id) or ""
    os.environ[clave] = valor_restaurado
    if clave in ("META_CATALOG_ID", "META_ACCESS_TOKEN"):
        try:
            from agent import tools as _tools
            _tools._catalog_cache = ""
            _tools._catalog_cache_at = None
            _tools._fb_items.clear()
            _tools._sku_map.clear()
            asyncio.create_task(_tools._cargar_fb_catalog())
        except Exception as e:
            logger.error(f"[config-restore] error invalidando cache: {e}")
    logger.info(f"[config-restore] {clave} restaurado por {user.get('email')} (historial_id={historial_id})")
    return JSONResponse(content={"ok": True, "clave": clave})


@app.post("/inbox/api/config/test/{service}")
async def inbox_test_config(
    service: str,
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Prueba la conexión a Meta, Shopify o Anthropic con las credenciales proporcionadas."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    body = await request.json()

    async def _val(clave: str) -> str:
        v = (body.get(clave) or "").strip()
        if not v:
            v = await get_config_value(clave, agent_id=agent_id) or ""
        if not v and agent_id == 1:
            v = os.getenv(clave, "")
        # Sanitización para tokens (mismo motivo que en /config/save): caracteres
        # invisibles que se copian de Meta Business rompen httpx en headers.
        if clave in {"META_ACCESS_TOKEN", "META_CAPI_TOKEN", "SHOPIFY_ADMIN_TOKEN",
                     "SHOPIFY_CLIENT_SECRET", "ANTHROPIC_API_KEY"}:
            for ch in ("​", "‌", "‍", " ", "﻿", " ", " "):
                v = v.replace(ch, "")
            try:
                v.encode("ascii")
            except UnicodeEncodeError:
                v = "".join(c for c in v if 32 <= ord(c) < 127)
        return v

    try:
        if service == "meta":
            # El test viejo solo hacía GET /me (basic auth). Eso da OK aunque
            # falten scopes whatsapp_business_*. Equora reportó bug 13-jun:
            # "Probar conexión" decía Conectado pero envíos a /messages
            # fallaban con 400. Ahora validamos los 3 endpoints reales que
            # Voco usa: /me (auth), /{phone_id}? (lectura phone),
            # /{waba_id}/message_templates (scope mgmt).
            access_token = await _val("META_ACCESS_TOKEN")
            phone_id     = await _val("META_PHONE_NUMBER_ID")
            waba_id      = await _val("META_WABA_ID")
            if not access_token:
                return JSONResponse(content={"ok": False, "error": "Token de acceso no configurado"})
            warnings: list[str] = []
            ok_total = True
            nombre = ""
            async with httpx.AsyncClient(timeout=12) as cli:
                # 1) auth básica
                r1 = await cli.get(
                    "https://graph.facebook.com/v21.0/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if r1.status_code != 200:
                    err = r1.json().get("error", {}).get("message", f"HTTP {r1.status_code}")
                    return JSONResponse(content={"ok": False, "error": f"Token inválido: {err}"})
                nombre = r1.json().get("name") or r1.json().get("id") or "OK"
                # 2) scope whatsapp_business_messaging (para enviar mensajes)
                if phone_id:
                    r2 = await cli.get(
                        f"https://graph.facebook.com/v21.0/{phone_id}",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    if r2.status_code != 200:
                        ok_total = False
                        err = r2.json().get("error", {}).get("message", f"HTTP {r2.status_code}")
                        warnings.append(f"❌ Phone Number ID {phone_id} inaccesible: {err}. Falta scope 'whatsapp_business_messaging' o ID incorrecto.")
                # 3) scope whatsapp_business_management (para plantillas/webhooks)
                if waba_id:
                    r3 = await cli.get(
                        f"https://graph.facebook.com/v21.0/{waba_id}/message_templates?limit=1",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    if r3.status_code != 200:
                        ok_total = False
                        err = r3.json().get("error", {}).get("message", f"HTTP {r3.status_code}")
                        warnings.append(f"❌ WABA {waba_id} inaccesible: {err}. Falta scope 'whatsapp_business_management' o WABA ID incorrecto.")
            if ok_total:
                return JSONResponse(content={"ok": True, "msg": f"✅ Conectado · {nombre} · Phone + WABA + Templates OK"})
            return JSONResponse(content={
                "ok": False,
                "error": "Token responde a /me pero faltan scopes WhatsApp:\n\n" + "\n".join(warnings) +
                         "\n\nRegenera el token en developers.facebook.com → tu app → WhatsApp → API Setup con scopes whatsapp_business_messaging + whatsapp_business_management."
            })

        elif service == "shopify":
            # Test Admin API únicamente (#62 retiró Storefront).
            domain = (await _val("SHOPIFY_STORE")).replace("https://", "").replace("http://", "").rstrip("/")
            if not domain:
                return JSONResponse(content={"ok": False, "error": "Dominio Shopify no configurado"})
            admin_token = await _val("SHOPIFY_ADMIN_TOKEN")
            if not admin_token:
                return JSONResponse(content={"ok": False, "error": "Sin Admin token — completa OAuth con 'Instalar'"})
            from agent.shopify_admin import verificar_admin_token
            resultado = await verificar_admin_token(domain, admin_token)
            if resultado.get("ok"):
                msg = f"✅ Conectado · {resultado.get('shop_name', domain)}"
                if resultado.get("plan"):
                    msg += f" ({resultado['plan']})"
                return JSONResponse(content={"ok": True, "msg": msg, "tipo": "admin"})
            return JSONResponse(content={"ok": False, "error": resultado.get("error", "Error con Admin API")})

        elif service == "anthropic":
            api_key = await _val("ANTHROPIC_API_KEY")
            if not api_key:
                return JSONResponse(content={"ok": False, "error": "API Key no configurada"})
            async with httpx.AsyncClient(timeout=20) as cli:
                r = await cli.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5", "max_tokens": 5,
                          "messages": [{"role": "user", "content": "hi"}]},
                )
            if r.status_code == 200:
                return JSONResponse(content={"ok": True, "msg": "✅ API key válida · Conexión exitosa"})
            if r.status_code == 401:
                return JSONResponse(content={"ok": False, "error": "API key inválida o revocada"})
            return JSONResponse(content={"ok": False, "error": f"Error {r.status_code}"})

    except Exception as e:
        return JSONResponse(content={"ok": False, "error": str(e)[:120]})

    return JSONResponse(content={"ok": False, "error": "Servicio no reconocido"})


# ══════════════════════════════════════════════════════════════════════════════
# #55 — OAuth Shopify (modelo Jelou/99Envíos)
# ══════════════════════════════════════════════════════════════════════════════
# Flujo OAuth Authorization Code Grant de Shopify:
#   1. Cliente da Client ID + Client Secret + dominio en Voco
#   2. Click 'Conectar con Shopify' → /oauth/shopify/start genera state + URL
#   3. Browser redirige al cliente a Shopify Admin para autorizar
#   4. Shopify redirige a /oauth/shopify/callback con code+shop+hmac+state
#   5. Voco verifica HMAC + state, intercambia code por access_token
#   6. Guarda SHOPIFY_ADMIN_TOKEN en config + redirige al panel
#
# Docs oficiales:
# https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/authorization-code-grant

# Scopes que Voco necesita. Si se agregan features, agregarlos acá y los
# clientes deben re-autorizar para recibir los nuevos permisos.
SHOPIFY_OAUTH_SCOPES = ",".join([
    # Catálogo (reemplaza Storefront API)
    "read_products",
    "write_products",
    "read_inventory",
    "write_inventory",
    # Pedidos (webhooks + confirmaciones)
    "read_orders",
    # Carrito (reemplaza permalinks /cart/c/)
    "write_draft_orders",
    # Cupones post-venta (feature #43)
    "write_discounts",
])

# State tracking en memoria (anti-CSRF). TTL 10 min.
# { state_token: {"agent_id": int, "shop": str, "user_id": int, "at": float} }
_shopify_oauth_states: dict[str, dict] = {}
_SHOPIFY_OAUTH_STATE_TTL = 600  # 10 min


def _cleanup_shopify_states() -> None:
    """Limpia states expirados (>10 min). Llamado en cada start/callback."""
    ahora = time.time()
    expirados = [s for s, info in _shopify_oauth_states.items()
                 if ahora - info.get("at", 0) > _SHOPIFY_OAUTH_STATE_TTL]
    for s in expirados:
        _shopify_oauth_states.pop(s, None)


def _shopify_oauth_verify_hmac(query_params: dict, client_secret: str) -> bool:
    """Verifica HMAC del callback de Shopify para asegurar que viene de Shopify
    y no fue tampered. Algoritmo según docs:
      1. Quitar 'hmac' y 'signature' del query
      2. Ordenar parámetros alfabéticamente
      3. Concatenar key=value separados por &
      4. Calcular HMAC-SHA256 con client_secret como key
      5. Comparar con el hmac que llegó
    """
    recibido = query_params.get("hmac", "")
    if not recibido or not client_secret:
        return False
    filtrado = {k: v for k, v in query_params.items() if k not in ("hmac", "signature")}
    mensaje = "&".join(f"{k}={v}" for k, v in sorted(filtrado.items()))
    esperado = hmac.new(
        client_secret.encode("utf-8"),
        mensaje.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(esperado, recibido)


def _shopify_callback_url(request: Request) -> str:
    """Construye la URL de callback OAuth a partir del host actual.
    Multi-tenant: funciona en Railway, dev local y futuro dominio propio."""
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://") and "localhost" not in base:
        base = base.replace("http://", "https://", 1)
    return f"{base}/oauth/shopify/callback"


@app.post("/inbox/api/oauth/shopify/start")
async def api_shopify_oauth_start(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Inicia el flujo OAuth. Cliente debe haber guardado SHOPIFY_STORE +
    SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET en Configuración antes.

    Response: {ok, auth_url} — el frontend hace window.location = auth_url
    """
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")

    try:
        body = await request.json()
    except Exception:
        body = {}

    # Permitir override desde el body (para 'probar antes de guardar') o leer del config
    from agent.memory import get_config_value
    # Para v1 usamos agent_id=1; con #45 (selector) el frontend podría pasarlo
    agent_id = int(body.get("agent_id") or 1)

    store = (body.get("store") or "").strip() or (
        await get_config_value("SHOPIFY_STORE", agent_id)
        or os.getenv("SHOPIFY_STORE", "")
    )
    client_id = (body.get("client_id") or "").strip() or (
        await get_config_value("SHOPIFY_CLIENT_ID", agent_id) or ""
    )
    client_secret = (body.get("client_secret") or "").strip() or (
        await get_config_value("SHOPIFY_CLIENT_SECRET", agent_id) or ""
    )
    store = store.replace("https://", "").replace("http://", "").rstrip("/")

    if not store or not client_id or not client_secret:
        return JSONResponse(status_code=400, content={
            "ok": False,
            "error": "Configura primero: Dominio + Client ID + Client Secret (guardar) antes de conectar.",
        })
    if not store.endswith(".myshopify.com"):
        return JSONResponse(status_code=400, content={
            "ok": False,
            "error": f"El dominio debe terminar en .myshopify.com (recibido: {store}). Usa el dominio interno, no el personalizado.",
        })

    # Generar state token aleatorio + guardar contexto
    _cleanup_shopify_states()
    state = secrets.token_urlsafe(32)
    # panel_path = la URL del panel del agente desde donde se inició el OAuth.
    # El callback la usa para redirigir de vuelta al panel correcto (no al
    # selector raíz /inbox). Validamos que empiece con / para evitar open
    # redirect a dominios externos.
    panel_path = (body.get("panel_path") or "").strip()
    if not panel_path.startswith("/"):
        panel_path = "/inbox"
    _shopify_oauth_states[state] = {
        "agent_id":      agent_id,
        "shop":          store,
        "client_id":     client_id,
        "client_secret": client_secret,
        "user_id":       user.get("id"),
        "panel_path":    panel_path,
        "at":            time.time(),
    }

    callback = _shopify_callback_url(request)
    auth_url = (
        f"https://{store}/admin/oauth/authorize"
        f"?client_id={client_id}"
        f"&scope={SHOPIFY_OAUTH_SCOPES}"
        f"&redirect_uri={callback}"
        f"&state={state}"
    )
    logger.info(f"[shopify-oauth] start agent={agent_id} shop={store} (callback={callback})")
    return JSONResponse(content={"ok": True, "auth_url": auth_url, "callback_url": callback})


@app.get("/oauth/shopify/callback")
async def shopify_oauth_callback(request: Request):
    """Callback OAuth de Shopify. NO requiere auth de Voco — viene del browser
    del cliente redirigido desde Shopify. Validamos HMAC + state para anti-CSRF.

    Recibe: ?code=X&shop=Y&hmac=Z&state=W&timestamp=N
    Devuelve: redirect al panel con ?shopify_oauth=ok|error&msg=...
    """
    qp = dict(request.query_params)
    code  = qp.get("code", "")
    shop  = qp.get("shop", "")
    state = qp.get("state", "")
    hmac_recibido = qp.get("hmac", "")

    # panel_path se resuelve desde el state cuando esté disponible (más abajo).
    # Si no, fallback a /inbox (selector raíz).
    panel_path_default = "/inbox"

    def _redirect_panel(estado: str, mensaje: str = "", path: str | None = None) -> RedirectResponse:
        import urllib.parse as _up
        msg = _up.quote(mensaje[:200])
        target = path or panel_path_default
        return RedirectResponse(
            f"{target}#configuracion?shopify_oauth={estado}&msg={msg}",
            status_code=302,
        )

    if not code or not shop or not state or not hmac_recibido:
        return _redirect_panel("error", "Parámetros incompletos del callback")

    # Recuperar contexto del state (anti-CSRF)
    _cleanup_shopify_states()
    info = _shopify_oauth_states.pop(state, None)
    if not info:
        return _redirect_panel("error", "State inválido o expirado. Reintenta el OAuth desde el panel.")

    # Shop mismatch tolerante: cuando una tienda tiene múltiples dominios
    # .myshopify.com (ej. equora-6 público + kbetje-6y interno canónico),
    # Shopify SIEMPRE devuelve el canónico interno en el callback aunque
    # el user haya iniciado con el alias público. Aceptamos el shop que
    # Shopify devuelve si es .myshopify.com válido — la seguridad la da
    # el HMAC (firmado con el client_secret de ESA app), no el dominio.
    if info["shop"] != shop:
        if not shop.endswith(".myshopify.com"):
            return _redirect_panel("error", f"Dominio inválido recibido de Shopify: {shop}")
        logger.info(
            f"[shopify-oauth] dominio canónico distinto al iniciado: "
            f"iniciado={info['shop']} canónico={shop} — adoptando canónico"
        )
    # Usar el panel_path del state para que el toast aterrice en el panel
    # del agente correcto (no en el selector raíz).
    panel_path_default = info.get("panel_path") or "/inbox"

    # Verificar HMAC (firma del client_secret)
    if not _shopify_oauth_verify_hmac(qp, info["client_secret"]):
        logger.warning(f"[shopify-oauth] HMAC inválido para shop={shop}")
        return _redirect_panel("error", "Firma HMAC inválida. Verifica el Client Secret en Configuración.")

    # Intercambiar code por access_token
    try:
        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.post(
                f"https://{shop}/admin/oauth/access_token",
                json={
                    "client_id":     info["client_id"],
                    "client_secret": info["client_secret"],
                    "code":          code,
                },
            )
        if r.status_code != 200:
            logger.error(f"[shopify-oauth] intercambio code→token HTTP {r.status_code}: {r.text[:300]}")
            return _redirect_panel("error", f"Shopify rechazó el code (HTTP {r.status_code}). Reintenta.")
        access_token = (r.json() or {}).get("access_token", "")
        if not access_token:
            return _redirect_panel("error", "Shopify no devolvió access_token. Reintenta.")
    except Exception as e:
        logger.error(f"[shopify-oauth] error intercambiando code: {e}")
        return _redirect_panel("error", f"Error de red: {e!s}")

    # Guardar el token + dominio en config del agente
    try:
        from agent.memory import set_config_value
        agent_id = info["agent_id"]
        await set_config_value("SHOPIFY_STORE",       shop,         agent_id)
        await set_config_value("SHOPIFY_ADMIN_TOKEN", access_token, agent_id)
        logger.info(f"[shopify-oauth] ✅ token guardado para shop={shop} agent={agent_id}")
    except Exception as e:
        logger.error(f"[shopify-oauth] error guardando token: {e}")
        return _redirect_panel("error", f"OAuth OK pero falló al guardar: {e!s}")

    # Auto-registrar webhooks de Voco (orders/create, orders/paid, etc.).
    # Best-effort: si falla, el cliente igual queda conectado y puede reintentar
    # desde el panel — no abortamos el OAuth por esto.
    try:
        from agent.shopify_admin import sincronizar_webhooks_voco
        callback_webhook = f"{str(request.base_url).rstrip('/').replace('http://', 'https://', 1)}/shopify-webhook"
        res = await sincronizar_webhooks_voco(shop, access_token, callback_webhook)
        creados = len(res.get("creados", []))
        existentes = len(res.get("conservados", []))
        fallidos = len(res.get("fallidos", []))
        logger.info(f"[shopify-oauth] webhooks auto-registrados: {creados} nuevos, {existentes} existentes, {fallidos} fallidos")
        if fallidos:
            logger.warning(f"[shopify-oauth] webhooks fallidos: {res.get('fallidos')}")
    except Exception as e:
        logger.error(f"[shopify-oauth] no se pudieron auto-registrar webhooks (no es bloqueante): {e}")

    return _redirect_panel("ok", f"Conectado con {shop}. Tu agente ya tiene acceso a tu catálogo y pedidos.")


# ══════════════════════════════════════════════════════════════════════════════
# #54 — Sincronización programática de webhooks Shopify
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/inbox/api/integraciones/shopify/sincronizar-webhooks")
async def api_shopify_sincronizar_webhooks(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Registra (o actualiza) los webhooks que Voco necesita en la tienda
    Shopify del agente, vía Admin API. Reemplaza el copy-paste manual del
    cliente en Shopify Admin → Notifications → Webhooks.

    Body opcional:
        {"store": "...", "admin_token": "..."}
    Si no se pasan, los lee del config_value/env del agente activo.

    Response:
        {ok, creados, conservados, recreados, fallidos, callback_url, error?}
    """
    user = await _obtener_sesion_usuario(voco_session or inbox_session or token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Resolver desde 3 fuentes (en orden): body explícito > config_value del
    # agente (BD, donde OAuth lo guarda) > env var (legacy). Esto soporta:
    # · Cliente probando sin guardar primero (body)
    # · Cliente ya conectado vía OAuth (config_value)
    # · Setup viejo con env vars de Railway (legacy)
    from agent.memory import get_config_value
    agent_id_int = int(body.get("agent_id") or 1)
    store = (body.get("store") or "").strip()
    if not store:
        store = (await get_config_value("SHOPIFY_STORE", agent_id_int)) or os.getenv("SHOPIFY_STORE", "")
    admin_token = (body.get("admin_token") or "").strip()
    if not admin_token:
        admin_token = (await get_config_value("SHOPIFY_ADMIN_TOKEN", agent_id_int)) or os.getenv("SHOPIFY_ADMIN_TOKEN", "")
    store = store.replace("https://", "").replace("http://", "").rstrip("/")
    if not store or not admin_token:
        return JSONResponse(status_code=400, content={
            "ok": False,
            "error": "Falta dominio Shopify o Admin API token. Conéctate primero con 'Conectar con Shopify' o configura el token en modo avanzado."
        })

    # Construir el callback URL desde el host de la request (multi-tenant ready
    # — funciona con cualquier dominio donde esté desplegado Voco)
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://") and "localhost" not in base:
        # Shopify exige HTTPS para webhooks — forzar si no estamos en local
        base = base.replace("http://", "https://", 1)
    callback_url = f"{base}/shopify-webhook"

    from agent.shopify_admin import sincronizar_webhooks_voco
    res = await sincronizar_webhooks_voco(store, admin_token, callback_url)
    res["callback_url"] = callback_url
    if res.get("ok"):
        logger.info(
            f"[shopify-admin] webhooks sync para {store}: "
            f"+{len(res.get('creados', []))} ={len(res.get('conservados', []))} "
            f"~{len(res.get('recreados', []))} !{len(res.get('fallidos', []))}"
        )
    return JSONResponse(content=res)


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT EDITOR — leer, guardar y mejorar el system prompt con IA
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/inbox/api/prompt")
async def inbox_get_prompt(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Devuelve el prompt actual (BD → archivo) y las variables del negocio."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    import yaml as _yaml

    # Prompt: BD primero, luego archivo, luego brain.py (fallback final para agentes existentes)
    db_prompt = await get_config_value("SYSTEM_PROMPT", agent_id)
    if db_prompt:
        prompt  = db_prompt
        fuente  = "db"
    else:
        try:
            with open("config/prompts.yaml", "r", encoding="utf-8") as f:
                cfg = _yaml.safe_load(f) or {}
            prompt = cfg.get("system_prompt", "")
        except FileNotFoundError:
            prompt = ""
        fuente = "file"

    # Si sigue vacío, intentar cargar desde brain.py (captura prompts.yaml con cache y fallback)
    if not prompt:
        try:
            from agent.brain import cargar_system_prompt as _csp
            raw = await _csp(agent_id)
            # Solo usar si no es el prompt genérico por defecto
            if raw and raw != "Eres un asistente virtual. Responde en español.":
                prompt = raw
                fuente = "brain"
        except Exception:
            pass

    # Variables del negocio (JSON guardado en BD)
    vars_json = await get_config_value("BUSINESS_VARS", agent_id)
    try:
        business_vars = json.loads(vars_json) if vars_json else {}
    except Exception:
        business_vars = {}

    # Tipo de negocio
    business_type = await get_config_value("BUSINESS_TYPE", agent_id) or "productos"

    # Módulos activos
    modules_json = await get_config_value("ACTIVE_MODULES", agent_id)
    try:
        active_modules = json.loads(modules_json) if modules_json else {}
    except Exception:
        active_modules = {}

    return JSONResponse(content={
        "prompt":         prompt,
        "business_vars":  business_vars,
        "fuente":         fuente,
        "business_type":  business_type,
        "active_modules": active_modules,
    })


@app.post("/inbox/api/prompt/save")
async def inbox_save_prompt(
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Guarda el prompt y las variables del negocio en la BD."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    body = await request.json()
    prompt        = (body.get("prompt") or "").strip()
    business_vars = body.get("business_vars") or {}
    business_type = (body.get("business_type") or "").strip()
    active_modules = body.get("active_modules")

    if prompt:
        await set_config_value("SYSTEM_PROMPT", prompt, agent_id)
    if isinstance(business_vars, dict):
        await set_config_value("BUSINESS_VARS", json.dumps(business_vars, ensure_ascii=False), agent_id)
    if business_type:
        await set_config_value("BUSINESS_TYPE", business_type, agent_id)
    if isinstance(active_modules, dict):
        await set_config_value("ACTIVE_MODULES", json.dumps(active_modules), agent_id)

    return JSONResponse(content={"ok": True})


@app.post("/inbox/api/prompt/improve")
async def inbox_improve_prompt(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """
    Recibe el prompt actual + una instrucción del usuario en lenguaje natural
    y devuelve una versión mejorada generada por Claude.
    """
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    body        = await request.json()
    prompt      = (body.get("prompt") or "").strip()
    instruccion = (body.get("instruccion") or "").strip()
    vars_dict   = body.get("business_vars") or {}
    imagenes    = body.get("imagenes") or []   # [{media_type, data}]

    if not prompt:
        return JSONResponse(content={"ok": False, "error": "Prompt vacío"})
    if not instruccion:
        return JSONResponse(content={"ok": False, "error": "Escribe qué quieres mejorar"})

    # Contexto de variables para que Claude las conserve
    vars_context = ""
    if vars_dict:
        vars_lines = "\n".join(f"  {{{k}}} = {v}" for k, v in vars_dict.items())
        vars_context = f"\n\nVariables del negocio definidas (CONSERVARLAS intactas en el prompt):\n{vars_lines}"

    system_meta = (
        "Eres un experto en diseño de system prompts para agentes de IA conversacionales "
        "que operan por WhatsApp. Tu tarea es mejorar el prompt de acuerdo a la instrucción "
        "del usuario.\n\n"
        "REGLAS ABSOLUTAS:\n"
        "- Conserva TODA la información existente; solo mejora, agrega o ajusta lo indicado\n"
        "- Conserva todas las variables {EN_MAYUSCULAS} exactamente como aparecen\n"
        "- Responde ÚNICAMENTE con el prompt mejorado — sin explicaciones, sin markdown extra, "
        "sin texto antes o después\n"
        "- Mantén el idioma español\n"
        "- El prompt debe ser claro, específico y directamente accionable"
    )

    texto_usuario = (
        f"PROMPT ACTUAL:\n{prompt}"
        f"{vars_context}\n\n"
        f"INSTRUCCIÓN DEL USUARIO: {instruccion}"
    )

    # Construir content blocks — texto + imágenes opcionales
    content_blocks: list = []
    for img in imagenes[:5]:   # máximo 5 imágenes
        media_type = img.get("media_type", "image/jpeg")
        data       = img.get("data", "")
        if not data:
            continue
        content_blocks.append({
            "type": "image",
            "source": {
                "type":       "base64",
                "media_type": media_type,
                "data":       data,
            }
        })
    content_blocks.append({"type": "text", "text": texto_usuario})

    from anthropic import AsyncAnthropic as _Anthropic
    _client = _Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    # Usar modelo con visión si hay imágenes; haiku no soporta visión en todas las versiones
    modelo = os.getenv("AI_MODEL", "claude-haiku-4-5")
    if imagenes:
        modelo = "claude-sonnet-4-5"   # garantiza soporte de visión
    try:
        resp = await _client.messages.create(
            model=modelo,
            max_tokens=4096,
            system=system_meta,
            messages=[{"role": "user", "content": content_blocks}],
        )
        improved = resp.content[0].text.strip()
        return JSONResponse(content={"ok": True, "improved_prompt": improved})
    except Exception as e:
        logger.error(f"Error mejorando prompt: {e}")
        return JSONResponse(content={"ok": False, "error": str(e)[:200]})


# ══════════════════════════════════════════════════════════════════════════════
# CHAT DE PRUEBA — simula conversación con el agente desde el panel
# ══════════════════════════════════════════════════════════════════════════════

def _test_phone(agent_id: int) -> str:
    return f"__test_inbox_{agent_id}__"


@app.post("/inbox/api/chat/test")
async def inbox_chat_test(
    request: Request,
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Envía un mensaje al agente y devuelve su respuesta (sin WhatsApp real)."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    body    = await request.json()
    mensaje = (body.get("mensaje") or "").strip()
    if not mensaje:
        return JSONResponse(status_code=400, content={"error": "Mensaje vacío"})

    tel = _test_phone(agent_id)
    historial = await obtener_historial(tel)
    try:
        respuesta = await generar_respuesta(mensaje, historial, telefono=None, contexto_campana=None, agent_id=agent_id)
    except Exception as e:
        logger.error(f"Error en chat de prueba: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)[:200]})

    await guardar_mensaje(tel, "user", mensaje, agent_id=agent_id)
    await guardar_mensaje(tel, "assistant", respuesta, agent_id=agent_id)

    return JSONResponse(content={"ok": True, "respuesta": respuesta})


@app.get("/inbox/api/chat/test/history")
async def inbox_chat_test_history(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Devuelve el historial de la conversación de prueba."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    mensajes = await obtener_historial_con_timestamps(_test_phone(agent_id), 100, agent_id=agent_id)
    return JSONResponse(content={"mensajes": mensajes})


@app.delete("/inbox/api/chat/test/clear")
async def inbox_chat_test_clear(
    agent_id: int = 1,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Borra el historial de la conversación de prueba."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")

    await limpiar_historial(_test_phone(agent_id))
    return JSONResponse(content={"ok": True})


@app.post("/inbox/plantillas/subir-header")
async def inbox_subir_header_media(
    file: UploadFile = File(...),
    file_type: str = Form(...),
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
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
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
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
    voco_session: str = Cookie(default=""),
):
    """Crea una nueva plantilla en Meta y la envía a revisión.
    Body JSON: { name, category, language, header_text?, body, footer?, buttons? }
    """
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
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
    voco_session: str = Cookie(default=""),
):
    """Lista todos los borradores de plantillas guardados localmente."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
        raise HTTPException(status_code=401, detail="No autorizado")
    borradores = await obtener_borradores_plantillas()
    return JSONResponse(content={"borradores": borradores})


@app.post("/inbox/plantillas/borrador")
async def inbox_plantillas_borrador_guardar(
    request: Request,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Guarda (crea o actualiza) un borrador de plantilla localmente.
    Body JSON: los mismos campos del formulario de creación.
    Si ya existe un borrador con el mismo nombre, lo sobreescribe.
    """
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
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
    voco_session: str = Cookie(default=""),
):
    """Elimina un borrador local por ID."""
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
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
    voco_session: str = Cookie(default=""),
):
    """Edita una plantilla existente en Meta (solo se pueden cambiar los componentes).
    Meta devuelve la plantilla a estado PENDING tras la edición.
    Body JSON: { template_id, header_type?, header_text?, header_handle?,
                 body, footer?, buttons? }
    """
    if not await _obtener_sesion_usuario(voco_session or inbox_session or token):
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


# ── Panel por slug (ruta comodín — DEBE ser la última ruta de /inbox/*) ────
# FastAPI evalúa rutas en orden de definición: al estar aquí al final, las rutas
# específicas (/inbox/api/*, /inbox/broadcast/*, etc.) ya fueron registradas primero.

@app.get("/inbox/{slug}", response_class=HTMLResponse)
async def inbox_agente_por_slug(
    slug: str,
    token: str = "",
    inbox_session: str = Cookie(default=""),
    voco_session: str = Cookie(default=""),
):
    """Panel de inbox para un agente específico por su slug (ej: /inbox/equora)."""
    effective_token = voco_session or inbox_session or token
    current_user = await _obtener_sesion_usuario(effective_token)

    if not current_user:
        return RedirectResponse("/inbox/login", status_code=302)

    from agent.memory import obtener_agente_por_slug
    agente = await obtener_agente_por_slug(slug)
    if not agente:
        raise HTTPException(status_code=404, detail=f"Agente '{slug}' no encontrado")

    # Verificar ownership: admin ve cualquier agente; usuario solo los suyos
    if current_user.get("rol") != "admin":
        owner = agente.get("owner_id")
        if owner != current_user["id"]:
            raise HTTPException(status_code=403, detail="No tienes acceso a este agente")

    response = HTMLResponse(content=obtener_inbox_html(agente, user=current_user))
    if token and _verificar_admin(token):
        response.set_cookie(
            INBOX_COOKIE, ADMIN_TOKEN,
            httponly=True, max_age=COOKIE_MAX_AGE, samesite="lax"
        )
    return response


SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
# Cache de deduplicación: evita procesar el mismo webhook de Shopify más de una vez
# Shopify reintenta hasta 19 veces si no recibe 200 — guardamos los procesados por 10 min
_shopify_dedup: dict[str, float] = {}
_SHOPIFY_DEDUP_TTL = 600  # segundos

ADMIN_WHATSAPP_NUMBERS = [
    n.strip() for n in os.getenv("ADMIN_WHATSAPP_NUMBERS", "").split(",") if n.strip()
]


# ══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE ALERTAS — Tracking de fallas del catálogo nativo de WhatsApp
# ══════════════════════════════════════════════════════════════════════════════
# Cuando el catálogo nativo de WhatsApp falla (Meta API caída, token expirado,
# catalog_id inválido, etc.) y caemos al fallback web, registramos la falla.
# Si se acumulan en una ventana corta, alertamos al admin por WhatsApp.

from collections import deque

# Buffer en memoria de las últimas 100 fallas del catálogo nativo
_catalogo_fallas: deque = deque(maxlen=100)
# Timestamp de la última alerta enviada al admin — cooldown 30 min
_ultima_alerta_catalogo_at: float = 0.0
_CATALOGO_ALERTA_COOLDOWN_SEG = 30 * 60  # 30 minutos entre alertas


async def _registrar_falla_catalogo(
    tipo: str, telefono_cliente: str, motivo: str, agent_id: int = 1
) -> None:
    """Registra una falla del catálogo nativo y alerta al admin si aplica.
    `tipo` puede ser: product_list, catalog_message, single_product, etc."""
    global _ultima_alerta_catalogo_at
    ahora = time.time()
    _catalogo_fallas.append({
        "tipo":     tipo,
        "telefono": telefono_cliente,
        "motivo":   motivo[:300],
        "agent_id": agent_id,
        "at":       datetime.utcnow().isoformat(),
    })
    logger.warning(f"[catalogo-falla] {tipo} → {telefono_cliente}: {motivo[:150]}")

    # Alerta al admin: solo si pasó el cooldown (evita spam) Y hay admins
    if not ADMIN_WHATSAPP_NUMBERS:
        return
    if ahora - _ultima_alerta_catalogo_at < _CATALOGO_ALERTA_COOLDOWN_SEG:
        return
    _ultima_alerta_catalogo_at = ahora

    # Contar fallas en la última hora para dar contexto
    hace_una_hora = datetime.utcnow() - timedelta(hours=1)
    fallas_recientes = sum(
        1 for f in _catalogo_fallas
        if datetime.fromisoformat(f["at"]) > hace_una_hora
    )

    mensaje_alerta = (
        f"⚠️ *Alerta Voco — Catálogo WhatsApp*\n\n"
        f"El catálogo nativo de WhatsApp falló y se está usando el fallback web.\n\n"
        f"*Último error:* {tipo}\n"
        f"*Motivo:* {motivo[:200]}\n"
        f"*Cliente afectado:* +{telefono_cliente}\n"
        f"*Fallas en la última hora:* {fallas_recientes}\n\n"
        f"Posibles causas: token Meta expirado, catálogo no sincronizado, "
        f"Meta API caída, o un SKU específico no existe en Facebook Catalog.\n\n"
        f"Próxima alerta en {_CATALOGO_ALERTA_COOLDOWN_SEG // 60} min si sigue fallando."
    )

    _prov = await _get_meta_para_agente({"id": agent_id})
    cliente_digits = "".join(filter(str.isdigit, telefono_cliente))
    for admin in ADMIN_WHATSAPP_NUMBERS:
        admin_digits = "".join(filter(str.isdigit, admin))
        if admin_digits == cliente_digits or admin_digits.endswith(cliente_digits[-10:]):
            continue
        try:
            await _prov.enviar_mensaje(admin, mensaje_alerta)
            logger.info(f"[alerta-catalogo] Notificado al admin {admin}")
        except Exception as e:
            logger.error(f"[alerta-catalogo] Error notificando a {admin}: {e}")


async def _notificar_escalacion(telefono_cliente: str, datos: dict, agent_id: int = 1):
    """Crea un ticket en BD, pausa el bot y notifica por WhatsApp a los asesores internos.
    NUNCA envía el aviso al número del propio cliente."""
    motivo        = datos.get("motivo", "sin especificar")
    contexto      = datos.get("contexto", "")
    urgencia      = datos.get("urgencia", "normal")
    cliente_nombre = datos.get("nombre_cliente", "")

    # ── 1. Crear ticket en BD y notificar via SSE ─────────────────────────────
    ticket = None
    try:
        ticket = await crear_ticket(
            agent_id=agent_id,
            telefono_cliente=telefono_cliente,
            nombre_cliente=cliente_nombre,
            motivo=motivo,
            urgencia=urgencia,
            contexto=contexto,
        )
        # Auditoría — autor = nombre del agente del tenant (no hardcode "Andrea Bot")
        try:
            from agent.memory import obtener_agente as _obtener_ag
            _ag = await _obtener_ag(agent_id)
            _bot_label = ((_ag or {}).get("agent_name") or "Bot") + " (IA)"
        except Exception:
            _bot_label = "Bot (IA)"
        await registrar_evento_ticket(ticket["id"], "creado", _bot_label,
                                      f"Motivo: {motivo} | Urgencia: {urgencia}")
        # Auto-asignación round-robin (si está habilitada)
        try:
            auto_asig = await get_config_value("AUTO_ASIGNAR", agent_id)
            if auto_asig == "1":
                agente_id_rr = await obtener_siguiente_agente_roundrobin(agent_id)
                if agente_id_rr:
                    ticket = await tomar_ticket(ticket["id"], agente_id_rr)
                    if ticket:
                        await registrar_evento_ticket(ticket["id"], "tomado",
                            "Sistema (auto)", f"Asignado automáticamente a {ticket.get('agente_nombre','')}")
        except Exception as e_rr:
            logger.warning(f"Auto-asignación falló: {e_rr}")

        _push_evento_ticket(agent_id, "ticket_nuevo", ticket)
        logger.info(f"Ticket creado para {telefono_cliente} — motivo: {motivo}")
    except Exception as e:
        logger.error(f"Error creando ticket de escalación: {e}")

    # ── 2. Pausar el bot para esta conversación ────────────────────────────────
    try:
        await set_modo_humano(telefono_cliente, True, agent_id=agent_id)
        logger.info(f"Bot pausado para {telefono_cliente} por escalación")
    except Exception as e:
        logger.error(f"Error pausando bot: {e}")

    # ── 3. Notificar por WhatsApp a los asesores que hayan opt-in ──────────────
    # Estrategia de resolución de receptores (#52):
    #   1. Usuarios internos del agente con notif_escalaciones_wa=True (BD).
    #   2. Si no hay nadie opt-in en BD → fallback a ADMIN_WHATSAPP_NUMBERS
    #      (env var legacy). Mantiene compatibilidad con setup actual de Railway.
    #   3. Si ambos están vacíos → solo se queda en el panel (sin notif WA).
    from agent.memory import obtener_receptores_escalacion_wa, obtener_agente
    receptores: list[str] = []
    try:
        receptores = await obtener_receptores_escalacion_wa(agent_id)
    except Exception as e:
        logger.error(f"[escalacion] error leyendo receptores de BD: {e}")
    origen_receptores = "BD"
    if not receptores:
        receptores = ADMIN_WHATSAPP_NUMBERS
        origen_receptores = "env(legacy)"

    if not receptores:
        logger.info(
            f"[escalacion] sin receptores configurados (BD vacía + ADMIN_WHATSAPP_NUMBERS "
            f"vacía) para agent={agent_id} — solo notificación en panel"
        )
        return

    # Nombre del negocio (para el mensaje, en lugar del hardcode "Equora")
    nombre_negocio = ""
    try:
        agente_info = await obtener_agente(agent_id)
        if agente_info:
            nombre_negocio = agente_info.get("name") or ""
    except Exception:
        pass
    referencia_panel = f"panel de {nombre_negocio}" if nombre_negocio else "panel de Voco"

    cliente_digits = "".join(filter(str.isdigit, telefono_cliente))
    mensaje = (
        f"🚨 *Escalación de conversación*\n\n"
        f"*Motivo:* {motivo}\n"
        f"*Urgencia:* {urgencia}\n"
        f"*Cliente:* {cliente_nombre or 'desconocido'}\n"
        f"*WhatsApp cliente:* +{telefono_cliente}\n\n"
        f"*Contexto:*\n{contexto}\n\n"
        f"Entra al {referencia_panel} para tomar la conversación."
    )

    logger.info(
        f"[escalacion] notificando a {len(receptores)} receptor(es) "
        f"(origen={origen_receptores}) para agent={agent_id}"
    )
    _prov = await _get_meta_para_agente({"id": agent_id})
    for admin in receptores:
        admin_digits = "".join(filter(str.isdigit, admin))
        # Filtro de seguridad: no notificarse a uno mismo si el cliente es el
        # mismo número del receptor (caso típico al hacer pruebas con propio WA).
        if admin_digits == cliente_digits or admin_digits.endswith(cliente_digits[-10:]):
            logger.warning(f"Escalación omitida para {admin}: es el mismo número del cliente")
            continue
        try:
            await _prov.enviar_mensaje(admin, mensaje)
            logger.info(f"Escalación notificada al asesor {admin}")
        except Exception as e:
            logger.error(f"Error notificando escalación a {admin}: {e}")


async def _verificar_hmac_shopify(body: bytes, hmac_header: str, shop: str = "") -> bool:
    """Verifica el HMAC del webhook de Shopify.

    Webhooks registrados vía Admin API (OAuth) se firman con el Client Secret
    de la app — el mismo que el merchant pegó en Configuración. Voco intenta
    validar contra el client_secret de cada agente conocido hasta encontrar
    coincidencia. Fallback al SHOPIFY_WEBHOOK_SECRET legacy (env var) para
    setups antiguos manuales.
    """
    if not hmac_header:
        return False

    secrets_a_probar: list[str] = []

    # 1) Client Secret del agente conectado a este shop (post-OAuth).
    #    Multi-tenant: si hay varios agentes, recolectamos todos los
    #    client_secrets de quienes tengan ese shop configurado.
    try:
        from agent.memory import async_session, ConfigValue
        from sqlalchemy import select
        async with async_session() as s:
            # Buscar todos los agentes con SHOPIFY_CLIENT_SECRET configurado.
            # Si conocemos el shop, filtramos por SHOPIFY_STORE coincidente.
            stmt = select(ConfigValue).where(ConfigValue.clave == "SHOPIFY_CLIENT_SECRET")
            res = await s.execute(stmt)
            for cv in res.scalars().all():
                if cv.valor:
                    if shop:
                        # Verificar que el agente tenga este shop configurado
                        stmt2 = select(ConfigValue).where(
                            ConfigValue.agent_id == cv.agent_id,
                            ConfigValue.clave == "SHOPIFY_STORE",
                        )
                        store_cv = (await s.execute(stmt2)).scalar_one_or_none()
                        if store_cv and store_cv.valor and store_cv.valor.lower() == shop.lower():
                            secrets_a_probar.append(cv.valor)
                    else:
                        secrets_a_probar.append(cv.valor)
    except Exception as e:
        logger.warning(f"[hmac] no pude leer client_secrets de BD: {e}")

    # 2) Fallback legacy: env var SHOPIFY_WEBHOOK_SECRET (setups manuales viejos)
    if SHOPIFY_WEBHOOK_SECRET:
        secrets_a_probar.append(SHOPIFY_WEBHOOK_SECRET)

    if not secrets_a_probar:
        logger.warning("[hmac] sin secrets configurados — saltando verificación")
        return True

    for secret in secrets_a_probar:
        digest = base64.b64encode(
            hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
        ).decode()
        if hmac.compare_digest(digest, hmac_header):
            return True
    return False


# NOTA: antes había aquí una segunda definición de _normalizar_telefono que
# sobrescribía la versión inteligente del panel (línea ~5302) porque Python
# carga el módulo top-down. Resultado: webhooks de Shopify que traían el
# teléfono sin indicativo (ej: '3022888274') NO recibían el prefijo +57, y
# el mensaje "Tu pedido está listo" se enviaba al número sin código de país
# → no llegaba al cliente. La función inteligente añade '57' si detecta
# 10 dígitos empezando por '3' (caso real Lorena Camayo, 2026-06-16).


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
    shop_header = request.headers.get("X-Shopify-Shop-Domain", "")

    if not await _verificar_hmac_shopify(body, hmac_header, shop=shop_header):
        logger.error(f"HMAC inválido en shopify-webhook (topic={topic}, shop={shop_header})")
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

    # Guardar/actualizar cliente con los datos que llegaron en la orden.
    # Solo incrementamos pedidos_realizados cuando es orders/paid (pago confirmado).
    datos_cliente = _extraer_datos_cliente(payload)
    if any(datos_cliente.values()):
        try:
            await guardar_cliente(
                telefono, datos_cliente,
                incrementar_pedidos=(topic == "orders/paid")
            )
            logger.info(f"Cliente {telefono} guardado/actualizado desde Shopify ({topic})")
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
            # Fallback: construir desde el token con formato correcto de Shopify.
            # Usar SHOPIFY_STORE configurado (multi-tenant) en lugar de hardcoded.
            token = payload.get("token") or ""
            if token:
                # Resolver tienda multi-tenant: config_value primero, env legacy
                from agent.tools import _resolver_store as _rs
                tienda = await _rs()
                if tienda:
                    checkout_url = f"https://{tienda}/checkouts/cn/{token}/es"
        # Normalizar dominio: si el cliente configuró SHOPIFY_CUSTOM_DOMAIN
        # (con la ruta /checkouts correctamente apuntada), usarlo. Si no,
        # dejar el dominio myshopify.com original — funciona SIEMPRE y evita
        # el 404 cuando el dominio personalizado no tiene esa ruta.
        if checkout_url:
            import re as _re
            custom_dom = os.getenv("SHOPIFY_CUSTOM_DOMAIN", "").strip()
            if custom_dom:
                # Limpiar custom_dom (sin https:// ni trailing slash)
                custom_dom = custom_dom.replace("https://", "").replace("http://", "").rstrip("/")
                checkout_url = _re.sub(
                    r"https://[^/]*\.myshopify\.com/",
                    f"https://{custom_dom}/",
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
                # NO vaciar carrito_activo aquí — el cliente abrió el checkout pero
                # puede abandonarlo. Solo vaciamos cuando llega orders/create o
                # orders/paid (pedido cerrado realmente).
                logger.info(f"Checkout creado para {telefono}: {checkout_url} — carrito persiste hasta orders/paid")
            except Exception as e:
                logger.error(f"Error guardando checkout create para {telefono}: {e}")
        return {"status": "ok"}

    # Cliente completó el checkout → ya no hay carrito pendiente NI activo.
    # IMPORTANTE: resolver TODOS los agent_ids bajo los cuales existe el cliente
    # y limpiar para cada uno. Sin esto, asumíamos agent_id=1 por default —
    # rompía multi-tenant y causaba el bug "checkout abandonado" enviado
    # DESPUÉS de confirmar pedido (el limpiar no aplicaba al agent correcto).
    if topic in ("orders/create", "orders/paid"):
        agent_ids = await obtener_agent_ids_por_telefono(telefono)
        if not agent_ids:
            agent_ids = [1]  # fallback legacy si el cliente no existe en BD
            logger.warning(
                f"[shopify-webhook] {telefono} no encontrado en BD — fallback agent_id=1"
            )
        for aid in agent_ids:
            try:
                await limpiar_pedido_pendiente(telefono, agent_id=aid)
                logger.info(f"[shopify-webhook] pedido_pendiente limpiado para {telefono} (agent_id={aid}) tras {topic}")
            except Exception as e:
                logger.error(f"Error limpiando pedido pendiente para {telefono} (agent_id={aid}): {e}")
            try:
                await limpiar_carrito_activo(telefono, agent_id=aid)
                logger.info(f"[shopify-webhook] carrito_activo vaciado para {telefono} (agent_id={aid}) tras {topic}")
            except Exception as e:
                logger.error(f"Error limpiando carrito_activo para {telefono} (agent_id={aid}) tras {topic}: {e}")

    if topic == "orders/fulfilled":
        # Shopify fulfillment puede traer tracking — si está, lo incluimos
        fulfillments = payload.get("fulfillments") or []
        tracking_num = ""
        tracking_url = ""
        if fulfillments:
            f0 = fulfillments[0]
            tracking_num = f0.get("tracking_number") or ""
            tracking_url = f0.get("tracking_url") or ""

        # Tracking opcional — se forma según lo que Shopify mande, se inyecta
        # como placeholder {tracking} en el template configurable.
        extra_tracking = ""
        if tracking_num:
            extra_tracking = f"\n📦 Guía: *{tracking_num}*"
        if tracking_url:
            extra_tracking += f"\n🔗 Seguimiento: {tracking_url}"

        # Resolver agent_id para leer el mensaje configurable del agente correcto.
        # Si no se resolvió antes en este handler, lo hacemos ahora.
        try:
            _aid_shopify = agent_ids[0]  # ya resuelto arriba en orders/create|paid
        except (NameError, IndexError):
            _aids_tmp = await obtener_agent_ids_por_telefono(telefono)
            _aid_shopify = _aids_tmp[0] if _aids_tmp else 1
        from agent.mensajes import format_seguro as _fmt_shopify
        _ctx_shopify = await construir_contexto_placeholders(_aid_shopify)
        _ctx_shopify["numero_pedido"] = nombre_orden
        _ctx_shopify["total"] = f"{total_int:,}"
        _ctx_shopify["tracking"] = extra_tracking
        mensaje = _fmt_shopify(
            await obtener_mensaje(_aid_shopify, "shopify.order_fulfilled"),
            _ctx_shopify,
        )
        if not mensaje:
            # Cliente desactivó este aviso desde el panel — no enviamos nada.
            logger.info(f"[shopify-webhook] orders/fulfilled desactivado para agent={_aid_shopify} — saltando")
            return {"status": "ok"}
    elif topic == "orders/paid":
        try:
            _aid_shopify = agent_ids[0]
        except (NameError, IndexError):
            _aids_tmp = await obtener_agent_ids_por_telefono(telefono)
            _aid_shopify = _aids_tmp[0] if _aids_tmp else 1

        # CAPI: Purchase — pago confirmado. Construir productos con
        # retailer_id desde los line_items del payload de Shopify para que
        # Meta haga match con el catálogo (crítico para optimizar campañas).
        try:
            line_items = payload.get("line_items") or []
            productos_capi = []
            for it in line_items:
                # Shopify expone sku en line_items; ese suele coincidir con
                # el retailer_id del catálogo Meta (Shopify Catalog Connector
                # sincroniza SKU → retailer_id por defecto).
                sku = (it.get("sku") or "").strip()
                if sku:
                    productos_capi.append({
                        "producto":        it.get("title", ""),
                        "presentacion":    it.get("variant_title", ""),
                        "cantidad":        int(it.get("quantity", 1)),
                        "precio_unitario": int(float(it.get("price", 0))),
                        "retailer_id":     sku,
                    })
            from agent.capi import capi_purchase
            asyncio.create_task(capi_purchase(
                telefono, total_int, productos_capi,
                order_id=str(payload.get("order_number") or payload.get("id") or ""),
            ))
        except Exception as _e_capi:
            logger.warning(f"[capi] Purchase falló (no bloqueante): {_e_capi}")

        from agent.mensajes import format_seguro as _fmt_shopify
        _ctx_shopify = await construir_contexto_placeholders(_aid_shopify)
        _ctx_shopify["numero_pedido"] = nombre_orden
        _ctx_shopify["total"] = f"{total_int:,}"
        mensaje = _fmt_shopify(
            await obtener_mensaje(_aid_shopify, "shopify.order_paid"),
            _ctx_shopify,
        )
        if not mensaje:
            logger.info(f"[shopify-webhook] orders/paid desactivado para agent={_aid_shopify} — saltando")
            return {"status": "ok"}
        # ── Promoción post-venta configurable por agente ──────────────────
        # Si el cliente está bajo un agent con promoción activa Y el subtotal
        # (sin envío) supera el umbral configurado, anexamos el código de
        # descuento. CERO defaults — si el agent no lo configuró en el panel,
        # no enviamos nada. Multi-tenant: cada agent tiene su propia promo.
        subtotal_raw = (
            payload.get("subtotal_price")
            or payload.get("current_subtotal_price")
            or total  # fallback solo si Shopify no expone subtotal
        )
        try:
            subtotal_int = int(float(subtotal_raw))
        except Exception:
            subtotal_int = total_int

        # Reutilizamos los agent_ids ya resueltos arriba para limpieza de
        # carrito — evitamos otro round-trip a BD. Si por alguna razón no
        # se resolvieron, los buscamos ahora.
        try:
            promo_agent_ids = agent_ids  # se resolvió antes en este mismo handler
        except NameError:
            promo_agent_ids = await obtener_agent_ids_por_telefono(telefono)

        for aid in promo_agent_ids:
            try:
                promo = await obtener_descuento_promo(aid)
            except Exception as e:
                logger.error(f"[descuento] error leyendo promo agent={aid}: {e}")
                continue
            if not promo:
                continue  # agent sin promo activa o config inválida
            if subtotal_int < promo["umbral"]:
                logger.info(
                    f"[descuento] {telefono} (agent={aid}) subtotal ${subtotal_int:,} "
                    f"< umbral ${promo['umbral']:,} → no enviar"
                )
                continue
            # Sustituir placeholders del template del cliente
            try:
                anuncio = promo["mensaje"].format(
                    codigo=promo["codigo"],
                    pct=promo["pct"],
                    umbral=f"{promo['umbral']:,}".replace(",", "."),
                )
            except (KeyError, IndexError) as e:
                logger.error(
                    f"[descuento] template inválido para agent={aid}: {e} — "
                    f"usando default"
                )
                anuncio = (
                    f"🎁 Como agradecimiento, usa el código *{promo['codigo']}* "
                    f"en tu próxima compra y obtén *{promo['pct']}% de descuento* 😊"
                )
            mensaje += f"\n\n{anuncio}"
            logger.info(
                f"[descuento] {telefono} (agent={aid}) subtotal ${subtotal_int:,} "
                f">= ${promo['umbral']:,} → enviado código {promo['codigo']}"
            )
            break  # ya enviamos para uno — no duplicar si está en varios agents
    else:
        # orders/create (y cualquier otro topic no manejado explícitamente)
        try:
            _aid_shopify = agent_ids[0]
        except (NameError, IndexError):
            _aids_tmp = await obtener_agent_ids_por_telefono(telefono)
            _aid_shopify = _aids_tmp[0] if _aids_tmp else 1
        from agent.mensajes import format_seguro as _fmt_shopify
        _ctx_shopify = await construir_contexto_placeholders(_aid_shopify)
        _ctx_shopify["numero_pedido"] = nombre_orden
        _ctx_shopify["total"] = f"{total_int:,}"
        mensaje = _fmt_shopify(
            await obtener_mensaje(_aid_shopify, "shopify.order_created"),
            _ctx_shopify,
        )
        if not mensaje:
            logger.info(f"[shopify-webhook] orders/create desactivado para agent={_aid_shopify} — saltando")
            return {"status": "ok"}

    try:
        _prov = await _get_meta_para_agente({"id": _aid_shopify})
        await _prov.enviar_mensaje(telefono, mensaje)
        # Guardar en BD para que aparezca en el inbox
        await _guardar_con_wamid(_prov, telefono, mensaje, agent_id=_aid_shopify)
        # Suprimir follow-up y cierre: esta es una notificación automática,
        # no un mensaje conversacional — no debe activar los timers de seguimiento
        await marcar_followup_enviado(telefono)
        await marcar_cierre_enviado(telefono)
        logger.info(f"Confirmación {topic} enviada a {telefono} ({nombre_orden})")
    except Exception as e:
        logger.error(f"Error enviando confirmación a {telefono}: {e}")

    return {"status": "ok"}
