import os
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import create_engine, String, Integer, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shaghla.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
Session = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(60), default="أخرى", index=True)
    governorate: Mapped[str] = mapped_column(String(60), default="كركوك", index=True)
    area: Mapped[str] = mapped_column(String(100), default="")
    wage_iqd: Mapped[int] = mapped_column(Integer, default=0)
    work_type: Mapped[str] = mapped_column(String(30), default="يومي", index=True)
    positions: Mapped[int] = mapped_column(Integer, default=1)
    employer_id: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(20), default="نشطة", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", "worker_id", name="uq_job_worker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, index=True)
    worker_id: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(30), default="جديد")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)
app = FastAPI(
    title="Shaghla Iraq API",
    version="0.2.0",
    description="واجهة API أولية لمنصة شَغلة العراقية",
)


class JobIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=5000)
    category: str = Field(default="أخرى", min_length=2, max_length=60)
    governorate: str = Field(default="كركوك", min_length=2, max_length=60)
    area: str = Field(default="", max_length=100)
    wage_iqd: int = Field(default=0, ge=0, le=100_000_000)
    work_type: Literal["يومي", "بالساعة", "شهري", "مهمة", "مؤقت", "موسمي", "دوام كامل", "دوام جزئي"] = "يومي"
    positions: int = Field(default=1, ge=1, le=500)
    employer_id: str = Field(min_length=1, max_length=80)


class ApplyIn(BaseModel):
    worker_id: str = Field(min_length=1, max_length=80)


def job_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "category": job.category,
        "governorate": job.governorate,
        "area": job.area,
        "wage_iqd": job.wage_iqd,
        "work_type": job.work_type,
        "positions": job.positions,
        "status": job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "shaghla-api", "version": app.version}


@app.get("/jobs")
def list_jobs(
    q: str = Query(default="", max_length=120),
    governorate: str | None = Query(default=None, max_length=60),
    work_type: str | None = Query(default=None, max_length=30),
    category: str | None = Query(default=None, max_length=60),
    min_wage: int | None = Query(default=None, ge=0),
    max_wage: int | None = Query(default=None, ge=0),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    if min_wage is not None and max_wage is not None and min_wage > max_wage:
        raise HTTPException(422, "الحد الأدنى للأجر أكبر من الحد الأعلى")
    with Session() as db:
        query = db.query(Job).filter(Job.status == "نشطة")
        if q:
            pattern = f"%{q.strip()}%"
            query = query.filter(
                (Job.title.ilike(pattern))
                | (Job.description.ilike(pattern))
                | (Job.area.ilike(pattern))
                | (Job.category.ilike(pattern))
            )
        if governorate:
            query = query.filter(Job.governorate == governorate)
        if work_type:
            query = query.filter(Job.work_type == work_type)
        if category:
            query = query.filter(Job.category == category)
        if min_wage is not None:
            query = query.filter(Job.wage_iqd >= min_wage)
        if max_wage is not None:
            query = query.filter(Job.wage_iqd <= max_wage)
        rows = query.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()
        return [job_dict(job) for job in rows]


@app.get("/jobs/{job_id}")
def get_job(job_id: int):
    with Session() as db:
        job = db.get(Job, job_id)
        if not job or job.status != "نشطة":
            raise HTTPException(404, "الوظيفة غير موجودة أو غير متاحة")
        return job_dict(job)


@app.post("/jobs", status_code=201)
def create_job(data: JobIn):
    # MVP only: employer_id is client-supplied. Add verified server-side auth before public launch.
    with Session() as db:
        job = Job(**data.model_dump())
        db.add(job)
        db.commit()
        db.refresh(job)
        return {"id": job.id, "title": job.title, "status": job.status}


@app.post("/jobs/{job_id}/apply", status_code=201)
def apply(job_id: int, data: ApplyIn):
    # MVP only: worker_id is client-supplied. Add verified server-side auth before public launch.
    with Session() as db:
        job = db.get(Job, job_id)
        if not job or job.status != "نشطة":
            raise HTTPException(404, "الوظيفة غير موجودة أو غير متاحة")
        existing = db.query(Application).filter_by(job_id=job_id, worker_id=data.worker_id).first()
        if existing:
            raise HTTPException(409, "سبق وقدمت على هذه الوظيفة")
        item = Application(job_id=job_id, worker_id=data.worker_id)
        db.add(item)
        db.commit()
        db.refresh(item)
        return {"id": item.id, "status": item.status}
