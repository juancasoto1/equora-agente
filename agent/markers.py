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

import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from agent.memory import (
    guardar_carrito_activo,
    limpiar_carrito_activo,
    marcar_cierre_enviado,
)

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
    datos_escalacion: dict | None = None
    abrir_tienda: bool = False
    tienda_query: str = ""
    productos_mencionados: list[str] = field(default_factory=list)
    datos_botones: dict | None = None
    datos_lista: dict | None = None
    datos_catalogo_cat: dict | None = None
    texto_absorbido_por_cta: bool = False


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


