import os
import yaml
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from agent.tools import obtener_catalogo_shopify
from agent.memory import obtener_cliente, obtener_pedido_pendiente, obtener_carrito_activo

load_dotenv()
logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── Cache del system prompt (se recarga solo si cambia el archivo) ────────────
_prompt_cache: str = ""
_prompt_mtime: float = 0.0
_prompt_config_cache: dict = {}
_PROMPTS_FILE = "config/prompts.yaml"


def _cargar_config() -> dict:
    """Lee prompts.yaml con cache basado en mtime del archivo."""
    global _prompt_cache, _prompt_mtime, _prompt_config_cache
    try:
        mtime = os.path.getmtime(_PROMPTS_FILE)
        if mtime == _prompt_mtime and _prompt_config_cache:
            return _prompt_config_cache
        with open(_PROMPTS_FILE, "r", encoding="utf-8") as f:
            _prompt_config_cache = yaml.safe_load(f) or {}
        _prompt_mtime = mtime
        _prompt_cache = _prompt_config_cache.get(
            "system_prompt",
            "Eres Andrea, asistente de Equora Distribuciones. Responde en español."
        )
        logger.info("prompts.yaml recargado desde disco")
        return _prompt_config_cache
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_system_prompt() -> str:
    return _cargar_config().get(
        "system_prompt",
        "Eres Andrea, asistente de Equora Distribuciones. Responde en español."
    )


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


async def generar_respuesta(mensaje: str, historial: list[dict], telefono: str | None = None) -> str:
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    system_prompt = cargar_system_prompt()

    # Inyectar catálogo (desde cache — sin HTTP en cada mensaje)
    catalogo = await obtener_catalogo_shopify()
    if catalogo:
        system_prompt = system_prompt + "\n\n" + catalogo

    if telefono:
        # Inyectar perfil del cliente si ya compró antes
        cliente = await obtener_cliente(telefono)
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

        # Inyectar carrito activo (persistido en BD — nunca se pierde por largo historial)
        carrito = await obtener_carrito_activo(telefono)
        if carrito:
            bloque_c = ["\n\n## Carrito actual del cliente (persistido en sistema)"]
            bloque_c.append(
                "IMPORTANTE: este es el carrito REAL y COMPLETO del cliente. "
                "Úsalo siempre como fuente de verdad — no lo reconstruyas desde el historial."
            )
            total_carrito = 0
            for item in carrito:
                subtotal = item.get("subtotal", 0)
                total_carrito += subtotal
                bloque_c.append(
                    f"- {item.get('cantidad', 1)}x {item.get('producto', '')} "
                    f"({item.get('presentacion', '')}) → ${subtotal:,}"
                )
            bloque_c.append(f"Total acumulado: ${total_carrito:,}")
            system_prompt += "\n".join(bloque_c)

        # Inyectar pedido pendiente (checkout generado pero no completado)
        pendiente = await obtener_pedido_pendiente(telefono)
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

    mensajes = [{"role": m["role"], "content": m["content"]} for m in historial]
    mensajes.append({"role": "user", "content": mensaje})

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5",  # Más rápido que sonnet para respuestas conversacionales
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
