import hashlib
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)

class Base(DeclarativeBase):
    pass

class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    nit: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)

class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class DocumentStatus(Base):
    __tablename__ = "document_status"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    number: Mapped[str] = mapped_column(String(80), nullable=False)
    dian_status: Mapped[str] = mapped_column(String(40), nullable=False)
    email_status: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)
app = FastAPI(title="WB Servicios Central API", version="0.1.0")

def session():
    with SessionLocal() as db:
        yield db

def admin(authorization: str = Header(default="")):
    expected = "Bearer " + os.environ["ADMIN_TOKEN"]
    if not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "Credencial administrativa inválida")

def agent_auth(x_api_key: str = Header(default=""), db: Session = Depends(session)) -> Agent:
    digest = hashlib.sha256(x_api_key.encode()).hexdigest()
    agent = db.scalar(select(Agent).where(Agent.key_hash == digest)) if x_api_key else None
    if not agent:
        raise HTTPException(401, "API Key inválida")
    return agent

class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    nit: str = Field(min_length=1, max_length=30)

class AgentCreate(BaseModel):
    company_id: int
    name: str = Field(min_length=1, max_length=100)

class StatusIn(BaseModel):
    document_type: str = Field(pattern="^(factura|nota_credito)$")
    number: str = Field(min_length=1, max_length=80)
    dian_status: str = Field(max_length=40)
    email_status: str = Field(max_length=40)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/admin/companies", dependencies=[Depends(admin)])
def create_company(data: CompanyCreate, db: Session = Depends(session)):
    if db.scalar(select(Company).where(Company.nit == data.nit)):
        raise HTTPException(409, "NIT ya registrado")
    obj = Company(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "name": obj.name, "nit": obj.nit}

@app.get("/admin/companies", dependencies=[Depends(admin)])
def list_companies(db: Session = Depends(session)):
    return [{"id": c.id, "name": c.name, "nit": c.nit} for c in db.scalars(select(Company)).all()]

@app.post("/admin/agents", dependencies=[Depends(admin)])
def create_agent(data: AgentCreate, db: Session = Depends(session)):
    if not db.get(Company, data.company_id):
        raise HTTPException(404, "Empresa no encontrada")
    key = secrets.token_urlsafe(48)
    obj = Agent(company_id=data.company_id, name=data.name, key_hash=hashlib.sha256(key.encode()).hexdigest())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "company_id": obj.company_id, "name": obj.name, "api_key": key, "notice": "Guarde la API Key: solo se muestra una vez"}

@app.get("/admin/agents", dependencies=[Depends(admin)])
def list_agents(db: Session = Depends(session)):
    return [{"id": a.id, "company_id": a.company_id, "name": a.name, "last_seen": a.last_seen} for a in db.scalars(select(Agent)).all()]

@app.post("/agent/heartbeat")
def heartbeat(agent: Agent = Depends(agent_auth), db: Session = Depends(session)):
    agent.last_seen = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "agent_id": agent.id}

@app.post("/agent/documents")
def upsert_document(data: StatusIn, agent: Agent = Depends(agent_auth), db: Session = Depends(session)):
    doc = db.scalar(select(DocumentStatus).where(DocumentStatus.agent_id == agent.id, DocumentStatus.document_type == data.document_type, DocumentStatus.number == data.number))
    if not doc:
        doc = DocumentStatus(agent_id=agent.id, document_type=data.document_type, number=data.number, dian_status=data.dian_status, email_status=data.email_status)
        db.add(doc)
    else:
        doc.dian_status = data.dian_status
        doc.email_status = data.email_status
        doc.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}

@app.get("/admin/documents", dependencies=[Depends(admin)])
def list_documents(db: Session = Depends(session)):
    docs = db.scalars(select(DocumentStatus).order_by(DocumentStatus.updated_at.desc()).limit(100)).all()
    return [{"agent_id": d.agent_id, "type": d.document_type, "number": d.number, "dian_status": d.dian_status, "email_status": d.email_status, "updated_at": d.updated_at} for d in docs]

# Panel web y cola de órdenes (MVP). La ejecución corresponde al agente local.
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import Boolean, Text

