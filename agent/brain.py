import os
import json
import time
import yaml
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from agent.tools import obtener_catalogo_shopify, obtener_costo_envio, obtener_umbral_envio_gratis
from agent.memory import (
    obtener_cliente, obtener_pedido_pendiente, obtener_carrito_activo, get_config_value,
    obtener_perfil_enriquecido, get_agent_modules, obtener_pipeline_activo, obtener_deal_abierto,
    obtener_integration_config,
)

load_dotenv()
logger = logging.getLogger("agentkit")

# #78 — el SDK de Anthropic mantiene un AsyncAnthropic (y su pool de conexiones
# httpx subyacente) vivo por toda la vida del proceso. En un container de
# Railway corriendo semanas, ese pool puede acumular conexiones "stale" que
# el servidor remoto ya cerró silenciosamente. Recreamos el cliente cada
# CLIENT_MAX_AGE_SEG (default 6h) en vez de confiar en uno solo para siempre.
CLIENT_MAX_AGE_SEG = int(os.getenv("AI_CLIENT_MAX_AGE_SEG", 6 * 3600))
_client: AsyncAnthropic | None = None
_client_created_at: float = 0.0


def _get_client() -> AsyncAnthropic:
    """Retorna el cliente Anthropic, recreándolo si pasó CLIENT_MAX_AGE_SEG."""
    global _client, _client_created_at
    ahora = time.monotonic()
    if _client is None or (ahora - _client_created_at) > CLIENT_MAX_AGE_SEG:
        _client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        _client_created_at = ahora
        logger.info("[anti-stale] Cliente Anthropic (re)creado")
    return _client

# ── Cache del system prompt desde archivo (se recarga si cambia el archivo) ───
_prompt_config_cache: dict = {}
_prompt_mtime: float = 0.0
_PROMPTS_FILE = "config/prompts.yaml"


def _cargar_config() -> dict:
    """Lee prompts.yaml con cache basado en mtime del archivo."""
    global _prompt_mtime, _prompt_config_cache
    try:
        mtime = os.path.getmtime(_PROMPTS_FILE)
        if mtime == _prompt_mtime and _prompt_config_cache:
            return _prompt_config_cache
        with open(_PROMPTS_FILE, "r", encoding="utf-8") as f:
            _prompt_config_cache = yaml.safe_load(f) or {}
        _prompt_mtime = mtime
        logger.info("prompts.yaml recargado desde disco")
        return _prompt_config_cache
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


async def cargar_system_prompt(agent_id: int = 1) -> str:
    """
    Carga el system prompt con esta prioridad:
    1. BD (SYSTEM_PROMPT) — editado desde el panel de configuración
    2. config/prompts.yaml — archivo base del repositorio
    Luego reemplaza {VARIABLES} del negocio y las tarifas de envío.
    """
    # ── 1. BD primero ──────────────────────────────────────────────────────────
    db_prompt = await get_config_value("SYSTEM_PROMPT", agent_id)
    if db_prompt:
        prompt = db_prompt
        logger.debug("System prompt cargado desde BD")
    else:
        prompt = _cargar_config().get(
            "system_prompt",
            "Eres un asistente virtual. Responde en español."
        )
        logger.debug("System prompt cargado desde prompts.yaml")

    # ── 2. Reemplazar variables del negocio {KEY} ───────────────────────────
    db_vars_json = await get_config_value("BUSINESS_VARS", agent_id)
    if db_vars_json:
        try:
            business_vars = json.loads(db_vars_json)
            for key, val in business_vars.items():
                prompt = prompt.replace("{" + key + "}", str(val))
        except Exception as e:
            logger.warning(f"Error al procesar BUSINESS_VARS: {e}")

    # ── 3. Reemplazar tarifas de envío (variables de sistema) ──────────────
    costo_fmt = f"{obtener_costo_envio():,}".replace(",", ".")
    gratis_fmt = f"{obtener_umbral_envio_gratis():,}".replace(",", ".")
    prompt = prompt.replace("{COSTO_ENVIO}", costo_fmt)
    prompt = prompt.replace("{ENVIO_GRATIS}", gratis_fmt)

    # ── 4. Pedido mínimo (configurable por agente desde el panel) ──────────
    # Si PEDIDO_MINIMO está configurado y > 0, se reemplaza con formato $50.000.
    # Si no está configurado o es 0, se reemplaza con string vacío (sin mínimo).
    try:
        pedido_min_raw = await get_config_value("PEDIDO_MINIMO", agent_id) or ""
        pedido_min_val = int(float(pedido_min_raw)) if pedido_min_raw else 0
    except Exception:
        pedido_min_val = 0
    pedido_min_fmt = f"${pedido_min_val:,}".replace(",", ".") if pedido_min_val > 0 else ""
    prompt = prompt.replace("{PEDIDO_MINIMO}", pedido_min_fmt)

    return prompt


