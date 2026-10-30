import os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shaghla.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
Session = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase): pass
class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    governorate: Mapped[str] = mapped_column(String(60), default="كركوك")
    area: Mapped[str] = mapped_column(String(100), default="")
    wage_iqd: Mapped[int] = mapped_column(Integer, default=0)
    work_type: Mapped[str] = mapped_column(String(30), default="يومي")
    employer_id: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", "worker_id", name="uq_job_worker"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="جديد")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)
app = FastAPI(title="Shaghla Iraq API", version="0.1.0")

class JobIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = ""
    governorate: str = "كركوك"
    area: str = ""
    wage_iqd: int = Field(default=0, ge=0)
    work_type: str = "يومي"
    employer_id: str = Field(min_length=1, max_length=80)

class ApplyIn(BaseModel):
    worker_id: str = Field(min_length=1, max_length=80)

@app.get("/health")
def health(): return {"status": "ok", "service": "shaghla-api"}

@app.get("/jobs")
def list_jobs(q: str = ""):
    with Session() as db:
        rows = db.query(Job).order_by(Job.created_at.desc()).all()
        return [{"id": j.id, "title": j.title, "description": j.description, "governorate": j.governorate, "area": j.area, "wage_iqd": j.wage_iqd, "work_type": j.work_type} for j in rows if q.lower() in (j.title + j.description + j.governorate + j.area).lower()]

@app.post("/jobs", status_code=201)
def create_job(data: JobIn):
    # MVP endpoint: identity/role enforcement must be added before public deployment.
    with Session() as db:
        job = Job(**data.model_dump())
        db.add(job); db.commit(); db.refresh(job)
        return {"id": job.id, "title": job.title}

@app.post("/jobs/{job_id}/apply", status_code=201)
def apply(job_id: int, data: ApplyIn):
    with Session() as db:
        if not db.get(Job, job_id): raise HTTPException(404, "الوظيفة غير موجودة")
        existing = db.query(Application).filter_by(job_id=job_id, worker_id=data.worker_id).first()
        if existing: raise HTTPException(409, "سبق وقدمت على هذه الوظيفة")
        item = Application(job_id=job_id, worker_id=data.worker_id)
        db.add(item); db.commit(); db.refresh(item)
        return {"id": item.id, "status": item.status}
