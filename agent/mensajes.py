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

      placeholders: tupla de placeholders {nombre} DISPONIBLES (sugeridos en UI).
                    El cliente puede usar 0, 1 o varios — son opcionales.
                    Si usa un placeholder que NO existe en el contexto resuelto
                    en runtime, se sustituye por string vacío (sin error).

      placeholders_requeridos:
                    subset de `placeholders` que SÍ deben estar presentes en
                    el texto al guardar. Default: tupla vacía (todo opcional).
                    Útil para casos donde la lógica depende del placeholder
                    (ej. mensaje de descuento debe incluir {codigo}).
    """
    key: str
    categoria: str
    titulo: str
    descripcion: str
    cuando: str
    default: str
    placeholders: tuple[str, ...] = field(default_factory=tuple)
    placeholders_requeridos: tuple[str, ...] = field(default_factory=tuple)


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
    "cart.bienvenida_catalogo": MensajeMeta(
        key="cart.bienvenida_catalogo",
        categoria="cart",
        titulo="Mensaje de bienvenida del catálogo",
        descripcion=(
            "Texto que aparece como pie/encabezado cuando Andrea muestra el "
            "catálogo de productos en WhatsApp. Puedes usar los placeholders "
            "para que el texto refleje SIEMPRE tu configuración actual "
            "(pedido mínimo, promoción vigente, etc.) sin tener que reescribirlo."
        ),
        cuando="Cada vez que se envía el catálogo nativo o se procesa [[TIENDA:]]",
        default="📦 Pedido mínimo ${minimo}",
        # Todos OPCIONALES — el cliente decide qué incluir. Si usa uno que
        # no aplica (ej. {descuento_codigo} sin descuento activo), queda
        # vacío y el resto del texto se mantiene.
        placeholders=(
            "minimo",            # PEDIDO_MINIMO del config (formateado: "25.000")
            "envio_gratis",      # umbral envío gratis del config (formateado), o vacío si 0
            "descuento_codigo",  # código de la promoción activa (#43), o vacío
            "descuento_pct",     # porcentaje del descuento, o vacío
            "descuento_umbral",  # umbral del descuento (formateado), o vacío
            "negocio",           # nombre del negocio (Agent.name)
        ),
        placeholders_requeridos=(),  # ninguno obligatorio
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Sustitución segura de placeholders
# ──────────────────────────────────────────────────────────────────────────────
class _SafeDict(dict):
    """Dict que devuelve '' (no KeyError) cuando falta una key.

    Permite hacer template.format_map(contexto) sin temer a placeholders
    desconocidos. Si el cliente escribió `{xyz}` en su mensaje y `xyz` no
    está en el contexto resuelto, queda como string vacío. Esto es
    deliberado: priorizar que el mensaje llegue al cliente sobre estricta
    validación del template (la validación se hace al guardar).
    """
    def __missing__(self, key):
        return ""


def format_seguro(template: str, contexto: dict) -> str:
    """Sustituye {placeholders} en `template` usando `contexto`.

    Si el template tiene placeholders no definidos en contexto, quedan
    vacíos (no lanza KeyError). Si tiene llaves literales que no son
    placeholders válidos (ej. `{` suelta sin cierre), las preservamos
    sin romper el envío.
    """
    if not template:
        return ""
    try:
        return template.format_map(_SafeDict(contexto or {}))
    except (ValueError, IndexError):
        # Template con llaves mal balanceadas o índices numéricos {0} —
        # devolvemos el template tal cual para no perder el mensaje.
        return template


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
