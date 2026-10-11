import argparse
import os

import uvicorn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description="Run the search engine web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Restart on code changes")
    args = parser.parse_args()

    os.chdir(ROOT)  # so `web.app` is importable from any working directory
    uvicorn.run("web.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == '__main__':
    main()
