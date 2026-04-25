import subprocess
import sys
import os
import time
import httpx

# Auto-cd to the folder containing this script so imports work from anywhere
os.chdir(os.path.dirname(os.path.abspath(__file__)))

processes = []


def start_fastapi():
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
        ],
    )
    processes.append(("FastAPI", proc))
    return proc


def start_streamlit():
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run",
            "frontend/app.py",
            "--server.port", "8501",
            "--server.headless", "true",
        ],
    )
    processes.append(("Streamlit", proc))
    return proc


def wait_for_fastapi(max_retries=30, delay=1):
    for i in range(max_retries):
        try:
            resp = httpx.get("http://localhost:8000/api/health", timeout=2.0)
            if resp.status_code == 200:
                print(f"  FastAPI ready (after {i + 1}s)")
                return True
        except httpx.ConnectError:
            pass
        time.sleep(delay)
    print("  WARNING: FastAPI did not become ready in time")
    return False


def shutdown():
    for name, proc in processes:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        print(f"  Stopped {name}")
    processes.clear()


if __name__ == "__main__":
    print("=" * 50)
    print("  Adversarial Procurement Agent")
    print("=" * 50)
    print()

    print("Starting FastAPI backend...")
    start_fastapi()

    print("Waiting for backend to be ready...")
    wait_for_fastapi()

    print("Starting Streamlit frontend...")
    start_streamlit()

    print()
    print("  Frontend: http://localhost:8501")
    print("  Backend:  http://localhost:8000/docs")
    print()
    print("Press Ctrl+C to stop both servers.")

    try:
        while True:
            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"{name} exited with code {proc.returncode}")
                    shutdown()
                    sys.exit(1)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        shutdown()
