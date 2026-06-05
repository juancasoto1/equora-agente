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
        "label": "Seguimientos automáticos",
        "descripcion": "Mensajes que se envían si el cliente deja de responder",
        "orden": 1,
    },
    "cart": {
        "label": "Flujo de compra",
        "descripcion": "Mensajes mientras el cliente arma su pedido y lo confirma",
        "orden": 2,
    },
    "shopify": {
        "label": "Confirmaciones de pedido",
        "descripcion": "Mensajes que se envían cuando se procesa una compra",
        "orden": 3,
    },
    "error": {
        "label": "Mensajes de error",
        "descripcion": "Qué decir cuando algo falla",
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

      max_length:   máximo de caracteres permitido en el texto. Default 4000
                    (límite cómodo para mensajes WhatsApp). Útil para botones
                    (máximo 20 chars en Meta) y textos cortos.

      puede_desactivarse:
                    Si True (default), el agente puede apagar este mensaje
                    desde el panel — cuando está OFF, el código no envía
                    nada en ese punto del flujo. Marcar False solo para
                    mensajes ESENCIALES sin los cuales el flujo se rompe
                    (ej. el botón del checkout — sin él no hay forma de
                    completar la compra).

      aviso_setup:  Texto informativo que se muestra como banner amarillo
                    arriba del editor en el panel. Úsalo para mensajes que
                    requieren configuración EXTERNA para que se disparen
                    (ej. los de Shopify necesitan webhook configurado).
                    Default vacío (sin aviso).

      aviso_setup_url:
                    URL opcional con instrucciones detalladas (ej. docs).
                    Aparece como link 'Ver guía' al lado del aviso.
    """
    key: str
    categoria: str
    titulo: str
    descripcion: str
    cuando: str
    default: str
    placeholders: tuple[str, ...] = field(default_factory=tuple)
    placeholders_requeridos: tuple[str, ...] = field(default_factory=tuple)
    max_length: int = 4000
    puede_desactivarse: bool = True
    aviso_setup: str = ""
    aviso_setup_url: str = ""


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
        titulo="Recordatorio si el cliente no responde",
        descripcion="Mensaje amable para retomar la conversación cuando el cliente lleva un rato sin escribir. Si tu negocio no quiere insistir, puedes apagarlo.",
        cuando="Se envía aproximadamente 10 minutos después del último mensaje del cliente",
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
        titulo="Despedida si el cliente sigue sin responder",
        descripcion="Cierra la conversación cuando el cliente no respondió ni al recordatorio. Útil para liberar el espacio mental sin sonar abandonado.",
        cuando="Se envía aproximadamente 5 minutos después del recordatorio sin respuesta",
        default=(
            "Te dejo descansar 🤗 Cuando quieras retomar, escríbeme y "
            "seguimos donde nos quedamos. ¡Que tengas un excelente día! 🌿"
        ),
        placeholders=(),
    ),
    "system.checkout_abandono": MensajeMeta(
        key="system.checkout_abandono",
        categoria="system",
        titulo="Recordatorio si el cliente no terminó el pago",
        descripcion="Mensaje que recupera al cliente que abrió el formulario de pago pero no lo completó. Se envía con el botón para retomar exactamente donde se quedó.",
        cuando="Se envía entre 15 y 40 minutos después de abrir el pago sin completarlo",
        default=(
            "Hola 👋 Vimos que iniciaste tu pedido pero no terminaste el proceso.\n\n"
            "Tu carrito está guardado — solo falta confirmar y listo 🎉"
        ),
        placeholders=(),
    ),
    "cart.checkout_listo_texto": MensajeMeta(
        key="cart.checkout_listo_texto",
        categoria="cart",
        titulo="Mensaje cuando el pedido está listo para pagar",
        descripcion=(
            "Texto que aparece justo encima del botón de pago. Se usa cada "
            "vez que el cliente está listo para confirmar."
        ),
        cuando="Justo antes de enviar el botón con el link del pago",
        default=(
            "🧾 *Tu pedido está listo*\n\n"
            "Toca el botón para confirmar tu pedido y completar el pago."
        ),
        placeholders=(
            "total", "descuento_codigo", "descuento_pct", "descuento_umbral", "negocio",
        ),
        placeholders_requeridos=(),
        puede_desactivarse=False,  # esencial — sin texto el botón CTA no se puede enviar
    ),
    "cart.checkout_listo_boton": MensajeMeta(
        key="cart.checkout_listo_boton",
        categoria="cart",
        titulo="Texto del botón para pagar",
        descripcion=(
            "Texto que aparece dentro del botón verde que abre el pago. "
            "Cámbialo según tu negocio: 'Pagar pedido', 'Reservar', "
            "'Comprar ahora', 'Pagar póliza', etc. Máximo 20 caracteres."
        ),
        cuando="Aparece como label del botón principal en cada checkout",
        default="Confirmar pedido",
        placeholders=(),
        max_length=20,
        puede_desactivarse=False,  # ESENCIAL — sin botón no hay forma de pagar
    ),
    "cart.estado4_cross_sell": MensajeMeta(
        key="cart.estado4_cross_sell",
        categoria="cart",
        titulo="Sugerencia de agregar más al alcanzar el monto mínimo",
        descripcion=(
            "Mensaje que se envía cuando el carrito ya cumple tu pedido mínimo. "
            "Es el momento ideal para sugerir agregar más productos (cross-sell). "
            "Si tu negocio no maneja pedido mínimo o no quieres hacer cross-sell, "
            "puedes apagarlo y se pasará directo al botón de pagar."
        ),
        cuando="Cuando el total del carrito alcanza el monto mínimo configurado",
        default=(
            "🎉 *¡Pedido confirmado por ${total}!*\n\n"
            "¿Quieres agregar algo más antes de cerrar tu pedido?\n"
            "Toca el botón para ver el catálogo:"
        ),
        placeholders=(
            "total", "minimo", "envio_gratis", "falta_envio_gratis",
            "descuento_codigo", "descuento_pct", "descuento_umbral", "negocio",
        ),
        placeholders_requeridos=(),
    ),
    "cart.estado4_cta_texto": MensajeMeta(
        key="cart.estado4_cta_texto",
        categoria="cart",
        titulo="Acompañante del botón cuando ofreces cerrar el pedido",
        descripcion=(
            "Mensaje corto que va junto al botón de pago cuando el cliente "
            "alcanzó el mínimo pero le ofrecemos también cerrar el pedido."
        ),
        cuando="Inmediatamente después del mensaje de sugerencia, con el botón de pagar",
        default="O si ya quieres cerrar tu pedido, toca aquí 👇",
        placeholders=("total", "negocio"),
        placeholders_requeridos=(),
        puede_desactivarse=False,  # esencial — sin texto el botón CTA no se puede enviar
    ),
    # ── Confirmaciones de Shopify (categoría "shopify") ──────────────────────
    # Cada uno se envía al recibir el evento correspondiente del webhook.
    # Los defaults son IDÉNTICOS a los strings que vivían hardcoded en el
    # handler — comportamiento sin personalizar = comportamiento previo.
    "shopify.order_created": MensajeMeta(
        key="shopify.order_created",
        categoria="shopify",
        titulo="Confirmación cuando se crea el pedido",
        descripcion=(
            "Mensaje que se envía cuando Shopify registra que el pedido fue "
            "creado (orders/create). Avísale al cliente que su pedido ya "
            "está en proceso, con el número y el total."
        ),
        cuando="Apenas Shopify confirma que el pedido fue creado",
        default=(
            "✅ *¡Pedido confirmado!*\n\n"
            "🧾 Número de pedido: *{numero_pedido}*\n"
            "💰 Total: *${total}*\n\n"
            "Ya estamos preparando tu pedido. Te avisamos cuando vaya en camino. "
            "¡Gracias por confiar en nosotros! 🌿"
        ),
        placeholders=("numero_pedido", "total", "negocio"),
        placeholders_requeridos=(),
        puede_desactivarse=False,  # esencial: sin esto el cliente no sabe el estado del pedido
        aviso_setup=(
            "Este mensaje se dispara cuando Shopify avisa que se creó un pedido nuevo. "
            "Para que llegue ese aviso, debes registrar el webhook **orders/create** "
            "en tu tienda apuntando a la URL de abajo."
        ),
        aviso_setup_url="https://help.shopify.com/en/manual/orders/notifications/webhooks",
    ),
    "shopify.order_paid": MensajeMeta(
        key="shopify.order_paid",
        categoria="shopify",
        titulo="Confirmación cuando se registra el pago",
        descripcion=(
            "Mensaje que se envía cuando Shopify registra el pago "
            "(orders/paid). Si tienes promoción activa con código de descuento, "
            "el bono se anexa automáticamente DESPUÉS de este mensaje "
            "(cuando el subtotal supera el umbral configurado)."
        ),
        cuando="Cuando Shopify confirma que el pago se procesó",
        default=(
            "💰 *¡Pago registrado!*\n\n"
            "Pedido: *{numero_pedido}*  ·  Total: *${total}*\n\n"
            "Pronto sale en camino. ¡Gracias por confiar en nosotros! 🌿"
        ),
        placeholders=("numero_pedido", "total", "negocio"),
        placeholders_requeridos=(),
        puede_desactivarse=False,  # esencial: notificación del pago confirmado
        aviso_setup=(
            "Debes registrar el webhook **orders/paid** en tu tienda apuntando a la URL "
            "de abajo.\n\nSi vendes contra-entrega, este evento solo se dispara cuando "
            "marcas manualmente el pedido como pagado en Shopify Admin (al recibir el "
            "efectivo). Para pagos online se dispara automáticamente."
        ),
        aviso_setup_url="https://help.shopify.com/en/manual/orders/notifications/webhooks",
    ),
    "shopify.order_fulfilled": MensajeMeta(
        key="shopify.order_fulfilled",
        categoria="shopify",
        titulo="Aviso cuando el pedido va en camino",
        descripcion=(
            "Mensaje que se envía cuando Shopify marca el pedido como "
            "despachado (orders/fulfilled). Si Shopify trae datos de guía "
            "de envío, se anexan automáticamente con el placeholder {tracking} "
            "— déjalo donde quieras que aparezcan."
        ),
        cuando="Cuando se marca el pedido como despachado en Shopify",
        default=(
            "🚚 *¡Tu pedido está listo y va en camino!*\n\n"
            "Pedido *{numero_pedido}* preparado y despachado.{tracking}\n\n"
            "Total del pedido: *${total}*. ¡Gracias por confiar en nosotros! 🌿"
        ),
        # {tracking} se forma en código: "" si no hay datos, o
        # "\n📦 Guía: *<num>*\n🔗 Seguimiento: <url>" si los hay.
        placeholders=("numero_pedido", "total", "tracking", "negocio"),
        placeholders_requeridos=(),
        # Sí desactivable: hay negocios que no quieren saturar con avisos de envío
        # (especialmente si tienen tracking en email aparte). Pero ojo: si lo
        # apagas, el cliente NO recibe aviso por WhatsApp del despacho.
        aviso_setup=(
            "Debes registrar el webhook **orders/fulfilled** en tu tienda apuntando "
            "a la URL de abajo.\n\nEste evento se dispara cuando marcas el pedido como "
            "despachado en Shopify Admin o cuando tu integración de envíos lo marca "
            "automáticamente."
        ),
        aviso_setup_url="https://help.shopify.com/en/manual/orders/notifications/webhooks",
    ),
    # ── Mensajes de error (categoría "error") ────────────────────────────────
    # Todos esenciales — el cliente necesita saber cuándo algo falló para no
    # quedarse esperando. Defaults BYTE-IDÉNTICOS a strings hardcoded previos.
    "error.checkout_no_encontrado": MensajeMeta(
        key="error.checkout_no_encontrado",
        categoria="error",
        titulo="No se encontró pedido al confirmar",
        descripcion=(
            "Se envía cuando el cliente toca 'Confirmar pedido' pero su carrito "
            "se vació o expiró. Invítalo a armar uno nuevo."
        ),
        cuando="Al tocar el botón Confirmar pedido sin carrito activo válido",
        default="🤔 No encontré tu pedido. Vuelve a abrir el catálogo y arma tu pedido de nuevo 🌿",
        placeholders=("negocio",),
        placeholders_requeridos=(),
        puede_desactivarse=False,
    ),
    "error.procesar_pedido_fallo": MensajeMeta(
        key="error.procesar_pedido_fallo",
        categoria="error",
        titulo="No se pudo procesar el pedido (productos agotados)",
        descripcion=(
            "Se envía cuando el sistema no logra crear el pedido en la tienda. "
            "Causa frecuente: stock agotado mientras el cliente armaba el carrito."
        ),
        cuando="Al fallar la creación del pedido en Shopify desde el catálogo nativo",
        default=(
            "😔 No pude procesar tu pedido. Algunos productos "
            "pueden haberse agotado. ¿Quieres que lo revisemos juntos?"
        ),
        placeholders=("negocio",),
        placeholders_requeridos=(),
        puede_desactivarse=False,
    ),
    "error.productos_no_reconocidos": MensajeMeta(
        key="error.productos_no_reconocidos",
        categoria="error",
        titulo="No se reconocieron los productos del pedido",
        descripcion=(
            "Se envía cuando los items del pedido no se pudieron mapear a "
            "productos válidos del catálogo. Pide al cliente que aclare qué quiere."
        ),
        cuando="Al recibir un pedido del catálogo con productos que no coinciden",
        default=(
            "😔 No reconocí los productos de tu pedido. "
            "¿Puedes escribirme qué quieres y te ayudo?"
        ),
        placeholders=("negocio",),
        placeholders_requeridos=(),
        puede_desactivarse=False,
    ),
    "error.excepcion_pedido": MensajeMeta(
        key="error.excepcion_pedido",
        categoria="error",
        titulo="Error general procesando un pedido",
        descripcion=(
            "Mensaje genérico cuando ocurre un error inesperado procesando "
            "el pedido del cliente. Invítalo a reintentar de forma conversacional."
        ),
        cuando="Al capturar una excepción inesperada en el flujo de pedido",
        default=(
            "😔 Tuve un problema procesando tu pedido. "
            "¿Me puedes decir qué quieres y te ayudo enseguida?"
        ),
        placeholders=("negocio",),
        placeholders_requeridos=(),
        puede_desactivarse=False,
    ),
    "error.checkout_no_generado": MensajeMeta(
        key="error.checkout_no_generado",
        categoria="error",
        titulo="No se pudo generar el pago",
        descripcion=(
            "Se envía cuando Andrea generó el pedido pero el checkout de "
            "Shopify falló (por ejemplo, producto agotado entre tanto). "
            "Invita al cliente a revisar el catálogo nuevamente."
        ),
        cuando="Cuando Andrea emite el pedido pero el checkout no se puede crear",
        default=(
            "😔 Disculpa, no pude generar tu pedido en este momento. "
            "Es posible que algún producto del carrito se haya agotado "
            "mientras conversábamos. ¿Quieres que revisemos juntos qué "
            "hay disponible ahora?"
        ),
        placeholders=("negocio",),
        placeholders_requeridos=(),
        puede_desactivarse=False,
    ),
    "cart.estado3_falta_minimo": MensajeMeta(
        key="cart.estado3_falta_minimo",
        categoria="cart",
        titulo="Recordatorio cuando falta para el pedido mínimo",
        descripcion=(
            "Mensaje del seguimiento automático cuando el cliente tiene "
            "productos en el carrito pero aún no alcanza tu pedido mínimo. "
            "Si tu negocio no maneja pedido mínimo, puedes apagarlo."
        ),
        cuando="A los pocos minutos de que el cliente deja el carrito por debajo del mínimo",
        default=(
            "Hola 😊 Tienes ${total} en tu carrito, ¡casi llegas!\n\n"
            "Te faltan *${falta}* para el pedido mínimo de *${minimo}*."
        ),
        placeholders=("total", "falta", "minimo", "negocio"),
        placeholders_requeridos=(),
        # Sí desactivable — algunos negocios no quieren insistir si no llega al mínimo
    ),
    "cart.estado4_timer": MensajeMeta(
        key="cart.estado4_timer",
        categoria="cart",
        titulo="Recordatorio cuando el carrito ya alcanzó el mínimo (seguimiento)",
        descripcion=(
            "Recordatorio automático cuando el cliente tiene un carrito "
            "que supera el pedido mínimo pero no lo confirmó. Es la oportunidad "
            "de invitarlo a cerrar la compra o agregar más productos."
        ),
        cuando="Tras unos minutos de inactividad con un carrito sobre el mínimo",
        default="🛒 Tienes *${total}* en tu carrito!\n\n¿Quieres agregar algo más o confirmar tu pedido?",
        placeholders=(
            "total", "minimo", "envio_gratis", "falta_envio_gratis",
            "descuento_codigo", "descuento_pct", "descuento_umbral", "negocio",
        ),
        placeholders_requeridos=(),
        # Sí desactivable — algunos negocios no quieren seguimiento automático
    ),
    "cart.bienvenida_catalogo": MensajeMeta(
        key="cart.bienvenida_catalogo",
        categoria="cart",
        titulo="Bienvenida al mostrar el catálogo",
        descripcion=(
            "Texto que aparece junto al catálogo de productos. Puedes usar "
            "los placeholders para que el texto refleje SIEMPRE tu "
            "configuración actual (pedido mínimo, promoción vigente, etc.) "
            "sin tener que reescribirlo cada vez que cambies algo."
        ),
        cuando="Cada vez que el agente muestra el catálogo al cliente",
        default="📦 Pedido mínimo ${minimo}",
        placeholders=(
            "minimo", "envio_gratis",
            "descuento_codigo", "descuento_pct", "descuento_umbral",
            "negocio",
        ),
        placeholders_requeridos=(),
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
