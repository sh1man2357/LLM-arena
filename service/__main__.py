import argparse
import uvicorn

from service.app import create_app

parser = argparse.ArgumentParser(description="LLM Arena local spectator application")
parser.add_argument("--port", type=int, default=8787)
parser.add_argument("--data")
parser.add_argument("--demo", action="store_true", help="Prepare one reference Bot per game; no automatic matches")
args = parser.parse_args()
uvicorn.run(create_app(args.data, demo=args.demo, workers=True), host="127.0.0.1", port=args.port)
