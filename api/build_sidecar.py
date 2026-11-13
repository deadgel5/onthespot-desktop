"""
Script to build the standalone Python backend sidecar for Tauri using PyInstaller.
"""
import os
import sys
import shutil
import subprocess

def get_target_triple():
    if len(sys.argv) > 1:
        return sys.argv[1]
    
    # Auto-detect target
    if sys.platform == "win32":
        return "x86_64-pc-windows-msvc"
    elif sys.platform == "darwin":
        import platform
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            return "aarch64-apple-darwin"
        return "x86_64-apple-darwin"
    else:
        return "x86_64-unknown-linux-gnu"

def main():
    target = get_target_triple()
    print(f"Building OnTheSpot backend sidecar for target: {target}")

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    api_dir = os.path.join(root_dir, "api")
    src_dir = os.path.join(api_dir, "src")
    entrypoint = os.path.join(api_dir, "entrypoint_tauri.py")
    output_dir = os.path.join(root_dir, "ui", "src-tauri", "binaries")
    os.makedirs(output_dir, exist_ok=True)

    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    ext = ".exe" if "windows" in target else ""
    final_binary_name = f"ots-backend-{target}{ext}"
    final_binary_path = os.path.join(output_dir, final_binary_name)

    # Strip any compiled .pyd / .so Cython binaries from zeroconf to force it into pure Python mode.
    # This prevents Windows Code Integrity / WDAC policies from blocking unsigned time.cp312-win_amd64.pyd.
    try:
        import zeroconf
        zc_dir = os.path.dirname(zeroconf.__file__)
        removed_count = 0
        for root, _, files in os.walk(zc_dir):
            for file in files:
                if file.endswith((".pyd", ".so")):
                    try:
                        os.remove(os.path.join(root, file))
                        removed_count += 1
                    except Exception as err:
                        print(f"Error removing {file}: {err}")
        if removed_count > 0:
            print(f"Removed {removed_count} compiled zeroconf binaries for pure-Python fallback (WDAC compatible)")
    except Exception as e:
        print(f"Warning: Could not strip zeroconf binaries: {e}")

    # Add default config & resources to bundle
    onthespot_pkg = os.path.join(src_dir, "onthespot")

    # PyInstaller arguments
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name", f"ots-backend-{target}",
        "--distpath", output_dir,
        "--paths", src_dir,
        "--add-data", f"{onthespot_pkg}{os.pathsep}onthespot",
        "--collect-all", "onthespot",
        "--collect-all", "fastapi",
        "--collect-all", "uvicorn",
        "--collect-all", "librespot",
        "--collect-all", "zeroconf",
        "--collect-all", "yt_dlp",
        "--collect-all", "music_tag",
        "--collect-all", "mutagen",
        "--collect-all", "PIL",
        "--collect-all", "cryptography",
        "--collect-all", "pywidevine",
        "--collect-all", "bgutil_ytdlp_pot_provider",
        "--hidden-import", "onthespot",
        "--hidden-import", "onthespot.main",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.lifespans",
        "--hidden-import", "uvicorn.lifespans.on",
        entrypoint
    ]

    env = os.environ.copy()
    env["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else src_dir

    print("Running command:", " ".join(cmd))
    res = subprocess.run(cmd, env=env)
    if res.returncode != 0:
        print("PyInstaller build failed!", file=sys.stderr)
        sys.exit(res.returncode)

    print(f"Successfully built sidecar: {final_binary_path}")

if __name__ == "__main__":
    main()
