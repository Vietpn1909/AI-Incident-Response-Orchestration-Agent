"""Test contract ④ — hình dạng response mà Long phụ thuộc vào.

Các test này là hàng rào bảo vệ contract: khi tuần 3 đổi nguồn dữ liệu từ
fixture sang Jira thật, nếu hình dạng response lệch đi thì CI đỏ ở đây thay vì
UI của Long vỡ âm thầm.
"""

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_status_page_tra_ve_du_lieu_cho_status_page():
    response = client.get("/api/status")
    assert response.status_code == 200

    data = response.json()
    assert "updated_at" in data
    assert len(data["services"]) >= 1

    service = data["services"][0]
    assert {"name", "health", "message"} <= service.keys()
    assert service["health"] in {"operational", "degraded", "down", "maintenance"}


def test_list_incidents_sap_xep_moi_nhat_truoc():
    response = client.get("/api/incidents")
    assert response.status_code == 200

    incidents = response.json()
    assert len(incidents) >= 2

    detected = [incident["detected_at"] for incident in incidents]
    assert detected == sorted(detected, reverse=True)


def test_only_open_loc_bo_incident_da_resolved():
    incidents = client.get("/api/incidents", params={"only_open": True}).json()
    assert all(incident["state"] != "Resolved" for incident in incidents)


def test_get_incident_tra_ve_bang_chung_va_giai_thuyet():
    incident = client.get("/api/incidents/INC-12").json()

    assert incident["severity"] == "P2"
    assert incident["state"] == "Awaiting Approval"

    # Ràng buộc đề bài: chẩn đoán phải có bằng chứng, không chỉ câu chữ từ LLM.
    hypothesis = incident["hypotheses"][0]
    assert hypothesis["evidence"], "giả thuyết phải kèm bằng chứng số"
    assert 0.0 <= hypothesis["confidence"] <= 1.0

    # Bằng chứng phải kèm PromQL để người khác kiểm chứng lại được.
    assert incident["signal"]["evidence"][0]["promql"]


def test_de_xuat_khac_phuc_luon_yeu_cau_duyet():
    incident = client.get("/api/incidents/INC-12").json()
    assert incident["proposal"]["requires_approval"] is True


def test_incident_lan_truyen_duoc_link_hai_chieu():
    inc12 = client.get("/api/incidents/INC-12").json()
    inc13 = client.get("/api/incidents/INC-13").json()

    assert "INC-13" in inc12["related_incidents"]
    assert "INC-12" in inc13["related_incidents"]


def test_incident_khong_ton_tai_tra_ve_404():
    assert client.get("/api/incidents/INC-9999").status_code == 404
