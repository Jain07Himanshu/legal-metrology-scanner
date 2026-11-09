"""
Launcher script for Legal Metrology Scanner (PS-34).
Starts the FastAPI application and serves the web frontend.
"""
import uvicorn
import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    is_dev = os.environ.get("ENVIRONMENT", "").lower() == "development" or os.environ.get("RELOAD", "").lower() == "true"
    print("=" * 70)
    print("  LEGAL METROLOGY COMPLIANCE SCANNER (PS-34)")
    print("  Under Legal Metrology Act, 2009 & Packaged Commodities Rules, 2011")
    print(f"  Starting server on http://{host}:{port}")
    print("=" * 70)
    uvicorn.run("app.main:app", host=host, port=port, reload=is_dev)
