import os
import json
import secrets
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, select, update, Integer, Boolean, func, text, PrimaryKeyConstraint
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    """Usuarios del sistema SaaS multi-tenant de Voco."""
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), default="")
    rol: Mapped[str] = mapped_column(String(20), default="user")        # "admin" | "user"
    plan: Mapped[str] = mapped_column(String(20), default="trial")      # "trial"|"starter"|"growth"|"pro"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SesionUsuario(Base):
    """Sesiones activas de usuarios en el sistema SaaS."""
    __tablename__ = "sesiones_usuario"

    token: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Agent(Base):
    """Agentes de la plataforma Voco — cada uno es un número de WhatsApp independiente."""
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")          # nombre del negocio
    agent_name: Mapped[str] = mapped_column(String(100), default="Agente")
    business_type: Mapped[str] = mapped_column(String(50), default="productos")
    status: Mapped[str] = mapped_column(String(20), default="draft")    # draft|active|paused
    phone_number_id: Mapped[str] = mapped_column(String(100), default="")
    waba_id: Mapped[str] = mapped_column(String(100), default="")
    color: Mapped[str] = mapped_column(String(20), default="#6366f1")
    emoji: Mapped[str] = mapped_column(String(10), default="🤖")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)  # None = admin-owned
    # Sprint A — toggles de módulos opt-in (JSON serializado).
    # Si el campo está vacío o null, get_modules() devuelve defaults seguros
    # (todos OFF para agentes existentes). Ver get_modules() / set_modules() abajo.
    modules_json: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Promoción post-venta: código de descuento que se envía al cliente
    # tras confirmar el pago (webhook orders/paid de Shopify) si el subtotal
    # (SIN envío) supera el umbral. Configurable 100% desde el panel Voco —
    # nada hardcoded por agente. Default: desactivado.
    descuento_activo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    descuento_umbral: Mapped[int] = mapped_column(Integer, default=0, nullable=False)      # COP, subtotal sin envío
    descuento_codigo: Mapped[str] = mapped_column(String(50), default="", nullable=False)  # Ej: GRACIAS5
    descuento_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)         # 1-100
    descuento_mensaje: Mapped[str] = mapped_column(Text, default="", nullable=False)       # Template con {codigo} {pct} {umbral}


class Mensaje(Base):
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (PrimaryKeyConstraint("agent_id", "telefono"),)

    agent_id: Mapped[int] = mapped_column(Integer, default=1)
    telefono: Mapped[str] = mapped_column(String(50))
    nombres: Mapped[str] = mapped_column(String(100), default="")
    apellidos: Mapped[str] = mapped_column(String(100), default="")
    razon_social: Mapped[str] = mapped_column(String(200), default="")
    cc_nit: Mapped[str] = mapped_column(String(50), default="")
    direccion: Mapped[str] = mapped_column(String(200), default="")
    barrio: Mapped[str] = mapped_column(String(100), default="")
    ciudad: Mapped[str] = mapped_column(String(100), default="")
    departamento: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(100), default="")
    pedidos_realizados: Mapped[int] = mapped_column(Integer, default=0)
    pedido_pendiente: Mapped[str] = mapped_column(Text, default="")
    pedido_pendiente_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    pedido_checkout_url: Mapped[str] = mapped_column(Text, default="")  # URL Shopify checkout
    carrito_activo: Mapped[str] = mapped_column(Text, default="")        # JSON del carrito en curso
    carrito_activo_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    # Cooldown persistente del aviso de checkout abandonado.
    # Antes vivía en _checkout_abandono_notif (memoria) y se reseteaba con cada
    # deploy a Railway → se duplicaban mensajes. Ahora persiste en BD.
    checkout_abandono_notif_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


CAMPOS_CLIENTE = (
    "nombres", "apellidos", "razon_social", "cc_nit",
    "direccion", "barrio", "ciudad", "departamento", "email",
)


class AgentMessage(Base):
    """Override y/o flag activo de un mensaje del sistema por agente.

    Resolución en runtime:
      - Sin row: usar default del catálogo (mensaje activo por defecto).
      - Con row + activo=True: usar content (o default si content vacío).
      - Con row + activo=False: NO enviar nada en ese punto del flujo.

    Borrar la row = restaurar default + reactivar.
    """
    __tablename__ = "agent_messages"
    __table_args__ = (PrimaryKeyConstraint("agent_id", "key"),)

    agent_id:   Mapped[int] = mapped_column(Integer)
    key:        Mapped[str] = mapped_column(String(80))          # ej. "system.followup"
    content:    Mapped[str] = mapped_column(Text, default="")
    activo:     Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PlantillaBorrador(Base):
    """Borradores de plantillas guardados localmente antes de enviar a Meta."""
    __tablename__ = "plantillas_borradores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    nombre: Mapped[str] = mapped_column(String(512), default="")
    categoria: Mapped[str] = mapped_column(String(50), default="MARKETING")
    idioma: Mapped[str] = mapped_column(String(20), default="es_CO")
    datos_json: Mapped[str] = mapped_column(Text, default="{}")   # todos los campos del formulario
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Difusion(Base):
    """Registro histórico de difusiones enviadas desde el inbox."""
    __tablename__ = "difusiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    campaign_name: Mapped[str] = mapped_column(String(200), default="")   # nombre que da el usuario
    campaign_id: Mapped[str] = mapped_column(String(100), default="")     # ID único por acción de envío
    template_name: Mapped[str] = mapped_column(String(100), default="")
    language: Mapped[str] = mapped_column(String(20), default="es_CO")
    destinatarios: Mapped[int] = mapped_column(Integer, default=0)
    enviados: Mapped[int] = mapped_column(Integer, default=0)
    fallidos: Mapped[int] = mapped_column(Integer, default=0)
    errores_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# Mapa de códigos de error de Meta → descripción amigable en español
_META_ERROR_CODES: dict[int, str] = {
    130429: "Límite de tasa alcanzado — intenta más tarde",
    131000: "Error interno de Meta",
    131005: "Permiso denegado por Meta",
    131008: "Parámetro requerido ausente",
    131009: "Valor de parámetro inválido",
    131016: "Servicio de Meta no disponible temporalmente",
    131021: "Número no está en la lista de prueba (sandbox)",
    131026: "Número no registrado en WhatsApp",
    131031: "Cuenta de empresa bloqueada por Meta",
    131047: "Ventana de 24 h expirada — el cliente debe escribir primero",
    131048: "Límite de mensajes no solicitados alcanzado",
    131049: "Mensaje expirado antes de entregarse",
    131051: "Tipo de mensaje no soportado",
    131053: "Error al subir archivo multimedia",
    132001: "Plantilla no encontrada en Meta",
    132005: "Error al personalizar variables de la plantilla",
    132007: "Texto de plantilla viola políticas de formato",
    132008: "Formato de parámetro no coincide con la plantilla",
    132009: "Número de parámetros no coincide con la plantilla",
    132012: "Número de botones no coincide con la plantilla",
    132015: "URL del botón inválida",
    133010: "Número de teléfono del negocio no verificado",
}


class DifusionMensaje(Base):
    """Tracking individual de cada mensaje de difusión: delivery, lectura y errores."""
    __tablename__ = "difusion_mensajes"

    id:            Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id:      Mapped[int]            = mapped_column(Integer, default=1, index=True)
    wamid:         Mapped[str]            = mapped_column(String(200), unique=True, index=True)
    campaign_id:   Mapped[str]            = mapped_column(String(100), index=True, default="")
    campaign_name: Mapped[str]            = mapped_column(String(200), default="")
    telefono:      Mapped[str]            = mapped_column(String(50),  index=True, default="")
    status:        Mapped[str]            = mapped_column(String(20),  default="sent")  # sent/delivered/read/failed
    error_code:    Mapped[int | None]     = mapped_column(Integer,     nullable=True)
    error_title:   Mapped[str]            = mapped_column(String(500), default="")
    sent_at:       Mapped[datetime]       = mapped_column(DateTime,    default=datetime.utcnow)
    delivered_at:  Mapped[datetime | None]= mapped_column(DateTime,    nullable=True)
    read_at:       Mapped[datetime | None]= mapped_column(DateTime,    nullable=True)
    failed_at:     Mapped[datetime | None]= mapped_column(DateTime,    nullable=True)


class EstadoConversacion(Base):
    """Timestamps por conversación para gestionar seguimientos automáticos."""
    __tablename__ = "estado_conversacion"
    __table_args__ = (PrimaryKeyConstraint("agent_id", "telefono"),)

    agent_id: Mapped[int] = mapped_column(Integer, default=1)
    telefono: Mapped[str] = mapped_column(String(50))
    last_user_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_assistant_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cierre_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    modo_humano: Mapped[int] = mapped_column(Integer, default=0)  # 1 = humano responde, 0 = Andrea
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OptOut(Base):
    """Números que pidieron ser dados de baja de las difusiones masivas."""
    __tablename__ = "opt_outs"
    __table_args__ = (PrimaryKeyConstraint("agent_id", "telefono"),)

    agent_id:  Mapped[int]      = mapped_column(Integer, default=1)
    telefono:  Mapped[str]      = mapped_column(String(50))
    motivo:    Mapped[str]      = mapped_column(String(200), default="")  # "STOP", "DAR DE BAJA", etc.
    creado_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConfigValue(Base):
    """Valores de configuración dinámica guardados en BD (sobrescriben variables de entorno)."""
    __tablename__ = "config_values"
    __table_args__ = (PrimaryKeyConstraint("agent_id", "clave"),)

    agent_id:       Mapped[int]      = mapped_column(Integer, default=1)
    clave:          Mapped[str]      = mapped_column(String(100))
    valor:          Mapped[str]      = mapped_column(Text, default="")
    actualizado_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 1 — Sistema de escalación multi-agente
# ══════════════════════════════════════════════════════════════════════════════

class UsuarioInterno(Base):
    """Agentes humanos de soporte interno de cada negocio (distinto de usuarios SaaS)."""
    __tablename__ = "usuarios_internos"

    id:             Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id:       Mapped[int]           = mapped_column(Integer, index=True)          # negocio al que pertenece
    nombre:         Mapped[str]           = mapped_column(String(200), default="")
    email:          Mapped[str]           = mapped_column(String(200), index=True)
    password_hash:  Mapped[str]           = mapped_column(String(200), default="")
    rol:            Mapped[str]           = mapped_column(String(20), default="agente")  # agente|supervisor|admin
    activo:         Mapped[bool]          = mapped_column(Boolean, default=True)
    ultimo_ping_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)      # para "online"
    # Notificaciones de escalación por WhatsApp (#52) — cada usuario decide
    # si quiere recibir los avisos en su número personal. Default OFF para
    # que no se le mande a nadie hasta opt-in explícito.
    telefono_wa:           Mapped[str]    = mapped_column(String(50), default="")
    notif_escalaciones_wa: Mapped[bool]   = mapped_column(Boolean, default=False)
    created_at:     Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)


class Ticket(Base):
    """Ticket de escalación: una conversación que requiere atención humana."""
    __tablename__ = "tickets"

    id:                Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id:          Mapped[int]           = mapped_column(Integer, index=True)
    telefono_cliente:  Mapped[str]           = mapped_column(String(50), index=True)
    nombre_cliente:    Mapped[str]           = mapped_column(String(200), default="")
    # Estado: sin_asignar → activo → pendiente ↔ activo → resuelto
    estado:            Mapped[str]           = mapped_column(String(20), default="sin_asignar", index=True)
    urgencia:          Mapped[str]           = mapped_column(String(20), default="normal")  # alta|normal|baja
    motivo:            Mapped[str]           = mapped_column(Text, default="")
    contexto:          Mapped[str]           = mapped_column(Text, default="")
    agente_humano_id:  Mapped[int|None]      = mapped_column(Integer, nullable=True)        # FK usuarios_internos
    creado_at:         Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)
    tomado_at:         Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    resuelto_at:       Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    actualizado_at:    Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow)


async def inicializar_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migración: agregar columnas nuevas si la tabla ya existía sin ellas
        # PostgreSQL soporta IF NOT EXISTS en ALTER TABLE ADD COLUMN
        for sql in (
            "ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS agent_id INTEGER DEFAULT 1",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS pedido_pendiente TEXT DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS pedido_pendiente_at TIMESTAMP",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS carrito_activo TEXT DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS carrito_activo_at TIMESTAMP",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS checkout_abandono_notif_at TIMESTAMP",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS pedido_checkout_url TEXT DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS agent_id INTEGER DEFAULT 1",
            "ALTER TABLE estado_conversacion ADD COLUMN IF NOT EXISTS modo_humano INTEGER DEFAULT 0",
            "ALTER TABLE estado_conversacion ADD COLUMN IF NOT EXISTS agent_id INTEGER DEFAULT 1",
            "ALTER TABLE difusiones ADD COLUMN IF NOT EXISTS campaign_name TEXT DEFAULT ''",
            "ALTER TABLE difusiones ADD COLUMN IF NOT EXISTS campaign_id TEXT DEFAULT ''",
            "ALTER TABLE difusiones ADD COLUMN IF NOT EXISTS template_name TEXT DEFAULT ''",
            "ALTER TABLE difusiones ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'es_CO'",
            "ALTER TABLE difusiones ADD COLUMN IF NOT EXISTS destinatarios INTEGER DEFAULT 0",
            "ALTER TABLE difusiones ADD COLUMN IF NOT EXISTS fallidos INTEGER DEFAULT 0",
            "ALTER TABLE difusiones ADD COLUMN IF NOT EXISTS agent_id INTEGER DEFAULT 1",
            "ALTER TABLE difusion_mensajes ADD COLUMN IF NOT EXISTS agent_id INTEGER DEFAULT 1",
            "ALTER TABLE difusion_mensajes ADD COLUMN IF NOT EXISTS campaign_id TEXT DEFAULT ''",
            "ALTER TABLE opt_outs ADD COLUMN IF NOT EXISTS agent_id INTEGER DEFAULT 1",
            "ALTER TABLE plantillas_borradores ADD COLUMN IF NOT EXISTS agent_id INTEGER DEFAULT 1",
            # Sprint 1 — multi-tenant
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS owner_id INTEGER",
            # Sprint 1 — sistema de escalación multi-agente
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS max_agentes INTEGER DEFAULT 2",
            "CREATE INDEX IF NOT EXISTS ix_tickets_agent_estado ON tickets (agent_id, estado)",
            "CREATE INDEX IF NOT EXISTS ix_ui_agent ON usuarios_internos (agent_id)",
            # Sprint 2 — notas internas y templates rápidos
            "CREATE INDEX IF NOT EXISTS ix_notas_ticket ON notas_internas (ticket_id)",
            "CREATE INDEX IF NOT EXISTS ix_tpl_agent ON templates_rapidos (agent_id)",
            # Sprint 3 — auditoría de tickets
            "CREATE INDEX IF NOT EXISTS ix_tevento_ticket ON ticket_eventos (ticket_id)",
            # Backfill agent_id NULL → 1 en datos históricos (preservar historial)
            "UPDATE difusiones        SET agent_id = 1 WHERE agent_id IS NULL",
            "UPDATE difusion_mensajes SET agent_id = 1 WHERE agent_id IS NULL",
            "UPDATE mensajes          SET agent_id = 1 WHERE agent_id IS NULL",
            "UPDATE clientes          SET agent_id = 1 WHERE agent_id IS NULL",
            "UPDATE estado_conversacion SET agent_id = 1 WHERE agent_id IS NULL",
            "UPDATE opt_outs          SET agent_id = 1 WHERE agent_id IS NULL",
            # Índices útiles
            "CREATE INDEX IF NOT EXISTS ix_difmsg_campaign ON difusion_mensajes (campaign_id)",
            "CREATE INDEX IF NOT EXISTS ix_mensajes_agent ON mensajes (agent_id)",
            # ─── Sprint A — Pipeline + Soporte ─────────────────────────
            # Agregar modules_json al Agent (default empty = todos OFF)
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS modules_json TEXT DEFAULT ''",
            # ─── Promoción post-venta configurable por agente ──────────
            # Default: desactivado para todos los agents existentes.
            # Cero hardcodes — cada cliente SaaS configura desde el panel.
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS descuento_activo BOOLEAN DEFAULT FALSE",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS descuento_umbral INTEGER DEFAULT 0",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS descuento_codigo VARCHAR(50) DEFAULT ''",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS descuento_pct INTEGER DEFAULT 0",
            "ALTER TABLE agents ADD COLUMN IF NOT EXISTS descuento_mensaje TEXT DEFAULT ''",
            # ─── #28 — Mensajes del sistema configurables por agente ───
            # La tabla agent_messages la crea Base.metadata.create_all.
            # Agregamos índice por agent_id para listados rápidos.
            "CREATE INDEX IF NOT EXISTS ix_agent_messages_agent ON agent_messages (agent_id)",
            # Flag activo (#28 fase 2.7): permite desactivar un mensaje sin
            # borrarlo. Default TRUE para preservar comportamiento existente.
            "ALTER TABLE agent_messages ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE",
            # #52 — Notificaciones de escalación configurables por usuario interno.
            # Default OFF: cada agente humano debe opt-in explícitamente.
            "ALTER TABLE usuarios_internos ADD COLUMN IF NOT EXISTS telefono_wa VARCHAR(50) DEFAULT ''",
            "ALTER TABLE usuarios_internos ADD COLUMN IF NOT EXISTS notif_escalaciones_wa BOOLEAN DEFAULT FALSE",
            # Índices para las nuevas tablas (create_all ya las creó si no existían)
            "CREATE INDEX IF NOT EXISTS ix_pipelines_agent       ON pipelines           (agent_id)",
            "CREATE INDEX IF NOT EXISTS ix_deals_agent           ON deals               (agent_id)",
            "CREATE INDEX IF NOT EXISTS ix_deals_pipeline        ON deals               (pipeline_id)",
            "CREATE INDEX IF NOT EXISTS ix_deals_telefono        ON deals               (cliente_telefono)",
            "CREATE INDEX IF NOT EXISTS ix_deals_stage           ON deals               (stage)",
            "CREATE INDEX IF NOT EXISTS ix_deals_created         ON deals               (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_dealact_deal          ON deal_activities     (deal_id)",
            "CREATE INDEX IF NOT EXISTS ix_dealact_created       ON deal_activities     (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_intcfg_agent_tipo     ON integration_configs (agent_id, tipo)",
            "CREATE INDEX IF NOT EXISTS ix_kbart_agent           ON kb_articles         (agent_id)",
        ):
            try:
                await conn.exec_driver_sql(sql)
            except Exception:
                pass  # ya existe o no aplica

    # Auto-crear agente Equora (agent_id=1) si no existe
    equora_name = os.getenv("EQUORA_NAME", "Equora Distribuciones")
    equora_phone_id = os.getenv("META_PHONE_NUMBER_ID", "")
    equora_waba_id = os.getenv("META_WABA_ID", "")
    async with async_session() as session:
        try:
            result = await session.execute(select(Agent).where(Agent.id == 1))
            existing = result.scalar_one_or_none()
            if not existing:
                equora = Agent(
                    id=1,
                    slug="equora",
                    name=equora_name,
                    agent_name="Andrea",
                    business_type="productos",
                    status="active",
                    phone_number_id=equora_phone_id,
                    waba_id=equora_waba_id,
                    color="#22c55e",
                    emoji="🌿",
                    created_at=datetime.utcnow(),
                )
                session.add(equora)
                await session.commit()
        except Exception:
            pass  # puede fallar en primera migración; la tabla se creará igual

    # Auto-crear usuario admin si ADMIN_EMAIL está configurado
    admin_email = os.getenv("ADMIN_EMAIL", "")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if admin_email:
        import bcrypt as _bcrypt
        async with async_session() as session:
            try:
                result = await session.execute(
                    select(Usuario).where(Usuario.email == admin_email)
                )
                existing_admin = result.scalar_one_or_none()
                if not existing_admin:
                    pw = admin_password or secrets.token_urlsafe(16)
                    pw_hash = _bcrypt.hashpw(pw.encode(), _bcrypt.gensalt()).decode()
                    admin_user = Usuario(
                        email=admin_email,
                        password_hash=pw_hash,
                        nombre="Admin",
                        rol="admin",
                        plan="admin",
                        is_active=True,
                        created_at=datetime.utcnow(),
                    )
                    session.add(admin_user)
                    await session.commit()
            except Exception:
                pass  # tabla puede no existir aún


