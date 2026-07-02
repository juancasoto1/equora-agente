"""
agent/mailer.py — Envío de emails transaccionales para Voco.

Prioridad de envío:
  1. SendGrid REST API (si SENDGRID_API_KEY está configurada)
  2. SMTP genérico (SMTP_HOST + SMTP_USER + SMTP_PASS) — stdlib smtplib, sin deps extras

Variables de entorno relevantes:
  SENDGRID_API_KEY   → clave de SendGrid (empieza con SG.)
  EMAIL_FROM         → dirección de origen (default: noreply@usevoco.com)
  EMAIL_FROM_NAME    → nombre del remitente (default: Voco)
  SMTP_HOST          → hostname SMTP (ej: smtp.gmail.com)
  SMTP_PORT          → puerto SMTP (default: 587)
  SMTP_USER          → usuario SMTP
  SMTP_PASS          → contraseña SMTP
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

logger = logging.getLogger("agentkit")

_FROM_EMAIL = os.getenv("EMAIL_FROM", "noreply@usevoco.com")
_FROM_NAME  = os.getenv("EMAIL_FROM_NAME", "Voco")


# ── Plantilla HTML del correo de verificación ────────────────────────────────

def _html_verificacion(nombre: str, codigo: str) -> str:
    nombre_display = nombre.split()[0].capitalize() if nombre else "ahí"
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Verifica tu email — Voco</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:40px 16px">
  <tr><td align="center">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width:480px">

      <!-- Logo -->
      <tr><td align="center" style="padding-bottom:24px">
        <svg width="44" height="44" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" fill="none">
          <path d="M30 18 H70 L82 38 V62 L70 75 H52 L42 92 L40 75 H30 L18 62 V38 Z"
                stroke="#10b981" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
        </svg>
        <div style="margin-top:8px;font-size:20px;font-weight:700;color:#111827;letter-spacing:-.5px">Voco</div>
      </td></tr>

      <!-- Card -->
      <tr><td style="background:#fff;border-radius:16px;border:1px solid #e5e7eb;padding:40px 36px">

        <p style="margin:0 0 4px;font-size:22px;font-weight:700;color:#111827">
          Hola, {nombre_display} 👋
        </p>
        <p style="margin:12px 0 28px;font-size:15px;color:#4b5563;line-height:1.6">
          Gracias por crear tu cuenta en Voco. Usa el siguiente código para verificar
          tu dirección de email. Válido por <strong>30 minutos</strong>.
        </p>

        <!-- Código -->
        <div style="text-align:center;margin:0 0 32px">
          <div style="display:inline-block;background:#f0fdf4;border:2px solid #bbf7d0;
                      border-radius:12px;padding:20px 40px">
            <span style="font-size:42px;font-weight:800;letter-spacing:10px;
                         color:#059669;font-variant-numeric:tabular-nums">{codigo}</span>
          </div>
          <p style="margin:12px 0 0;font-size:13px;color:#6b7280">
            Ingresa este código en la pantalla de verificación
          </p>
        </div>

        <hr style="border:none;border-top:1px solid #f3f4f6;margin:0 0 28px">

        <p style="margin:0;font-size:13px;color:#9ca3af;line-height:1.6">
          Si no creaste una cuenta en Voco, puedes ignorar este mensaje de forma segura.
          Nadie puede acceder a tu cuenta sin este código.
        </p>
      </td></tr>

      <!-- Footer -->
      <tr><td align="center" style="padding:24px 0 0">
        <p style="margin:0;font-size:12px;color:#9ca3af">
          © 2026 Voco · Plataforma de atención al cliente con IA
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def _texto_verificacion(nombre: str, codigo: str) -> str:
    nombre_display = nombre.split()[0].capitalize() if nombre else "ahí"
    return (
        f"Hola {nombre_display},\n\n"
        f"Tu código de verificación de Voco es: {codigo}\n\n"
        f"Válido por 30 minutos. Si no creaste esta cuenta, ignora este mensaje.\n\n"
        f"— El equipo de Voco"
    )


# ── Envío vía SendGrid REST ───────────────────────────────────────────────────

async def _enviar_sendgrid(to_email: str, to_name: str, subject: str, html: str, text: str) -> bool:
    api_key = os.getenv("SENDGRID_API_KEY", "")
    if not api_key:
        return False
    payload = {
        "personalizations": [{"to": [{"email": to_email, "name": to_name}]}],
        "from":    {"email": _FROM_EMAIL, "name": _FROM_NAME},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html",  "value": html},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if r.status_code in (200, 202):
            logger.info(f"[mailer] SendGrid OK → {to_email}")
            return True
        logger.error(f"[mailer] SendGrid error {r.status_code}: {r.text[:300]}")
        return False
    except Exception as e:
        logger.error(f"[mailer] SendGrid excepción: {e}")
        return False


# ── Envío vía SMTP (stdlib) ───────────────────────────────────────────────────

def _enviar_smtp(to_email: str, to_name: str, subject: str, html: str, text: str) -> bool:
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    pwd  = os.getenv("SMTP_PASS", "")
    if not (host and user and pwd):
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{_FROM_NAME} <{_FROM_EMAIL}>"
    msg["To"]      = f"{to_name} <{to_email}>" if to_name else to_email
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html",  "utf-8"))
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.login(user, pwd)
            s.sendmail(_FROM_EMAIL, [to_email], msg.as_bytes())
        logger.info(f"[mailer] SMTP OK → {to_email}")
        return True
    except Exception as e:
        logger.error(f"[mailer] SMTP excepción: {e}")
        return False


# ── Función pública ───────────────────────────────────────────────────────────

async def enviar_verificacion(email: str, nombre: str, codigo: str) -> bool:
    """Envía el código de verificación de email al usuario.
    Prueba SendGrid primero; si falla o no está configurado, intenta SMTP.
    Retorna True si se envió por algún canal."""
    subject = f"{codigo} es tu código de verificación de Voco"
    html    = _html_verificacion(nombre, codigo)
    text    = _texto_verificacion(nombre, codigo)

    if await _enviar_sendgrid(email, nombre, subject, html, text):
        return True
    return _enviar_smtp(email, nombre, subject, html, text)
