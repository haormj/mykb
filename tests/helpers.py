from __future__ import annotations


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register(client, username: str = "alice", password: str = "secret123") -> dict[str, str]:
    response = client.post(
        "/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return auth(response.json()["token"])


def login(client, username: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return auth(response.json()["token"])


def create_kb(client, headers: dict[str, str], name: str = "kb", **kwargs) -> dict:
    response = client.post("/kbs", json={"name": name, **kwargs}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()
