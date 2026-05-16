import os
import json
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, select, Integer, func
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Mensaje(Base):
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Cliente(Base):
    __tablename__ = "clientes"

    telefono: Mapped[str] = mapped_column(String(50), primary_key=True)
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
    carrito_activo: Mapped[str] = mapped_column(Text, default="")        # JSON del carrito en curso
    carrito_activo_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


CAMPOS_CLIENTE = (
    "nombres", "apellidos", "razon_social", "cc_nit",
    "direccion", "barrio", "ciudad", "departamento", "email",
)


class EstadoConversacion(Base):
    """Timestamps por conversación para gestionar seguimientos automáticos."""
    __tablename__ = "estado_conversacion"

    telefono: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_user_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_assistant_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cierre_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    modo_humano: Mapped[int] = mapped_column(Integer, default=0)  # 1 = humano responde, 0 = Andrea
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def inicializar_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migración: agregar columnas nuevas si la tabla ya existía sin ellas
        for sql in (
            "ALTER TABLE clientes ADD COLUMN pedido_pendiente TEXT DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN pedido_pendiente_at DATETIME",
            "ALTER TABLE clientes ADD COLUMN carrito_activo TEXT DEFAULT ''",
            "ALTER TABLE clientes ADD COLUMN carrito_activo_at DATETIME",
            "ALTER TABLE estado_conversacion ADD COLUMN modo_humano INTEGER DEFAULT 0",
        ):
            try:
                await conn.exec_driver_sql(sql)
            except Exception:
                pass  # ya existe


async def guardar_mensaje(telefono: str, role: str, content: str):
    async with async_session() as session:
        mensaje = Mensaje(
            telefono=telefono,
            role=role,
            content=content,
            timestamp=datetime.utcnow()
        )
        session.add(mensaje)
        await session.commit()


async def obtener_historial(telefono: str, limite: int = 20) -> list[dict]:
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono)
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


async def limpiar_historial(telefono: str):
    async with async_session() as session:
        query = select(Mensaje).where(Mensaje.telefono == telefono)
        result = await session.execute(query)
        mensajes = result.scalars().all()
        for msg in mensajes:
            await session.delete(msg)
        await session.commit()


async def guardar_cliente(telefono: str, datos: dict):
    """Crea o actualiza el perfil del cliente. Solo guarda campos no vacíos."""
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        if cliente:
            for campo in CAMPOS_CLIENTE:
                valor = datos.get(campo)
                if valor:
                    setattr(cliente, campo, str(valor))
            cliente.pedidos_realizados = (cliente.pedidos_realizados or 0) + 1
            cliente.actualizado = datetime.utcnow()
        else:
            valores = {c: str(datos.get(c, "")) for c in CAMPOS_CLIENTE}
            cliente = Cliente(telefono=telefono, pedidos_realizados=1, **valores)
            session.add(cliente)
        await session.commit()


async def obtener_cliente(telefono: str) -> dict | None:
    """Devuelve los datos guardados del cliente o None si no existe."""
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
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
        }


PEDIDO_PENDIENTE_TTL_HORAS = 48


async def guardar_pedido_pendiente(telefono: str, productos: list[dict]):
    """Guarda el carrito que el cliente confirmó pero aún no completó en Shopify.
    Sirve para retomarlo si vuelve a escribir antes de finalizar el checkout."""
    if not productos:
        return
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        ahora = datetime.utcnow()
        if not cliente:
            cliente = Cliente(telefono=telefono)
            session.add(cliente)
        cliente.pedido_pendiente = json.dumps(productos, ensure_ascii=False)
        cliente.pedido_pendiente_at = ahora
        cliente.actualizado = ahora
        await session.commit()


async def obtener_pedido_pendiente(telefono: str) -> list[dict] | None:
    """Devuelve el carrito pendiente si existe y no ha expirado."""
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        if not cliente or not cliente.pedido_pendiente or not cliente.pedido_pendiente_at:
            return None
        if datetime.utcnow() - cliente.pedido_pendiente_at > timedelta(hours=PEDIDO_PENDIENTE_TTL_HORAS):
            return None
        try:
            return json.loads(cliente.pedido_pendiente)
        except Exception:
            return None


