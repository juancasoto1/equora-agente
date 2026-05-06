import os
import re
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.providers import obtener_proveedor
from agent.providers.twilio import obtener_url_imagen
from agent.tools import guardar_pedido_en_sheet

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    yield


app = FastAPI(
    title="AgentKit — Andrea (Equora Distribuciones)",
    version="1.0.0",
    lifespan=lifespan
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


@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            logger.info(f"Mensaje de {msg.telefono}: {msg.texto}")

            historial = await obtener_historial(msg.telefono)
            respuesta = await generar_respuesta(msg.texto, historial)

            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)

            # Detectar y procesar marcador de pedido confirmado
            numero_pedido = None
            match_pedido = re.search(r'\[\[PEDIDO:(.*?)\]\]', respuesta, re.DOTALL)
            if match_pedido:
                try:
                    datos_pedido = json.loads(match_pedido.group(1))
                    numero_pedido = await guardar_pedido_en_sheet(msg.telefono, datos_pedido)
                    logger.info(f"Pedido {numero_pedido} guardado en sheet para {msg.telefono}")
                except Exception as e:
                    logger.error(f"Error procesando datos del pedido: {e}")
                # Eliminar el marcador antes de enviar el mensaje al cliente
                respuesta = re.sub(r'\s*\[\[PEDIDO:.*?\]\]', '', respuesta, flags=re.DOTALL).strip()

            await proveedor.enviar_mensaje(msg.telefono, respuesta)

            # Enviar número de pedido al cliente si se generó uno
            if numero_pedido:
                msg_pedido = f"🧾 *Número de pedido:* {numero_pedido}\nGuárdalo para cualquier consulta sobre tu pedido."
                await proveedor.enviar_mensaje(msg.telefono, msg_pedido)

            # Enviar imagen del producto si el cliente preguntó por uno específico
            url_imagen = obtener_url_imagen(msg.texto)
            if url_imagen and hasattr(proveedor, "enviar_imagen"):
                await proveedor.enviar_imagen(msg.telefono, url_imagen)
                logger.info(f"Imagen enviada a {msg.telefono}: {url_imagen}")

            logger.info(f"Respuesta a {msg.telefono}: {respuesta}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
