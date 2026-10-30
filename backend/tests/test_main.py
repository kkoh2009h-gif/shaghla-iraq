import os
import secrets

os.environ["DATABASE_URL"] = "sqlite:///./test_shaghla_auth.db"
os.environ["SHAGHLA_AUTH_SECRET"] = "test-secret-key-with-more-than-32-characters"

from fastapi.testclient import TestClient
import app.main as main

client = TestClient(main.app)
issued_codes = {}


async def fake_send_otp(phone: str, code: str):
    issued_codes[phone] = code


def phone_number():
    return "07" + "".join(str(secrets.randbelow(10)) for _ in range(9))


def register(role: str, monkeypatch):
    monkeypatch.setattr(main, "send_otp_sms", fake_send_otp)
    phone = phone_number()
    requested = client.post("/auth/request-otp", json={"phone": phone, "role": role})
    assert requested.status_code == 200
    verified = client.post(
        "/auth/verify-otp",
        json={"phone": phone, "code": issued_codes[main.normalize_iraqi_phone(phone)]},
    )
    assert verified.status_code == 200
    token = verified.json()["access_token"]
    return phone, {"Authorization": f"Bearer {token}"}


def job_payload(title="عامل مخزن", **overrides):
    payload = {
        "title": title,
        "description": "فرصة عمل تجريبية للاختبار",
        "category": "مخازن",
        "governorate": "كركوك",
        "area": "المركز",
        "wage_iqd": 25000,
        "work_type": "يومي",
        "positions": 2,
    }
    payload.update(overrides)
    return payload


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.3.0"


def test_iraqi_phone_normalization():
    assert main.normalize_iraqi_phone("07701234567") == "+9647701234567"
    assert main.normalize_iraqi_phone("+9647701234567") == "+9647701234567"


def test_invalid_phone_rejected():
    response = client.post("/auth/request-otp", json={"phone": "12345", "role": "worker"})
    assert response.status_code == 422


def test_phone_otp_registration_and_profile(monkeypatch):
    phone, headers = register("worker", monkeypatch)
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["phone"] == main.normalize_iraqi_phone(phone)
    assert me.json()["role"] == "worker"

    updated = client.patch("/auth/me", json={"full_name": "أحمد علي"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "أحمد علي"


def test_otp_is_not_returned_in_api_response(monkeypatch):
    monkeypatch.setattr(main, "send_otp_sms", fake_send_otp)
    phone = phone_number()
    response = client.post("/auth/request-otp", json={"phone": phone, "role": "worker"})
    assert response.status_code == 200
    assert "code" not in response.json()
    assert "otp" not in response.json()


def test_wrong_role_cannot_create_job(monkeypatch):
    _, worker_headers = register("worker", monkeypatch)
    response = client.post("/jobs", json=job_payload(), headers=worker_headers)
    assert response.status_code == 403


def test_job_create_search_and_detail(monkeypatch):
    _, employer_headers = register("employer", monkeypatch)
    created = client.post("/jobs", json=job_payload(), headers=employer_headers)
    assert created.status_code == 201

    listed = client.get("/jobs?q=عامل&governorate=كركوك&work_type=يومي")
    assert listed.status_code == 200
    assert any(job["title"] == "عامل مخزن" for job in listed.json())

    detail = client.get(f"/jobs/{created.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["positions"] == 2


def test_wage_filters_and_pagination(monkeypatch):
    _, employer_headers = register("employer", monkeypatch)
    client.post("/jobs", json=job_payload("موظف مبيعات", wage_iqd=500000, work_type="شهري"), headers=employer_headers)
    response = client.get("/jobs?min_wage=100000&max_wage=600000&limit=1")
    assert response.status_code == 200
    assert len(response.json()) <= 1


def test_invalid_wage_range():
    response = client.get("/jobs?min_wage=90000&max_wage=1000")
    assert response.status_code == 422


def test_invalid_work_type_rejected(monkeypatch):
    _, employer_headers = register("employer", monkeypatch)
    response = client.post("/jobs", json=job_payload("عمل غير معروف", work_type="غير صالح"), headers=employer_headers)
    assert response.status_code == 422


def test_worker_application_and_duplicate_blocked(monkeypatch):
    _, employer_headers = register("employer", monkeypatch)
    _, worker_headers = register("worker", monkeypatch)
    job = client.post("/jobs", json=job_payload("فني صيانة"), headers=employer_headers).json()

    first = client.post(f"/jobs/{job['id']}/apply", headers=worker_headers)
    second = client.post(f"/jobs/{job['id']}/apply", headers=worker_headers)
    assert first.status_code == 201
    assert second.status_code == 409

    applications = client.get("/worker/applications", headers=worker_headers)
    assert applications.status_code == 200
    assert any(item["job_id"] == job["id"] for item in applications.json())


def test_employer_sees_only_own_jobs(monkeypatch):
    _, employer_headers = register("employer", monkeypatch)
    client.post("/jobs", json=job_payload("وظيفة خاصة"), headers=employer_headers)
    response = client.get("/employer/jobs", headers=employer_headers)
    assert response.status_code == 200
    assert any(job["title"] == "وظيفة خاصة" for job in response.json())


def test_protected_endpoint_requires_login():
    response = client.post("/jobs", json=job_payload())
    assert response.status_code == 401


def test_unknown_job_returns_404():
    response = client.get("/jobs/99999999")
    assert response.status_code == 404
