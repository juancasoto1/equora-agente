# agent/markers.py — Dispatcher de marcadores del LLM
#
# El agente (Claude) emite marcadores como [[VACIAR_CARRITO]], [[CARRITO:...]],
# [[PEDIDO:...]], etc. Antes vivían como un bloque gigante de if/elif dentro
# del webhook handler de main.py — frágil para extender y difícil de testear.
#
# Este módulo los convierte en handlers aislados, registrados en orden, con
# un contexto compartido. Para agregar un marcador nuevo:
#
#   @register_marker("MI_MARCADOR")
#   async def handle_mi_marcador(ctx: MarkerContext) -> MarkerContext:
#       if "[[MI_MARCADOR]]" not in ctx.respuesta:
#           return ctx
#       ctx.respuesta = ctx.respuesta.replace("[[MI_MARCADOR]]", "").strip()
#       # ... hacer la acción ...
#       return ctx
#
# El dispatcher `aplicar_marcadores` los corre todos en orden de registro.
# El orden es semánticamente importante: [[PEDIDO:...]] produce el
# checkout_url que main.py envía al final, [[ESCALAR:...]] guarda datos
# para notificar al equipo después, etc.

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from agent.memory import (
    guardar_carrito_activo,
    guardar_checkout_url,
    guardar_cliente,
    guardar_pedido_pendiente,
    limpiar_carrito_activo,
    marcar_cierre_enviado,
    get_agent_modules,
    obtener_pipeline_activo,
    obtener_deal_abierto,
    crear_deal,
    actualizar_deal,
    obtener_cliente,
    obtener_carrito_activo,
    crear_pedido_desde_carrito,
)
from agent.tools import crear_checkout_shopify

logger = logging.getLogger("agentkit")


# ──────────────────────────────────────────────────────────────────────────────
# Contexto compartido entre handlers
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class MarkerContext:
    """Estado que comparten todos los handlers de marcadores.

    Inputs (vienen del webhook):
      - respuesta: texto que devolvió el LLM (se va recortando a medida que
        cada handler extrae su marcador).
      - telefono, agent_id: identifican al cliente.

    Outputs acumulados (los llenan los handlers, los consume main.py al final):
      - checkout_url / checkout_fallo: del marcador [[PEDIDO:...]].
      - pedido_creado: dict del pedido nativo Voco creado por [[PEDIDO_CONFIRMAR]].
      - datos_escalacion: del marcador [[ESCALAR:...]].
      - abrir_tienda / tienda_query: del marcador [[TIENDA:...]].
      - productos_mencionados: del marcador [[PRODUCTO:...]].
      - datos_botones / datos_lista / datos_catalogo_cat: marcadores interactivos.
      - texto_absorbido_por_cta: flag que indica si el texto del LLM se fusiona
        en el cuerpo del CTA del catálogo (en lugar de enviarse como mensaje
        separado).
    """

    # Inputs requeridos
    respuesta: str
    telefono: str
    agent_id: int

    # Outputs acumulados (consumidos por main.py al final del webhook)
    checkout_url: str | None = None
    checkout_fallo: bool = False
    pedido_creado: dict | None = None          # pedido nativo Voco
    datos_escalacion: dict | None = None
    mostrar_carrito_pendiente: bool = False
    abrir_tienda: bool = False
    tienda_query: str = ""
    productos_mencionados: list[str] = field(default_factory=list)
    datos_botones: dict | None = None
    datos_lista: dict | None = None
    datos_catalogo_cat: dict | None = None
    texto_absorbido_por_cta: bool = False
    # Pipeline Fase 2 (Calendly, ver BACKLOG.md) — del marcador [[CITA_DISPONIBILIDAD:]]
    mostrar_citas_pendiente: bool = False


# Type alias para handlers
MarkerHandler = Callable[[MarkerContext], Awaitable[MarkerContext]]