async def guardar_mensaje(telefono: str, role: str, content: str, agent_id: int = 1):
    async with async_session() as session:
        mensaje = Mensaje(
            agent_id=agent_id,
            telefono=telefono,
            role=role,
            content=content,
            timestamp=datetime.utcnow()
        )
        session.add(mensaje)
        await session.commit()


async def obtener_historial(telefono: str, limite: int = 20, agent_id: int = 1) -> list[dict]:
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono, Mensaje.agent_id == agent_id)
            .order_by(Mensaje.timestamp.desc())
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()
        mensajes.reverse()
        return [
            {"role": msg.role, "content": msg.content}
            for msg in mensajes
        ]


async def limpiar_historial(telefono: str, agent_id: int = 1):
    async with async_session() as session:
        query = select(Mensaje).where(Mensaje.telefono == telefono, Mensaje.agent_id == agent_id)
        result = await session.execute(query)
        mensajes = result.scalars().all()
        for msg in mensajes:
            await session.delete(msg)
        await session.commit()


async def _get_cliente(session: AsyncSession, telefono: str, agent_id: int) -> "Cliente | None":
    """Helper interno para buscar cliente por PK compuesta (agent_id, telefono)."""
    result = await session.execute(
        select(Cliente).where(Cliente.agent_id == agent_id, Cliente.telefono == telefono)
    )
    return result.scalar_one_or_none()


async def obtener_agent_ids_por_telefono(telefono: str) -> list[int]:
    """Devuelve TODOS los agent_ids bajo los que existe el cliente con ese teléfono.

    Útil para webhooks externos (Shopify, etc.) que llegan SIN contexto de
    agent_id — en multi-tenant un mismo número podría existir bajo varios
    agents si el mismo cliente compra a varios negocios usando la plataforma.
    El caller itera y aplica el efecto (limpiar, actualizar) en cada uno.

    Si el teléfono no está en BD, devuelve lista vacía — el caller decide
    fallback (ej. asumir agent_id=1 por compatibilidad legacy).
    """
    if not telefono:
        return []
    async with async_session() as session:
        result = await session.execute(
            select(Cliente.agent_id).where(Cliente.telefono == telefono).distinct()
        )
        return [row[0] for row in result.all()]


async def guardar_cliente(
    telefono: str, datos: dict, agent_id: int = 1, incrementar_pedidos: bool = False
):
    """Crea o actualiza el perfil del cliente. Solo guarda campos no vacíos.
    `incrementar_pedidos=True` SOLO cuando se confirma el pago (webhook Shopify),
    nunca al crear un checkout — un checkout es intención, no compra confirmada."""
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if cliente:
            for campo in CAMPOS_CLIENTE:
                valor = datos.get(campo)
                if valor:
                    setattr(cliente, campo, str(valor))
            if incrementar_pedidos:
                cliente.pedidos_realizados = (cliente.pedidos_realizados or 0) + 1
            cliente.actualizado = datetime.utcnow()
        else:
            valores = {c: str(datos.get(c, "")) for c in CAMPOS_CLIENTE}
            cliente = Cliente(
                agent_id=agent_id, telefono=telefono,
                pedidos_realizados=(1 if incrementar_pedidos else 0),
                **valores
            )
            session.add(cliente)
        await session.commit()


async def guardar_cliente_import(telefono: str, datos: dict, agent_id: int = 1) -> str:
    """Importa un cliente desde CSV sin incrementar pedidos_realizados.
    Retorna 'inserted' si es nuevo o 'updated' si ya existía."""
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if cliente:
            for campo in CAMPOS_CLIENTE:
                valor = datos.get(campo)
                if valor:
                    setattr(cliente, campo, str(valor))
            cliente.actualizado = datetime.utcnow()
            await session.commit()
            return "updated"
        else:
            valores = {c: str(datos.get(c, "")) for c in CAMPOS_CLIENTE}
            cliente = Cliente(agent_id=agent_id, telefono=telefono, pedidos_realizados=0, **valores)
            session.add(cliente)
            await session.commit()
            return "inserted"


# Tablas con columna que referencia el teléfono del cliente. Si el merchant
# corrige el número (ej: agregar +57 cuando el cliente se guardó sin indicativo),
# hay que migrar TODAS las referencias en una sola transacción — si no, los
# mensajes/escalaciones/deals quedan huérfanos apuntando al número viejo.
#
# El tercer campo (pk_compuesta) indica si la tabla tiene PK sobre (agent_id, telefono).
# En esos casos, si YA existe una fila en el teléfono nuevo, el UPDATE viola la
# constraint UNIQUE — toca borrar la fila vieja antes (preferimos conservar la
# fila del teléfono nuevo, que es la "correcta"). Pasó con Lorena Camayo: estaba
# el mismo cliente registrado con y sin indicativo en estado_conversacion.
_TABLAS_REF_TELEFONO = (
    ("mensajes",            "telefono",         False),
    ("difusion_mensajes",   "telefono",         False),
    ("estado_conversacion", "telefono",         True),
    ("opt_outs",            "telefono",         True),
    ("tickets",             "telefono_cliente", False),
    ("deals",               "cliente_telefono", False),
)


async def editar_cliente(
    telefono_original: str,
    datos: dict,
    agent_id: int = 1,
    telefono_nuevo: str | None = None,
) -> dict:
    """Edita un cliente del panel. Si telefono_nuevo es distinto al original,
    migra todas las referencias (mensajes, escalaciones, deals, etc) atómicamente.

    Retorna: {"ok": bool, "error": str | None, "telefono": str}
    """
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono_original, agent_id)
        if not cliente:
            return {"ok": False, "error": "Cliente no encontrado", "telefono": telefono_original}

        # Actualizar campos editables (nombres, apellidos, ciudad, etc)
        for campo in CAMPOS_CLIENTE:
            if campo in datos:
                setattr(cliente, campo, str(datos.get(campo) or ""))
        cliente.actualizado = datetime.utcnow()

        # Si no hay cambio de teléfono, solo persistir y salir
        if not telefono_nuevo or telefono_nuevo == telefono_original:
            await session.commit()
            return {"ok": True, "error": None, "telefono": telefono_original}

        # Cambio de teléfono — verificar que el nuevo no choque con otro cliente
        existente = await _get_cliente(session, telefono_nuevo, agent_id)
        if existente:
            return {
                "ok": False,
                "error": f"Ya existe un cliente con el teléfono {telefono_nuevo}",
                "telefono": telefono_original,
            }

        # Migrar referencias en tablas relacionadas + el propio cliente.
        # Usamos raw SQL porque telefono es parte de la PK en Cliente y SQLAlchemy
        # ORM no permite actualizar PKs directamente.
        params = {"nuevo": telefono_nuevo, "viejo": telefono_original, "aid": agent_id}
        for tabla, columna, pk_compuesta in _TABLAS_REF_TELEFONO:
            if pk_compuesta:
                # Borrar la fila vieja si ya existe una para el teléfono nuevo,
                # para evitar violar la PK compuesta al hacer el UPDATE.
                await session.execute(
                    text(f"DELETE FROM {tabla} "
                         f"WHERE {columna} = :viejo AND agent_id = :aid "
                         f"AND EXISTS (SELECT 1 FROM {tabla} "
                         f"            WHERE {columna} = :nuevo AND agent_id = :aid)"),
                    params,
                )
            await session.execute(
                text(f"UPDATE {tabla} SET {columna} = :nuevo "
                     f"WHERE {columna} = :viejo AND agent_id = :aid"),
                params,
            )
        # Actualizar la fila Cliente al final (cambia PK)
        await session.execute(
            text("UPDATE clientes SET telefono = :nuevo "
                 "WHERE telefono = :viejo AND agent_id = :aid"),
            {"nuevo": telefono_nuevo, "viejo": telefono_original, "aid": agent_id},
        )
        await session.commit()
        return {"ok": True, "error": None, "telefono": telefono_nuevo}


async def obtener_perfil_enriquecido(telefono: str, agent_id: int = 1) -> dict:
    """Perfil compacto del cliente para alimentar el contexto del LLM (#65).

    Inferimos en una sola query las señales que más cambian el tono y la
    estrategia de respuesta del agente:

      segmento       : activo (<30d) / tibio (30-90d) / frio (>90d) / nuevo (sin mensajes)
                       Mismo umbral que el listado de Clientes — fuente de verdad única.
      tier           : nuevo (0 pedidos) / recurrente (1-4) / vip (5+)
      total_mensajes : proxy de engagement histórico (todo el chat acumulado)
      dias_inactivo  : cuántos días desde el último mensaje del cliente
      ticket_abierto : True si hay una escalación activa (no resuelta)
      es_opt_out     : si pidió baja de difusiones

    Diseñado para correr en ~3-5ms en hot path (cada respuesta del LLM).
    """
    ahora = datetime.utcnow()
    perfil = {
        "segmento":       "nuevo",
        "tier":           "nuevo",
        "total_mensajes": 0,
        "dias_inactivo":  None,
        "ticket_abierto": False,
        "es_opt_out":     False,
    }
    async with async_session() as session:
        # Último mensaje + total — una sola query agregada
        r = await session.execute(
            select(
                func.max(Mensaje.timestamp).label("last_msg"),
                func.count(Mensaje.id).label("total_msgs"),
            ).where(Mensaje.agent_id == agent_id, Mensaje.telefono == telefono)
        )
        fila = r.one()
        last_msg = fila.last_msg
        total = fila.total_msgs or 0
        perfil["total_mensajes"] = total

        # Segmento por días desde el último mensaje
        if last_msg:
            if isinstance(last_msg, str):
                try:
                    last_msg = datetime.fromisoformat(last_msg.replace("Z", ""))
                except Exception:
                    last_msg = None
            if last_msg:
                dias = (ahora - last_msg).days
                perfil["dias_inactivo"] = dias
                if dias < 30:
                    perfil["segmento"] = "activo"
                elif dias < 90:
                    perfil["segmento"] = "tibio"
                else:
                    perfil["segmento"] = "frio"

        # Tier por pedidos realizados
        cliente = await _get_cliente(session, telefono, agent_id)
        if cliente:
            pedidos = cliente.pedidos_realizados or 0
            if pedidos >= 5:
                perfil["tier"] = "vip"
            elif pedidos >= 1:
                perfil["tier"] = "recurrente"

        # Ticket abierto — cualquier estado no resuelto
        rt = await session.execute(
            select(func.count(Ticket.id)).where(
                Ticket.agent_id == agent_id,
                Ticket.telefono_cliente == telefono,
                Ticket.estado != "resuelto",
            )
        )
        perfil["ticket_abierto"] = (rt.scalar() or 0) > 0

        # Opt-out activo
        ro = await session.execute(
            select(func.count(OptOut.telefono)).where(
                OptOut.agent_id == agent_id,
                OptOut.telefono == telefono,
            )
        )
        perfil["es_opt_out"] = (ro.scalar() or 0) > 0

    return perfil


async def obtener_cliente(telefono: str, agent_id: int = 1) -> dict | None:
    """Devuelve los datos guardados del cliente o None si no existe."""
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if not cliente:
            return None
        return {
            "telefono": cliente.telefono,
            "nombres": cliente.nombres,
            "apellidos": cliente.apellidos,
            "razon_social": cliente.razon_social,
            "cc_nit": cliente.cc_nit,
            "direccion": cliente.direccion,
            "barrio": cliente.barrio,
            "ciudad": cliente.ciudad,
            "departamento": cliente.departamento,
            "email": cliente.email,
            "pedidos_realizados": cliente.pedidos_realizados or 0,
            "pedido_checkout_url": cliente.pedido_checkout_url or "",
        }


PEDIDO_PENDIENTE_TTL_HORAS = 48


async def guardar_pedido_pendiente(telefono: str, productos: list[dict], agent_id: int = 1):
    """Guarda el carrito que el cliente confirmó pero aún no completó en Shopify.
    Sirve para retomarlo si vuelve a escribir antes de finalizar el checkout."""
    if not productos:
        return
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        ahora = datetime.utcnow()
        if not cliente:
            cliente = Cliente(agent_id=agent_id, telefono=telefono)
            session.add(cliente)
        cliente.pedido_pendiente = json.dumps(productos, ensure_ascii=False)
        cliente.pedido_pendiente_at = ahora
        cliente.actualizado = ahora
        await session.commit()


async def obtener_pedido_pendiente(telefono: str, agent_id: int = 1) -> list[dict] | None:
    """Devuelve el carrito pendiente si existe y no ha expirado."""
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if not cliente or not cliente.pedido_pendiente or not cliente.pedido_pendiente_at:
            return None
        if datetime.utcnow() - cliente.pedido_pendiente_at > timedelta(hours=PEDIDO_PENDIENTE_TTL_HORAS):
            return None
        try:
            return json.loads(cliente.pedido_pendiente)
        except Exception:
            return None


async def limpiar_pedido_pendiente(telefono: str, agent_id: int = 1):
    """Borra el carrito pendiente y el checkout URL — cliente completó el pedido en Shopify."""
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if cliente:
            cliente.pedido_pendiente = ""
            cliente.pedido_pendiente_at = None
            cliente.pedido_checkout_url = ""
            cliente.actualizado = datetime.utcnow()
            await session.commit()


async def puede_enviar_checkout_abandono(
    telefono: str, cooldown_min: int, agent_id: int = 1
) -> bool:
    """Verifica si pasó el cooldown desde el último aviso de checkout abandonado.
    Persistente en BD (no en memoria) — sobrevive a deploys de Railway."""
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if not cliente or not cliente.checkout_abandono_notif_at:
            return True
        delta = datetime.utcnow() - cliente.checkout_abandono_notif_at
        return delta >= timedelta(minutes=cooldown_min)


