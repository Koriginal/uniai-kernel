from fastapi.testclient import TestClient
from app.main import app
import sys
import os

# Add root to path
sys.path.append(os.getcwd())

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "UniAI Kernel is running."}
    print("Root endpoint test passed.")

def test_health():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    print("Health endpoint test passed.")

if __name__ == "__main__":
    try:
        test_root()
        test_health()
        print("Basic infrastructure verified successfully.")
    except Exception as e:
        print(f"Verification failed: {e}")
        sys.exit(1)
