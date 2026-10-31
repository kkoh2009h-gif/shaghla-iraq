import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, String, Integer, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shaghla.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
Session = sessionmaker(bind=engine, expire_on_commit=False)
OTP_TTL_MINUTES = 5
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
PHONE_RE = re.compile(r"^\+9647\d{9}$")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str | None] = mapped_column(String(16), unique=True, index=True, nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(20), index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OTPChallenge(Base):
    __tablename__ = "otp_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(16), index=True)
    role: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    employer_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(20), default="نشطة", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", "worker_id", name="uq_job_worker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, index=True)
    worker_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(30), default="جديد")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)
app = FastAPI(
    title="Shaghla Iraq API",
    version="0.4.0",
    description="واجهة API لمنصة شَغلة العراقية",
)


class GoogleLogin(BaseModel):
    credential: str = Field(min_length=100, max_length=10000)
    role: Literal["worker", "employer"]


class OTPRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=16)
    role: Literal["worker", "employer"]


class OTPVerify(BaseModel):
    phone: str = Field(min_length=10, max_length=16)
    code: str = Field(pattern=r"^\d{6}$")


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)


class ApplicationStatusUpdate(BaseModel):
    status: Literal["قيد المراجعة", "مقبول", "مرفوض"]


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


def normalize_iraqi_phone(raw: str) -> str:
    value = re.sub(r"[\s()-]", "", raw)
    if value.startswith("00"):
        value = "+" + value[2:]
    if value.startswith("07"):
        value = "+964" + value[1:]
    elif value.startswith("7") and len(value) == 10:
        value = "+964" + value
    if not PHONE_RE.fullmatch(value):
        raise HTTPException(422, "أدخل رقم هاتف عراقي صحيح يبدأ بـ 07")
    return value