async def marcar_checkout_abandono_enviado(telefono: str, agent_id: int = 1):
    """Marca el timestamp del último aviso para respetar el cooldown."""
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if not cliente:
            return
        cliente.checkout_abandono_notif_at = datetime.utcnow()
        await session.commit()


async def guardar_checkout_url(telefono: str, checkout_url: str, agent_id: int = 1):
    """Guarda la URL del checkout de Shopify para poder reenviarla si el cliente no termina.

    VALIDACIONES:
      1) Aceptamos URLs de checkout reales — Shopify usa varios formatos:
         - '/checkouts/cn/...' (webhook checkouts/create — SIN tokens de sesión)
         - '/checkouts/...'    (formato clásico)
         - '/cart/c/...?key=...&_s=...&_y=...' (Storefront API cartCreate — CON tokens)
         Cualquier otro patrón (home, /products, etc.) se rechaza.
      2) NO DEGRADAR: si ya hay un URL con tokens de sesión
         (?_r=, _s=, _y= o ?key= en /cart/c/) y la nueva NO los tiene,
         conservamos la actual. Es el bug donde el webhook checkouts/create
         reemplazaba la URL del Storefront API (con tokens) por una sin
         tokens → Shopify rechazaba la sesión y mostraba la home.
    """
    if not telefono or not checkout_url:
        return
    import logging
    log = logging.getLogger("agentkit")

    def _es_checkout_url_valida(url: str) -> bool:
        return ("/checkouts/" in url) or ("/checkout/" in url) or ("/cart/c/" in url)

    def _tiene_sesion(url: str) -> bool:
        """True si la URL trae tokens de sesión que Shopify necesita para no redirigir a home."""
        return (
            "_r=" in url
            or "_s=" in url
            or "_y=" in url
            or ("/cart/c/" in url and "key=" in url)
        )

    # Validar que sea una URL de checkout real, no la home de la tienda
    if not _es_checkout_url_valida(checkout_url):
        log.warning(
            f"[guardar_checkout_url] URL inválida (sin /checkouts/ ni /cart/c/) para {telefono}: "
            f"{checkout_url[:80]} — NO se guarda"
        )
        return
    nueva_tiene_auth = _tiene_sesion(checkout_url)
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if not cliente:
            cliente = Cliente(agent_id=agent_id, telefono=telefono)
            session.add(cliente)
        # Anti-degradación: si ya hay un URL con sesión y la nueva no, conservar la actual
        url_actual = (cliente.pedido_checkout_url or "").strip()
        actual_tiene_auth = _tiene_sesion(url_actual)
        if actual_tiene_auth and not nueva_tiene_auth:
            log.info(
                f"[guardar_checkout_url] {telefono}: NO sobreescribir — "
                f"actual tiene tokens de auth, nueva no (evita bug Shopify home)"
            )
            return
        cliente.pedido_checkout_url = checkout_url
        cliente.actualizado = datetime.utcnow()
        await session.commit()


async def limpiar_checkout_url(telefono: str, agent_id: int = 1) -> None:
    """Borra el pedido_checkout_url del cliente. Se llama cuando el cliente
    vacía explícitamente el carrito, para que el loop de checkout-abandonado
    no envíe un seguimiento de 'no terminaste tu pedido' minutos después."""
    if not telefono:
        return
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if not cliente:
            return
        cliente.pedido_checkout_url = ""
        cliente.actualizado = datetime.utcnow()
        await session.commit()


async def clientes_con_checkout_abandonado(
    min_min: int = 20,
    max_min: int = 120,
    agent_id: int = 1,
) -> list[tuple[str, str]]:
    """
    Devuelve (telefono, checkout_url) de clientes que iniciaron checkout
    pero no lo completaron (pedido_pendiente_at entre min_min y max_min minutos atrás
    y Shopify aún no disparó orders/create para limpiar el pedido_pendiente).

    DEFENSA: descartamos clientes cuyo `actualizado > pedido_pendiente_at`.
    Si el cliente fue actualizado DESPUÉS de marcar el pedido pendiente,
    algo pasó después — típicamente el webhook orders/create se procesó
    correctamente (y actualizó el cliente) pero por alguna razón el
    pedido_pendiente quedó colgado. Evita el bug "mensaje de carrito
    abandonado llega después de confirmar pedido".
    """
    import logging
    log = logging.getLogger("agentkit")
    ahora = datetime.utcnow()
    cutoff_reciente = ahora - timedelta(minutes=min_min)   # al menos min_min min de antigüedad
    cutoff_viejo = ahora - timedelta(minutes=max_min)      # no más de max_min min
    async with async_session() as session:
        q = select(Cliente).where(
            Cliente.agent_id == agent_id,
            Cliente.pedido_pendiente != "",
            Cliente.pedido_pendiente_at.is_not(None),
            Cliente.pedido_pendiente_at <= cutoff_reciente,
            Cliente.pedido_pendiente_at >= cutoff_viejo,
            Cliente.pedido_checkout_url != "",
        )
        result = await session.execute(q)
        clientes = result.scalars().all()
        # Defensa post-query: si actualizado > pedido_pendiente_at + ~30s,
        # hubo actividad posterior — el pedido probablemente se completó pero
        # algo no limpió. NO enviar recordatorio (cinturón ante limpiar fallido).
        clientes_filtrados = []
        for c in clientes:
            if c.actualizado and c.pedido_pendiente_at:
                if c.actualizado > c.pedido_pendiente_at + timedelta(seconds=30):
                    log.info(
                        f"[checkout-abandono] {c.telefono} saltado — actualizado "
                        f"({c.actualizado.isoformat()}) > pedido_pendiente_at "
                        f"({c.pedido_pendiente_at.isoformat()}) — probable pedido completado"
                    )
                    continue
            clientes_filtrados.append(c)
        return [
            (c.telefono, c.pedido_checkout_url)
            for c in clientes_filtrados
            if c.pedido_checkout_url
        ]


# ── Carrito activo (persistencia independiente del historial) ────────────────

CARRITO_TTL_HORAS = 4  # El carrito expira si el cliente no vuelve en 4 h
CARRITO_MERGE_HORAS = 2  # Si última actividad fue hace más, NO mergear (reemplazar)


async def guardar_carrito_activo(telefono: str, items: list[dict], agent_id: int = 1):
    """Guarda el estado actual del carrito en BD.
    Se llama cada vez que Andrea agrega/quita un producto."""
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        ahora = datetime.utcnow()
        if not cliente:
            cliente = Cliente(agent_id=agent_id, telefono=telefono)
            session.add(cliente)
        cliente.carrito_activo = json.dumps(items, ensure_ascii=False)
        cliente.carrito_activo_at = ahora
        cliente.actualizado = ahora
        await session.commit()


async def obtener_carrito_activo(telefono: str, agent_id: int = 1) -> list[dict]:
    """Devuelve el carrito en curso. Lista vacía si no existe o expiró."""
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if not cliente or not cliente.carrito_activo or not cliente.carrito_activo_at:
            return []
        if datetime.utcnow() - cliente.carrito_activo_at > timedelta(hours=CARRITO_TTL_HORAS):
            return []
        try:
            return json.loads(cliente.carrito_activo) or []
        except Exception:
            return []


async def limpiar_carrito_activo(telefono: str, agent_id: int = 1):
    """Borra el carrito activo — se llama cuando el pedido se confirma o se vacía."""
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if cliente:
            cliente.carrito_activo = ""
            cliente.carrito_activo_at = None
            cliente.actualizado = datetime.utcnow()
            await session.commit()


async def carrito_es_fresco_para_merge(telefono: str, agent_id: int = 1) -> bool:
    """Devuelve True si el carrito tiene actividad reciente (< CARRITO_MERGE_HORAS)
    y por tanto es seguro hacer merge con una orden nueva.

    Si False: el carrito anterior es muy viejo (entre CARRITO_MERGE_HORAS y
    CARRITO_TTL_HORAS) o no existe. La orden nueva debe REEMPLAZAR no sumar —
    evita acumular pedidos de días pasados que el cliente ya olvidó.
    """
    async with async_session() as session:
        cliente = await _get_cliente(session, telefono, agent_id)
        if not cliente or not cliente.carrito_activo or not cliente.carrito_activo_at:
            return False
        return (datetime.utcnow() - cliente.carrito_activo_at) <= timedelta(hours=CARRITO_MERGE_HORAS)


async def _clientes_carrito_en_ventana(
    min_min: int,
    max_min: int,
    agent_id: int = 1,
) -> list[tuple[str, list[dict]]]:
    """Helper interno: clientes con carrito activo guardado hace entre min_min y max_min minutos."""
    ahora = datetime.utcnow()
    # carrito guardado hace MÁS de min_min minutos
    cutoff_reciente = ahora - timedelta(minutes=min_min)
    # carrito guardado hace MENOS de max_min minutos (no tan viejo)
    cutoff_viejo = ahora - timedelta(minutes=max_min)
    async with async_session() as session:
        q = select(Cliente).where(
            Cliente.agent_id == agent_id,
            Cliente.carrito_activo != "",
            Cliente.carrito_activo_at.is_not(None),
            Cliente.carrito_activo_at <= cutoff_reciente,   # al menos min_min minutos de antigüedad
            Cliente.carrito_activo_at >= cutoff_viejo,      # no más de max_min minutos
        )
        result = await session.execute(q)
        clientes = result.scalars().all()
        out = []
        for c in clientes:
            try:
                items = json.loads(c.carrito_activo) if c.carrito_activo else []
                if items:
                    out.append((c.telefono, items))
            except Exception:
                pass
        return out


async def clientes_con_carrito_abandonado(
    min_inactivo: int = 10,
    max_inactivo: int = 30,
    agent_id: int = 1,
) -> list[tuple[str, list[dict]]]:
    """Carritos sin finalizar entre min_inactivo y max_inactivo minutos de antigüedad."""
    return await _clientes_carrito_en_ventana(min_inactivo, max_inactivo, agent_id)


async def clientes_para_crosssell(
    min_min: int = 2,
    max_min: int = 8,
    agent_id: int = 1,
) -> list[tuple[str, list[dict]]]:
    """Carritos recientes (2-8 min de antigüedad) para enviar cross-sell si total < $60k."""
    return await _clientes_carrito_en_ventana(min_min, max_min, agent_id)


# ── Estado de conversación / seguimientos automáticos ───────────────────────

async def _get_or_create_estado(session: AsyncSession, telefono: str, agent_id: int = 1) -> "EstadoConversacion":
    result = await session.execute(
        select(EstadoConversacion).where(
            EstadoConversacion.agent_id == agent_id,
            EstadoConversacion.telefono == telefono,
        )
    )
    estado = result.scalar_one_or_none()
    if not estado:
        estado = EstadoConversacion(agent_id=agent_id, telefono=telefono)
        session.add(estado)
    return estado


async def registrar_mensaje_usuario(telefono: str, agent_id: int = 1):
    """Cliente acaba de escribir → resetea timers de seguimiento."""
    async with async_session() as session:
        estado = await _get_or_create_estado(session, telefono, agent_id)
        ahora = datetime.utcnow()
        estado.last_user_at = ahora
        estado.follow_up_at = None
        estado.cierre_at = None
        estado.actualizado = ahora
        await session.commit()


async def registrar_mensaje_asistente(telefono: str, agent_id: int = 1):
    """Andrea acaba de responder → marca el último mensaje del bot."""
    async with async_session() as session:
        estado = await _get_or_create_estado(session, telefono, agent_id)
        ahora = datetime.utcnow()
        estado.last_assistant_at = ahora
        estado.actualizado = ahora
        await session.commit()


async def marcar_followup_enviado(telefono: str, agent_id: int = 1):
    async with async_session() as session:
        estado = await _get_or_create_estado(session, telefono, agent_id)
        estado.follow_up_at = datetime.utcnow()
        estado.actualizado = estado.follow_up_at
        await session.commit()


async def marcar_cierre_enviado(telefono: str, agent_id: int = 1):
    async with async_session() as session:
        estado = await _get_or_create_estado(session, telefono, agent_id)
        estado.cierre_at = datetime.utcnow()
        estado.actualizado = estado.cierre_at
        await session.commit()


async def conversaciones_para_followup(
    inactividad_minutos: int = 2,
    max_edad_horas: int = 12,
    agent_id: int = 1,
) -> list[str]:
    """Conversaciones donde:
    - El último mensaje fue del asistente (last_assistant_at > last_user_at o user nulo)
    - Pasaron al menos `inactividad_minutos` desde la última respuesta del bot
    - Aún no enviamos follow-up (follow_up_at IS NULL)
    - El último mensaje del bot no es más viejo que `max_edad_horas`
    - El cliente NO cerró la conversación (cierre_at IS NULL)
    - El cliente NO tiene carrito activo (esos se manejan en _procesar_carrito_unificado)
    - El cliente NO está en proceso de checkout
    """
    ahora = datetime.utcnow()
    cutoff_inactividad = ahora - timedelta(minutes=inactividad_minutos)
    cutoff_max_edad = ahora - timedelta(hours=max_edad_horas)
    async with async_session() as session:
        query = select(EstadoConversacion).where(
            EstadoConversacion.agent_id == agent_id,
            EstadoConversacion.last_assistant_at.is_not(None),
            EstadoConversacion.last_assistant_at <= cutoff_inactividad,
            EstadoConversacion.last_assistant_at >= cutoff_max_edad,
            EstadoConversacion.follow_up_at.is_(None),
            EstadoConversacion.cierre_at.is_(None),  # no molestar si cerró la conv
        )
        result = await session.execute(query)
        candidatos = result.scalars().all()

        telefonos = []
        for e in candidatos:
            # El último mensaje debe ser del asistente (no del cliente)
            if e.last_user_at is not None and e.last_assistant_at <= e.last_user_at:
                continue
            # No molestar si tiene carrito activo o está en checkout
            cliente = await _get_cliente(session, e.telefono, agent_id)
            if cliente and (cliente.pedido_checkout_url or cliente.carrito_activo):
                continue
            telefonos.append(e.telefono)
        return telefonos


async def conversaciones_para_cierre(min_despues_followup: int = 5, agent_id: int = 1) -> list[str]:
    """Conversaciones que ya recibieron follow-up genérico y siguen sin respuesta.
    Solo aplica a estado 6 (sin carrito, sin checkout)."""
    cutoff = datetime.utcnow() - timedelta(minutes=min_despues_followup)
    async with async_session() as session:
        query = select(EstadoConversacion).where(
            EstadoConversacion.agent_id == agent_id,
            EstadoConversacion.follow_up_at.is_not(None),
            EstadoConversacion.follow_up_at <= cutoff,
            EstadoConversacion.cierre_at.is_(None),
        )
        result = await session.execute(query)
        candidatos = result.scalars().all()
        telefonos = []
        for e in candidatos:
            if e.last_user_at is not None and e.follow_up_at <= e.last_user_at:
                continue
            # Solo cierre si no tiene carrito ni checkout activo
            cliente = await _get_cliente(session, e.telefono, agent_id)
            if cliente and (cliente.pedido_checkout_url or cliente.carrito_activo):
                continue
            telefonos.append(e.telefono)
        return telefonos


async def verificar_cierre_enviado(telefono: str, agent_id: int = 1) -> bool:
    """Retorna True si la conversación fue cerrada explícitamente (cierre_at set)."""
    async with async_session() as session:
        result = await session.execute(
            select(EstadoConversacion).where(
                EstadoConversacion.agent_id == agent_id,
                EstadoConversacion.telefono == telefono,
            )
        )
        estado = result.scalar_one_or_none()
        return bool(estado and estado.cierre_at)


# ── Opt-out — gestión de bajas de difusiones ─────────────────────────────────

async def marcar_opt_out(telefono: str, motivo: str = "", agent_id: int = 1) -> None:
    """Registra que este número no quiere recibir más difusiones masivas."""
    async with async_session() as session:
        result = await session.execute(
            select(OptOut).where(OptOut.agent_id == agent_id, OptOut.telefono == telefono)
        )
        existente = result.scalar_one_or_none()
        if not existente:
            session.add(OptOut(
                agent_id=agent_id,
                telefono=telefono,
                motivo=motivo[:200],
                creado_at=datetime.utcnow(),
            ))
            await session.commit()


async def verificar_opt_out(telefono: str, agent_id: int = 1) -> bool:
    """Retorna True si el número está dado de baja de las difusiones."""
    async with async_session() as session:
        result = await session.execute(
            select(OptOut).where(OptOut.agent_id == agent_id, OptOut.telefono == telefono)
        )
        return result.scalar_one_or_none() is not None


async def revertir_opt_out(telefono: str, agent_id: int = 1) -> None:
    """Reactiva el número para recibir difusiones (el cliente cambió de opinión)."""
    async with async_session() as session:
        result = await session.execute(
            select(OptOut).where(OptOut.agent_id == agent_id, OptOut.telefono == telefono)
        )
        registro = result.scalar_one_or_none()
        if registro:
            await session.delete(registro)
            await session.commit()


