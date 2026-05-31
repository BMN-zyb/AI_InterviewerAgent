"""API 接口测试"""
from fastapi.testclient import TestClient


def test_health():
    from api.main import app
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


if __name__ == "__main__":
    test_health()
    print("All tests passed!")

    # python -m tests.test_api