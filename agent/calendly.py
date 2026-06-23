# agent/calendly.py — Cliente de la Calendly Scheduling API
#
# Pipeline Fase 2 (mini-CRM, ver BACKLOG.md). Cada agente de Voco conecta su
# propia cuenta de Calendly (Personal Access Token guardado en
# IntegrationConfig tipo="calendly", ver agent/memory.py) — no existe una
# cuenta maestra de Voco. Mismo patrón que Shopify (cada merchant su token).
#
# Dos niveles de uso (decisión 2026-06-22, ver BACKLOG.md):
#   Nivel 1 — compartir el `scheduling_url` público (no usa este módulo,
#             funciona en el plan gratis de Calendly).
#   Nivel 2 — agendar sin salir de WhatsApp, usando este módulo:
#             obtener_event_types() -> obtener_horarios_disponibles() -> crear_cita()
#
# El schema de POST /invitees no está documentado en HTML estático (la doc
# oficial de Calendly es una SPA que no se puede leer sin JS) — se reconstruyó
# probando campo por campo contra la API real el 2026-06-23 con un token de
# prueba (ver BACKLOG.md para el detalle). La cuenta de prueba estaba en tier
# "trial": ese endpoint tiene rate limit de 5 requests/día — un cliente de
# Voco en plan gratis/trial de Calendly se va a topar con ese límite rápido;
# producción real necesita que ESE cliente tenga Calendly en plan pago.
#
# IMPORTANTE — pendiente de confirmar: el shape de la respuesta EXITOSA de
# POST /invitees (200/201) es una suposición razonable basada en el patrón
# de /users/me (wrapped en "resource"), pero nunca se confirmó con una
# llamada real exitosa porque se agotó el rate limit de prueba antes de
# llegar a esa validación. Revisar `crear_cita()` en la primera reserva real
# que se haga y ajustar si el shape no coincide.

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from agent.memory import obtener_integration_config

logger = logging.getLogger("agentkit")

API_BASE = "https://api.calendly.com"