async def obtener_opt_outs(agent_id: int = 1) -> list[dict]:
    """Devuelve la lista completa de números dados de baja."""
    async with async_session() as session:
        result = await session.execute(
            select(OptOut).where(OptOut.agent_id == agent_id).order_by(OptOut.creado_at.desc())
        )
        rows = result.scalars().all()
        return [
            {
                "telefono": r.telefono,
                "motivo": r.motivo,
                "fecha": r.creado_at.isoformat() if r.creado_at else "",
            }
            for r in rows
        ]


async def obtener_clientes_con_estado(limite: int = 500, agent_id: int = 1) -> list[dict]:
    """
    Devuelve la base de clientes con su estado de engagement:
      activo  — último mensaje hace < 30 días
      tibio   — último mensaje hace 30-90 días
      frio    — último mensaje hace > 90 días
      baja    — registrado en opt_outs
    """
    ahora = datetime.utcnow()
    async with async_session() as session:
        # Subconsulta: último mensaje por teléfono y su timestamp (filtrado por agente)
        sub = (
            select(
                Mensaje.telefono,
                func.max(Mensaje.timestamp).label("last_msg"),
                func.count(Mensaje.id).label("total_msgs"),
            )
            .where(Mensaje.agent_id == agent_id, ~Mensaje.telefono.like("test-%"))
            .group_by(Mensaje.telefono)
            .subquery()
        )
        query = (
            select(sub, Cliente, OptOut)
            .outerjoin(Cliente, (sub.c.telefono == Cliente.telefono) & (Cliente.agent_id == agent_id))
            .outerjoin(OptOut,  (sub.c.telefono == OptOut.telefono) & (OptOut.agent_id == agent_id))
            .order_by(sub.c.last_msg.desc())
            .limit(limite)
        )
        result = await session.execute(query)
        rows = result.all()

    clientes = []
    for row in rows:
        tel        = row.telefono
        last_msg   = row.last_msg
        total_msgs = row.total_msgs or 0
        cliente    = row.Cliente
        opt_out    = row.OptOut

        # Calcular días desde el último mensaje
        if isinstance(last_msg, str):
            try:
                last_msg = datetime.fromisoformat(last_msg.replace("Z", ""))
            except Exception:
                last_msg = None

        if opt_out:
            estado = "baja"
        elif last_msg is None:
            estado = "frio"
        else:
            dias = (ahora - last_msg).days
            if dias < 30:
                estado = "activo"
            elif dias < 90:
                estado = "tibio"
            else:
                estado = "frio"

        nombre = ""
        pedidos = 0
        ciudad = ""
        if cliente:
            nombre  = f"{cliente.nombres or ''} {cliente.apellidos or ''}".strip()
            pedidos = cliente.pedidos_realizados or 0
            ciudad  = cliente.ciudad or ""

        clientes.append({
            "telefono":   tel,
            "nombre":     nombre or "",
            "ciudad":     ciudad,
            "estado":     estado,
            "pedidos":    pedidos,
            "total_msgs": total_msgs,
            "last_msg":   last_msg.isoformat() if last_msg else "",
            "opt_out_motivo": opt_out.motivo if opt_out else "",
        })

    return clientes


# ── Inbox / panel de administración ─────────────────────────────────────────

async def get_modo_humano(telefono: str, agent_id: int = 1) -> bool:
    """Retorna True si el modo humano está activo para esta conversación."""
    async with async_session() as session:
        result = await session.execute(
            select(EstadoConversacion).where(
                EstadoConversacion.agent_id == agent_id,
                EstadoConversacion.telefono == telefono,
            )
        )
        estado = result.scalar_one_or_none()
        if not estado:
            return False
        return bool(estado.modo_humano)


async def set_modo_humano(telefono: str, activo: bool, agent_id: int = 1):
    """Activa o desactiva el modo humano para una conversación."""
    async with async_session() as session:
        estado = await _get_or_create_estado(session, telefono, agent_id)
        estado.modo_humano = 1 if activo else 0
        estado.actualizado = datetime.utcnow()
        await session.commit()


async def obtener_todas_conversaciones(agent_id: int = 1) -> list[dict]:
    """Lista de conversaciones con el último mensaje de cada una, ordenadas por recientes."""
    async with async_session() as session:
        # Subconsulta: id del último mensaje por teléfono (filtrado por agente)
        sub = (
            select(Mensaje.telefono, func.max(Mensaje.id).label("max_id"))
            .where(Mensaje.agent_id == agent_id)
            .group_by(Mensaje.telefono)
            .subquery()
        )
        query = (
            select(Mensaje, EstadoConversacion, Cliente, OptOut)
            .join(sub, Mensaje.id == sub.c.max_id)
            .outerjoin(EstadoConversacion, (Mensaje.telefono == EstadoConversacion.telefono) & (EstadoConversacion.agent_id == agent_id))
            .outerjoin(Cliente, (Mensaje.telefono == Cliente.telefono) & (Cliente.agent_id == agent_id))
            .outerjoin(OptOut, (Mensaje.telefono == OptOut.telefono) & (OptOut.agent_id == agent_id))
            .where(~Mensaje.telefono.like("test-%"))
            .order_by(Mensaje.timestamp.desc())
            .limit(300)
        )
        result = await session.execute(query)
        rows = result.all()
        convs = []
        for msg, estado, cliente, opt_out in rows:
            nombre = ""
            if cliente:
                nombre = f"{cliente.nombres or ''} {cliente.apellidos or ''}".strip()
            convs.append({
                "telefono": msg.telefono,
                "nombre": nombre or msg.telefono,
                "ultimo_mensaje": (msg.content or "")[:100],
                "ultimo_role": msg.role,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else "",
                "modo_humano": bool(estado.modo_humano) if estado else False,
                "opt_out": opt_out is not None,
            })
        return convs


async def guardar_borrador_plantilla(nombre: str, categoria: str, idioma: str, datos: dict) -> int:
    """Crea o actualiza un borrador de plantilla. Retorna el ID del borrador."""
    async with async_session() as session:
        # Si ya existe un borrador con este nombre, actualizarlo
        q = select(PlantillaBorrador).where(PlantillaBorrador.nombre == nombre)
        result = await session.execute(q)
        borrador = result.scalar_one_or_none()
        ahora = datetime.utcnow()
        if borrador:
            borrador.categoria   = categoria
            borrador.idioma      = idioma
            borrador.datos_json  = json.dumps(datos, ensure_ascii=False)
            borrador.updated_at  = ahora
        else:
            borrador = PlantillaBorrador(
                nombre=nombre, categoria=categoria, idioma=idioma,
                datos_json=json.dumps(datos, ensure_ascii=False),
                created_at=ahora, updated_at=ahora,
            )
            session.add(borrador)
        await session.commit()
        await session.refresh(borrador)
        return borrador.id


async def obtener_borradores_plantillas() -> list[dict]:
    async with async_session() as session:
        q = select(PlantillaBorrador).order_by(PlantillaBorrador.updated_at.desc())
        result = await session.execute(q)
        rows = result.scalars().all()
        return [
            {
                "id": b.id,
                "nombre": b.nombre,
                "categoria": b.categoria,
                "idioma": b.idioma,
                "datos": json.loads(b.datos_json or "{}"),
                "updated_at": b.updated_at.isoformat() if b.updated_at else "",
            }
            for b in rows
        ]


async def eliminar_borrador_plantilla(bid: int) -> bool:
    async with async_session() as session:
        borrador = await session.get(PlantillaBorrador, bid)
        if borrador:
            await session.delete(borrador)
            await session.commit()
            return True
        return False


async def guardar_mensaje_difusion(
    wamid: str,
    campaign_id: str,
    campaign_name: str,
    telefono: str,
) -> None:
    """Registra un mensaje de difusión recién enviado para tracking posterior."""
    if not wamid or not campaign_id:
        return
    async with async_session() as session:
        msg = DifusionMensaje(
            wamid=wamid,
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            telefono=telefono,
            status="sent",
            sent_at=datetime.utcnow(),
        )
        session.add(msg)
        try:
            await session.commit()
        except Exception:
            pass  # duplicado (wamid ya existe)


async def actualizar_status_difusion(
    wamid: str,
    status: str,
    error_code: int | None = None,
    error_title: str = "",
    ts_str: str = "",
) -> None:
    """Actualiza el estado de entrega/lectura/fallo de un mensaje de difusión.
    Llamado desde el webhook de Meta cuando llega un status update."""
    if not wamid or not status:
        return
    try:
        ts = datetime.utcfromtimestamp(int(ts_str)) if ts_str else datetime.utcnow()
    except (ValueError, OSError, OverflowError):
        ts = datetime.utcnow()

    async with async_session() as session:
        result = await session.execute(
            select(DifusionMensaje).where(DifusionMensaje.wamid == wamid)
        )
        msg = result.scalar_one_or_none()
        if not msg:
            return  # no era un mensaje de difusión rastreado

        msg.status = status
        if status == "delivered":
            if not msg.delivered_at:
                msg.delivered_at = ts
        elif status == "read":
            if not msg.delivered_at:
                msg.delivered_at = ts   # read implica delivered
            if not msg.read_at:
                msg.read_at = ts
        elif status == "failed":
            msg.failed_at = ts or datetime.utcnow()
            if error_code is not None:
                msg.error_code = error_code
            # Descripción amigable: prioridad a la de nuestro mapa, luego la de Meta
            friendly = _META_ERROR_CODES.get(error_code or 0, "")
            msg.error_title = friendly or error_title or f"Error {error_code}"

        await session.commit()


async def obtener_detalle_campana(campaign_id: str) -> dict:
    """Estadísticas detalladas de una campaña: resumen + errores agrupados."""
    async with async_session() as session:
        result = await session.execute(
            select(DifusionMensaje)
            .where(DifusionMensaje.campaign_id == campaign_id)
            .order_by(DifusionMensaje.sent_at.asc())
        )
        msgs = result.scalars().all()

    total       = len(msgs)
    entregados  = sum(1 for m in msgs if m.status in ("delivered", "read"))
    leidos      = sum(1 for m in msgs if m.status == "read")
    fallidos    = sum(1 for m in msgs if m.status == "failed")
    pendientes  = total - entregados - fallidos  # aún sin confirmar entrega

    # Agrupar fallidos por código de error
    from collections import defaultdict
    err_groups: dict[int, dict] = defaultdict(lambda: {"count": 0, "numeros": [], "title": ""})
    for m in msgs:
        if m.status == "failed":
            key = m.error_code or 0
            err_groups[key]["count"] += 1
            err_groups[key]["title"] = m.error_title or _META_ERROR_CODES.get(key, f"Código {key}")
            if len(err_groups[key]["numeros"]) < 8:
                err_groups[key]["numeros"].append(m.telefono)

    errores_agrupados = sorted(
        [
            {
                "code": k,
                "description": v["title"],
                "count": v["count"],
                "numeros": v["numeros"],
            }
            for k, v in err_groups.items()
        ],
        key=lambda x: -x["count"],
    )

    return {
        "total":      total,
        "entregados": entregados,
        "leidos":     leidos,
        "fallidos":   fallidos,
        "pendientes": pendientes,
        "errores":    errores_agrupados,
    }


async def registrar_difusion(
    template_name: str,
    language: str,
    destinatarios: int,
    enviados: int,
    fallidos: int,
    errores: list[str],
    campaign_name: str = "",
    campaign_id: str = "",
):
    """Guarda el resultado de un lote de difusión. Cada lote de 50 es un registro;
    se agrupan por campaign_id al consultar el historial."""
    async with async_session() as session:
        dif = Difusion(
            campaign_name=campaign_name,
            campaign_id=campaign_id,
            template_name=template_name,
            language=language,
            destinatarios=destinatarios,
            enviados=enviados,
            fallidos=fallidos,
            errores_json=json.dumps(errores[:20], ensure_ascii=False),
            created_at=datetime.utcnow(),
        )
        session.add(dif)
        await session.commit()


async def obtener_difusiones(limite: int = 100, agent_id: int = 1) -> list[dict]:
    """Campañas de difusión agrupadas por campaign_id, con stats en vivo de delivery/lectura."""
    from sqlalchemy import text
    async with async_session() as session:
        # ── Query 1: base de difusiones (agrupada) ──────────────────────────
        sql_base = text("""
            SELECT
                COALESCE(NULLIF(campaign_id,''), CAST(id AS TEXT))          AS grp,
                COALESCE(NULLIF(MAX(campaign_name),''), MAX(template_name)) AS campaign_name,
                MAX(template_name)                                          AS template_name,
                MAX(language)                                               AS language,
                SUM(destinatarios)                                          AS destinatarios,
                SUM(enviados)                                               AS enviados,
                MIN(created_at)                                             AS created_at,
                MAX(CASE WHEN campaign_id != '' THEN campaign_id ELSE NULL END) AS campaign_id
            FROM difusiones
            WHERE COALESCE(agent_id, 1) = :agent_id
            GROUP BY COALESCE(NULLIF(campaign_id,''), CAST(id AS TEXT))
            ORDER BY MIN(created_at) DESC
            LIMIT :lim
        """)
        r1 = await session.execute(sql_base, {"lim": limite, "agent_id": agent_id})
        rows = r1.fetchall()

        # ── Query 2: stats en vivo de difusion_mensajes ──────────────────────
        sql_stats = text("""
            SELECT
                campaign_id,
                COUNT(CASE WHEN status IN ('delivered','read') THEN 1 END) AS entregados,
                COUNT(CASE WHEN status = 'read'                THEN 1 END) AS leidos,
                COUNT(CASE WHEN status = 'failed'              THEN 1 END) AS fallidos_wh
            FROM difusion_mensajes
            WHERE COALESCE(agent_id, 1) = :agent_id
            GROUP BY campaign_id
        """)
        r2 = await session.execute(sql_stats, {"agent_id": agent_id})
        stats_map = {row.campaign_id: row for row in r2.fetchall()}

    resultado = []
    for row in rows:
        cid   = row.campaign_id       # None si registro antiguo sin campaign_id
        stats = stats_map.get(cid) if cid else None
        resultado.append({
            "campaign_id":   cid or "",
            "campaign_name": row.campaign_name or row.template_name,
            "template_name": row.template_name,
            "language":      row.language,
            "destinatarios": row.destinatarios,
            "enviados":      row.enviados,
            "entregados":    stats.entregados if stats else None,
            "leidos":        stats.leidos     if stats else None,
            "fallidos_wh":   stats.fallidos_wh if stats else None,
            "has_tracking":  cid is not None,
            "created_at":    row.created_at if isinstance(row.created_at, str)
                             else (row.created_at.isoformat() if row.created_at else ""),
        })
    return resultado


# Tarifa Meta por conversación de marketing iniciada por empresa (USD)
# Meta cobra cuando el template se envía y abre una ventana de 24 h.
# 1 destinatario = 1 conversación = 1 cobro.
# Fuente: Meta Business Messaging Pricing (Colombia/LATAM, categoría Marketing)
META_TARIFA_MARKETING_USD = 0.0165


async def _atribuir_ventas_shopify(
    campaign_id: str,
    telefono_lista: list[str],
    desde_dt: datetime,
    ventana_dias: int = 7,
) -> float:
    """
    Consulta Shopify Admin API para sumar ventas de órdenes creadas
    dentro de `ventana_dias` días después de `desde_dt`,
    cuyos clientes tienen teléfono en `telefono_lista`.
    Retorna total en COP (currency del store).
    """
    import os, httpx
    store       = os.getenv("SHOPIFY_STORE", "")
    admin_token = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
    if not store or not admin_token or not telefono_lista:
        return 0.0

    hasta_dt = desde_dt + timedelta(days=ventana_dias)
    # Normalizar teléfonos: quitar +57 y dejar solo dígitos para comparar
    def _norm(p: str) -> str:
        d = "".join(c for c in p if c.isdigit())
        return d[-10:] if len(d) >= 10 else d  # últimos 10 dígitos

    tels_norm = {_norm(t) for t in telefono_lista if t}

    url = (
        f"https://{store}/admin/api/2024-10/orders.json"
        f"?status=any&created_at_min={desde_dt.isoformat()}Z"
        f"&created_at_max={hasta_dt.isoformat()}Z"
        f"&limit=250&fields=total_price,currency,billing_address,customer"
    )
    headers = {"X-Shopify-Access-Token": admin_token}

    total = 0.0
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            while url:
                r = await client.get(url, headers=headers)
                data = r.json()
                for order in data.get("orders", []):
                    # Obtener teléfono del cliente desde billing_address o customer
                    phone = ""
                    ba = order.get("billing_address") or {}
                    phone = ba.get("phone", "") or ""
                    if not phone:
                        cust = order.get("customer") or {}
                        phone = cust.get("phone", "") or ""
                    if _norm(phone) in tels_norm:
                        try:
                            total += float(order.get("total_price", 0) or 0)
                        except (ValueError, TypeError):
                            pass
                # Paginación via Link header
                link = r.headers.get("link", "")
                url = None
                if 'rel="next"' in link:
                    import re as _re
                    m = _re.search(r'<([^>]+)>;\s*rel="next"', link)
                    if m:
                        url = m.group(1)
    except Exception:
        pass
    return round(total, 2)


