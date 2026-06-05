# agent/mensajes.py — Catálogo central de mensajes configurables por agente
#
# Voco es un facilitador de comunicación — los mensajes que envía a los
# clientes finales NO deben ser hardcoded para Equora. Cada agente SaaS
# debe poder personalizarlos desde el panel sin tocar código.
#
# Este módulo es la ÚNICA fuente de verdad del catálogo. Para agregar un
# mensaje nuevo:
#   1. Añadir entry al diccionario MENSAJES
#   2. En el código que lo envía, llamar `await obtener_mensaje(agent_id, key)`
#      en lugar de usar el string literal
#   3. La UI del panel se auto-puebla con la metadata declarada acá
#
# Para personalizar el valor por agente: guardar el override en BD vía
# `guardar_mensaje_agente(agent_id, key, content)`. Si no hay override,
# `obtener_mensaje` devuelve el default declarado acá.

from __future__ import annotations

from dataclasses import dataclass, field


# ──────────────────────────────────────────────────────────────────────────────
# Categorías — solo para agrupar en la UI del panel
# ──────────────────────────────────────────────────────────────────────────────
CATEGORIAS: dict[str, dict] = {
    "system": {
        "label": "Sistema",
        "descripcion": "Seguimientos automáticos y despedidas",
        "orden": 1,
    },
    "shopify": {
        "label": "Confirmaciones de pedido",
        "descripcion": "Mensajes enviados al cliente cuando Shopify dispara eventos",
        "orden": 2,
    },
    "cart": {
        "label": "Carrito y checkout",
        "descripcion": "Mensajes durante el flujo de compra",
        "orden": 3,
    },
    "error": {
        "label": "Errores y fallbacks",
        "descripcion": "Mensajes cuando algo falla en el flujo",
        "orden": 4,
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Metadata de cada mensaje
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MensajeMeta:
    """Metadata de un mensaje del catálogo.

    Campos:
      key:          identificador namespaced (ej. "system.followup")
      categoria:    una de CATEGORIAS — para agruparlo en UI
      titulo:       nombre corto que ve el admin en el panel
      descripcion:  qué hace este mensaje (1-2 líneas)
      cuando:       cuándo se dispara (línea adicional de contexto)
      default:      texto que se envía si el agente no lo personaliza
      placeholders: tupla de placeholders {nombre} soportados. Vacía si no.
    """
    key: str
    categoria: str
    titulo: str
    descripcion: str
    cuando: str
    default: str
    placeholders: tuple[str, ...] = field(default_factory=tuple)


# ──────────────────────────────────────────────────────────────────────────────
# Catálogo — fuente de verdad
# ──────────────────────────────────────────────────────────────────────────────
# Empezamos con los 3 mensajes "system" para la Fase 2 (los explícitos como
# constantes en main.py). Las siguientes fases agregarán Shopify, carrito y
# errores. Cada entry NUEVO se vuelve automáticamente editable desde la UI.
MENSAJES: dict[str, MensajeMeta] = {
    "system.followup": MensajeMeta(
        key="system.followup",
        categoria="system",
        titulo="Recordatorio de inactividad",
        descripcion="Se envía al cliente si lleva varios minutos sin responder.",
        cuando="Tras ~10 min sin respuesta",
        default=(
            "Hola de nuevo 😊 Veo que andas un poco ocupado/a. "
            "¿Sigues por aquí o prefieres que continuemos en otro momento? "
            "No hay afán, retomamos cuando puedas."
        ),
        placeholders=(),
    ),
    "system.cierre": MensajeMeta(
        key="system.cierre",
        categoria="system",
        titulo="Despedida por inactividad",
        descripcion="Se envía cuando el cliente no respondió al recordatorio. Cierra la conversación con un mensaje amable.",
        cuando="Tras ~5 min sin responder al recordatorio",
        default=(
            "Te dejo descansar 🤗 Cuando quieras retomar, escríbeme y "
            "seguimos donde nos quedamos. ¡Que tengas un excelente día! 🌿"
        ),
        placeholders=(),
    ),
    "system.checkout_abandono": MensajeMeta(
        key="system.checkout_abandono",
        categoria="system",
        titulo="Recuperación de checkout abandonado",
        descripcion="Se envía al cliente que abrió el formulario de pago de Shopify pero no completó. Incluye un botón con el link del checkout para retomar.",
        cuando="Entre 15 y 40 min después de iniciar el checkout sin completar",
        default=(
            "Hola 👋 Vimos que iniciaste tu pedido pero no terminaste el proceso.\n\n"
            "Tu carrito está guardado — solo falta confirmar y listo 🎉"
        ),
        placeholders=(),
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de inspección del catálogo (no tocan BD)
# ──────────────────────────────────────────────────────────────────────────────
def obtener_meta(key: str) -> MensajeMeta | None:
    """Devuelve la metadata del mensaje con esa key, o None si no existe."""
    return MENSAJES.get(key)


def obtener_default(key: str) -> str:
    """Devuelve el texto default de un mensaje, o string vacío si la key es desconocida."""
    meta = MENSAJES.get(key)
    return meta.default if meta else ""


def listar_keys_validas() -> list[str]:
    """Lista todas las keys del catálogo (para validación de input)."""
    return list(MENSAJES.keys())


def listar_categorias_ordenadas() -> list[tuple[str, dict]]:
    """Devuelve [(slug, dict_meta), ...] ordenado por `orden` para la UI."""
    return sorted(CATEGORIAS.items(), key=lambda kv: kv[1].get("orden", 999))


def listar_mensajes_por_categoria() -> dict[str, list[MensajeMeta]]:
    """Agrupa los mensajes por categoría — útil para la UI agrupada."""
    grupos: dict[str, list[MensajeMeta]] = {cat: [] for cat in CATEGORIAS}
    for meta in MENSAJES.values():
        grupos.setdefault(meta.categoria, []).append(meta)
    # Ordenar dentro de cada grupo por key (estable)
    for cat in grupos:
        grupos[cat].sort(key=lambda m: m.key)
    return grupos
