"""
Entrypoint for OnTheSpot Tauri Desktop Backend Sidecar.
"""
import os
import sys

# Ensure protobuf python implementation
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

# Add src to sys.path if running from source or bundle
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, "src")
if os.path.isdir(src_dir) and src_dir not in sys.path:
    sys.path.insert(0, src_dir)

if getattr(sys, "frozen", False):
    bundle_dir = getattr(sys, "_MEIPASS", current_dir)
    if os.path.isdir(bundle_dir) and bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)

import uvicorn
from onthespot.main import app

def main():
    host = os.environ.get("OTS_HOST", "127.0.0.1")
    port = int(os.environ.get("OTS_PORT", "6767"))
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    main()