def obtener_mensaje_error() -> str:
    return _cargar_config().get(
        "error_message",
        "Lo siento, estoy teniendo un problemita técnico. Por favor intenta de nuevo en unos minuticos."
    )


def obtener_mensaje_fallback() -> str:
    return _cargar_config().get(
        "fallback_message",
        "Disculpa, no entendí bien tu mensaje. ¿Me puedes contar con más detalle en qué te puedo ayudar? 😊"
    )


async def _cargar_modulos(agent_id: int = 1) -> dict:
    """Devuelve los módulos activos desde BD. Si no hay config, todos activos por defecto."""
    raw = await get_config_value("ACTIVE_MODULES", agent_id)
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _mod(modules: dict, key: str) -> bool:
    """True si el módulo está activo (default True para compatibilidad hacia atrás)."""
    return modules.get(key, True)


async def generar_respuesta(
    mensaje: str,
    historial: list[dict],
    telefono: str | None = None,
    contexto_campana: dict | None = None,
    agent_id: int = 1,
) -> str:
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    system_prompt = await cargar_system_prompt(agent_id)
    modules       = await _cargar_modulos(agent_id)

    # ── Escalación a humano — garantizada para todos los agentes ─────────────
    # Si el prompt del agente no incluye instrucciones de [[ESCALAR:...]]
    # (p.ej. agentes demo / nuevos con prompt personalizado), las inyectamos
    # aquí para que la funcionalidad esté siempre disponible.
    if "[[ESCALAR" not in system_prompt:
        system_prompt += """

## Transferir a equipo humano
Cuando el cliente pida hablar con una persona, haya un reclamo, devolución, pregunta técnica que no puedes responder, o cualquier situación que requiera atención humana: escribe tu respuesta normal y añade AL FINAL (en línea aparte, NUNCA lo menciones al cliente) este marcador:

[[ESCALAR:{"motivo":"<describe en 1 línea>","urgencia":"alta|media|normal","nombre_cliente":"<nombre si lo sabes, vacío si no>","contexto":"<2-4 líneas con todos los detalles para el equipo>"}]]

REGLA CRÍTICA: el contenido entre [[ESCALAR: y ]] DEBE ser JSON válido con comillas dobles. Nunca texto plano. Usa exactamente los campos: motivo, urgencia, nombre_cliente, contexto."""

    # ── Contexto de campaña de difusión ───────────────────────────────────────
    if contexto_campana and _mod(modules, "campaign_context"):
        nombre        = contexto_campana.get("campaign_name", "")
        template_name = contexto_campana.get("template_name", "")
        horas         = contexto_campana.get("horas_ago", 0)
        tiempo_str    = f"hace {horas} hora{'s' if horas != 1 else ''}" if horas > 0 else "hace menos de una hora"

        id_campana = nombre
        if template_name and template_name != nombre:
            id_campana = f"{nombre} (plantilla: {template_name})"

        system_prompt += f"""

## ⚠️ CONTEXTO OBLIGATORIO: el cliente responde a una difusión tuya
Enviaste un mensaje de difusión a este número {tiempo_str}.
Campaña: "{id_campana}"

REGLAS ABSOLUTAS — NO las ignores bajo ninguna circunstancia:
1. ESTÁ PROHIBIDO preguntarle al cliente "¿qué producto te interesa?", "¿sobre qué producto preguntas?", "¿vienes de algún anuncio?" o cualquier variante. Ya sabes qué producto es: el de la campaña indicada arriba.
2. Su mensaje (precio, presentaciones, cómo comprar, disponibilidad, etc.) se refiere AL PRODUCTO DE ESA CAMPAÑA. Responde directamente sobre ese producto.
3. Si preguntan el precio → da el precio de ese producto ya, sin preguntar más.
4. Si preguntan presentaciones → lista las presentaciones de ese producto ya.
5. Solo pide aclaración si el cliente menciona explícitamente un producto DIFERENTE al de la campaña."""

    # ── Catálogo Shopify (toggle: shopify_catalog) ────────────────────────────
    if _mod(modules, "shopify_catalog"):
        catalogo = await obtener_catalogo_shopify()
        if catalogo:
            system_prompt = system_prompt + "\n\n" + catalogo

    # ── Catálogo nativo Voco (toggle: voco_catalog) ───────────────────────────
    if _mod(modules, "voco_catalog"):
        from agent.tools import obtener_catalogo_voco_texto
        cat_voco = await obtener_catalogo_voco_texto(agent_id)
        if cat_voco:
            system_prompt = system_prompt + "\n\n" + cat_voco

    if telefono:
        # ── Perfil enriquecido del cliente (#65) ──────────────────────────────
        # Señales compactas que más cambian la estrategia de respuesta:
        # segmento (engagement), tier (lifetime value), ticket abierto.
        # Sin esto, el LLM trata a un VIP con 12 pedidos igual que a alguien
        # que escribe por primera vez — pierde la oportunidad de adaptar tono.
        if _mod(modules, "client_memory"):
            perfil = await obtener_perfil_enriquecido(telefono, agent_id)
            partes = []
            seg = perfil["segmento"]
            tier = perfil["tier"]
            dias = perfil["dias_inactivo"]

            if seg == "nuevo":
                partes.append("Cliente NUEVO: primera vez escribiendo. Explica el flujo con claridad y bájale fricción al primer pedido.")
            elif seg == "activo":
                partes.append(f"Cliente ACTIVO (último contacto hace {dias}d). Trato cercano, ya conoce el flujo.")
            elif seg == "tibio":
                partes.append(f"Cliente TIBIO (sin escribir hace {dias}d). Reactivación amable, recuérdale por qué le gustaron tus productos.")
            elif seg == "frio":
                partes.append(f"Cliente FRÍO (sin escribir hace {dias}d). Bienvenida calurosa, evita asumir que recuerda detalles de antes.")

            if tier == "vip":
                partes.append("Es VIP (5+ pedidos). Reconoce su recurrencia, trato premium, ofrécele lo mejor.")
            elif tier == "recurrente":
                partes.append("Es comprador RECURRENTE. Salta intro larga, ve directo a lo que necesita.")

            if perfil["ticket_abierto"]:
                partes.append("⚠️ TIENE UN TICKET DE SOPORTE ABIERTO con un humano. NO intentes cerrar venta nueva — pregunta si necesita algo nuevo o sigue con su caso pendiente.")

            if perfil["es_opt_out"]:
                partes.append("Está en opt-out de difusiones — no le ofrezcas suscribirse a campañas.")

            if partes:
                system_prompt += "\n\n## Perfil del cliente (resumen para adaptar tono)\n- " + "\n- ".join(partes)

        # ── Perfil del cliente (toggle: client_memory) ────────────────────────
        if _mod(modules, "client_memory"):
            cliente = await obtener_cliente(telefono, agent_id)
            if cliente and cliente.get("nombres"):
                bloque = ["\n\n## Cliente conocido (ya compró antes)"]
                bloque.append(f"Pedidos previos: {cliente.get('pedidos_realizados', 0)}")
                for campo in ("nombres", "apellidos", "razon_social", "cc_nit",
                              "direccion", "barrio", "ciudad", "departamento", "email"):
                    valor = cliente.get(campo, "")
                    if valor:
                        bloque.append(f"- {campo}: {valor}")
                bloque.append(
                    "\nINSTRUCCIONES con cliente conocido:\n"
                    "- Salúdalo por su nombre.\n"
                    "- El flujo de pedido es el mismo: arma el carrito, muestra resumen, "
                    "confirma. Los datos de entrega los maneja Shopify."
                )
                system_prompt += "\n".join(bloque)

        # ── Carrito SIEMPRE inyectado si existe ──────────────────────────────
        # ANTES: dependía del toggle cart_orders. Si el cliente vaciaba o
        # mostraba el carrito pero el toggle estaba OFF, Andrea inventaba.
        # AHORA: si hay carrito en BD, Andrea SIEMPRE lo ve — fuente de verdad
        # única. El toggle cart_orders solo controla si Andrea PUEDE armar
        # pedidos nuevos, no si ve el estado actual del carrito.
        carrito = await obtener_carrito_activo(telefono, agent_id)
        if carrito:
            bloque_c = ["\n\n## Carrito actual del cliente (persistido en sistema)"]
            bloque_c.append(
                "IMPORTANTE: este es el carrito REAL y COMPLETO del cliente. "
                "Úsalo siempre como fuente de verdad — no lo reconstruyas desde el historial. "
                "Si el cliente pide ver/vaciar el carrito, recuérdale que use los BOTONES "
                "que aparecen automáticamente en cada mensaje del sistema."
            )
            total_carrito = 0
            origen_wa = False
            for item in carrito:
                subtotal = item.get("subtotal", 0)
                total_carrito += subtotal
                if item.get("retailer_id"):
                    origen_wa = True
                bloque_c.append(
                    f"- {item.get('cantidad', 1)}x {item.get('producto', '')} "
                    f"({item.get('presentacion', '')}) → ${subtotal:,}"
                )
            bloque_c.append(f"Total acumulado: ${total_carrito:,}")

            # ── REGLA CRÍTICA DE FLUJO ──
            # Si el carrito tiene retailer_id, el cliente armó pedido vía catálogo
            # nativo de WhatsApp. Andrea NO debe sugerirle ir a la web — los carritos
            # de WhatsApp y de la web no se comunican, mezclarlos confunde al cliente.
            if origen_wa:
                bloque_c.append(
                    "\n## ⚠️ FLUJO ACTIVO: WhatsApp (catálogo nativo)\n"
                    "El cliente está armando su pedido en el catálogo de WhatsApp.\n\n"
                    "REGLAS ABSOLUTAS de este flujo:\n"
                    "1. NO uses [[TIENDA:]] ni [[TIENDA:producto]] en este chat — los\n"
                    "   carritos de WhatsApp y la web NO se comunican.\n"
                    "2. Si el cliente pregunta '¿qué más tienes?' o quiere ver más\n"
                    "   productos: usa [[PRODUCTO:nombre]] específicos (que muestran\n"
                    "   la tarjeta del catálogo) o sugiérele tocar el catálogo que ya\n"
                    "   le enviaste arriba.\n"
                    "3. Si el cliente quiere cambiar al flujo web: explícale claramente\n"
                    "   que perderá su carrito actual de WhatsApp y deberá armarlo de\n"
                    "   nuevo en la web. Solo entonces puedes usar [[TIENDA:]].\n"
                    "4. NO crees el pedido manualmente con [[PEDIDO:]] — el cliente lo\n"
                    "   confirma desde el catálogo nativo de WhatsApp tocando 'Ver carrito'\n"
                    "   y luego 'Enviar pedido'. El sistema procesa eso automáticamente.\n"
                )
            system_prompt += "\n".join(bloque_c)

        # Pedido pendiente sigue dependiendo del módulo cart_orders
        if _mod(modules, "cart_orders"):
            pendiente = await obtener_pedido_pendiente(telefono, agent_id)
            if pendiente:
                bloque_p = ["\n\n## Pedido pendiente sin completar"]
                bloque_p.append("Este cliente confirmó hace poco un pedido pero NO completó el "
                                "checkout en Shopify. Su carrito quedó así:")
                for item in pendiente:
                    bloque_p.append(
                        f"- {item.get('cantidad', 1)}x {item.get('producto', '')} "
                        f"({item.get('presentacion', '')})"
                    )
                bloque_p.append(
                    "\nINSTRUCCIONES:\n"
                    "- En tu primer mensaje, pregúntale si quiere retomar este pedido o "
                    "armar uno nuevo.\n"
                    "- Si quiere retomarlo, salta directo al PASO 4 (resumen + botón "
                    "Confirmar pedido) con esos productos.\n"
                    "- Si quiere algo distinto, ignora el pendiente y arranca de cero."
                )
                system_prompt += "\n".join(bloque_p)

        # ── Pipeline (mini-CRM) — Fase 1, ver BACKLOG.md ──────────────────────
        # Gateado al módulo "pipeline" de Agent.modules_json (Sprint A), NO al
        # sistema viejo de ACTIVE_MODULES que usa _mod() — son dos sistemas
        # de toggles distintos, ver comentario sobre DEFAULT_MODULES en memory.py.
        if (await get_agent_modules(agent_id)).get("pipeline", False):
            pipeline = await obtener_pipeline_activo(agent_id)
            stages = pipeline.get("stages") or []
            if stages:
                deal_abierto = await obtener_deal_abierto(agent_id, pipeline["id"], telefono)
                bloque_pl = ["\n\n## Pipeline (CRM interno) — revisa esto antes de terminar tu respuesta"]
                bloque_pl.append(
                    "No es opcional: en cada mensaje del cliente, evalúa rápido si cambia su "
                    "intención de compra. Si aplica, agrega [[DEAL_STAGE:Nombre exacto de la "
                    "etapa]] al final de tu respuesta, junto a cualquier otro marcador que ya "
                    "uses ([[PRODUCTO:]], [[TIENDA:]], [[PEDIDO:]] — no son excluyentes)."
                )
                bloque_pl.append(f"\nEtapas disponibles, en orden: {' → '.join(stages)}")
                if deal_abierto:
                    bloque_pl.append(
                        f"Este cliente YA tiene una oportunidad abierta en la etapa "
                        f"\"{deal_abierto['stage']}\" (valor estimado: ${deal_abierto['valor_cop']:,})."
                    )
                else:
                    bloque_pl.append("Este cliente no tiene ninguna oportunidad abierta todavía.")
                bloque_pl.append(
                    "\nSÍ usa el marcador cuando el cliente:\n"
                    "- pregunta precio o detalles de un producto específico → etapa de calificación\n"
                    "- confirma que quiere comprar / pide cómo pagar → etapa de negociación\n"
                    "- completa el pedido / paga → etapa de ganado\n"
                    "- dice explícitamente que ya no le interesa o se arrepiente → etapa de perdido\n"
                    "\nNO uses el marcador cuando el cliente:\n"
                    "- solo saluda, agradece, o pregunta algo sin relación a comprar (ej. "
                    "'¿hola, cómo estás?', '¿tienen domicilios a tal ciudad?' sin haber mencionado "
                    "un producto) — esto NO es intención de compra todavía, déjalo sin marcador.\n"
                    "- ya está en la etapa correcta y este mensaje no cambia nada\n"
                    "\nReglas adicionales:\n"
                    "- Usa el nombre de la etapa EXACTO de la lista de arriba (copia el texto, "
                    "no traduzcas ni inventes uno nuevo). Si ninguna etapa encaja, no uses el "
                    "marcador.\n"
                    "- Si el cliente ya tiene oportunidad abierta, el marcador la actualiza — no "
                    "se crea una nueva.\n"
                    "- Avanza la etapa con el progreso real de la conversación; no retrocedas sin "
                    "que el cliente lo exprese explícitamente.\n"
                    "- El marcador es invisible para el cliente — nunca menciones \"pipeline\", "
                    "\"etapa\" ni \"oportunidad\" en tu respuesta, son términos internos de Voco."
                )
                system_prompt += "\n".join(bloque_pl)

        # ── Calendly (agendamiento) — Pipeline Fase 2, ver BACKLOG.md ─────────
        # Gateado igual que Pipeline: módulo "calendly" de Agent.modules_json +
        # que el agente realmente tenga un token de Calendly conectado (chequeo
        # local en BD, sin llamar a la API de Calendly en cada mensaje — eso
        # solo pasa cuando el marcador realmente dispara el envío de horarios).
        if (await get_agent_modules(agent_id)).get("calendly", False):
            cal_cfg = await obtener_integration_config(agent_id, "calendly")
            if cal_cfg and cal_cfg.get("api_token"):
                bloque_cal = ["\n\n## Agendamiento de citas — revisa esto antes de terminar tu respuesta"]
                bloque_cal.append(
                    "Si el cliente quiere agendar una cita, reunión o llamada (o pregunta "
                    "por disponibilidad de horario), agrega el marcador "
                    "[[CITA_DISPONIBILIDAD:]] al final de tu respuesta. El sistema se "
                    "encarga de consultar los horarios reales y mandarle una lista para "
                    "elegir — tú NO inventes horarios ni fechas, nunca digas una hora "
                    "específica disponible, eso lo hace el sistema después de tu mensaje.\n"
                    "No uses este marcador si el cliente solo pregunta algo general sobre "
                    "el negocio sin intención de agendar.\n"
                    "CRÍTICO — REGLAS ABSOLUTAS SOBRE CITAS (nunca las ignores):\n"
                    "1. NUNCA generes un mensaje de confirmación, reagendamiento o "
                    "actualización de cita. Esto incluye cualquier variante de '¡Cita "
                    "confirmada!', '¡Cita reagendada!', '¡Cita actualizada!', 'quedó "
                    "agendado', 'reprogramamos para', etc. El sistema genera esos mensajes "
                    "automáticamente — si tú los repites, el cliente recibe duplicados.\n"
                    "2. NUNCA uses el formato ✅ + 📅 + 👤 + 📧 para listar detalles de "
                    "una cita. Ese formato lo produce el sistema, no tú.\n"
                    "3. Si en el historial aparece un mensaje '✅ ¡Tu cita está confirmada!' "
                    "o similar, la cita YA quedó agendada. Solo responde normalmente a lo "
                    "que el cliente pregunte, sin volver a mencionar los detalles de la cita "
                    "a menos que el cliente lo pida explícitamente."
                )
                system_prompt += "\n".join(bloque_cal)

    mensajes = [{"role": m["role"], "content": m["content"]} for m in historial]
    mensajes.append({"role": "user", "content": mensaje})

    try:
        response = await _get_client().messages.create(
            model=os.getenv("AI_MODEL", "claude-haiku-4-5"),  # Configurable desde panel de Configuración
            max_tokens=1024,
            system=system_prompt,
            messages=mensajes
        )
        respuesta = response.content[0].text
        logger.info(
            f"Respuesta generada ({response.usage.input_tokens} in / "
            f"{response.usage.output_tokens} out) modelo={response.model}"
        )
        return respuesta

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error()
