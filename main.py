"""Amazon PPC Intelligence Terminal Application - Entry Point.

Launch modes:
  python main.py           → Textual TUI in terminal (hover tooltips)
  python main.py --web     → Opens in web browser at http://localhost:8501
  python main.py --web 9000 → Custom port
  python main.py --classic → Rich CLI (original menu-driven, no mouse)
"""

import logging
import subprocess
import sys
from pathlib import Path

# Setup logging
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "analysis.log", encoding="utf-8"),
    ],
)


def check_dependencies():
    """Check and install required packages."""
    required = ["rich", "pandas", "requests", "bs4", "textual"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"Installing missing packages: {', '.join(missing)}")
        req_file = Path(__file__).parent / "requirements.txt"
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def run_textual():
    """Launch the Textual TUI in terminal."""
    from ui.app import AmazonPPCApp
    app = AmazonPPCApp()
    app.run()


def run_web(port: int = 8501):
    """Launch the Textual app in a web browser via textual-serve."""
    try:
        from textual_serve.server import Server
    except ImportError:
        print("Installing textual-serve for browser mode...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "textual-serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        from textual_serve.server import Server

    import webbrowser
    import threading

    # Use absolute path to serve_app.py so it works regardless of cwd
    serve_script = Path(__file__).resolve().parent / "serve_app.py"
    server = Server(
        command=f'"{sys.executable}" "{serve_script}"',
        host="localhost",
        port=port,
        title="Amazon PPC Intelligence",
    )

    url = f"http://localhost:{port}"
    print(f"\n  Amazon PPC Intelligence — Web Mode")
    print(f"  Opening browser at: {url}")
    print(f"  Press Ctrl+C to stop the server.\n")

    # Open browser after a short delay so server can start
    def open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    server.serve()


def run_classic():
    """Launch the classic Rich CLI application."""
    from main_classic import main
    main()


if __name__ == "__main__":
    check_dependencies()

    if "--classic" in sys.argv:
        run_classic()
    elif "--web" in sys.argv:
        # Parse optional port: --web 9000
        port = 8501
        idx = sys.argv.index("--web")
        if idx + 1 < len(sys.argv):
            try:
                port = int(sys.argv[idx + 1])
            except ValueError:
                pass
        run_web(port)
    else:
        run_textual()
