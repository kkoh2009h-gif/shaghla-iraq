import os

os.environ["DATABASE_URL"] = "sqlite:///./test_shaghla.db"
os.environ["SHAGHLA_AUTH_SECRET"] = "test-secret-key-that-is-long-enough-for-hmac"

from fastapi.testclient import TestClient
from app import main
from app.main import app

client = TestClient(app)
sent_codes = {}


async def fake_send_otp_sms(phone, code):
    sent_codes[phone] = code


main.send_otp_sms = fake_send_otp_sms


def register(phone, role):
    sent_codes.pop(phone, None)
    requested = client.post("/auth/request-otp", json={"phone": phone, "role": role})
    assert requested.status_code == 200
    code = sent_codes[phone]
    verified = client.post("/auth/verify-otp", json={"phone": phone, "code": code})
    assert verified.status_code == 200
    return verified.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def create_job(token, title="عامل مخزن", **overrides):
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
    return client.post("/jobs", json=payload, headers=auth(token))


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.4.0"


def test_iraqi_phone_normalization():
    assert main.normalize_iraqi_phone("07701234567") == "+9647701234567"
    assert main.normalize_iraqi_phone("+9647701234567") == "+9647701234567"


def test_invalid_phone_rejected():
    response = client.post("/auth/request-otp", json={"phone": "12345", "role": "worker"})
    assert response.status_code == 422


def test_otp_login_and_profile():
    token = register("+9647700000001", "worker")
    response = client.get("/auth/me", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["role"] == "worker"
    updated = client.patch("/auth/me", json={"full_name": "عامل تجريبي"}, headers=auth(token))
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "عامل تجريبي"


def test_wrong_otp_rejected():
    phone = "+9647700000002"
    sent_codes.pop(phone, None)
    assert client.post("/auth/request-otp", json={"phone": phone, "role": "worker"}).status_code == 200
    response = client.post("/auth/verify-otp", json={"phone": phone, "code": "111111"})
    assert response.status_code == 400


def test_job_create_requires_employer_role():
    worker_token = register("+9647700000003", "worker")
    response = create_job(worker_token)
    assert response.status_code == 403


def test_create_and_list_job():
    employer_token = register("+9647700000004", "employer")
    created = create_job(employer_token)
    assert created.status_code == 201
    listed = client.get("/jobs?q=عامل&governorate=كركوك&work_type=يومي")
    assert listed.status_code == 200
    assert any(job["title"] == "عامل مخزن" for job in listed.json())


def test_job_detail():
    employer_token = register("+9647700000005", "employer")
    created = create_job(employer_token, "فني شبكات").json()
    response = client.get(f"/jobs/{created['id']}")
    assert response.status_code == 200
    assert response.json()["category"] == "مخازن"
    assert response.json()["positions"] == 2


def test_wage_filters_and_pagination():
    employer_token = register("+9647700000006", "employer")
    create_job(employer_token, "موظف مبيعات", wage_iqd=500000, work_type="شهري")
    response = client.get("/jobs?min_wage=100000&max_wage=600000&limit=1")
    assert response.status_code == 200
    assert len(response.json()) <= 1


def test_invalid_wage_range():
    response = client.get("/jobs?min_wage=90000&max_wage=1000")
    assert response.status_code == 422


def test_invalid_work_type_rejected():
    employer_token = register("+9647700000007", "employer")
    response = create_job(employer_token, "عمل غير معروف", work_type="غير صالح")
    assert response.status_code == 422


def test_duplicate_application_rejected():
    employer_token = register("+9647700000008", "employer")
    worker_token = register("+9647700000009", "worker")
    job = create_job(employer_token, "فني صيانة").json()
    first = client.post(f"/jobs/{job['id']}/apply", headers=auth(worker_token))
    second = client.post(f"/jobs/{job['id']}/apply", headers=auth(worker_token))
    assert first.status_code == 201
    assert second.status_code == 409


def test_employer_cannot_apply_as_worker():
    employer_token = register("+9647700000010", "employer")
    response = client.post("/jobs/1/apply", headers=auth(employer_token))
    assert response.status_code == 403


def test_unknown_job_returns_404():
    response = client.get("/jobs/999999")
    assert response.status_code == 404



def test_employer_can_review_applications_and_close_job():
    employer_token = register("+9647700000011", "employer")
    worker_token = register("+9647700000012", "worker")
    job = create_job(employer_token, "مساعد إداري").json()
    applied = client.post(f"/jobs/{job['id']}/apply", headers=auth(worker_token))
    assert applied.status_code == 201
    application_id = applied.json()["id"]

    listing = client.get(
        f"/employer/jobs/{job['id']}/applications",
        headers=auth(employer_token),
    )
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    changed = client.patch(
        f"/employer/applications/{application_id}/status",
        json={"status": "مقبول"},
        headers=auth(employer_token),
    )
    assert changed.status_code == 200
    assert changed.json()["status"] == "مقبول"

    closed = client.patch(
        f"/employer/jobs/{job['id']}/status?status=مغلقة",
        headers=auth(employer_token),
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "مغلقة"


def test_other_employer_cannot_manage_application():
    owner_token = register("+9647700000013", "employer")
    other_token = register("+9647700000014", "employer")
    worker_token = register("+9647700000015", "worker")
    job = create_job(owner_token, "عامل إنتاج").json()
    applied = client.post(f"/jobs/{job['id']}/apply", headers=auth(worker_token))
    application_id = applied.json()["id"]
    response = client.patch(
        f"/employer/applications/{application_id}/status",
        json={"status": "مرفوض"},
        headers=auth(other_token),
    )
    assert response.status_code == 404


def test_employer_can_review_worker_application(monkeypatch):
    _, employer_headers = register("employer", monkeypatch)
    _, worker_headers = register("worker", monkeypatch)
    job = client.post("/jobs", json=job_payload("فني كهرباء"), headers=employer_headers).json()
    application = client.post(f"/jobs/{job['id']}/apply", headers=worker_headers).json()

    inbox = client.get(f"/employer/jobs/{job['id']}/applications", headers=employer_headers)
    assert inbox.status_code == 200
    assert any(item["id"] == application["id"] for item in inbox.json())

    reviewed = client.patch(
        f"/employer/applications/{application['id']}",
        json={"status": "مقبول"},
        headers=employer_headers,
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "مقبول"


def test_employer_cannot_manage_another_employers_job(monkeypatch):
    _, owner_headers = register("employer", monkeypatch)
    _, other_headers = register("employer", monkeypatch)
    job = client.post("/jobs", json=job_payload("عامل توصيل"), headers=owner_headers).json()
    response = client.post(f"/employer/jobs/{job['id']}/close", headers=other_headers)
    assert response.status_code == 404


def test_worker_can_withdraw_application(monkeypatch):
    _, employer_headers = register("employer", monkeypatch)
    _, worker_headers = register("worker", monkeypatch)
    job = client.post("/jobs", json=job_payload("عامل مطعم"), headers=employer_headers).json()
    application = client.post(f"/jobs/{job['id']}/apply", headers=worker_headers).json()

    response = client.post(
        f"/worker/applications/{application['id']}/withdraw",
        headers=worker_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "منسحب"
