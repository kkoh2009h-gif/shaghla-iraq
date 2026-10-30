import os

os.environ["DATABASE_URL"] = "sqlite:///./test_shaghla.db"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def create_job(title="عامل مخزن", **overrides):
    payload = {
        "title": title,
        "description": "فرصة عمل تجريبية للاختبار",
        "category": "مخازن",
        "governorate": "كركوك",
        "area": "المركز",
        "wage_iqd": 25000,
        "work_type": "يومي",
        "positions": 2,
        "employer_id": "employer-test",
    }
    payload.update(overrides)
    return client.post("/jobs", json=payload)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.2.0"


def test_create_and_list_job():
    created = create_job()
    assert created.status_code == 201
    listed = client.get("/jobs?q=عامل&governorate=كركوك&work_type=يومي")
    assert listed.status_code == 200
    assert any(job["title"] == "عامل مخزن" for job in listed.json())


def test_job_detail():
    created = create_job("فني شبكات").json()
    response = client.get(f"/jobs/{created['id']}")
    assert response.status_code == 200
    assert response.json()["category"] == "مخازن"
    assert response.json()["positions"] == 2


def test_wage_filters_and_pagination():
    create_job("موظف مبيعات", wage_iqd=500000, work_type="شهري")
    response = client.get("/jobs?min_wage=100000&max_wage=600000&limit=1")
    assert response.status_code == 200
    assert len(response.json()) <= 1


def test_invalid_wage_range():
    response = client.get("/jobs?min_wage=90000&max_wage=1000")
    assert response.status_code == 422


def test_invalid_work_type_rejected():
    response = create_job("عمل غير معروف", work_type="غير صالح")
    assert response.status_code == 422


def test_duplicate_application_rejected():
    job = create_job("فني صيانة").json()
    payload = {"worker_id": "worker-test"}
    first = client.post(f"/jobs/{job['id']}/apply", json=payload)
    second = client.post(f"/jobs/{job['id']}/apply", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


def test_unknown_job_returns_404():
    response = client.get("/jobs/999999")
    assert response.status_code == 404