async def _token(agent_id: int) -> str | None:
    """Personal Access Token de Calendly del agente, o None si no conectó."""
    cfg = await obtener_integration_config(agent_id, "calendly")
    if not cfg or not cfg.get("api_token"):
        return None
    return cfg["api_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def obtener_usuario(agent_id: int) -> dict[str, Any]:
    """GET /users/me — valida el token y trae el URI del usuario (lo pide
    /event_types) y su scheduling_url público (nivel 1)."""
    token = await _token(agent_id)
    if not token:
        return {"ok": False, "error": "Calendly no está conectado para este agente"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{API_BASE}/users/me", headers=_headers(token))
        if r.status_code == 401:
            return {"ok": False, "error": "Token de Calendly inválido o vencido"}
        if r.status_code != 200:
            logger.error(f"[calendly] /users/me {r.status_code}: {r.text[:200]}")
            return {"ok": False, "error": f"Error de Calendly ({r.status_code})"}
        data = r.json().get("resource", {})
        return {
            "ok": True,
            "uri": data.get("uri", ""),
            "nombre": data.get("name", ""),
            "email": data.get("email", ""),
            "timezone": data.get("timezone", "America/Bogota"),
            "scheduling_url": data.get("scheduling_url", ""),
        }
    except Exception as e:
        logger.error(f"[calendly] Error en obtener_usuario: {e}")
        return {"ok": False, "error": "Error de red consultando Calendly"}


async def obtener_event_types(agent_id: int, user_uri: str) -> list[dict]:
    """GET /event_types?user=... — tipos de evento activos del agente."""
    token = await _token(agent_id)
    if not token:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{API_BASE}/event_types",
                headers=_headers(token),
                params={"user": user_uri, "active": "true"},
            )
        if r.status_code != 200:
            logger.error(f"[calendly] /event_types {r.status_code}: {r.text[:200]}")
            return []
        items = r.json().get("collection", [])
        return [
            {
                "uri":            it.get("uri", ""),
                "nombre":         it.get("name", ""),
                "duracion_min":   it.get("duration", 0),
                "scheduling_url": it.get("scheduling_url", ""),
                "slug":           it.get("slug", ""),
                # locations[].kind — necesario para crear_cita(location_kind=...)
                "location_kinds": [loc.get("kind") for loc in (it.get("locations") or []) if loc.get("kind")],
            }
            for it in items
        ]
    except Exception as e:
        logger.error(f"[calendly] Error en obtener_event_types: {e}")
        return []


async def obtener_horarios_disponibles(agent_id: int, event_type_uri: str, dias: int = 7) -> list[dict]:
    """GET /event_type_available_times — Calendly solo permite consultar
    máximo 7 días por request (lo cápamos acá). Para más rango habría que
    encadenar varias llamadas corriendo la ventana — no implementado todavía,
    no hace falta para el flujo de "próximos horarios disponibles"."""
    token = await _token(agent_id)
    if not token:
        return []
    dias = min(dias, 7)
    # +10 min de margen — Calendly rechaza start_time si está "en el pasado",
    # y un now() calculado justo al filo del segundo puede llegar tarde al
    # servidor y caer del lado equivocado.
    inicio = datetime.now(timezone.utc) + timedelta(minutes=10)
    fin = inicio + timedelta(days=dias)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{API_BASE}/event_type_available_times",
                headers=_headers(token),
                params={
                    "event_type": event_type_uri,
                    "start_time": inicio.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end_time":   fin.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
        if r.status_code != 200:
            logger.error(f"[calendly] /event_type_available_times {r.status_code}: {r.text[:200]}")
            return []
        items = r.json().get("collection", [])
        return [
            {"start_time": it.get("start_time", ""), "scheduling_url": it.get("scheduling_url", "")}
            for it in items
            if it.get("status") == "available"
        ]
    except Exception as e:
        logger.error(f"[calendly] Error en obtener_horarios_disponibles: {e}")
        return []


async def crear_cita(
    agent_id: int,
    event_type_uri: str,
    start_time_iso: str,
    invitee_email: str,
    invitee_nombre: str,
    invitee_timezone: str = "America/Bogota",
    location_kind: str | None = None,
) -> dict[str, Any]:
    """POST /invitees — agenda la cita sin redirigir al cliente a Calendly.

    `location_kind` debe ser uno de los `location_kinds` que devolvió
    obtener_event_types() para ese tipo de evento (ej. "google_conference",
    "physical", "custom") — se omite el campo si el event type no requiere
    ubicación (Calendly devuelve un error explícito pidiéndolo si hacía falta).
    """
    token = await _token(agent_id)
    if not token:
        return {"ok": False, "error": "Calendly no está conectado para este agente"}

    body: dict[str, Any] = {
        "event_type": event_type_uri,
        "start_time": start_time_iso,
        "invitee": {
            "email":    invitee_email,
            "name":     invitee_nombre,
            "timezone": invitee_timezone,
        },
    }
    if location_kind:
        body["location"] = {"kind": location_kind}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{API_BASE}/invitees", headers=_headers(token), json=body)
        if r.status_code == 429:
            logger.warning(f"[calendly] Rate limit alcanzado creando cita (agent_id={agent_id})")
            return {"ok": False, "error": "Calendly alcanzó su límite de citas por hoy — intenta más tarde"}
        if r.status_code == 401:
            return {"ok": False, "error": "Token de Calendly inválido o vencido"}
        if r.status_code not in (200, 201):
            logger.error(f"[calendly] /invitees {r.status_code}: {r.text[:300]}")
            return {"ok": False, "error": "Calendly rechazó la cita — revisa el horario y los datos"}
        raw = r.json()
        data = raw.get("resource", raw)  # ver nota al inicio del archivo — shape sin confirmar
        return {
            "ok": True,
            "uri":            data.get("uri", ""),
            "cancel_url":     data.get("cancel_url", ""),
            "reschedule_url": data.get("reschedule_url", ""),
        }
    except Exception as e:
        logger.error(f"[calendly] Error en crear_cita: {e}")
        return {"ok": False, "error": "Error de red agendando con Calendly"}
