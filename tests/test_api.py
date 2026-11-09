"""
API Integration Test for Legal Metrology Scanner FastAPI endpoints.
"""
import sys
from pathlib import Path
import json

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    print("[OK] /api/health endpoint: PASSED")

def test_samples_endpoint():
    response = client.get("/api/samples")
    assert response.status_code == 200
    samples = response.json()
    assert len(samples) >= 4
    print(f"[OK] /api/samples returned {len(samples)} benchmark products: PASSED")

def test_scan_endpoint_with_benchmark_sample():
    # Fetch sample 1
    sample_res = client.get("/api/samples/SAMPLE_BISCUIT_VIOLATION")
    assert sample_res.status_code == 200
    sample_data = sample_res.json()

    # Post scan
    scan_payload = {
        "product_name": sample_data["name"],
        "brand": sample_data["brand"],
        "category": sample_data["category"],
        "sides": sample_data["sides"],
        "inspector_id": "INSP-DL-4089",
        "location": "Delhi Central Market"
    }
    scan_res = client.post("/api/scan", json=scan_payload)
    assert scan_res.status_code == 200
    res_data = scan_res.json()
    
    assert res_data["compliance_status"] == "NON_COMPLIANT"
    assert res_data["failed_rules"] >= 2
    assert res_data["pdf_report_url"] is not None
    print("[OK] /api/scan with violation detection: PASSED")

    # Generate Show-Cause Notice
    notice_payload = {
        "scan_id": res_data["scan_id"],
        "company_name": "SuperFoods Confectionery Ltd",
        "company_address": "Plot 14, Haridwar, Uttarakhand - 249401"
    }
    notice_res = client.post("/api/notice/generate", json=notice_payload)
    assert notice_res.status_code == 200
    notice_data = notice_res.json()
    assert "SHOW-CAUSE NOTICE" in notice_data["full_notice_text"]
    print("[OK] /api/notice/generate: PASSED")

def test_analytics_endpoint():
    response = client.get("/api/analytics")
    assert response.status_code == 200
    data = response.json()
    assert data["total_scans"] > 0
    print(f"[OK] /api/analytics with {data['total_scans']} total scans: PASSED")

def test_history_endpoint():
    response = client.get("/api/history")
    assert response.status_code == 200
    history = response.json()
    assert len(history) > 0
    print(f"[OK] /api/history returned {len(history)} records: PASSED")

if __name__ == "__main__":
    print("Running API Integration Tests...")
    test_health_endpoint()
    test_samples_endpoint()
    test_scan_endpoint_with_benchmark_sample()
    test_analytics_endpoint()
    test_history_endpoint()
    print("\nALL API INTEGRATION TESTS PASSED!")