class AgentCommand(Base):
    __tablename__ = 'agent_commands'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey('agents.id'), nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    number: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='pending', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Numbering(Base):
    __tablename__ = 'numberings'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    prefix: Mapped[str] = mapped_column(String(30), default='', nullable=False)
    resolution: Mapped[str] = mapped_column(String(100), default='', nullable=False)
    range_start: Mapped[int] = mapped_column(Integer, default=1)
    range_end: Mapped[int] = mapped_column(Integer, default=999999)
    current_number: Mapped[int] = mapped_column(Integer, default=0)
    valid_from: Mapped[str] = mapped_column(String(10), default='')
    valid_until: Mapped[str] = mapped_column(String(10), default='')

Base.metadata.create_all(engine)

class CommandCreate(BaseModel):
    agent_id: int
    document_type: str = Field(pattern='^(factura|nota_credito)$')
    number: str = Field(min_length=1, max_length=80)
    action: str = Field(pattern='^(consultar_dian|reenviar_correo)$')

class CommandAck(BaseModel):
    status: str = Field(pattern='^(completed|failed)$')

class NumberingIn(BaseModel):
    company_id: int
    document_type: str = Field(pattern='^(factura|nota_credito)$')
    prefix: str = Field(max_length=30)
    resolution: str = Field(default='', max_length=100)
    range_start: int = Field(ge=0)
    range_end: int = Field(ge=0)
    current_number: int = Field(ge=0)
    valid_from: str = ''
    valid_until: str = ''

@app.get('/')
def dashboard():
    return FileResponse(Path(__file__).parent / 'static' / 'index.html')

@app.post('/admin/commands', dependencies=[Depends(admin)])
def queue_command(data: CommandCreate, db: Session = Depends(session)):
    if not db.get(Agent, data.agent_id):
        raise HTTPException(404, 'Agente no encontrado')
    if data.action == 'reenviar_correo':
        doc = db.scalar(select(DocumentStatus).where(DocumentStatus.agent_id == data.agent_id, DocumentStatus.document_type == data.document_type, DocumentStatus.number == data.number))
        if not doc or doc.dian_status.lower() not in ('aceptada', 'aceptado', 'accepted'):
            raise HTTPException(409, 'Solo se permite reenviar correo de documentos aceptados por DIAN')
    obj = AgentCommand(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return {'id':obj.id,'status':obj.status}

@app.get('/admin/commands', dependencies=[Depends(admin)])
def admin_commands(db: Session = Depends(session)):
    return [{'id':x.id,'agent_id':x.agent_id,'number':x.number,'action':x.action,'status':x.status,'created_at':x.created_at} for x in db.scalars(select(AgentCommand).order_by(AgentCommand.id.desc()).limit(200)).all()]

@app.get('/agent/commands')
def poll_commands(agent: Agent = Depends(agent_auth), db: Session = Depends(session)):
    return [{'id':x.id,'document_type':x.document_type,'number':x.number,'action':x.action} for x in db.scalars(select(AgentCommand).where(AgentCommand.agent_id == agent.id, AgentCommand.status == 'pending').order_by(AgentCommand.id).limit(50)).all()]

@app.post('/agent/commands/{command_id}/ack')
def ack_command(command_id: int, data: CommandAck, agent: Agent = Depends(agent_auth), db: Session = Depends(session)):
    cmd = db.get(AgentCommand, command_id)
    if not cmd or cmd.agent_id != agent.id:
        raise HTTPException(404, 'Orden no encontrada')
    cmd.status = data.status; db.commit()
    return {'ok':True}

@app.get('/admin/numberings', dependencies=[Depends(admin)])
def get_numberings(db: Session = Depends(session)):
    return [{'id':n.id,'company_id':n.company_id,'document_type':n.document_type,'prefix':n.prefix,'resolution':n.resolution,'range_start':n.range_start,'range_end':n.range_end,'current_number':n.current_number,'valid_from':n.valid_from,'valid_until':n.valid_until} for n in db.scalars(select(Numbering)).all()]

@app.post('/admin/numberings', dependencies=[Depends(admin)])
def save_numbering(data: NumberingIn, db: Session = Depends(session)):
    if not db.get(Company, data.company_id):
        raise HTTPException(404,'Empresa no encontrada')
    if data.range_end < data.range_start:
        raise HTTPException(422,'Rango inválido')
    n = db.scalar(select(Numbering).where(Numbering.company_id == data.company_id, Numbering.document_type == data.document_type))
    if not n:
        n = Numbering(**data.model_dump()); db.add(n)
    else:
        for k,v in data.model_dump().items(): setattr(n,k,v)
    db.commit()
    return {'ok':True}