# Registro ordenado de handlers. El orden de registro = orden de ejecución.
MARKER_HANDLERS: "OrderedDict[str, MarkerHandler]" = OrderedDict()


def register_marker(nombre: str):
    """Decorador para registrar un handler en MARKER_HANDLERS.

    El `nombre` es solo para logs y debugging — no se usa para matchear el
    marcador en el texto (cada handler lo hace internamente con su propio regex).
    """

    def deco(fn: MarkerHandler) -> MarkerHandler:
        if nombre in MARKER_HANDLERS:
            logger.warning(f"[markers] handler '{nombre}' ya registrado — sobreescribiendo")
        MARKER_HANDLERS[nombre] = fn
        return fn

    return deco


async def aplicar_marcadores(ctx: MarkerContext) -> MarkerContext:
    """Corre todos los handlers registrados en orden.

    Si un handler falla, lo logueamos y seguimos con los demás — un marcador
    roto NO debe romper la respuesta entera al cliente.
    """
    for nombre, handler in MARKER_HANDLERS.items():
        try:
            ctx = await handler(ctx)
        except Exception as e:
            logger.error(f"[markers] handler '{nombre}' falló: {e}")
    return ctx


# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS — registrados en orden de ejecución
# ══════════════════════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────────────────────
# [[CARRITO:[...]]] — persistir estado del carrito en BD
# ──────────────────────────────────────────────────────────────────────────────
@register_marker("CARRITO")
async def handle_carrito(ctx: MarkerContext) -> MarkerContext:
    """Andrea emite [[CARRITO:[...]]] cada vez que el carrito cambia.

    El payload es JSON con la lista de items. Lo persistimos en `carrito_activo`
    de la BD para que los timers de seguimiento (carrito abandonado, cross-sell)
    puedan usarlo.
    """
    match = re.search(r"\[\[CARRITO:(\[.*?\])\]\]", ctx.respuesta, re.DOTALL)
    if not match:
        return ctx
    try:
        items = json.loads(match.group(1))
    except Exception as e:
        logger.warning(f"[CARRITO] payload no es JSON válido para {ctx.telefono}: {e}")
        items = None
    ctx.respuesta = re.sub(
        r"\s*\[\[CARRITO:\[.*?\]\]\]", "", ctx.respuesta, flags=re.DOTALL
    ).strip()
    if items is None:
        return ctx
    try:
        await guardar_carrito_activo(ctx.telefono, items, agent_id=ctx.agent_id)
        logger.info(f"Carrito actualizado para {ctx.telefono}: {len(items)} items")
    except Exception as e:
        logger.error(f"Error guardando carrito: {e}")
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[VACIAR_CARRITO]] — borrar el carrito en BD
# ──────────────────────────────────────────────────────────────────────────────
@register_marker("VACIAR_CARRITO")
async def handle_vaciar_carrito(ctx: MarkerContext) -> MarkerContext:
    """El LLM lo emite cuando el cliente pide vaciar/borrar/limpiar el carrito.

    Acepta variantes tolerantes a typos del LLM:
    [[VACIAR_CARRITO]], [[VACIAR CARRITO]], [[LIMPIAR_CARRITO]], [[LIMPIAR CARRITO]].
    """
    patron = r"\[\[(?:VACIAR|LIMPIAR)[_ ]?CARRITO\]\]"
    if not re.search(patron, ctx.respuesta, flags=re.IGNORECASE):
        return ctx
    ctx.respuesta = re.sub(patron, "", ctx.respuesta, flags=re.IGNORECASE).strip()
    try:
        await limpiar_carrito_activo(ctx.telefono, agent_id=ctx.agent_id)
        logger.info(f"[VACIAR_CARRITO] carrito vaciado para {ctx.telefono}")
    except Exception as e:
        logger.error(f"Error vaciando carrito de {ctx.telefono}: {e}")
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[MOSTRAR_CARRITO]] — pedir a main.py que envíe el resumen con reply buttons
# ──────────────────────────────────────────────────────────────────────────────
# Acepta variantes [[MOSTRAR_CARRITO]], [[VER_CARRITO]], [[VER CARRITO]].
# El handler NO envía el resumen directamente (eso requiere acceso al proveedor
# de WhatsApp + a _enviar_resumen_carrito, que viven en main.py). Solo levanta
# el flag `mostrar_carrito_pendiente`; main.py lo consume al salir del
# dispatcher para invocar el handler determinístico que lee BD y manda botones.
@register_marker("MOSTRAR_CARRITO")
async def handle_mostrar_carrito(ctx: MarkerContext) -> MarkerContext:
    patron = r"\[\[(?:MOSTRAR|VER)[_ ]?CARRITO\]\]"
    if not re.search(patron, ctx.respuesta, flags=re.IGNORECASE):
        return ctx
    ctx.respuesta = re.sub(patron, "", ctx.respuesta, flags=re.IGNORECASE).strip()
    ctx.mostrar_carrito_pendiente = True
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[CITA_DISPONIBILIDAD:]] — Pipeline Fase 2 (Calendly, ver BACKLOG.md)
# ──────────────────────────────────────────────────────────────────────────────
# Andrea lo emite cuando el cliente quiere agendar/agendarse una cita. Mismo
# patrón que MOSTRAR_CARRITO: el handler solo levanta la bandera — consultar
# Calendly (HTTP) y mandar la lista interactiva requiere el proveedor de
# WhatsApp, que vive en main.py. main.py consume `mostrar_citas_pendiente`
# al salir del dispatcher.
@register_marker("CITA_DISPONIBILIDAD")
async def handle_cita_disponibilidad(ctx: MarkerContext) -> MarkerContext:
    patron = r"\[\[CITA_DISPONIBILIDAD:?\]\]"
    if not re.search(patron, ctx.respuesta, flags=re.IGNORECASE):
        return ctx
    ctx.respuesta = re.sub(patron, "", ctx.respuesta, flags=re.IGNORECASE).strip()
    ctx.mostrar_citas_pendiente = True
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[ESCALAR:...]] — solicitud de notificar al equipo humano
# ──────────────────────────────────────────────────────────────────────────────
# Andrea idealmente escribe JSON ({"motivo":"...", "urgencia":"...", ...}),
# pero a veces se desvía y escribe texto plano. Aceptamos ambos formatos para
# no perder escalaciones reales. El resultado va a ctx.datos_escalacion; main.py
# lo consume al final con _notificar_escalacion().
@register_marker("ESCALAR")
async def handle_escalar(ctx: MarkerContext) -> MarkerContext:
    match = re.search(r"\[\[ESCALAR:(.*?)\]\]", ctx.respuesta, re.DOTALL)
    if not match:
        return ctx
    contenido_raw = match.group(1).strip()
    datos: dict | None = None
    # Intento 1: parsear como JSON (formato canónico)
    try:
        datos = json.loads(contenido_raw)
    except Exception:
        # Intento 2: texto plano "motivo - cliente: X - contexto: Y"
        logger.warning(f"ESCALAR recibido como texto plano: {contenido_raw[:200]}")
        datos = {
            "motivo":         "Escalación solicitada",
            "urgencia":       "normal",
            "nombre_cliente": "",
            "contexto":       contenido_raw[:500],
        }
        m_nombre = re.search(r"cliente:\s*([^-\n]+)", contenido_raw, re.IGNORECASE)
        if m_nombre:
            datos["nombre_cliente"] = m_nombre.group(1).strip()[:200]
        primera_parte = contenido_raw.split(" - ")[0].strip()
        if primera_parte and len(primera_parte) < 100:
            datos["motivo"] = primera_parte
        if re.search(r"\b(urgente|urgencia\s*:?\s*alta|alta)\b", contenido_raw, re.IGNORECASE):
            datos["urgencia"] = "alta"
    # Validar estructura mínima
    if not isinstance(datos, dict):
        logger.error(f"ESCALAR sin estructura válida — se ignora: {contenido_raw[:200]}")
        datos = None
    ctx.respuesta = re.sub(r"\s*\[\[ESCALAR:.*?\]\]", "", ctx.respuesta, flags=re.DOTALL).strip()
    ctx.datos_escalacion = datos
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[PEDIDO:{...}]] — crear checkout en Shopify
# ──────────────────────────────────────────────────────────────────────────────
# Andrea emite este marcador con el JSON del pedido. El handler:
#   1. Llama crear_checkout_shopify() → URL de checkout
#   2. Persiste cliente + pedido_pendiente + checkout_url
#   3. Setea ctx.checkout_url y ctx.checkout_fallo
#
# main.py consume ctx.checkout_url más abajo para enviar el cta_url
# (botón "Confirmar entrega") y consume checkout_fallo para avisar al
# cliente si algo falló (stock agotado, producto no mapeado, etc.).
#
# IMPORTANTE: NO vaciar carrito_activo aquí. El carrito persiste hasta:
#   1) Webhook orders/paid de Shopify (pago confirmado)
#   2) Expira el TTL (CARRITO_TTL_HORAS)
# Antes se vaciaba inmediatamente al crear checkout — si el cliente NO
# completaba el pago, perdía todo el carrito.
@register_marker("PEDIDO")
async def handle_pedido(ctx: MarkerContext) -> MarkerContext:
    match = re.search(r"\[\[PEDIDO:(.*?)\]\]", ctx.respuesta, re.DOTALL)
    if not match:
        return ctx
    try:
        datos_pedido = json.loads(match.group(1))
        checkout_url = await crear_checkout_shopify(ctx.telefono, datos_pedido)
        if checkout_url:
            ctx.checkout_url = checkout_url
            await guardar_cliente(ctx.telefono, datos_pedido, agent_id=ctx.agent_id)
            await guardar_pedido_pendiente(
                ctx.telefono, datos_pedido.get("productos", []), agent_id=ctx.agent_id,
            )
            try:
                await guardar_checkout_url(ctx.telefono, checkout_url, agent_id=ctx.agent_id)
            except Exception as e_url:
                logger.warning(f"No pude guardar checkout_url: {e_url}")
            logger.info(
                f"Checkout Shopify creado para {ctx.telefono} — "
                f"carrito persiste hasta orders/paid"
            )
        else:
            ctx.checkout_fallo = True
            logger.error(f"No se pudo crear checkout Shopify para {ctx.telefono}")
    except Exception as e:
        ctx.checkout_fallo = True
        logger.error(f"Error procesando pedido: {e}")
    ctx.respuesta = re.sub(
        r"\s*\[\[PEDIDO:.*?\]\]", "", ctx.respuesta, flags=re.DOTALL,
    ).strip()
    return ctx


