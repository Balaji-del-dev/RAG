import uuid


def test_validation_errors_use_the_standard_shape(client):
    response = client.post("/api/v1/auth/login/", {}, format="json")
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert set(body["error"]["details"]) == {"username", "password"}
    assert body["request_id"] == response["X-Request-ID"]


def test_not_found_uses_the_standard_shape(admin_client):
    response = admin_client.get(f"/api/v1/admin/users/{uuid.uuid4()}/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_not_signed_in_is_401_not_403(client):
    response = client.get("/api/v1/auth/me/")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