async def obtener_campana_reciente_para_telefono(
    telefono: str,
    max_horas: int = 72,
    agent_id: int = 1,
) -> dict | None:
    """
    Retorna la campaña más reciente enviada a este teléfono (dentro de max_horas).
    Se usa para inyectar contexto cuando el cliente responde a una difusión.
    Retorna None si no hay campaña reciente o si el cliente ya inició conversación antes de responder.
    """
    desde = datetime.utcnow() - timedelta(hours=max_horas)
    async with async_session() as session:
        r = await session.execute(
            text(
                """
                SELECT dm.campaign_id, dm.campaign_name, dm.sent_at,
                       d.template_name
                FROM difusion_mensajes dm
                LEFT JOIN difusiones d ON d.campaign_id = dm.campaign_id
                WHERE dm.telefono = :tel
                  AND dm.sent_at  >= :desde
                  AND dm.agent_id = :agent_id
                ORDER BY dm.sent_at DESC
                LIMIT 1
                """
            ),
            {"tel": telefono, "desde": desde, "agent_id": agent_id},
        )
        row = r.fetchone()
        if not row:
            return None

        sent_at_raw = row[2]
        horas_ago = 0
        sent_at_iso = ""

        # SQLite devuelve strings al usar text() — convertir si es necesario
        if sent_at_raw:
            if isinstance(sent_at_raw, str):
                try:
                    sent_at_dt = datetime.fromisoformat(sent_at_raw.replace("Z", ""))
                except ValueError:
                    sent_at_dt = None
            else:
                sent_at_dt = sent_at_raw  # ya es datetime

            if sent_at_dt:
                delta = datetime.utcnow() - sent_at_dt
                horas_ago = max(0, int(delta.total_seconds() / 3600))
                sent_at_iso = sent_at_dt.isoformat()

        return {
            "campaign_id":   row[0] or "",
            "campaign_name": row[1] or row[3] or "campaña reciente",
            "template_name": row[3] or "",
            "sent_at":       sent_at_iso,
            "horas_ago":     horas_ago,
        }


async def obtener_metricas_internas(
    dias: int = 30,
    agent_id: int = 1,
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> dict:
    """
    Métricas calculadas íntegramente desde la base de datos local.
    Incluye costo Meta (conversaciones iniciadas × tarifa) y
    atribución de ventas Shopify por teléfonos de destinatarios.

    Si se pasan `desde` y `hasta` se usan esas fechas. Si no, se calcula
    `desde = ahora - dias` y `hasta = ahora`.
    """
    if desde is None:
        desde = datetime.utcnow() - timedelta(days=dias)
    if hasta is None:
        hasta = datetime.utcnow()

    params = {"desde": desde, "hasta": hasta, "agent_id": agent_id}
    async with async_session() as session:
        # ── Difusiones (campañas) ──────────────────────────────────────────
        r_dif = await session.execute(
            text(
                """
                SELECT
                  COUNT(DISTINCT COALESCE(NULLIF(campaign_id,''), CAST(id AS TEXT))) AS total_campanas,
                  COALESCE(SUM(enviados), 0)      AS total_enviados,
                  COALESCE(SUM(destinatarios), 0) AS total_destinatarios
                FROM difusiones
                WHERE created_at >= :desde AND created_at <= :hasta AND agent_id = :agent_id
                """
            ),
            params,
        )
        row_dif = r_dif.fetchone()
        total_campanas    = int(row_dif[0] or 0)
        total_enviados    = int(row_dif[1] or 0)

        # ── Tracking de difusión (difusion_mensajes) ──────────────────────
        r_tr = await session.execute(
            text(
                """
                SELECT
                  COUNT(*)                                        AS rastreados,
                  SUM(CASE WHEN status IN ('delivered','read') THEN 1 ELSE 0 END) AS entregados,
                  SUM(CASE WHEN status = 'read'  THEN 1 ELSE 0 END)              AS leidos,
                  SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)             AS fallidos
                FROM difusion_mensajes
                WHERE sent_at >= :desde AND sent_at <= :hasta AND agent_id = :agent_id
                """
            ),
            params,
        )
        row_tr = r_tr.fetchone()
        rastreados  = int(row_tr[0] or 0)
        entregados  = int(row_tr[1] or 0)
        leidos      = int(row_tr[2] or 0)
        fallidos    = int(row_tr[3] or 0)

        tasa_entrega = round(entregados / rastreados * 100, 1) if rastreados else 0
        tasa_lectura = round(leidos     / rastreados * 100, 1) if rastreados else 0

        # ── Conversaciones (mensajes) ─────────────────────────────────────
        r_conv = await session.execute(
            text(
                """
                SELECT
                  COUNT(DISTINCT telefono)                                         AS chats_activos,
                  SUM(CASE WHEN role = 'user'      THEN 1 ELSE 0 END)             AS mensajes_recibidos,
                  SUM(CASE WHEN role = 'assistant' THEN 1 ELSE 0 END)             AS mensajes_enviados_ai
                FROM mensajes
                WHERE timestamp >= :desde AND timestamp <= :hasta AND agent_id = :agent_id
                """
            ),
            params,
        )
        row_conv = r_conv.fetchone()
        chats_activos      = int(row_conv[0] or 0)
        mensajes_recibidos = int(row_conv[1] or 0)
        mensajes_ai        = int(row_conv[2] or 0)

        # ── Rendimiento por campaña (top 15 más recientes) ────────────────
        r_camp = await session.execute(
            text(
                """
                SELECT
                  d.campaign_id,
                  d.campaign_name,
                  d.created_at,
                  d.enviados,
                  COALESCE(tr.rastreados, 0)  AS rastreados,
                  COALESCE(tr.entregados, 0)  AS entregados,
                  COALESCE(tr.leidos, 0)      AS leidos,
                  COALESCE(tr.fallidos, 0)    AS fallidos
                FROM (
                  SELECT
                    COALESCE(NULLIF(campaign_id,''), CAST(id AS TEXT))                          AS campaign_id,
                    COALESCE(NULLIF(MAX(campaign_name),''), NULLIF(MAX(template_name),''), 'Sin nombre') AS campaign_name,
                    MAX(created_at) AS created_at,
                    SUM(enviados)   AS enviados
                  FROM difusiones
                  WHERE created_at >= :desde AND created_at <= :hasta AND agent_id = :agent_id
                  GROUP BY COALESCE(NULLIF(campaign_id,''), CAST(id AS TEXT))
                ) d
                LEFT JOIN (
                  SELECT
                    campaign_id,
                    COUNT(*)                                                       AS rastreados,
                    SUM(CASE WHEN status IN ('delivered','read') THEN 1 ELSE 0 END) AS entregados,
                    SUM(CASE WHEN status = 'read'   THEN 1 ELSE 0 END)            AS leidos,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)            AS fallidos
                  FROM difusion_mensajes
                  WHERE sent_at >= :desde AND sent_at <= :hasta AND agent_id = :agent_id
                  GROUP BY campaign_id
                ) tr ON d.campaign_id = tr.campaign_id
                ORDER BY d.created_at DESC
                LIMIT 15
                """
            ),
            params,
        )
        # Recopilar filas de campañas primero
        camp_rows = r_camp.fetchall()

        # ── Teléfonos por campaña (para atribución Shopify) ──────────────
        campaign_ids = [rw[0] for rw in camp_rows if rw[0]]
        tels_por_campana: dict[str, list[str]] = {}
        if campaign_ids:
            placeholders = ",".join([f"'{cid}'" for cid in campaign_ids])
            r_tels = await session.execute(
                text(
                    f"""
                    SELECT campaign_id, telefono
                    FROM difusion_mensajes
                    WHERE campaign_id IN ({placeholders})
                      AND agent_id = {agent_id}
                    """
                )
            )
            for row in r_tels.fetchall():
                tels_por_campana.setdefault(row[0], []).append(row[1])

    # ── Atribución de ventas Shopify (fuera del session context) ─────────
    # Se hace de forma asíncrona por campaña
    ventas_por_campana: dict[str, float] = {}
    for rw in camp_rows:
        cid   = rw[0]
        fecha = rw[2]  # datetime
        tels  = tels_por_campana.get(cid, [])
        if tels and fecha:
            ventas = await _atribuir_ventas_shopify(cid, tels, fecha, ventana_dias=7)
            ventas_por_campana[cid] = ventas

    # ── Totales globales de costo y ventas ────────────────────────────────
    costo_total_usd = round(total_enviados * META_TARIFA_MARKETING_USD, 4)
    ventas_total_cop = sum(ventas_por_campana.values())

    campanas = []
    for rw in camp_rows:
        env   = int(rw[3] or 0)
        ra    = int(rw[4] or 0)
        en    = int(rw[5] or 0)
        le    = int(rw[6] or 0)
        fa    = int(rw[7] or 0)
        cid   = rw[0]
        fecha = rw[2]

        # Costo Meta: 1 conversación por destinatario enviado × tarifa
        costo_usd   = round(env * META_TARIFA_MARKETING_USD, 4)
        ventas_cop  = ventas_por_campana.get(cid, 0.0)

        roi = None
        roas = None
        if costo_usd > 0 and ventas_cop > 0:
            # ROI y ROAS requieren moneda común — se calcula como ratio puro
            # (ventas en COP, costo en USD: se muestran por separado)
            # ROAS = ventas / costo (en misma moneda, usamos ratio ventas/costo_cop)
            # Para ROI necesitamos convertir → se omite conversión automática,
            # se muestran las cifras separadas y el usuario interpreta.
            roas = round(ventas_cop / (costo_usd * 1), 2)  # placeholder ratio

        campanas.append({
            "campaign_id":   cid,
            "campaign_name": rw[1],
            "fecha":         fecha.isoformat() if fecha else "",
            "enviados":      env,
            "rastreados":    ra,
            "entregados":    en,
            "leidos":        le,
            "fallidos":      fa,
            "pct_entrega":   round(en / ra * 100, 1) if ra else None,
            "pct_lectura":   round(le / ra * 100, 1) if ra else None,
            "costo_usd":     costo_usd,
            "ventas_cop":    ventas_cop,
            "tiene_ventas":  ventas_cop > 0,
        })

    return {
        "periodo_dias": dias,
        "tarifa_meta_usd": META_TARIFA_MARKETING_USD,
        "difusiones": {
            "total_campanas":  total_campanas,
            "total_enviados":  total_enviados,
            "costo_total_usd": costo_total_usd,
            "rastreados":      rastreados,
            "entregados":      entregados,
            "leidos":          leidos,
            "fallidos":        fallidos,
            "tasa_entrega":    tasa_entrega,
            "tasa_lectura":    tasa_lectura,
        },
        "conversaciones": {
            "chats_activos":      chats_activos,
            "mensajes_recibidos": mensajes_recibidos,
            "mensajes_ai":        mensajes_ai,
        },
        "campanas":           campanas,
        "ventas_total_cop":   ventas_total_cop,
        "shopify_habilitado": bool(os.getenv("SHOPIFY_ADMIN_TOKEN", "")),
        "desde":              desde.isoformat(),
        "hasta":              hasta.isoformat(),
    }


async def obtener_series_metricas(
    desde: datetime,
    hasta: datetime,
    granularidad: str = "dia",   # "dia" | "semana" | "mes"
    agent_id: int = 1,
) -> dict:
    """Series temporales para gráficas: enviados, entregados, leídos, mensajes
    agrupados por día, semana o mes. PostgreSQL-friendly (usa date_trunc)."""
    # Validar granularidad
    if granularidad not in ("dia", "semana", "mes"):
        granularidad = "dia"
    pg_trunc = {"dia": "day", "semana": "week", "mes": "month"}[granularidad]

    params = {"desde": desde, "hasta": hasta, "agent_id": agent_id}

    async with async_session() as session:
        # ── Serie de difusiones (enviados por período) ──
        r_dif = await session.execute(
            text(f"""
                SELECT
                  date_trunc('{pg_trunc}', created_at) AS periodo,
                  COUNT(DISTINCT COALESCE(NULLIF(campaign_id,''), CAST(id AS TEXT))) AS campanas,
                  COALESCE(SUM(enviados), 0) AS enviados
                FROM difusiones
                WHERE created_at >= :desde AND created_at <= :hasta AND agent_id = :agent_id
                GROUP BY 1
                ORDER BY 1
            """),
            params,
        )
        serie_difusiones = [
            {"periodo": r[0].isoformat() if r[0] else "",
             "campanas": int(r[1] or 0),
             "enviados": int(r[2] or 0)}
            for r in r_dif.fetchall()
        ]

        # ── Serie de tracking (entregados/leídos/fallidos por período) ──
        r_tr = await session.execute(
            text(f"""
                SELECT
                  date_trunc('{pg_trunc}', sent_at) AS periodo,
                  COUNT(*) AS rastreados,
                  SUM(CASE WHEN status IN ('delivered','read') THEN 1 ELSE 0 END) AS entregados,
                  SUM(CASE WHEN status = 'read'   THEN 1 ELSE 0 END) AS leidos,
                  SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS fallidos
                FROM difusion_mensajes
                WHERE sent_at >= :desde AND sent_at <= :hasta AND agent_id = :agent_id
                GROUP BY 1
                ORDER BY 1
            """),
            params,
        )
        serie_tracking = [
            {"periodo": r[0].isoformat() if r[0] else "",
             "rastreados": int(r[1] or 0),
             "entregados": int(r[2] or 0),
             "leidos":     int(r[3] or 0),
             "fallidos":   int(r[4] or 0)}
            for r in r_tr.fetchall()
        ]

        # ── Serie de conversaciones (mensajes recibidos/enviados por IA) ──
        r_conv = await session.execute(
            text(f"""
                SELECT
                  date_trunc('{pg_trunc}', timestamp) AS periodo,
                  COUNT(DISTINCT telefono) AS chats,
                  SUM(CASE WHEN role = 'user'      THEN 1 ELSE 0 END) AS recibidos,
                  SUM(CASE WHEN role = 'assistant' THEN 1 ELSE 0 END) AS enviados_ai
                FROM mensajes
                WHERE timestamp >= :desde AND timestamp <= :hasta AND agent_id = :agent_id
                GROUP BY 1
                ORDER BY 1
            """),
            params,
        )
        serie_conversaciones = [
            {"periodo": r[0].isoformat() if r[0] else "",
             "chats":       int(r[1] or 0),
             "recibidos":   int(r[2] or 0),
             "enviados_ai": int(r[3] or 0)}
            for r in r_conv.fetchall()
        ]

    return {
        "granularidad":  granularidad,
        "desde":         desde.isoformat(),
        "hasta":         hasta.isoformat(),
        "difusiones":    serie_difusiones,
        "tracking":      serie_tracking,
        "conversaciones": serie_conversaciones,
    }


async def obtener_historial_con_timestamps(telefono: str, limite: int = 150, agent_id: int = 1) -> list[dict]:
    """Historial reciente con timestamps para el inbox.

    Devuelve los últimos `limite` mensajes en orden cronológico (los más
    antiguos primero, los más recientes al final). Antes ordenaba ASC y
    aplicaba LIMIT, lo que traía los 150 más VIEJOS — los más recientes
    nunca llegaban al panel cuando la conversación superaba ese tope.
    Ahora ordena DESC + LIMIT (los más recientes) y revierte para mostrar
    cronológicamente. Mismo patrón que obtener_historial() para Claude.
    """
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono, Mensaje.agent_id == agent_id)
            .order_by(Mensaje.timestamp.desc())
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()
        mensajes = list(reversed(mensajes))
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else "",
            }
            for msg in mensajes
        ]


# ── Configuración dinámica ──────────────────────────────────────────────────

async def get_config_value(clave: str, agent_id: int = 1) -> str | None:
    """Lee un valor de configuración desde la BD. Retorna None si no existe."""
    async with async_session() as session:
        result = await session.execute(
            select(ConfigValue).where(ConfigValue.agent_id == agent_id, ConfigValue.clave == clave)
        )
        row = result.scalar_one_or_none()
        return row.valor if row and row.valor else None


async def set_config_value(clave: str, valor: str, agent_id: int = 1) -> None:
    """Guarda o actualiza un valor de configuración en la BD."""
    async with async_session() as session:
        result = await session.execute(
            select(ConfigValue).where(ConfigValue.agent_id == agent_id, ConfigValue.clave == clave)
        )
        row = result.scalar_one_or_none()
        ahora = datetime.utcnow()
        if row:
            row.valor = valor
            row.actualizado_at = ahora
        else:
            session.add(ConfigValue(agent_id=agent_id, clave=clave, valor=valor, actualizado_at=ahora))
        await session.commit()


async def get_all_config_values(agent_id: int = 1) -> dict[str, str]:
    """Devuelve todos los valores de configuración como dict {clave: valor}."""
    async with async_session() as session:
        result = await session.execute(select(ConfigValue).where(ConfigValue.agent_id == agent_id))
        return {row.clave: row.valor for row in result.scalars().all() if row.valor}


async def resolve_setting(clave: str, default: str = "", agent_id: int = 1) -> str:
    """Lee el valor de BD primero; si no existe, usa la variable de entorno."""
    db_val = await get_config_value(clave, agent_id)
    if db_val:
        return db_val
    return os.getenv(clave, default)


