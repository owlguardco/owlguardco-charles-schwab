"""
Launch the trading dashboard.
Usage: python scripts/dashboard.py
       python scripts/dashboard.py --port 8080
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from dashboard.server import app
from loguru import logger

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()
    logger.info(f"Dashboard → http://localhost:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)

if __name__ == "__main__":
    main()
