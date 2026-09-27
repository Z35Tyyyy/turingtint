"""Run with python -m turingtint; no public network binding by default."""

import argparse
import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TuringTint local writing analysis app.")
    parser.add_argument("--port", type=int, default=8765)
    options = parser.parse_args()
    if not 1 <= options.port <= 65535:
        parser.error("port must be between 1 and 65535")
    uvicorn.run("turingtint.app:app", host="127.0.0.1", port=options.port, access_log=False)


if __name__ == "__main__":
    main()