def _secret() -> str:
    value = os.getenv("SHAGHLA_AUTH_SECRET", "")
    if len(value) < 32:
        raise HTTPException(503, "خدمة تسجيل الدخول غير مهيأة بأمان على الخادم")
    return value


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _token_for(user: User) -> str:
    now = datetime.utcnow()
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(json.dumps({
        "sub": str(user.id),
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=7)).timestamp()),
    }, separators=(",", ":")).encode())
    body = f"{header}.{payload}"
    signature = hmac.new(_secret().encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def _current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "سجّل الدخول أولاً")
    token = authorization[7:].strip()
    try:
        header, payload, signature = token.split(".")
        body = f"{header}.{payload}"
        expected = _b64(hmac.new(_secret().encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if int(data["exp"]) <= int(datetime.utcnow().timestamp()):
            raise ValueError("expired")
        user_id = int(data["sub"])
    except Exception:
        raise HTTPException(401, "جلسة الدخول غير صالحة أو منتهية")
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(401, "الحساب غير موجود")
        return {"id": user.id, "phone": user.phone, "email": user.email, "role": user.role, "full_name": user.full_name}


def require_role(role: str):
    def dependency(user: dict = Depends(_current_user)) -> dict:
        if user["role"] != role:
            raise HTTPException(403, "هذه الخدمة غير متاحة لنوع حسابك")
        return user
    return dependency


async def send_otp_sms(phone: str, code: str) -> None:
    gateway_url = os.getenv("SMS_GATEWAY_URL", "")
    gateway_token = os.getenv("SMS_GATEWAY_TOKEN", "")
    if not gateway_url or not gateway_token:
        raise HTTPException(503, "إرسال الرسائل غير مهيأ. اربط مزود SMS أولاً")
    message = f"رمز تسجيل الدخول إلى شَغلة: {code} — صالح لمدة 5 دقائق."
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(
                gateway_url,
                json={"to": phone, "message": message},
                headers={"Authorization": f"Bearer {gateway_token}"},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(502, "تعذر إرسال رمز التحقق حالياً")


@app.get("/health")
def health():
    return {"status": "ok", "service": "shaghla-api", "version": app.version}


@app.post("/auth/google")
def google_login(data: GoogleLogin):
    audience = os.getenv("GOOGLE_WEB_CLIENT_ID", "").strip()
    if not audience:
        raise HTTPException(503, "تسجيل Google غير مهيأ على الخادم")
    try:
        info = google_id_token.verify_oauth2_token(
            data.credential, google_requests.Request(), audience
        )
    except Exception:
        raise HTTPException(401, "تعذر التحقق من حساب Google")
    google_sub = info.get("sub")
    email = info.get("email")
    if not google_sub or not email or not info.get("email_verified"):
        raise HTTPException(401, "حساب Google غير مكتمل أو غير موثّق")
    display_name = (info.get("name") or "").strip()[:120]
    with Session() as db:
        user = db.query(User).filter_by(google_sub=google_sub).first()
        if user and user.role != data.role:
            raise HTTPException(409, "هذا الحساب مسجل بنوع حساب آخر")
        if not user:
            user = User(google_sub=google_sub, email=email, role=data.role,
                        full_name=display_name)
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user.email = email
            if display_name and not user.full_name:
                user.full_name = display_name
            db.commit()
        token = _token_for(user)
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 604800,
            "user": {"id": user.id, "email": user.email, "role": user.role,
                     "full_name": user.full_name},
        }


@app.post("/auth/request-otp")
async def request_otp(data: OTPRequest):
    phone = normalize_iraqi_phone(data.phone)
    secret = _secret()
    now = datetime.utcnow()
    with Session() as db:
        user = db.query(User).filter_by(phone=phone).first()
        if user and user.role != data.role:
            raise HTTPException(409, "هذا الرقم مسجل بنوع حساب آخر")
        previous = db.query(OTPChallenge).filter_by(phone=phone, consumed=False).order_by(OTPChallenge.created_at.desc()).first()
        if previous and (now - previous.created_at).total_seconds() < OTP_RESEND_SECONDS:
            raise HTTPException(429, "انتظر دقيقة قبل طلب رمز جديد")
        code = f"{secrets.randbelow(1_000_000):06d}"
        digest = hmac.new(secret.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()
        challenge = OTPChallenge(
            phone=phone,
            role=data.role,
            code_hash=digest,
            expires_at=now + timedelta(minutes=OTP_TTL_MINUTES),
        )
        db.add(challenge)
        db.commit()
        challenge_id = challenge.id
    try:
        await send_otp_sms(phone, code)
    except HTTPException:
        with Session() as db:
            challenge = db.get(OTPChallenge, challenge_id)
            if challenge:
                challenge.consumed = True
                db.commit()
        raise
    return {"message": "تم إرسال رمز التحقق إذا كان الرقم صالحاً", "expires_in_seconds": OTP_TTL_MINUTES * 60}


@app.post("/auth/verify-otp")
def verify_otp(data: OTPVerify):
    phone = normalize_iraqi_phone(data.phone)
    secret = _secret()
    now = datetime.utcnow()
    with Session() as db:
        challenge = db.query(OTPChallenge).filter_by(phone=phone, consumed=False).order_by(OTPChallenge.created_at.desc()).first()
        if not challenge or challenge.expires_at < now:
            raise HTTPException(400, "رمز التحقق منتهي أو غير موجود")
        if challenge.attempts >= OTP_MAX_ATTEMPTS:
            challenge.consumed = True
            db.commit()
            raise HTTPException(429, "تجاوزت عدد المحاولات المسموح")
        digest = hmac.new(secret.encode(), f"{phone}:{data.code}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(digest, challenge.code_hash):
            challenge.attempts += 1
            db.commit()
            raise HTTPException(400, "رمز التحقق غير صحيح")
        challenge.consumed = True
        user = db.query(User).filter_by(phone=phone).first()
        if not user:
            user = User(phone=phone, role=challenge.role)
            db.add(user)
            db.commit()
            db.refresh(user)
        token = _token_for(user)
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 604800,
            "user": {"id": user.id, "phone": user.phone, "role": user.role, "full_name": user.full_name},
        }


@app.get("/auth/me")
def me(user: dict = Depends(_current_user)):
    return user


@app.patch("/auth/me")
def update_me(data: ProfileUpdate, user: dict = Depends(_current_user)):
    with Session() as db:
        record = db.get(User, user["id"])
        record.full_name = data.full_name.strip()
        db.commit()
        return {"id": record.id, "phone": record.phone, "email": record.email, "role": record.role, "full_name": record.full_name}


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
def create_job(data: JobIn, user: dict = Depends(require_role("employer"))):
    with Session() as db:
        job = Job(**data.model_dump(), employer_id=user["id"])
        db.add(job)
        db.commit()
        db.refresh(job)
        return {"id": job.id, "title": job.title, "status": job.status}


@app.post("/jobs/{job_id}/apply", status_code=201)
def apply(job_id: int, user: dict = Depends(require_role("worker"))):
    with Session() as db:
        job = db.get(Job, job_id)
        if not job or job.status != "نشطة":
            raise HTTPException(404, "الوظيفة غير موجودة أو غير متاحة")
        existing = db.query(Application).filter_by(job_id=job_id, worker_id=user["id"]).first()
        if existing:
            raise HTTPException(409, "سبق وقدمت على هذه الوظيفة")
        item = Application(job_id=job_id, worker_id=user["id"])
        db.add(item)
        db.commit()
        db.refresh(item)
        return {"id": item.id, "status": item.status}


@app.get("/employer/jobs")
def employer_jobs(user: dict = Depends(require_role("employer"))):
    with Session() as db:
        rows = db.query(Job).filter_by(employer_id=user["id"]).order_by(Job.created_at.desc()).all()
        return [job_dict(job) for job in rows]


@app.get("/worker/applications")
def worker_applications(user: dict = Depends(require_role("worker"))):
    with Session() as db:
        rows = db.query(Application).filter_by(worker_id=user["id"]).order_by(Application.created_at.desc()).all()
        return [
            {"id": item.id, "job_id": item.job_id, "status": item.status, "created_at": item.created_at.isoformat()}
            for item in rows
        ]


@app.get("/employer/jobs/{job_id}/applications")
def employer_job_applications(job_id: int, user: dict = Depends(require_role("employer"))):
    with Session() as db:
        job = db.query(Job).filter_by(id=job_id, employer_id=user["id"]).first()
        if not job:
            raise HTTPException(404, "الوظيفة غير موجودة")
        rows = db.query(Application).filter_by(job_id=job_id).order_by(Application.created_at.desc()).all()
        return [
            {"id": item.id, "job_id": item.job_id, "worker_id": item.worker_id,
             "status": item.status, "created_at": item.created_at.isoformat()}
            for item in rows
        ]


@app.patch("/employer/applications/{application_id}/status")
def update_application_status(
    application_id: int,
    data: ApplicationStatusUpdate,
    user: dict = Depends(require_role("employer")),
):
    with Session() as db:
        item = db.get(Application, application_id)
        if not item:
            raise HTTPException(404, "طلب التقديم غير موجود")
        job = db.query(Job).filter_by(id=item.job_id, employer_id=user["id"]).first()
        if not job:
            raise HTTPException(404, "طلب التقديم غير موجود")
        item.status = data.status
        db.commit()
        return {"id": item.id, "status": item.status}


@app.patch("/employer/jobs/{job_id}/status")
def update_job_status(
    job_id: int,
    status: Literal["نشطة", "مغلقة"],
    user: dict = Depends(require_role("employer")),
):
    with Session() as db:
        job = db.query(Job).filter_by(id=job_id, employer_id=user["id"]).first()
        if not job:
            raise HTTPException(404, "الوظيفة غير موجودة")
        job.status = status
        db.commit()
        return {"id": job.id, "status": job.status}


@app.post("/worker/applications/{application_id}/withdraw")
def withdraw_application(application_id: int, user: dict = Depends(require_role("worker"))):
    with Session() as db:
        item = db.get(Application, application_id)
        if not item or item.worker_id != user["id"]:
            raise HTTPException(404, "طلب التقديم غير موجود")
        if item.status in ("مقبول", "مرفوض"):
            raise HTTPException(409, "لا يمكن سحب طلب حُسمت حالته")
        item.status = "منسحب"
        db.commit()
        return {"id": item.id, "status": item.status}


@app.post("/employer/jobs/{job_id}/close")
def close_job(job_id: int, user: dict = Depends(require_role("employer"))):
    with Session() as db:
        job = db.get(Job, job_id)
        if not job or job.employer_id != user["id"]:
            raise HTTPException(404, "الوظيفة غير موجودة")
        job.status = "مغلقة"
        db.commit()
        return {"id": job.id, "status": job.status}
