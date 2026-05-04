import os
import logging
import base64
import httpx
from urllib.parse import quote
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")

# Mapa producto → nombre del archivo de imagen en equoradistribuciones.com
IMAGENES_PRODUCTOS = {
    "lavaloza pro":         "Lavaloza Liq Antibacterial PRO Atom 500ml.png",
    "lavaloza antibacterial pro": "Lavaloza Liq Antibacterial PRO Atom 500ml.png",
    "lavaloza":             "Lavaloza Liq Antibacterial Atom 500ml.png",
    "jabon manos":          "Jabón Manos y Cuerpo Aconcagua Dispensador 500ml.png",
    "jabón manos":          "Jabón Manos y Cuerpo Aconcagua Dispensador 500ml.png",
    "suavizante":           "Suavizante de Ropa Bolsa DP 500ml-1L.png",
    "detergente ropa blanca": "Detergente Liq RB DP 500ml-1L.png",
    "detergente blanca":    "Detergente Liq RB DP 500ml-1L.png",
    "detergente ropa color": "Detergente Liq RC DP 500ml-1L.png",
    "detergente color":     "Detergente Liq RC DP 500ml-1L.png",
    "detergente delicada":  "Detergente Ropa Delicada DP 500ml-1L.png",
    "detergente multiusos": "Detergente Multiusos DP 500ml-1L.png",
    "limpiavidrios":        "Limpiavidrios Atom 500ml.png",
    "desmanchador":         "Desmanchador de Juntas y Baños Atom 500ml.png",
    "eliminador de olores": "Eliminador de Olores Atom 500ml.png",
    "ambientador":          "Ambientador y Limpiapisos DP 500ml-1L.png",
    "limpiapisos":          "Ambientador y Limpiapisos DP 500ml-1L.png",
    "limpiador desinfectante": "Limpiador Desinfectante Superfices Atom 500ml.png",
    "desengrasante profesional": "Desengrasante Profesional Tarro 500ml.png",
    "desengrasante pro":    "Desengrasante Profesional Tarro 500ml.png",
    "desengrasante cocina": "Desengrasante Atom 500ml.png",
    "desengrasante":        "Desengrasante Atom 500ml.png",
    "desengrasante motores": "Desengrasante de Motores DP 500ml-1L.png",
    "shampoo vehiculos":    "Shampoo para vehiculos DP 500ml-1L.png",
    "shampoo vehículos":    "Shampoo para vehiculos DP 500ml-1L.png",
}

BASE_URL_IMAGENES = "https://equoradistribuciones.com"


def obtener_url_imagen(nombre_producto: str) -> str | None:
    """Busca la URL de imagen para un producto dado su nombre."""
    nombre = nombre_producto.lower().strip()
    for clave, archivo in IMAGENES_PRODUCTOS.items():
        if clave in nombre or nombre in clave:
            return f"{BASE_URL_IMAGENES}/{quote(archivo)}"
    return None


class ProveedorTwilio(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Twilio."""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.phone_number = os.getenv("TWILIO_PHONE_NUMBER")

    def _auth_header(self) -> dict:
        auth = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        return {"Authorization": f"Basic {auth}"}

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload form-encoded de Twilio."""
        form = await request.form()
        texto = form.get("Body", "")
        telefono = form.get("From", "").replace("whatsapp:", "")
        mensaje_id = form.get("MessageSid", "")
        if not texto:
            return []
        return [MensajeEntrante(
            telefono=telefono,
            texto=texto,
            mensaje_id=mensaje_id,
            es_propio=False,
        )]

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje de texto via Twilio API."""
        if not all([self.account_sid, self.auth_token, self.phone_number]):
            logger.warning("Variables de Twilio no configuradas")
            return False
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = {
            "From": f"whatsapp:{self.phone_number}",
            "To": f"whatsapp:{telefono}",
            "Body": mensaje,
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, data=data, headers=self._auth_header())
            if r.status_code != 201:
                logger.error(f"Error Twilio texto: {r.status_code} — {r.text}")
            return r.status_code == 201

    async def enviar_imagen(self, telefono: str, url_imagen: str, caption: str = "") -> bool:
        """Envía una imagen con caption opcional via Twilio API."""
        if not all([self.account_sid, self.auth_token, self.phone_number]):
            return False
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = {
            "From": f"whatsapp:{self.phone_number}",
            "To": f"whatsapp:{telefono}",
            "MediaUrl": url_imagen,
            "Body": caption,
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, data=data, headers=self._auth_header())
            if r.status_code != 201:
                logger.error(f"Error Twilio imagen: {r.status_code} — {r.text}")
            return r.status_code == 201