async def limpiar_pedido_pendiente(telefono: str):
    """Borra el carrito pendiente — cliente completó el pedido en Shopify."""
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        if cliente:
            cliente.pedido_pendiente = ""
            cliente.pedido_pendiente_at = None
            cliente.actualizado = datetime.utcnow()
            await session.commit()


# ── Carrito activo (persistencia independiente del historial) ────────────────

CARRITO_TTL_HORAS = 24  # El carrito expira si el cliente no vuelve en 24 h


async def guardar_carrito_activo(telefono: str, items: list[dict]):
    """Guarda el estado actual del carrito en BD.
    Se llama cada vez que Andrea agrega/quita un producto."""
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        ahora = datetime.utcnow()
        if not cliente:
            cliente = Cliente(telefono=telefono)
            session.add(cliente)
        cliente.carrito_activo = json.dumps(items, ensure_ascii=False)
        cliente.carrito_activo_at = ahora
        cliente.actualizado = ahora
        await session.commit()


async def obtener_carrito_activo(telefono: str) -> list[dict]:
    """Devuelve el carrito en curso. Lista vacía si no existe o expiró."""
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        if not cliente or not cliente.carrito_activo or not cliente.carrito_activo_at:
            return []
        if datetime.utcnow() - cliente.carrito_activo_at > timedelta(hours=CARRITO_TTL_HORAS):
            return []
        try:
            return json.loads(cliente.carrito_activo) or []
        except Exception:
            return []


async def limpiar_carrito_activo(telefono: str):
    """Borra el carrito activo — se llama cuando el pedido se confirma o se vacía."""
    async with async_session() as session:
        cliente = await session.get(Cliente, telefono)
        if cliente:
            cliente.carrito_activo = ""
            cliente.carrito_activo_at = None
            cliente.actualizado = datetime.utcnow()
            await session.commit()


