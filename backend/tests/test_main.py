import os
os.environ["DATABASE_URL"] = "sqlite:///./test_shaghla.db"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_create_and_list_job():
    created = client.post("/jobs", json={
        "title": "عامل مخزن",
        "description": "عمل تجريبي للاختبار",
        "governorate": "كركوك",
        "area": "المركز",
        "wage_iqd": 25000,
        "work_type": "يومي",
        "employer_id": "employer-test"
    })
    assert created.status_code == 201
    listed = client.get("/jobs?q=عامل")
    assert listed.status_code == 200
    assert any(job["title"] == "عامل مخزن" for job in listed.json())

def test_duplicate_application_rejected():
    job = client.post("/jobs", json={
        "title": "فني صيانة",
        "employer_id": "employer-test"
    }).json()
    payload = {"worker_id": "worker-test"}
    first = client.post(f"/jobs/{job['id']}/apply", json=payload)
    second = client.post(f"/jobs/{job['id']}/apply", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409