async def cargar_config_en_env(agent_id: int = 1) -> None:
    """Al iniciar, carga los valores de config_values de la BD en os.environ.
    Solo carga el agente indicado (default: Equora, agent_id=1).
    Así todas las partes del sistema que leen os.getenv() reciben los valores
    guardados por el usuario sin necesidad de reiniciar."""
    try:
        valores = await get_all_config_values(agent_id)
        for clave, valor in valores.items():
            if valor:
                os.environ[clave] = valor
    except Exception:
        pass  # La tabla puede no existir aún en el primer arranque


# ── CRUD de agentes ─────────────────────────────────────────────────────────

def _agent_to_dict(a: Agent) -> dict:
    return {
        "id": a.id,
        "slug": a.slug,
        "name": a.name,
        "agent_name": a.agent_name,
        "business_type": a.business_type,
        "status": a.status,
        "phone_number_id": a.phone_number_id,
        "waba_id": a.waba_id,
        "color": a.color,
        "emoji": a.emoji,
        "created_at": a.created_at.isoformat() if a.created_at else "",
        "owner_id": a.owner_id,
    }


async def crear_agente(
    name: str,
    slug: str,
    agent_name: str = "Agente",
    business_type: str = "productos",
    phone_number_id: str = "",
    waba_id: str = "",
    color: str = "#6366f1",
    emoji: str = "🤖",
    owner_id: int | None = None,
) -> dict:
    """Crea un nuevo agente en la plataforma Voco. Retorna el dict del agente creado."""
    async with async_session() as session:
        agente = Agent(
            slug=slug,
            name=name,
            agent_name=agent_name,
            business_type=business_type,
            status="draft",
            phone_number_id=phone_number_id,
            waba_id=waba_id,
            color=color,
            emoji=emoji,
            created_at=datetime.utcnow(),
            owner_id=owner_id,
        )
        session.add(agente)
        await session.commit()
        await session.refresh(agente)
        return _agent_to_dict(agente)


async def obtener_agente(agent_id: int) -> dict | None:
    """Retorna el dict de un agente por su ID, o None si no existe."""
    async with async_session() as session:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agente = result.scalar_one_or_none()
        return _agent_to_dict(agente) if agente else None


async def obtener_agente_por_slug(slug: str) -> dict | None:
    """Retorna el dict de un agente por su slug, o None si no existe."""
    async with async_session() as session:
        result = await session.execute(select(Agent).where(Agent.slug == slug))
        agente = result.scalar_one_or_none()
        return _agent_to_dict(agente) if agente else None


async def obtener_agente_por_phone_id(phone_number_id: str) -> dict | None:
    """Retorna el agente asociado a un phone_number_id de Meta, o None."""
    if not phone_number_id:
        return None
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.phone_number_id == phone_number_id)
        )
        agente = result.scalar_one_or_none()
        return _agent_to_dict(agente) if agente else None


async def obtener_todos_agentes() -> list[dict]:
    """Retorna la lista de todos los agentes registrados."""
    async with async_session() as session:
        result = await session.execute(select(Agent).order_by(Agent.id))
        return [_agent_to_dict(a) for a in result.scalars().all()]


async def actualizar_agente(agent_id: int, **kwargs) -> bool:
    """Actualiza campos de un agente. Retorna True si el agente existe."""
    campos_permitidos = {
        "name", "slug", "agent_name", "business_type", "status",
        "phone_number_id", "waba_id", "color", "emoji", "owner_id",
    }
    async with async_session() as session:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agente = result.scalar_one_or_none()
        if not agente:
            return False
        for campo, valor in kwargs.items():
            if campo in campos_permitidos:
                setattr(agente, campo, valor)
        await session.commit()
        return True


# ── Promoción post-venta configurable por agente ─────────────────────────────
# Subsystem aislado para encapsular validación. NO se expone vía actualizar_agente()
# para que un cambio accidental en otro endpoint no rompa promociones activas.

DESCUENTO_MENSAJE_DEFAULT = (
    "🎁 Como agradecimiento, en tu próxima compra usa el código *{codigo}* "
    "y obtén *{pct}% de descuento* 😊"
)


async def obtener_descuento_promo(agent_id: int) -> dict | None:
    """Devuelve la config de promoción activa del agente, o None si no aplica.

    None significa: NO enviar mensaje de descuento. Esto ocurre cuando:
      - El agente no existe
      - descuento_activo = False
      - Falta alguno de los campos críticos (codigo vacío, umbral <= 0, pct <= 0)

    El caller debe interpretar None como "no hacer nada" (no enviar mensaje).
    """
    async with async_session() as session:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agente = result.scalar_one_or_none()
        if not agente or not agente.descuento_activo:
            return None
        codigo = (agente.descuento_codigo or "").strip()
        umbral = int(agente.descuento_umbral or 0)
        pct    = int(agente.descuento_pct or 0)
        # Validación defensiva — si la config quedó incompleta por algún edge case,
        # NO enviamos nada (mejor silencio que mensaje roto al cliente).
        if not codigo or umbral <= 0 or pct <= 0 or pct > 100:
            return None
        mensaje = (agente.descuento_mensaje or "").strip() or DESCUENTO_MENSAJE_DEFAULT
        return {
            "umbral":  umbral,
            "codigo":  codigo,
            "pct":     pct,
            "mensaje": mensaje,
        }


async def guardar_descuento_promo(
    agent_id: int,
    activo: bool,
    umbral: int = 0,
    codigo: str = "",
    pct: int = 0,
    mensaje: str = "",
) -> tuple[bool, str]:
    """Guarda la configuración de promoción del agente.

    Retorna (ok, mensaje_error). Si ok=False, no se guardó nada y mensaje_error
    explica el problema. Validaciones:
      - Si activo=True: umbral >= 1000, codigo no vacío y solo [A-Z0-9_-], pct 1-100
      - Si activo=False: se permite guardar los otros campos (para preservar lo
        que el cliente ya tenía configurado y poder reactivar luego)

    El template del mensaje puede usar {codigo}, {pct} y {umbral} como placeholders.
    """
    import re as _re

    if activo:
        if umbral < 1000:
            return False, "El umbral debe ser al menos $1.000"
        if not codigo or not _re.match(r"^[A-Z0-9_-]{2,30}$", codigo):
            return False, "El código debe tener entre 2 y 30 caracteres y solo letras MAYÚSCULAS, números, guion o guion bajo"
        if pct < 1 or pct > 100:
            return False, "El porcentaje debe estar entre 1 y 100"
        # Mensaje vacío usa default; si viene, debe contener al menos {codigo}
        if mensaje and "{codigo}" not in mensaje:
            return False, "El mensaje debe incluir el placeholder {codigo} para que el cliente vea el código"

    async with async_session() as session:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agente = result.scalar_one_or_none()
        if not agente:
            return False, "Agente no encontrado"
        agente.descuento_activo  = bool(activo)
        agente.descuento_umbral  = int(umbral or 0)
        agente.descuento_codigo  = (codigo or "").strip().upper()
        agente.descuento_pct     = int(pct or 0)
        agente.descuento_mensaje = (mensaje or "").strip()
        await session.commit()
        return True, ""


async def obtener_descuento_promo_config(agent_id: int) -> dict:
    """Devuelve los valores actuales del agente para mostrar en el panel.

    A diferencia de obtener_descuento_promo() que retorna None cuando no aplica,
    esta función SIEMPRE devuelve un dict con los campos (vacíos si no se ha
    configurado) — la UI necesita mostrar el form aunque esté desactivado.
    """
    async with async_session() as session:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agente = result.scalar_one_or_none()
        if not agente:
            return {"activo": False, "umbral": 0, "codigo": "", "pct": 0, "mensaje": ""}
        return {
            "activo":  bool(agente.descuento_activo),
            "umbral":  int(agente.descuento_umbral or 0),
            "codigo":  agente.descuento_codigo or "",
            "pct":     int(agente.descuento_pct or 0),
            "mensaje": agente.descuento_mensaje or "",
        }


# ── Mensajes del sistema configurables por agente (#28) ─────────────────────
# Cada mensaje tiene un default en agent/mensajes.py:MENSAJES. Si el agente lo
# personalizó, su override vive en la tabla agent_messages. La función
# obtener_mensaje() resuelve esto transparentemente — el código que envía
# mensajes no necesita saber si hay override o no.