# ══════════════════════════════════════════════════════════════════════════════
# FASE E (#27) — Marcadores interactivos
# ══════════════════════════════════════════════════════════════════════════════
# Los siguientes 5 handlers solo EXTRAEN y populan el contexto. El envío real
# (single_product, product_list, reply_buttons, interactive_list, cta_url) sigue
# en main.py porque la lógica de ORDEN y FALLBACKS depende de variables locales
# del webhook (_proveedor_agente, _agent_id, msg.telefono) y tiene encadenamientos
# delicados que NO conviene mover sin un refactor mayor del envío.
#
# Comportamiento: defaults byte-idénticos a los extractores originales que
# vivían en main.py — cero regresión esperada.


# ──────────────────────────────────────────────────────────────────────────────
# [[CATALOGO_CAT:{"categoria":"X"}]] — abre catálogo nativo de WhatsApp
# ──────────────────────────────────────────────────────────────────────────────
@register_marker("CATALOGO_CAT")
async def handle_catalogo_cat(ctx: MarkerContext) -> MarkerContext:
    match = re.search(r"\[\[CATALOGO_CAT:(.*?)\]\]", ctx.respuesta, re.DOTALL)
    if not match:
        return ctx
    try:
        datos = json.loads(match.group(1))
    except Exception:
        datos = None
    ctx.respuesta = re.sub(
        r"\s*\[\[CATALOGO_CAT:.*?\]\]", "", ctx.respuesta, flags=re.DOTALL
    ).strip()
    ctx.datos_catalogo_cat = datos
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[BOTONES:{...}]] — reply buttons de WhatsApp (máx 3)
# ──────────────────────────────────────────────────────────────────────────────
@register_marker("BOTONES")
async def handle_botones(ctx: MarkerContext) -> MarkerContext:
    match = re.search(r"\[\[BOTONES:(.*?)\]\]", ctx.respuesta, re.DOTALL)
    if not match:
        return ctx
    try:
        datos = json.loads(match.group(1))
    except Exception:
        datos = None
    ctx.respuesta = re.sub(
        r"\s*\[\[BOTONES:.*?\]\]", "", ctx.respuesta, flags=re.DOTALL
    ).strip()
    ctx.datos_botones = datos
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[LISTA:{...}]] — interactive list de WhatsApp con secciones
# ──────────────────────────────────────────────────────────────────────────────
@register_marker("LISTA")
async def handle_lista(ctx: MarkerContext) -> MarkerContext:
    match = re.search(r"\[\[LISTA:(.*?)\]\]", ctx.respuesta, re.DOTALL)
    if not match:
        return ctx
    try:
        datos = json.loads(match.group(1))
    except Exception:
        datos = None
    ctx.respuesta = re.sub(
        r"\s*\[\[LISTA:.*?\]\]", "", ctx.respuesta, flags=re.DOTALL
    ).strip()
    ctx.datos_lista = datos
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[TIENDA:]] o [[TIENDA:término]] — abre catálogo/tienda con query opcional
# ──────────────────────────────────────────────────────────────────────────────
@register_marker("TIENDA")
async def handle_tienda(ctx: MarkerContext) -> MarkerContext:
    # Forma con término de búsqueda: [[TIENDA:nombre producto]]
    m = re.search(r"\[\[TIENDA:([^\]]+)\]\]", ctx.respuesta)
    if m:
        query = m.group(1).strip()
        ctx.respuesta = re.sub(
            r"\s*\[\[TIENDA:[^\]]*\]\]", "", ctx.respuesta
        ).strip()
        ctx.abrir_tienda = True
        ctx.tienda_query = query
        return ctx
    # Forma sin término: [[TIENDA:]]
    if "[[TIENDA:]]" in ctx.respuesta:
        ctx.respuesta = re.sub(
            r"\s*\[\[TIENDA:\]\]", "", ctx.respuesta
        ).strip()
        ctx.abrir_tienda = True
        ctx.tienda_query = ""
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[PRODUCTO:nombre|presentacion]] — single_product del catálogo (uno o más)
# ──────────────────────────────────────────────────────────────────────────────
@register_marker("PRODUCTO")
async def handle_producto(ctx: MarkerContext) -> MarkerContext:
    matches = re.findall(r"\[\[PRODUCTO:([^\]]+)\]\]", ctx.respuesta)
    if not matches:
        return ctx
    ctx.respuesta = re.sub(
        r"\s*\[\[PRODUCTO:[^\]]+\]\]", "", ctx.respuesta
    ).strip()
    productos = [m.strip() for m in matches if m.strip()]
    ctx.productos_mencionados = productos
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[CIERRE_CONV:]] — marcar conversación cerrada (suprime seguimientos)
# ──────────────────────────────────────────────────────────────────────────────
@register_marker("CIERRE_CONV")
async def handle_cierre_conv(ctx: MarkerContext) -> MarkerContext:
    """El LLM lo emite cuando la conversación llega a fin natural (cliente se
    despide, pedido completado, escalación a humano, etc.). Suprime los timers
    de seguimiento para que el cliente no reciba mensajes no solicitados."""
    if "[[CIERRE_CONV:]]" not in ctx.respuesta:
        return ctx
    ctx.respuesta = ctx.respuesta.replace("[[CIERRE_CONV:]]", "").strip()
    try:
        await marcar_cierre_enviado(ctx.telefono, agent_id=ctx.agent_id)
        logger.info(f"Conversación cerrada para {ctx.telefono} — seguimientos suprimidos")
    except Exception as e:
        logger.error(f"Error marcando cierre: {e}")
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[DEAL_STAGE:Nombre del stage]] — Pipeline Fase 1 (mini-CRM, ver BACKLOG.md)
# ──────────────────────────────────────────────────────────────────────────────
# Andrea lo emite cuando detecta un cambio real de intención de compra (ver
# guía inyectada en brain.py). Un cliente tiene como máximo UNA oportunidad
# ABIERTA a la vez (closed_at IS NULL) — si ya existe, este marcador la mueve
# de stage en vez de crear una duplicada por cada mensaje.
#
# El nombre de stage tiene que coincidir EXACTO con uno de los stages reales
# del pipeline (los mismos que se inyectan en el prompt). Si Andrea alucina
# un nombre que no existe, el marcador se ignora — fail-safe: preferimos
# perder un movimiento de stage a corromper el kanban con etapas inventadas.
#
# Gateado al módulo "pipeline" (Agent.modules_json, no el sistema viejo de
# ACTIVE_MODULES) — si el negocio no activó Pipeline, el marcador no hace
# nada aunque por algún motivo el LLM lo emita.
@register_marker("DEAL_STAGE")
async def handle_deal_stage(ctx: MarkerContext) -> MarkerContext:
    match = re.search(r"\[\[DEAL_STAGE:([^\]]+)\]\]", ctx.respuesta)
    if not match:
        return ctx
    stage_nombre = match.group(1).strip()
    ctx.respuesta = re.sub(r"\s*\[\[DEAL_STAGE:[^\]]+\]\]", "", ctx.respuesta).strip()
    if not stage_nombre:
        return ctx
    try:
        modules = await get_agent_modules(ctx.agent_id)
        if not modules.get("pipeline", False):
            return ctx

        pipeline = await obtener_pipeline_activo(ctx.agent_id)
        stages_validos = pipeline.get("stages") or []
        if stage_nombre not in stages_validos:
            logger.warning(
                f"[DEAL_STAGE] '{stage_nombre}' no es un stage válido del pipeline "
                f"(agent_id={ctx.agent_id}) — se ignora. Stages: {stages_validos}"
            )
            return ctx

        deal_abierto = await obtener_deal_abierto(ctx.agent_id, pipeline["id"], ctx.telefono)
        if deal_abierto:
            await actualizar_deal(
                deal_abierto["id"], ctx.agent_id,
                stage=stage_nombre, autor_nombre="Andrea (IA)",
            )
            logger.info(f"[DEAL_STAGE] Deal {deal_abierto['id']} de {ctx.telefono} → '{stage_nombre}'")
            _hs_sync_if_enabled(modules, ctx.agent_id, deal_abierto["id"], ctx.telefono)
        else:
            cliente = await obtener_cliente(ctx.telefono, ctx.agent_id) or {}
            cliente_nombre = " ".join(filter(None, [
                cliente.get("nombres", ""), cliente.get("apellidos", ""),
            ])).strip()
            # Si ya hay carrito activo, lo usamos como valor inicial estimado
            # del deal — dato gratis que ya existe, mejor que arrancar en $0.
            carrito = await obtener_carrito_activo(ctx.telefono, agent_id=ctx.agent_id)
            valor_inicial = sum(int(it.get("subtotal", 0)) for it in carrito) if carrito else 0
            nuevo = await crear_deal(
                agent_id=ctx.agent_id,
                pipeline_id=pipeline["id"],
                cliente_telefono=ctx.telefono,
                cliente_nombre=cliente_nombre,
                valor_cop=valor_inicial,
                source="whatsapp",
                stage=stage_nombre,
                autor_nombre="Andrea (IA)",
            )
            logger.info(f"[DEAL_STAGE] Deal {nuevo['id']} creado para {ctx.telefono} en '{stage_nombre}'")
            _hs_sync_if_enabled(modules, ctx.agent_id, nuevo["id"], ctx.telefono)
    except Exception as e:
        logger.error(f"[DEAL_STAGE] Error procesando para {ctx.telefono}: {e}")
    return ctx