async def clientes_con_carrito_abandonado(
    min_inactivo: int = 10,
    max_inactivo: int = 30,
) -> list[tuple[str, list[dict]]]:
    """
    Devuelve teléfonos con carrito activo que llevan entre min y max minutos sin finalizar.
    Retorna lista de (telefono, items_carrito).
    """
    ahora = datetime.utcnow()
    cutoff_min = ahora - timedelta(minutes=max_inactivo)
    cutoff_max = ahora - timedelta(minutes=min_inactivo)
    async with async_session() as session:
        q = select(Cliente).where(
            Cliente.carrito_activo != "",
            Cliente.carrito_activo != None,
            Cliente.carrito_activo_at >= cutoff_min,
            Cliente.carrito_activo_at <= cutoff_max,
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


# ── Estado de conversación / seguimientos automáticos ───────────────────────

async def _get_or_create_estado(session: AsyncSession, telefono: str) -> "EstadoConversacion":
    estado = await session.get(EstadoConversacion, telefono)
    if not estado:
        estado = EstadoConversacion(telefono=telefono)
        session.add(estado)
    return estado


async def registrar_mensaje_usuario(telefono: str):
    """Cliente acaba de escribir → resetea timers de seguimiento."""
    async with async_session() as session:
        estado = await _get_or_create_estado(session, telefono)
        ahora = datetime.utcnow()
        estado.last_user_at = ahora
        estado.follow_up_at = None
        estado.cierre_at = None
        estado.actualizado = ahora
        await session.commit()


async def registrar_mensaje_asistente(telefono: str):
    """Andrea acaba de responder → marca el último mensaje del bot."""
    async with async_session() as session:
        estado = await _get_or_create_estado(session, telefono)
        ahora = datetime.utcnow()
        estado.last_assistant_at = ahora
        estado.actualizado = ahora
        await session.commit()


async def marcar_followup_enviado(telefono: str):
    async with async_session() as session:
        estado = await _get_or_create_estado(session, telefono)
        estado.follow_up_at = datetime.utcnow()
        estado.actualizado = estado.follow_up_at
        await session.commit()


async def marcar_cierre_enviado(telefono: str):
    async with async_session() as session:
        estado = await _get_or_create_estado(session, telefono)
        estado.cierre_at = datetime.utcnow()
        estado.actualizado = estado.cierre_at
        await session.commit()


async def conversaciones_para_followup(
    inactividad_minutos: int = 2,
    max_edad_horas: int = 12,
) -> list[str]:
    """Conversaciones donde:
    - El último mensaje fue del asistente (last_assistant_at > last_user_at o user nulo)
    - Pasaron al menos `inactividad_minutos` desde la última respuesta del bot
    - Aún no enviamos follow-up (follow_up_at IS NULL)
    - El último mensaje del bot no es más viejo que `max_edad_horas`
    """
    ahora = datetime.utcnow()
    cutoff_inactividad = ahora - timedelta(minutes=inactividad_minutos)
    cutoff_max_edad = ahora - timedelta(hours=max_edad_horas)
    async with async_session() as session:
        query = select(EstadoConversacion).where(
            EstadoConversacion.last_assistant_at.is_not(None),
            EstadoConversacion.last_assistant_at <= cutoff_inactividad,
            EstadoConversacion.last_assistant_at >= cutoff_max_edad,
            EstadoConversacion.follow_up_at.is_(None),
        )
        result = await session.execute(query)
        candidatos = result.scalars().all()
        # Filtrar: el último mensaje debe ser del asistente
        return [
            e.telefono for e in candidatos
            if e.last_user_at is None or e.last_assistant_at > e.last_user_at
        ]


async def conversaciones_para_cierre(min_despues_followup: int = 5) -> list[str]:
    """Conversaciones que ya recibieron follow-up y siguen sin respuesta del cliente."""
    cutoff = datetime.utcnow() - timedelta(minutes=min_despues_followup)
    async with async_session() as session:
        query = select(EstadoConversacion).where(
            EstadoConversacion.follow_up_at.is_not(None),
            EstadoConversacion.follow_up_at <= cutoff,
            EstadoConversacion.cierre_at.is_(None),
        )
        result = await session.execute(query)
        candidatos = result.scalars().all()
        return [
            e.telefono for e in candidatos
            if e.last_user_at is None or e.follow_up_at > e.last_user_at
        ]


# ── Inbox / panel de administración ─────────────────────────────────────────

async def get_modo_humano(telefono: str) -> bool:
    """Retorna True si el modo humano está activo para esta conversación."""
    async with async_session() as session:
        estado = await session.get(EstadoConversacion, telefono)
        if not estado:
            return False
        return bool(estado.modo_humano)


async def set_modo_humano(telefono: str, activo: bool):
    """Activa o desactiva el modo humano para una conversación."""
    async with async_session() as session:
        estado = await _get_or_create_estado(session, telefono)
        estado.modo_humano = 1 if activo else 0
        estado.actualizado = datetime.utcnow()
        await session.commit()


async def obtener_todas_conversaciones() -> list[dict]:
    """Lista de conversaciones con el último mensaje de cada una, ordenadas por recientes."""
    async with async_session() as session:
        # Subconsulta: id del último mensaje por teléfono
        sub = (
            select(Mensaje.telefono, func.max(Mensaje.id).label("max_id"))
            .group_by(Mensaje.telefono)
            .subquery()
        )
        query = (
            select(Mensaje, EstadoConversacion, Cliente)
            .join(sub, Mensaje.id == sub.c.max_id)
            .outerjoin(EstadoConversacion, Mensaje.telefono == EstadoConversacion.telefono)
            .outerjoin(Cliente, Mensaje.telefono == Cliente.telefono)
            .where(~Mensaje.telefono.like("test-%"))
            .order_by(Mensaje.timestamp.desc())
            .limit(300)
        )
        result = await session.execute(query)
        rows = result.all()
        convs = []
        for msg, estado, cliente in rows:
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
            })
        return convs


async def obtener_historial_con_timestamps(telefono: str, limite: int = 150) -> list[dict]:
    """Historial completo con timestamps para el inbox."""
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono)
            .order_by(Mensaje.timestamp.asc())
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else "",
            }
            for msg in mensajes
        ]
