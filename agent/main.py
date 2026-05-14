import os
import re
import json
import hmac
import hashlib
import base64
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import (
    inicializar_db, guardar_mensaje, obtener_historial,
    guardar_cliente, guardar_pedido_pendiente, limpiar_pedido_pendiente,
    guardar_carrito_activo, limpiar_carrito_activo,
    registrar_mensaje_usuario, registrar_mensaje_asistente,
    marcar_followup_enviado, marcar_cierre_enviado,
    conversaciones_para_followup, conversaciones_para_cierre,
)
from agent.providers import obtener_proveedor
from agent.tools import (
    crear_checkout_shopify,
    obtener_catalogo_shopify,
    obtener_secciones_catalogo,
    obtener_producto_por_retailer_id,
)

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# Configuración de seguimientos automáticos (env vars opcionales)
FOLLOWUP_MIN = int(os.getenv("FOLLOWUP_MIN", 2))   # min sin respuesta del cliente
CIERRE_MIN = int(os.getenv("CIERRE_MIN", 5))       # min después del follow-up
FOLLOWUP_MAX_HORAS = int(os.getenv("FOLLOWUP_MAX_HORAS", 12))
CHECK_INTERVAL_SEG = int(os.getenv("CHECK_INTERVAL_SEG", 30))

MENSAJE_FOLLOWUP = (
    "Hola de nuevo 😊 Veo que andas un poco ocupado/a. "
    "¿Sigues por aquí o prefieres que continuemos en otro momento? "
    "No hay afán, retomamos cuando puedas."
)

MENSAJE_CIERRE = (
    "Te dejo descansar 🤗 Cuando quieras retomar, escríbeme y "
    "seguimos donde nos quedamos. ¡Que tengas un excelente día! 🌿"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    logger.info(
        f"Seguimientos: follow-up a los {FOLLOWUP_MIN} min, "
        f"cierre a los {CIERRE_MIN} min después, ventana max {FOLLOWUP_MAX_HORAS} h"
    )
    seguimiento_task = asyncio.create_task(_loop_seguimientos())
    try:
        yield
    finally:
        seguimiento_task.cancel()
        try:
            await seguimiento_task
        except asyncio.CancelledError:
            pass


async def _loop_seguimientos():
    """Cada CHECK_INTERVAL_SEG revisa conversaciones inactivas y manda
    follow-ups o cierres según corresponda."""
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SEG)
            await _procesar_followups()
            await _procesar_cierres()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error en loop de seguimientos: {e}")


async def _procesar_followups():
    telefonos = await conversaciones_para_followup(FOLLOWUP_MIN, FOLLOWUP_MAX_HORAS)
    for telefono in telefonos:
        try:
            await proveedor.enviar_mensaje(telefono, MENSAJE_FOLLOWUP)
            await guardar_mensaje(telefono, "assistant", MENSAJE_FOLLOWUP)
            await marcar_followup_enviado(telefono)
            logger.info(f"Follow-up enviado a {telefono}")
        except Exception as e:
            logger.error(f"Error enviando follow-up a {telefono}: {e}")


async def _procesar_cierres():
    telefonos = await conversaciones_para_cierre(CIERRE_MIN)
    for telefono in telefonos:
        try:
            await proveedor.enviar_mensaje(telefono, MENSAJE_CIERRE)
            await guardar_mensaje(telefono, "assistant", MENSAJE_CIERRE)
            await marcar_cierre_enviado(telefono)
            logger.info(f"Cierre enviado a {telefono}")
        except Exception as e:
            logger.error(f"Error enviando cierre a {telefono}: {e}")


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