# ──────────────────────────────────────────────────────────────────────────────
# [[PEDIDO_CONFIRMAR]] — crear pedido nativo Voco desde el carrito activo
# ──────────────────────────────────────────────────────────────────────────────
# Se usa cuando el agente NO tiene Shopify. El LLM lo emite al confirmar
# una venta conversacional. Extrae el carrito de BD, crea el Pedido y expone
# el dict en ctx.pedido_creado para que main.py envíe la confirmación.
#
# Payload opcional: [[PEDIDO_CONFIRMAR:{"direccion":"...","notas":"..."}]]
# Si no hay payload, se usan valores vacíos.
@register_marker("PEDIDO_CONFIRMAR")
async def handle_pedido_confirmar(ctx: MarkerContext) -> MarkerContext:
    match = re.search(r"\[\[PEDIDO_CONFIRMAR(?::({.*?}))?\]\]", ctx.respuesta, re.DOTALL)
    if not match:
        return ctx
    ctx.respuesta = re.sub(
        r"\s*\[\[PEDIDO_CONFIRMAR(?::{.*?})?\]\]", "", ctx.respuesta, flags=re.DOTALL
    ).strip()

    payload: dict = {}
    if match.group(1):
        try:
            payload = json.loads(match.group(1))
        except Exception:
            pass

    try:
        carrito = await obtener_carrito_activo(ctx.telefono, agent_id=ctx.agent_id)
        if not carrito:
            logger.warning(f"[PEDIDO_CONFIRMAR] carrito vacío para {ctx.telefono} — se ignora")
            return ctx

        cliente = await obtener_cliente(ctx.telefono, ctx.agent_id) or {}
        nombre = " ".join(filter(None, [
            cliente.get("nombres", ""), cliente.get("apellidos", ""),
        ])).strip() or ctx.telefono

        pedido = await crear_pedido_desde_carrito(
            telefono=ctx.telefono,
            agent_id=ctx.agent_id,
            carrito=carrito,
            nombre_cliente=nombre,
            direccion=str(payload.get("direccion", ""))[:1000],
            notas_cliente=str(payload.get("notas", ""))[:2000],
            costo_envio=int(payload.get("costo_envio", 0)),
            descuento=int(payload.get("descuento", 0)),
        )
        ctx.pedido_creado = pedido
        await limpiar_carrito_activo(ctx.telefono, agent_id=ctx.agent_id)
        logger.info(
            f"[PEDIDO_CONFIRMAR] Pedido {pedido['numero']} creado para {ctx.telefono} "
            f"— total ${pedido['total']:,}"
        )
    except Exception as e:
        logger.error(f"[PEDIDO_CONFIRMAR] Error para {ctx.telefono}: {e}")
    return ctx


def _hs_sync_if_enabled(modules: dict, agent_id: int, deal_id: int, telefono: str) -> None:
    """Lanza la sincronización HubSpot en background si el módulo está activo.
    Fire-and-forget: usa asyncio.create_task() para no bloquear el webhook.
    """
    if not modules.get("hubspot", False):
        return
    from agent.hubspot import sincronizar_deal_bg
    asyncio.create_task(sincronizar_deal_bg(agent_id, deal_id, telefono))


