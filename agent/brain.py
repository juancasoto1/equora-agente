import os
import yaml
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from agent.tools import obtener_catalogo_shopify
from agent.memory import obtener_cliente

load_dotenv()
logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def cargar_config_prompts() -> dict:
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_system_prompt() -> str:
    config = cargar_config_prompts()
    return config.get("system_prompt", "Eres Andrea, asistente de Equora Distribuciones. Responde en español.")


def obtener_mensaje_error() -> str:
    config = cargar_config_prompts()
    return config.get("error_message", "Lo siento, estoy teniendo un problemita técnico. Por favor intenta de nuevo en unos minuticos.")


def obtener_mensaje_fallback() -> str:
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpa, no entendí bien tu mensaje. ¿Me puedes contar con más detalle en qué te puedo ayudar? 😊")


async def generar_respuesta(mensaje: str, historial: list[dict], telefono: str | None = None) -> str:
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    system_prompt = cargar_system_prompt()

    # Inyectar catálogo actualizado desde Shopify en tiempo real
    catalogo = await obtener_catalogo_shopify()
    if catalogo:
        system_prompt = system_prompt + "\n\n" + catalogo

    # Inyectar perfil del cliente si ya nos compró antes
    if telefono:
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
                "- Si quiere pedir, NO le pidas los datos otra vez. Pregúntale si quiere "
                "usar los mismos datos de envío de la última vez (resúmelos brevemente).\n"
                "- Si confirma que sí, salta al PASO 5 del flujo de pedido (resumen + "
                "botón confirmar) usando estos datos guardados.\n"
                "- Si quiere cambiar algún dato, pregúntale solo el que va a cambiar."
            )
            system_prompt += "\n".join(bloque)

    mensajes = []
    for msg in historial:
        mensajes.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    mensajes.append({
        "role": "user",
        "content": mensaje
    })

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=mensajes
        )

        respuesta = response.content[0].text
        logger.info(f"Respuesta generada ({response.usage.input_tokens} in / {response.usage.output_tokens} out)")
        return respuesta

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error()