async def obtener_mensaje(agent_id: int, key: str) -> str:
    """Devuelve el texto del mensaje para ese agente.

    Resolución:
      1. Si la key no existe en el catálogo → "" + log defensivo
      2. Si el agente tiene override con activo=False → "" (señal de skip)
      3. Si el agente tiene override con content no vacío → ese content
      4. Si no, default del catálogo

    El caller DEBE chequear `if not texto: skip` para manejar el caso
    desactivado correctamente. Devolver "" es deliberadamente uniforme
    con "key desconocida" — ambos son "no enviar nada".
    """
    from agent.mensajes import obtener_default, obtener_meta
    if not obtener_meta(key):
        import logging
        logging.getLogger("agentkit").error(
            f"[mensajes] key desconocida solicitada: {key!r} (agent_id={agent_id})"
        )
        return ""
    async with async_session() as session:
        result = await session.execute(
            select(AgentMessage).where(
                AgentMessage.agent_id == agent_id,
                AgentMessage.key == key,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            # Override existe: respetar el flag activo
            if not row.activo:
                return ""  # desactivado por el cliente — no enviar
            if row.content:
                return row.content
            # activo pero sin content → caer al default
    return obtener_default(key)


async def guardar_mensaje_agente(
    agent_id: int, key: str, content: str,
) -> tuple[bool, str]:
    """Guarda el override del CONTENIDO del mensaje para ese agente.

    Solo modifica el content — el flag activo se preserva (default True
    si la row no existía). Para activar/desactivar usar set_mensaje_activo.

    Validaciones:
      - La key debe existir en el catálogo
      - El contenido no puede ser vacío (para eso usar restaurar_mensaje_agente
        o set_mensaje_activo(activo=False))
      - Longitud máxima según meta.max_length (default 4000)
      - Placeholders REQUERIDOS deben estar presentes (los demás son
        sugeridos/opcionales)
    """
    from agent.mensajes import obtener_meta
    meta = obtener_meta(key)
    if not meta:
        return False, f"Mensaje desconocido: {key}"
    content = (content or "").strip()
    if not content:
        return False, "El mensaje no puede estar vacío. Para volver al default usa el botón 'Restaurar'."
    max_len = getattr(meta, "max_length", 4000) or 4000
    if len(content) > max_len:
        return False, f"El mensaje es muy largo ({len(content)} caracteres). Máximo {max_len}."
    requeridos = getattr(meta, "placeholders_requeridos", ()) or ()
    faltantes = [
        f"{{{p}}}" for p in requeridos if f"{{{p}}}" not in content
    ]
    if faltantes:
        return False, (
            "Faltan placeholders obligatorios para este mensaje: "
            + ", ".join(faltantes)
            + ". Cópialos tal cual al texto donde quieras que aparezca el valor."
        )
    async with async_session() as session:
        result = await session.execute(
            select(AgentMessage).where(
                AgentMessage.agent_id == agent_id,
                AgentMessage.key == key,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.content = content
            row.updated_at = datetime.utcnow()
        else:
            session.add(AgentMessage(
                agent_id=agent_id, key=key,
                content=content, activo=True,
                updated_at=datetime.utcnow(),
            ))
        await session.commit()
        return True, ""


async def set_mensaje_activo(
    agent_id: int, key: str, activo: bool,
) -> tuple[bool, str]:
    """Activa o desactiva un mensaje sin tocar su contenido.

    Cuando activo=False, obtener_mensaje retorna "" — el código que envía
    ese mensaje hace skip y no se envía nada en ese punto del flujo.

    Validaciones:
      - La key debe existir en el catálogo
      - Si el mensaje está marcado como puede_desactivarse=False (esencial),
        NO permitimos desactivar — sería romper el flujo.

    Si la row no existe y activo=False, la creamos con content="" (el
    default del catálogo se ignorará en runtime porque activo=False).
    """
    from agent.mensajes import obtener_meta
    meta = obtener_meta(key)
    if not meta:
        return False, f"Mensaje desconocido: {key}"
    if not activo and not getattr(meta, "puede_desactivarse", True):
        return False, (
            "Este mensaje es esencial para el flujo y no se puede desactivar. "
            "Solo puedes cambiar su contenido."
        )
    async with async_session() as session:
        result = await session.execute(
            select(AgentMessage).where(
                AgentMessage.agent_id == agent_id,
                AgentMessage.key == key,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.activo = bool(activo)
            row.updated_at = datetime.utcnow()
        else:
            session.add(AgentMessage(
                agent_id=agent_id, key=key,
                content="", activo=bool(activo),
                updated_at=datetime.utcnow(),
            ))
        await session.commit()
        return True, ""


async def restaurar_mensaje_agente(agent_id: int, key: str) -> bool:
    """Borra el override del mensaje — vuelve a usar el default.

    Retorna True si existía y se borró, False si no había override (no error,
    simplemente ya estaba en default).
    """
    async with async_session() as session:
        result = await session.execute(
            select(AgentMessage).where(
                AgentMessage.agent_id == agent_id,
                AgentMessage.key == key,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return False
        await session.delete(row)
        await session.commit()
        return True


async def construir_contexto_placeholders(agent_id: int) -> dict:
    """Construye el dict de placeholders dinámicos para el agente.

    Reúne en un solo dict toda la configuración del agente que puede usarse
    como placeholder en mensajes (pedido mínimo, umbral envío gratis,
    descuento activo, nombre del negocio, etc.).

    Si un valor NO está configurado, se devuelve string vacío — junto con
    format_seguro() del módulo mensajes garantiza que un placeholder no
    aplicable quede vacío en lugar de romper el mensaje.

    Valores devueltos:
      minimo:           pedido mínimo formateado ("25.000") o "" si 0
      envio_gratis:     umbral envío gratis formateado o "" si 0/no aplica
      descuento_codigo: código de la promoción activa o ""
      descuento_pct:    porcentaje del descuento o ""
      descuento_umbral: umbral del descuento formateado o ""
      negocio:          Agent.name o ""
    """
    ctx: dict[str, str] = {
        "minimo": "", "envio_gratis": "",
        "descuento_codigo": "", "descuento_pct": "", "descuento_umbral": "",
        "negocio": "",
    }
    # Datos del agente (nombre del negocio)
    async with async_session() as session:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agente = result.scalar_one_or_none()
        if agente:
            ctx["negocio"] = agente.name or ""
            # Descuento — solo si está activo
            if agente.descuento_activo and agente.descuento_codigo:
                ctx["descuento_codigo"] = agente.descuento_codigo
                ctx["descuento_pct"]    = str(agente.descuento_pct or "")
                if agente.descuento_umbral > 0:
                    ctx["descuento_umbral"] = f"{int(agente.descuento_umbral):,}".replace(",", ".")
    # Pedido mínimo desde config_value (con fallback a env var por compatibilidad)
    pedido_min_raw = await get_config_value("PEDIDO_MINIMO", agent_id)
    if not pedido_min_raw:
        import os as _os
        pedido_min_raw = _os.getenv("PEDIDO_MINIMO", "0")
    try:
        pedido_min_int = int(float(pedido_min_raw))
        if pedido_min_int > 0:
            ctx["minimo"] = f"{pedido_min_int:,}".replace(",", ".")
    except (TypeError, ValueError):
        pass
    # Umbral envío gratis desde config_value
    envio_raw = await get_config_value("ENVIO_GRATIS_DESDE", agent_id)
    if not envio_raw:
        import os as _os
        envio_raw = _os.getenv("ENVIO_GRATIS_DESDE", "0")
    try:
        envio_int = int(float(envio_raw))
        if envio_int > 0:
            ctx["envio_gratis"] = f"{envio_int:,}".replace(",", ".")
    except (TypeError, ValueError):
        pass
    return ctx


async def listar_mensajes_agente(agent_id: int) -> list[dict]:
    """Devuelve la lista completa del catálogo con el valor actual de cada uno.

    Para cada mensaje del catálogo:
      - Si el agente tiene override → content = override, personalizado = True
      - Si no → content = default, personalizado = False

    Incluye toda la metadata (categoría, descripción, placeholders) para que
    la UI no tenga que cruzar con otro endpoint.
    """
    from agent.mensajes import MENSAJES
    # Una sola query para los overrides de ese agente
    async with async_session() as session:
        result = await session.execute(
            select(AgentMessage).where(AgentMessage.agent_id == agent_id)
        )
        overrides = {row.key: row for row in result.scalars().all()}
    items: list[dict] = []
    for key, meta in MENSAJES.items():
        override = overrides.get(key)
        items.append({
            "key":            meta.key,
            "categoria":      meta.categoria,
            "titulo":         meta.titulo,
            "descripcion":    meta.descripcion,
            "cuando":         meta.cuando,
            "default":        meta.default,
            "placeholders":   list(meta.placeholders),
            "placeholders_requeridos": list(getattr(meta, "placeholders_requeridos", ()) or ()),
            "max_length":     getattr(meta, "max_length", 4000),
            "puede_desactivarse": bool(getattr(meta, "puede_desactivarse", True)),
            "aviso_setup":    getattr(meta, "aviso_setup", "") or "",
            "aviso_setup_url": getattr(meta, "aviso_setup_url", "") or "",
            "content":        (override.content if override and override.content else meta.default),
            "personalizado":  bool(override and override.content),
            "activo":         bool(override.activo) if override else True,
            "updated_at":     override.updated_at.isoformat() if override and override.updated_at else "",
        })
    return items


# ── Usuario / Sesiones (Sprint 1 — SaaS multi-tenant) ───────────────────────

def _usuario_to_dict(u: Usuario) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "nombre": u.nombre,
        "rol": u.rol,
        "plan": u.plan,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else "",
    }


async def crear_usuario(
    email: str,
    password_hash: str,
    nombre: str = "",
    rol: str = "user",
    plan: str = "trial",
) -> dict:
    """Crea un nuevo usuario. Retorna el dict del usuario creado."""
    async with async_session() as session:
        usuario = Usuario(
            email=email.lower().strip(),
            password_hash=password_hash,
            nombre=nombre,
            rol=rol,
            plan=plan,
            is_active=True,
            created_at=datetime.utcnow(),
        )
        session.add(usuario)
        await session.commit()
        await session.refresh(usuario)
        return _usuario_to_dict(usuario)


async def obtener_usuario_por_email(email: str) -> dict | None:
    """Retorna el dict del usuario por email (incluyendo password_hash), o None."""
    async with async_session() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.email == email.lower().strip())
        )
        u = result.scalar_one_or_none()
        if not u:
            return None
        d = _usuario_to_dict(u)
        d["password_hash"] = u.password_hash  # incluir para verificación
        return d


async def obtener_usuario_por_id(user_id: int) -> dict | None:
    """Retorna el dict del usuario por ID, o None."""
    async with async_session() as session:
        result = await session.execute(select(Usuario).where(Usuario.id == user_id))
        u = result.scalar_one_or_none()
        return _usuario_to_dict(u) if u else None


async def crear_sesion(user_id: int) -> str:
    """Crea una sesión para el usuario. Retorna el token (expira en 30 días)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=30)
    async with async_session() as session:
        sesion = SesionUsuario(
            token=token,
            user_id=user_id,
            expires_at=expires_at,
            created_at=datetime.utcnow(),
        )
        session.add(sesion)
        await session.commit()
    return token


async def verificar_sesion(token: str) -> dict | None:
    """Verifica una sesión por token. Retorna el dict del usuario o None si expiró/inválido."""
    if not token:
        return None
    async with async_session() as session:
        result = await session.execute(
            select(SesionUsuario).where(SesionUsuario.token == token)
        )
        sesion = result.scalar_one_or_none()
        if not sesion:
            return None
        if sesion.expires_at < datetime.utcnow():
            await session.delete(sesion)
            await session.commit()
            return None
        # Cargar el usuario
        u_result = await session.execute(
            select(Usuario).where(Usuario.id == sesion.user_id)
        )
        u = u_result.scalar_one_or_none()
        if not u or not u.is_active:
            return None
        return _usuario_to_dict(u)


async def cerrar_sesion(token: str) -> None:
    """Elimina la sesión por token (logout)."""
    if not token:
        return
    async with async_session() as session:
        result = await session.execute(
            select(SesionUsuario).where(SesionUsuario.token == token)
        )
        sesion = result.scalar_one_or_none()
        if sesion:
            await session.delete(sesion)
            await session.commit()


async def listar_usuarios() -> list[dict]:
    """Retorna todos los usuarios registrados (para vista de admin)."""
    async with async_session() as session:
        result = await session.execute(select(Usuario).order_by(Usuario.created_at.desc()))
        return [_usuario_to_dict(u) for u in result.scalars().all()]


async def actualizar_usuario(user_id: int, **kwargs) -> bool:
    """Actualiza campos de un usuario (nombre, plan, is_active, rol). Retorna True si existe."""
    campos_permitidos = {"nombre", "plan", "is_active", "rol", "password_hash"}
    async with async_session() as session:
        result = await session.execute(select(Usuario).where(Usuario.id == user_id))
        u = result.scalar_one_or_none()
        if not u:
            return False
        for campo, valor in kwargs.items():
            if campo in campos_permitidos:
                setattr(u, campo, valor)
        await session.commit()
        return True


async def obtener_agentes_de_usuario(user_id: int) -> list[dict]:
    """Retorna los agentes cuyo owner_id == user_id."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.owner_id == user_id).order_by(Agent.id)
        )
        return [_agent_to_dict(a) for a in result.scalars().all()]


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 1 — Usuarios internos (agentes humanos de soporte)
# ══════════════════════════════════════════════════════════════════════════════

import hashlib as _hashlib


def _hash_password(password: str) -> str:
    """Hash simple SHA-256 para passwords de usuarios internos."""
    return _hashlib.sha256(password.encode()).hexdigest()


def _ui_to_dict(u: UsuarioInterno) -> dict:
    return {
        "id":             u.id,
        "agent_id":       u.agent_id,
        "nombre":         u.nombre,
        "email":          u.email,
        "rol":            u.rol,
        "activo":         u.activo,
        "ultimo_ping_at": u.ultimo_ping_at.isoformat() if u.ultimo_ping_at else None,
        "created_at":     u.created_at.isoformat(),
        # #52 — preferencias de notificación por WhatsApp
        "telefono_wa":            getattr(u, "telefono_wa", "") or "",
        "notif_escalaciones_wa":  bool(getattr(u, "notif_escalaciones_wa", False)),
    }


async def obtener_receptores_escalacion_wa(agent_id: int) -> list[str]:
    """Devuelve los teléfonos WA de usuarios internos que opt-in para recibir
    notificaciones de escalación, filtrados por agente.

    Solo incluye:
      - Usuarios activos (UsuarioInterno.activo=True)
      - Que pertenecen al agent_id dado
      - Con notif_escalaciones_wa=True
      - Con telefono_wa no vacío

    Retorna lista de strings con solo dígitos (sin '+' ni espacios).
    Si nadie está opt-in, retorna lista vacía — el caller decide si usar
    fallback (env var ADMIN_WHATSAPP_NUMBERS) o solo notificar al panel.
    """
    import re as _re
    async with async_session() as session:
        result = await session.execute(
            select(UsuarioInterno).where(
                UsuarioInterno.agent_id == agent_id,
                UsuarioInterno.activo == True,
                UsuarioInterno.notif_escalaciones_wa == True,
                UsuarioInterno.telefono_wa != "",
            )
        )
        telefonos = []
        for u in result.scalars().all():
            digitos = _re.sub(r"\D", "", u.telefono_wa or "")
            if digitos:
                telefonos.append(digitos)
        return telefonos


async def crear_usuario_interno(
    agent_id: int, nombre: str, email: str, password: str, rol: str = "agente"
) -> dict:
    """Crea un nuevo agente humano de soporte para el negocio."""
    async with async_session() as session:
        ui = UsuarioInterno(
            agent_id=agent_id,
            nombre=nombre,
            email=email.lower().strip(),
            password_hash=_hash_password(password),
            rol=rol,
        )
        session.add(ui)
        await session.commit()
        await session.refresh(ui)
        return _ui_to_dict(ui)


async def autenticar_usuario_interno(email: str, password: str) -> dict | None:
    """Autentica un usuario interno por email+password. Retorna dict o None."""
    async with async_session() as session:
        result = await session.execute(
            select(UsuarioInterno).where(
                UsuarioInterno.email == email.lower().strip(),
                UsuarioInterno.activo == True,
            )
        )
        ui = result.scalar_one_or_none()
        if not ui:
            return None
        if ui.password_hash != _hash_password(password):
            return None
        return _ui_to_dict(ui)


async def obtener_usuarios_internos(agent_id: int) -> list[dict]:
    """Lista todos los usuarios internos de un negocio."""
    async with async_session() as session:
        result = await session.execute(
            select(UsuarioInterno)
            .where(UsuarioInterno.agent_id == agent_id)
            .order_by(UsuarioInterno.nombre)
        )
        return [_ui_to_dict(u) for u in result.scalars().all()]


async def actualizar_usuario_interno(ui_id: int, **kwargs) -> bool:
    """Actualiza campos de un usuario interno (nombre, rol, activo, password)."""
    async with async_session() as session:
        result = await session.execute(select(UsuarioInterno).where(UsuarioInterno.id == ui_id))
        ui = result.scalar_one_or_none()
        if not ui:
            return False
        for k, v in kwargs.items():
            if k == "password":
                ui.password_hash = _hash_password(v)
            elif hasattr(ui, k):
                setattr(ui, k, v)
        await session.commit()
        return True


async def ping_usuario_interno(ui_id: int) -> None:
    """Actualiza ultimo_ping_at — usado para detectar agentes online."""
    async with async_session() as session:
        result = await session.execute(select(UsuarioInterno).where(UsuarioInterno.id == ui_id))
        ui = result.scalar_one_or_none()
        if ui:
            ui.ultimo_ping_at = datetime.utcnow()
            await session.commit()


async def obtener_usuario_interno_por_id(ui_id: int) -> dict | None:
    async with async_session() as session:
        result = await session.execute(select(UsuarioInterno).where(UsuarioInterno.id == ui_id))
        ui = result.scalar_one_or_none()
        return _ui_to_dict(ui) if ui else None


async def obtener_o_crear_admin_interno(
    agent_id: int, email: str, nombre: str = ""
) -> dict:
    """Obtiene (o crea automáticamente) un UsuarioInterno con rol 'admin' que
    representa al dueño/admin SaaS dentro del sistema de tickets.
    Permite que cuando el admin toma un ticket, quede registrado con nombre + rol
    en lugar de aparecer como 'sin agente asignado'."""
    email_norm = (email or "admin@voco.local").lower().strip()
    nombre_safe = nombre.strip() or "Administrador"
    async with async_session() as session:
        # Buscar por email + agent_id (uno por negocio)
        result = await session.execute(
            select(UsuarioInterno).where(
                UsuarioInterno.agent_id == agent_id,
                UsuarioInterno.email == email_norm,
            )
        )
        ui = result.scalar_one_or_none()
        if ui:
            # Si cambió el nombre, lo actualizamos
            if nombre.strip() and ui.nombre != nombre_safe:
                ui.nombre = nombre_safe
                await session.commit()
            return _ui_to_dict(ui)
        # No existe: crear uno marcado como admin del sistema
        nuevo = UsuarioInterno(
            agent_id=agent_id,
            nombre=nombre_safe,
            email=email_norm,
            password_hash="",   # No login directo — autenticación via sesión SaaS
            rol="admin",
            activo=True,
        )
        session.add(nuevo)
        await session.commit()
        await session.refresh(nuevo)
        return _ui_to_dict(nuevo)


async def contar_agentes_activos(agent_id: int) -> int:
    """Cuenta agentes humanos activos del negocio (para verificar límite por plan)."""
    async with async_session() as session:
        result = await session.execute(
            select(func.count()).where(
                UsuarioInterno.agent_id == agent_id,
                UsuarioInterno.activo == True,
            )
        )
        return result.scalar() or 0


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 1 — Tickets de escalación
# ══════════════════════════════════════════════════════════════════════════════

def _ticket_to_dict(t: Ticket, agente_nombre: str = "", agente_rol: str = "") -> dict:
    return {
        "id":               t.id,
        "agent_id":         t.agent_id,
        "telefono_cliente": t.telefono_cliente,
        "nombre_cliente":   t.nombre_cliente,
        "estado":           t.estado,
        "urgencia":         t.urgencia,
        "motivo":           t.motivo,
        "contexto":         t.contexto,
        "agente_humano_id": t.agente_humano_id,
        "agente_nombre":    agente_nombre,
        "agente_rol":       agente_rol,
        "creado_at":        t.creado_at.isoformat(),
        "tomado_at":        t.tomado_at.isoformat() if t.tomado_at else None,
        "resuelto_at":      t.resuelto_at.isoformat() if t.resuelto_at else None,
        "actualizado_at":   t.actualizado_at.isoformat(),
    }


async def crear_ticket(
    agent_id: int,
    telefono_cliente: str,
    nombre_cliente: str,
    motivo: str,
    urgencia: str = "normal",
    contexto: str = "",
) -> dict:
    """Crea un ticket de escalación y lo deja en estado sin_asignar."""
    async with async_session() as session:
        # Si ya hay un ticket activo/sin_asignar para este teléfono, reusar
        result = await session.execute(
            select(Ticket).where(
                Ticket.agent_id == agent_id,
                Ticket.telefono_cliente == telefono_cliente,
                Ticket.estado.in_(["sin_asignar", "activo", "pendiente"]),
            ).order_by(Ticket.creado_at.desc())
        )
        existente = result.scalar_one_or_none()
        if existente:
            # Actualizar con el nuevo motivo/contexto y refrescar timestamp
            existente.motivo = motivo
            existente.contexto = contexto
            existente.urgencia = urgencia
            existente.actualizado_at = datetime.utcnow()
            await session.commit()
            return _ticket_to_dict(existente)

        ticket = Ticket(
            agent_id=agent_id,
            telefono_cliente=telefono_cliente,
            nombre_cliente=nombre_cliente,
            motivo=motivo,
            urgencia=urgencia,
            contexto=contexto,
            estado="sin_asignar",
            actualizado_at=datetime.utcnow(),
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        return _ticket_to_dict(ticket)


async def obtener_tickets(agent_id: int, estado: str | None = None) -> list[dict]:
    """Lista tickets de un negocio, opcionalmente filtrados por estado."""
    async with async_session() as session:
        q = select(Ticket).where(Ticket.agent_id == agent_id)
        if estado:
            q = q.where(Ticket.estado == estado)
        q = q.order_by(Ticket.actualizado_at.desc())
        result = await session.execute(q)
        tickets = result.scalars().all()

        # Enriquecer con nombre + rol del agente humano que gestionó el ticket
        ids_agente = {t.agente_humano_id for t in tickets if t.agente_humano_id}
        ui_info: dict[int, tuple[str, str]] = {}
        if ids_agente:
            r2 = await session.execute(
                select(UsuarioInterno).where(UsuarioInterno.id.in_(ids_agente))
            )
            for ui in r2.scalars().all():
                ui_info[ui.id] = (ui.nombre, ui.rol or "")

        return [
            _ticket_to_dict(
                t,
                ui_info.get(t.agente_humano_id, ("", ""))[0],
                ui_info.get(t.agente_humano_id, ("", ""))[1],
            )
            for t in tickets
        ]


async def contar_tickets(agent_id: int) -> dict:
    """Retorna conteo de tickets por estado para badges del panel."""
    async with async_session() as session:
        result = await session.execute(
            select(Ticket.estado, func.count().label("n"))
            .where(Ticket.agent_id == agent_id)
            .where(Ticket.estado != "resuelto")   # resueltos no cuentan en badge
            .group_by(Ticket.estado)
        )
        counts = {row.estado: row.n for row in result}
        total_abiertos = sum(counts.values())
        return {
            "sin_asignar": counts.get("sin_asignar", 0),
            "activo":      counts.get("activo", 0),
            "pendiente":   counts.get("pendiente", 0),
            "total":       total_abiertos,
        }


async def tomar_ticket(ticket_id: int, agente_humano_id: int) -> dict | None:
    """Un agente humano toma un ticket sin_asignar o pendiente."""
    async with async_session() as session:
        result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if not ticket:
            return None
        ticket.estado = "activo"
        ticket.agente_humano_id = agente_humano_id
        ticket.tomado_at = datetime.utcnow()
        ticket.actualizado_at = datetime.utcnow()
        await session.commit()

        # Nombre del agente
        r2 = await session.execute(select(UsuarioInterno).where(UsuarioInterno.id == agente_humano_id))
        ui = r2.scalar_one_or_none()
        return _ticket_to_dict(
            ticket,
            ui.nombre if ui else "",
            (ui.rol or "") if ui else "",
        )


async def marcar_ticket_pendiente(ticket_id: int) -> dict | None:
    """Marca el ticket como pendiente (el agente necesita más info o pausó)."""
    async with async_session() as session:
        result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if not ticket:
            return None
        ticket.estado = "pendiente"
        ticket.actualizado_at = datetime.utcnow()
        await session.commit()
        return _ticket_to_dict(ticket)


async def resolver_ticket(ticket_id: int) -> dict | None:
    """Resuelve el ticket y retorna el telefono_cliente para reactivar el bot."""
    async with async_session() as session:
        result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if not ticket:
            return None
        ticket.estado = "resuelto"
        ticket.resuelto_at = datetime.utcnow()
        ticket.actualizado_at = datetime.utcnow()
        await session.commit()
        return _ticket_to_dict(ticket)


async def obtener_ticket_activo_por_telefono(agent_id: int, telefono: str) -> dict | None:
    """Retorna el ticket abierto (sin_asignar/activo/pendiente) de un cliente."""
    async with async_session() as session:
        result = await session.execute(
            select(Ticket).where(
                Ticket.agent_id == agent_id,
                Ticket.telefono_cliente == telefono,
                Ticket.estado.in_(["sin_asignar", "activo", "pendiente"]),
            ).order_by(Ticket.creado_at.desc())
        )
        ticket = result.scalar_one_or_none()
        return _ticket_to_dict(ticket) if ticket else None


async def transferir_ticket(ticket_id: int, nuevo_agente_id: int) -> dict | None:
    """Transfiere un ticket activo a otro agente humano."""
    async with async_session() as session:
        result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if not ticket:
            return None
        ticket.agente_humano_id = nuevo_agente_id
        ticket.estado = "activo"
        ticket.actualizado_at = datetime.utcnow()
        await session.commit()
        r2 = await session.execute(select(UsuarioInterno).where(UsuarioInterno.id == nuevo_agente_id))
        ui = r2.scalar_one_or_none()
        return _ticket_to_dict(
            ticket,
            ui.nombre if ui else "",
            (ui.rol or "") if ui else "",
        )


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 2 — Notas internas
# ══════════════════════════════════════════════════════════════════════════════

class NotaInterna(Base):
    """Nota interna de un agente sobre un ticket (no visible al cliente)."""
    __tablename__ = "notas_internas"

    id:               Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id:        Mapped[int]      = mapped_column(Integer, index=True)
    agente_humano_id: Mapped[int]      = mapped_column(Integer, default=0)
    agente_nombre:    Mapped[str]      = mapped_column(String(200), default="")
    contenido:        Mapped[str]      = mapped_column(Text)
    created_at:       Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def crear_nota_interna(
    ticket_id: int, agente_humano_id: int, agente_nombre: str, contenido: str
) -> dict:
    async with async_session() as session:
        nota = NotaInterna(
            ticket_id=ticket_id,
            agente_humano_id=agente_humano_id,
            agente_nombre=agente_nombre,
            contenido=contenido,
        )
        session.add(nota)
        await session.commit()
        await session.refresh(nota)
        return {
            "id":               nota.id,
            "ticket_id":        nota.ticket_id,
            "agente_humano_id": nota.agente_humano_id,
            "agente_nombre":    nota.agente_nombre,
            "contenido":        nota.contenido,
            "created_at":       nota.created_at.isoformat(),
        }


async def obtener_notas_ticket(ticket_id: int) -> list[dict]:
    async with async_session() as session:
        result = await session.execute(
            select(NotaInterna)
            .where(NotaInterna.ticket_id == ticket_id)
            .order_by(NotaInterna.created_at)
        )
        return [
            {
                "id":            n.id,
                "agente_nombre": n.agente_nombre,
                "contenido":     n.contenido,
                "created_at":    n.created_at.isoformat(),
            }
            for n in result.scalars().all()
        ]


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 2 — Templates rápidos de respuesta
# ══════════════════════════════════════════════════════════════════════════════

class TemplateRapido(Base):
    """Respuestas rápidas predefinidas para agentes de soporte."""
    __tablename__ = "templates_rapidos"

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id:   Mapped[int]      = mapped_column(Integer, index=True)
    titulo:     Mapped[str]      = mapped_column(String(100))
    contenido:  Mapped[str]      = mapped_column(Text)
    orden:      Mapped[int]      = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def _tpl_to_dict(t: TemplateRapido) -> dict:
    return {"id": t.id, "agent_id": t.agent_id, "titulo": t.titulo,
            "contenido": t.contenido, "orden": t.orden}


async def obtener_templates_rapidos(agent_id: int) -> list[dict]:
    async with async_session() as session:
        result = await session.execute(
            select(TemplateRapido)
            .where(TemplateRapido.agent_id == agent_id)
            .order_by(TemplateRapido.orden, TemplateRapido.id)
        )
        return [_tpl_to_dict(t) for t in result.scalars().all()]


async def crear_template_rapido(agent_id: int, titulo: str, contenido: str, orden: int = 0) -> dict:
    async with async_session() as session:
        tpl = TemplateRapido(agent_id=agent_id, titulo=titulo, contenido=contenido, orden=orden)
        session.add(tpl)
        await session.commit()
        await session.refresh(tpl)
        return _tpl_to_dict(tpl)


async def eliminar_template_rapido(tpl_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(select(TemplateRapido).where(TemplateRapido.id == tpl_id))
        tpl = result.scalar_one_or_none()
        if not tpl:
            return False
        await session.delete(tpl)
        await session.commit()
        return True


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 3 — Auditoría de tickets
# ══════════════════════════════════════════════════════════════════════════════

class TicketEvento(Base):
    """Registro inmutable de cada cambio de estado en un ticket."""
    __tablename__ = "ticket_eventos"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id:    Mapped[int]      = mapped_column(Integer, index=True)
    tipo:         Mapped[str]      = mapped_column(String(40))   # creado|tomado|pendiente|resuelto|transferido|nota|respuesta
    actor_nombre: Mapped[str]      = mapped_column(String(200), default="Sistema")
    detalle:      Mapped[str]      = mapped_column(Text, default="")
    created_at:   Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def registrar_evento_ticket(
    ticket_id: int, tipo: str, actor_nombre: str = "Sistema", detalle: str = ""
) -> dict:
    async with async_session() as session:
        ev = TicketEvento(ticket_id=ticket_id, tipo=tipo,
                          actor_nombre=actor_nombre, detalle=detalle)
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        return {"id": ev.id, "tipo": ev.tipo, "actor_nombre": ev.actor_nombre,
                "detalle": ev.detalle, "created_at": ev.created_at.isoformat()}


async def obtener_eventos_ticket(ticket_id: int) -> list[dict]:
    async with async_session() as session:
        result = await session.execute(
            select(TicketEvento)
            .where(TicketEvento.ticket_id == ticket_id)
            .order_by(TicketEvento.created_at)
        )
        return [{"id": e.id, "tipo": e.tipo, "actor_nombre": e.actor_nombre,
                 "detalle": e.detalle, "created_at": e.created_at.isoformat()}
                for e in result.scalars().all()]


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 3 — Dashboard supervisor
# ══════════════════════════════════════════════════════════════════════════════

async def obtener_stats_equipo(agent_id: int) -> list[dict]:
    """Métricas por agente: tickets resueltos, activos, tiempo promedio (min)."""
    async with async_session() as session:
        # Agentes activos del negocio
        r_agentes = await session.execute(
            select(UsuarioInterno)
            .where(UsuarioInterno.agent_id == agent_id, UsuarioInterno.activo == True)
        )
        agentes = r_agentes.scalars().all()

        stats = []
        ahora = datetime.utcnow()
        for ui in agentes:
            # Tickets activos asignados
            r_activos = await session.execute(
                select(func.count()).select_from(Ticket).where(
                    Ticket.agente_humano_id == ui.id,
                    Ticket.estado.in_(["activo", "pendiente"])
                )
            )
            activos = r_activos.scalar() or 0

            # Tickets resueltos (todos)
            r_resueltos = await session.execute(
                select(Ticket).where(
                    Ticket.agente_humano_id == ui.id,
                    Ticket.estado == "resuelto",
                    Ticket.tomado_at.isnot(None),
                    Ticket.resuelto_at.isnot(None),
                )
            )
            tickets_res = r_resueltos.scalars().all()
            total_resueltos = len(tickets_res)

            # Tiempo promedio de resolución en minutos
            tiempos = []
            for t in tickets_res:
                if t.tomado_at and t.resuelto_at:
                    delta = (t.resuelto_at - t.tomado_at).total_seconds() / 60
                    tiempos.append(delta)
            avg_mins = round(sum(tiempos) / len(tiempos), 1) if tiempos else None

            # Online si hizo ping en últimos 90s
            online = (ui.ultimo_ping_at is not None and
                      (ahora - ui.ultimo_ping_at).total_seconds() < 90)

            stats.append({
                "id":               ui.id,
                "nombre":           ui.nombre,
                "email":            ui.email,
                "rol":              ui.rol,
                "online":           online,
                "tickets_activos":  activos,
                "tickets_resueltos": total_resueltos,
                "avg_resolucion_min": avg_mins,
            })

        # Ordenar: supervisores/admin primero, luego por tickets resueltos desc
        stats.sort(key=lambda x: (-{"admin":2,"supervisor":1}.get(x["rol"],0),
                                   -x["tickets_resueltos"]))
        return stats


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 3 — Asignación automática round-robin
# ══════════════════════════════════════════════════════════════════════════════

async def obtener_siguiente_agente_roundrobin(agent_id: int) -> int | None:
    """Devuelve el id del siguiente agente disponible en round-robin, o None."""
    async with async_session() as session:
        # Solo agentes con rol 'agente' o 'supervisor' activos
        r = await session.execute(
            select(UsuarioInterno)
            .where(UsuarioInterno.agent_id == agent_id,
                   UsuarioInterno.activo == True,
                   UsuarioInterno.rol.in_(["agente", "supervisor"]))
            .order_by(UsuarioInterno.id)
        )
        agentes = r.scalars().all()
        if not agentes:
            return None

        # Leer índice actual del round-robin desde config_values
        r_idx = await session.execute(
            select(ConfigValue).where(
                ConfigValue.agent_id == agent_id,
                ConfigValue.clave == "_rr_index"
            )
        )
        cfg = r_idx.scalar_one_or_none()
        idx = int(cfg.valor) if cfg and cfg.valor.isdigit() else 0
        idx = idx % len(agentes)

        agente_elegido = agentes[idx]

        # Avanzar índice
        nuevo_idx = str((idx + 1) % len(agentes))
        if cfg:
            cfg.valor = nuevo_idx
        else:
            session.add(ConfigValue(agent_id=agent_id, clave="_rr_index", valor=nuevo_idx))
        await session.commit()

        return agente_elegido.id


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT A — Pipeline + Soporte (modelos)
# ──────────────────────────────────────────────────────────────────────────────
# Tablas opt-in: solo se usan cuando el agente activa el módulo correspondiente
# en Agent.modules_json. Andrea (Equora) no las ve hasta que se activen módulos.
# ══════════════════════════════════════════════════════════════════════════════

class Pipeline(Base):
    """Pipeline de un agente — define las etapas (stages) por las que pasan los deals.

    Cada agente puede tener UN pipeline activo (`activo=True`). Los stages se
    guardan como JSON-array de strings para que el operador los personalice
    (ej: ["Nuevo", "Calificado", "Negociando", "Ganado", "Perdido"]).
    """
    __tablename__ = "pipelines"

    id:          Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id:    Mapped[int]      = mapped_column(Integer, index=True, nullable=False)
    nombre:      Mapped[str]      = mapped_column(String(100), default="Pipeline principal")
    stages_json: Mapped[str]      = mapped_column(
        Text,
        default='["Nuevo","Calificado","Negociando","Ganado","Perdido"]'
    )
    activo:      Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Deal(Base):
    """Oportunidad/lead asignada a un cliente y pipeline.

    Source indica el canal de origen del lead (whatsapp|instagram|messenger|manual).
    Score es 0-100, calculado por reglas determinísticas (ver pipeline_logic.py).
    """
    __tablename__ = "deals"

    id:               Mapped[int]                = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id:         Mapped[int]                = mapped_column(Integer, index=True, nullable=False)
    pipeline_id:      Mapped[int]                = mapped_column(Integer, index=True, nullable=False)
    cliente_telefono: Mapped[str]                = mapped_column(String(50), index=True)
    cliente_nombre:   Mapped[str]                = mapped_column(String(200), default="")
    cliente_email:    Mapped[str]                = mapped_column(String(200), default="")
    titulo:           Mapped[str]                = mapped_column(String(200), default="")
    stage:            Mapped[str]                = mapped_column(String(50), default="Nuevo", index=True)
    valor_cop:        Mapped[int]                = mapped_column(Integer, default=0)
    score:            Mapped[int]                = mapped_column(Integer, default=0)
    source:           Mapped[str]                = mapped_column(String(40), default="whatsapp")
    owner_id:         Mapped[int | None]         = mapped_column(Integer, nullable=True, default=None)
    notas:            Mapped[str]                = mapped_column(Text, default="")
    created_at:       Mapped[datetime]           = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at:       Mapped[datetime]           = mapped_column(DateTime, default=datetime.utcnow)
    closed_at:        Mapped[datetime | None]    = mapped_column(DateTime, nullable=True, default=None)


class DealActivity(Base):
    """Evento en el timeline de un deal — mensajes, cambios de stage, meetings, emails.

    tipo ∈ {msg_in, msg_out, note, stage_change, email_sent, meeting_booked,
            order_placed, score_change, deal_created}
    metadata_json guarda datos extra (stage_old/new, calendly_uri, email_id, etc.)
    """
    __tablename__ = "deal_activities"

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id:       Mapped[int]      = mapped_column(Integer, index=True, nullable=False)
    tipo:          Mapped[str]      = mapped_column(String(40))
    contenido:     Mapped[str]      = mapped_column(Text, default="")
    metadata_json: Mapped[str]      = mapped_column(Text, default="{}")
    autor_nombre:  Mapped[str]      = mapped_column(String(200), default="Sistema")
    created_at:    Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class IntegrationConfig(Base):
    """Configuración por agente de integraciones externas.

    tipo ∈ {calendly, sendgrid, hubspot, pipedrive}
    Un (agent_id, tipo) único por agente — pero no se aplica constraint UNIQUE
    en BD por ahora para evitar problemas de migración; se valida en código.
    """
    __tablename__ = "integration_configs"

    id:            Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id:      Mapped[int]              = mapped_column(Integer, index=True, nullable=False)
    tipo:          Mapped[str]              = mapped_column(String(40), index=True)
    api_token:     Mapped[str]              = mapped_column(Text, default="")
    settings_json: Mapped[str]              = mapped_column(Text, default="{}")
    activo:        Mapped[bool]             = mapped_column(Boolean, default=False)
    last_sync_at:  Mapped[datetime | None]  = mapped_column(DateTime, nullable=True, default=None)
    created_at:    Mapped[datetime]         = mapped_column(DateTime, default=datetime.utcnow)


class KbArticle(Base):
    """Artículo de Knowledge Base para agentes de soporte.

    El agente Soporte consulta esta tabla cuando emite [[KB:tema]].
    tags es un string CSV simple para búsqueda — si crece, indexar con fulltext.
    """
    __tablename__ = "kb_articles"

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id:   Mapped[int]      = mapped_column(Integer, index=True, nullable=False)
    titulo:     Mapped[str]      = mapped_column(String(200))
    contenido:  Mapped[str]      = mapped_column(Text, default="")
    tags:       Mapped[str]      = mapped_column(String(300), default="")
    activo:     Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de módulos por agente
# ──────────────────────────────────────────────────────────────────────────────
# DEFAULT_MODULES es la verdad sobre qué módulos existen y su estado por
# defecto. Cuando un agente no tiene modules_json, get_modules() devuelve
# este dict — todos los nuevos módulos OFF para que Andrea no se entere.
#
# Los módulos viejos (shopify_catalog, cart_orders, client_memory,
# campaign_context) siguen siendo controlados por config_values como
# hasta ahora — modules_json es SOLO para los toggles del Sprint A.
# Eso evita migrar datos existentes.
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_MODULES: dict[str, bool] = {
    # Sprint A — Pipeline + Soporte
    "pipeline":       False,
    "calendly":       False,
    "sendgrid":       False,
    "knowledge_base": False,
    "order_status":   False,
}


def get_modules_from_json(modules_json: str) -> dict[str, bool]:
    """Parsea Agent.modules_json y devuelve dict completo con defaults aplicados.

    Si el JSON está vacío, malformado o le faltan claves, se rellenan con
    DEFAULT_MODULES. Garantiza que el caller siempre recibe TODAS las claves
    válidas — nunca KeyError.
    """
    result = dict(DEFAULT_MODULES)
    if not modules_json:
        return result
    try:
        parsed = json.loads(modules_json)
        if isinstance(parsed, dict):
            for k, v in parsed.items():
                if k in DEFAULT_MODULES:
                    result[k] = bool(v)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass  # devolvemos defaults si el JSON está roto
    return result


async def get_agent_modules(agent_id: int) -> dict[str, bool]:
    """Devuelve el dict de módulos activos para un agente.

    Si el agente no existe, devuelve DEFAULT_MODULES (todo OFF) para que
    el caller no tenga que manejar None.
    """
    async with async_session() as session:
        r = await session.execute(select(Agent).where(Agent.id == agent_id))
        agent = r.scalar_one_or_none()
        if not agent:
            return dict(DEFAULT_MODULES)
        return get_modules_from_json(agent.modules_json or "")


async def set_agent_modules(agent_id: int, modules: dict[str, bool]) -> dict[str, bool]:
    """Persiste los módulos del agente. Solo guarda claves válidas (en DEFAULT_MODULES).

    Devuelve el dict normalizado guardado.
    """
    # Filtrar a claves válidas y normalizar a bool
    sanitized = {k: bool(modules.get(k, DEFAULT_MODULES[k])) for k in DEFAULT_MODULES}
    async with async_session() as session:
        r = await session.execute(select(Agent).where(Agent.id == agent_id))
        agent = r.scalar_one_or_none()
        if not agent:
            return dict(DEFAULT_MODULES)
        agent.modules_json = json.dumps(sanitized)
        await session.commit()
        return sanitized
