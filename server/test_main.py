import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_read_main():
    response = client.get("/")
    assert response.status_code == 404  # Since we don't have a root endpoint

def test_create_project():
    project_data = {
        "name": "Test Project",
        "description": "A test project for SQL generation"
    }
    response = client.post("/projects/", json=project_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == project_data["name"]
    assert data["description"] == project_data["description"]

def test_get_projects():
    response = client.get("/projects/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_get_nonexistent_project():
    response = client.get("/projects/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found" 