@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            logger.info(f"Mensaje de {msg.telefono}: {msg.texto[:80]}")

            # ── Orden directa desde catálogo nativo WhatsApp ──────────────────
            # El cliente armó su carrito en WhatsApp y confirmó — bypaseamos Claude
            # y creamos el checkout de Shopify directamente.
            if msg.texto.startswith("__ORDEN_CATALOGO__:"):
                await registrar_mensaje_usuario(msg.telefono)
                try:
                    items_raw = json.loads(msg.texto[len("__ORDEN_CATALOGO__:"):])
                    productos = []
                    no_encontrados = []
                    for item in items_raw:
                        rid = item.get("product_retailer_id", "")
                        qty = int(item.get("quantity", 1))
                        info = obtener_producto_por_retailer_id(rid)
                        if not info:
                            # Catálogo puede no estar cargado aún — recargar y reintentar
                            await obtener_catalogo_shopify()
                            info = obtener_producto_por_retailer_id(rid)
                        if info:
                            precio = info["precio_unitario"]
                            productos.append({
                                "producto": info["producto"],
                                "presentacion": info["presentacion"],
                                "cantidad": qty,
                                "precio_unitario": precio,
                                "subtotal": precio * qty,
                            })
                        else:
                            no_encontrados.append(rid)
                            logger.warning(f"retailer_id no encontrado en _sku_map: {rid}")

                    if no_encontrados:
                        logger.error(f"IDs sin mapear: {no_encontrados}. SKUs en Shopify necesarios.")

                    if productos:
                        total = sum(p["subtotal"] for p in productos)
                        datos_pedido = {"productos": productos, "total": total}
                        checkout_url = await crear_checkout_shopify(msg.telefono, datos_pedido)
                        if checkout_url:
                            await guardar_pedido_pendiente(msg.telefono, productos)
                            await limpiar_carrito_activo(msg.telefono)
                            texto_checkout = (
                                "🎉 *¡Pedido recibido!*\n\n"
                                "Toca el botón para confirmar tu dirección de entrega. "
                                "El pago es *contra entrega*. 🌿"
                            )
                            if hasattr(proveedor, "enviar_cta_url"):
                                await proveedor.enviar_cta_url(
                                    msg.telefono, texto_checkout,
                                    "Confirmar entrega", checkout_url
                                )
                            else:
                                await proveedor.enviar_mensaje(
                                    msg.telefono, f"{texto_checkout}\n\n👉 {checkout_url}"
                                )
                        else:
                            await proveedor.enviar_mensaje(
                                msg.telefono,
                                "😔 No pude procesar tu pedido. Algunos productos "
                                "pueden haberse agotado. ¿Quieres que lo revisemos juntos?"
                            )
                    else:
                        await proveedor.enviar_mensaje(
                            msg.telefono,
                            "😔 No reconocí los productos de tu pedido. "
                            "¿Puedes escribirme qué quieres y te ayudo?"
                        )
                except Exception as e:
                    logger.error(f"Error procesando orden catálogo: {e}")
                    await proveedor.enviar_mensaje(
                        msg.telefono,
                        "😔 Tuve un problema procesando tu pedido. "
                        "¿Me puedes decir qué quieres y te ayudo enseguida?"
                    )
                continue  # No pasa por Claude

            # Cliente respondió → resetea timers de seguimiento
            await registrar_mensaje_usuario(msg.telefono)

            historial = await obtener_historial(msg.telefono)
            respuesta = await generar_respuesta(msg.texto, historial, msg.telefono)

            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)
            await registrar_mensaje_asistente(msg.telefono)

            # Procesar marcador de carrito → persistir estado en BD
            respuesta, items_carrito = extraer_marcador_carrito(respuesta)
            if items_carrito is not None:
                try:
                    await guardar_carrito_activo(msg.telefono, items_carrito)
                    logger.info(f"Carrito actualizado para {msg.telefono}: {len(items_carrito)} items")
                except Exception as e:
                    logger.error(f"Error guardando carrito: {e}")

            # Procesar marcador de pedido → crear checkout en Shopify
            checkout_url = None
            checkout_fallo = False
            match_pedido = re.search(r'\[\[PEDIDO:(.*?)\]\]', respuesta, re.DOTALL)
            if match_pedido:
                try:
                    datos_pedido = json.loads(match_pedido.group(1))
                    checkout_url = await crear_checkout_shopify(msg.telefono, datos_pedido)
                    if checkout_url:
                        await guardar_cliente(msg.telefono, datos_pedido)
                        # Guardamos el carrito como pendiente: lo limpia el webhook de Shopify
                        await guardar_pedido_pendiente(
                            msg.telefono, datos_pedido.get("productos", [])
                        )
                        # El carrito activo se vacía: el pedido ya fue generado
                        await limpiar_carrito_activo(msg.telefono)
                        logger.info(f"Checkout Shopify creado para {msg.telefono}")
                    else:
                        checkout_fallo = True
                        logger.error(f"No se pudo crear checkout Shopify para {msg.telefono}")
                except Exception as e:
                    checkout_fallo = True
                    logger.error(f"Error procesando pedido: {e}")
                respuesta = re.sub(r'\s*\[\[PEDIDO:.*?\]\]', '', respuesta, flags=re.DOTALL).strip()

            # Procesar marcador de escalación → notificar al equipo
            datos_escalacion = None
            match_escalar = re.search(r'\[\[ESCALAR:(.*?)\]\]', respuesta, re.DOTALL)
            if match_escalar:
                try:
                    datos_escalacion = json.loads(match_escalar.group(1))
                except Exception as e:
                    logger.error(f"Marcador ESCALAR inválido: {e}")
                respuesta = re.sub(r'\s*\[\[ESCALAR:.*?\]\]', '', respuesta, flags=re.DOTALL).strip()

            # Extraer marcadores interactivos ANTES de enviar el texto
            respuesta, datos_catalogo_cat = extraer_marcador_catalogo_cat(respuesta)
            respuesta, datos_botones = extraer_marcador_botones(respuesta)
            respuesta, datos_lista = extraer_marcador_lista(respuesta)

            # Enviar texto primero
            if respuesta:
                await proveedor.enviar_mensaje(msg.telefono, respuesta)

            # Catálogo nativo WhatsApp (product_list con fotos reales)
            if datos_catalogo_cat and hasattr(proveedor, "enviar_catalogo_productos"):
                categoria = datos_catalogo_cat.get("categoria")
                secciones = obtener_secciones_catalogo(categoria)
                if secciones:
                    header = categoria or "Catálogo Biotú 🌿"
                    cuerpo = "Selecciona los productos que quieres, ajusta las cantidades y confirma tu pedido."
                    cat_enviado = await proveedor.enviar_catalogo_productos(
                        msg.telefono, header, cuerpo, secciones
                    )
                    if cat_enviado:
                        logger.info(f"Catálogo nativo '{categoria}' enviado a {msg.telefono}")
                    else:
                        logger.warning(f"Catálogo nativo falló, sin fallback para {msg.telefono}")
                else:
                    logger.warning(f"Sin secciones para categoría '{categoria}'")

            # Luego enviar mensajes interactivos
            if datos_botones and hasattr(proveedor, "enviar_botones"):
                try:
                    await proveedor.enviar_botones(
                        msg.telefono,
                        datos_botones.get("texto", ""),
                        datos_botones.get("botones", [])
                    )
                    logger.info(f"Botones enviados a {msg.telefono}")
                except Exception as e:
                    logger.error(f"Error enviando botones: {e}")

            if datos_lista and hasattr(proveedor, "enviar_lista"):
                lista_enviada = False
                try:
                    lista_enviada = await proveedor.enviar_lista(
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
                        await proveedor.enviar_mensaje(msg.telefono, fallback_text[:4000])
                        logger.info(f"Fallback texto de lista enviado a {msg.telefono}")

            # Enviar link de checkout de Shopify si se generó
            if checkout_url:
                texto_checkout = (
                    "🧾 *Tu pedido está listo*\n\n"
                    "Toca el botón para confirmar tu dirección de entrega. "
                    "El pago se realiza *contra entrega*. En cuanto registres tus datos, "
                    "te confirmo aquí mismo el número de tu pedido. 🌿"
                )
                enviado_cta = False
                if hasattr(proveedor, "enviar_cta_url"):
                    try:
                        enviado_cta = await proveedor.enviar_cta_url(
                            msg.telefono, texto_checkout, "Confirmar entrega", checkout_url
                        )
                    except Exception as e:
                        logger.error(f"Error enviando cta_url: {e}")
                if not enviado_cta:
                    await proveedor.enviar_mensaje(
                        msg.telefono, f"{texto_checkout}\n\n👉 {checkout_url}"
                    )

            # Si la creación del checkout falló (stock agotado, producto no
            # mapeado, etc.) avísale al cliente en vez de quedarnos mudos
            if checkout_fallo:
                await proveedor.enviar_mensaje(
                    msg.telefono,
                    "😔 Disculpa, no pude generar tu pedido en este momento. "
                    "Es posible que algún producto del carrito se haya agotado "
                    "mientras conversábamos. ¿Quieres que revisemos juntos qué "
                    "hay disponible ahora?"
                )

            # Notificar al equipo si Andrea decidió escalar
            if datos_escalacion:
                await _notificar_escalacion(msg.telefono, datos_escalacion)

            logger.info(f"Respuesta a {msg.telefono}: {respuesta}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
ADMIN_WHATSAPP_NUMBERS = [
    n.strip() for n in os.getenv("ADMIN_WHATSAPP_NUMBERS", "").split(",") if n.strip()
]


async def _notificar_escalacion(telefono_cliente: str, datos: dict):
    """Envía un mensaje a los administradores con el contexto de la escalación."""
    if not ADMIN_WHATSAPP_NUMBERS:
        logger.warning("ADMIN_WHATSAPP_NUMBERS no configurado — escalación no se notifica")
        return

    motivo = datos.get("motivo", "sin especificar")
    contexto = datos.get("contexto", "")
    urgencia = datos.get("urgencia", "normal")
    cliente_nombre = datos.get("nombre_cliente", "")

    mensaje = (
        f"🚨 *Escalación Andrea Bot*\n\n"
        f"*Motivo:* {motivo}\n"
        f"*Urgencia:* {urgencia}\n"
        f"*Cliente:* {cliente_nombre or 'desconocido'}\n"
        f"*WhatsApp cliente:* +{telefono_cliente}\n\n"
        f"*Contexto:*\n{contexto}\n\n"
        f"Responde al cliente desde el WhatsApp Business o llámalo directamente."
    )

    for admin in ADMIN_WHATSAPP_NUMBERS:
        try:
            await proveedor.enviar_mensaje(admin, mensaje)
            logger.info(f"Escalación notificada a admin {admin}")
        except Exception as e:
            logger.error(f"Error notificando escalación a {admin}: {e}")


def _verificar_hmac_shopify(body: bytes, hmac_header: str) -> bool:
    if not SHOPIFY_WEBHOOK_SECRET:
        # Sin secret configurado, dejamos pasar (útil para pruebas iniciales)
        logger.warning("SHOPIFY_WEBHOOK_SECRET no configurado — saltando verificación HMAC")
        return True
    digest = base64.b64encode(
        hmac.new(SHOPIFY_WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(digest, hmac_header or "")


def _normalizar_telefono(valor: str | None) -> str | None:
    """Quita +, espacios, guiones — deja solo dígitos."""
    if not valor:
        return None
    digitos = re.sub(r"\D", "", str(valor))
    return digitos or None


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

    if not _verificar_hmac_shopify(body, hmac_header):
        logger.error(f"HMAC inválido en shopify-webhook (topic={topic})")
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

    if not telefono or not numero:
        logger.warning(f"Sin teléfono o número de orden — no se notifica (telefono={telefono}, numero={numero})")
        return {"status": "ok"}

    try:
        total_int = int(float(total))
    except Exception:
        total_int = 0

    # Guardar/actualizar cliente con los datos que llegaron en la orden
    datos_cliente = _extraer_datos_cliente(payload)
    if any(datos_cliente.values()):
        try:
            await guardar_cliente(telefono, datos_cliente)
            logger.info(f"Cliente {telefono} guardado/actualizado desde Shopify")
        except Exception as e:
            logger.error(f"Error guardando cliente desde webhook: {e}")

    # Cliente completó el checkout → ya no hay carrito pendiente
    if topic in ("orders/create", "orders/paid"):
        try:
            await limpiar_pedido_pendiente(telefono)
        except Exception as e:
            logger.error(f"Error limpiando pedido pendiente: {e}")

    if topic == "orders/fulfilled":
        # Shopify fulfillment puede traer tracking — si está, lo incluimos
        fulfillments = payload.get("fulfillments") or []
        tracking_num = ""
        tracking_url = ""
        if fulfillments:
            f0 = fulfillments[0]
            tracking_num = f0.get("tracking_number") or ""
            tracking_url = f0.get("tracking_url") or ""

        extra_tracking = ""
        if tracking_num:
            extra_tracking = f"\n📦 Guía: *{tracking_num}*"
        if tracking_url:
            extra_tracking += f"\n🔗 Seguimiento: {tracking_url}"

        mensaje = (
            f"🚚 *¡Tu pedido está listo y va en camino!*\n\n"
            f"Pedido *{nombre_orden}* preparado y despachado.{extra_tracking}\n\n"
            f"Recuerda tener los *${total_int:,}* listos para el pago contra entrega. "
            f"¡Gracias por confiar en Equora! 🌿"
        )
    elif topic == "orders/paid":
        mensaje = (
            f"💰 *¡Pago registrado!*\n\n"
            f"Pedido: *{nombre_orden}*  ·  Total: *${total_int:,}*\n\n"
            f"Pronto sale en camino. ¡Gracias por confiar en Equora! 🌿"
        )
    else:
        mensaje = (
            f"✅ *¡Pedido confirmado!*\n\n"
            f"🧾 Número de pedido: *{nombre_orden}*\n"
            f"💰 Total: *${total_int:,}*  (pago contra entrega)\n\n"
            f"Ya estamos preparando tu pedido. Te avisamos cuando vaya en camino. "
            f"¡Gracias por confiar en Equora! 🌿"
        )

    try:
        await proveedor.enviar_mensaje(telefono, mensaje)
        logger.info(f"Confirmación {topic} enviada a {telefono} ({nombre_orden})")
    except Exception as e:
        logger.error(f"Error enviando confirmación a {telefono}: {e}")

    return {"status": "ok"}
