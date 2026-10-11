"""Single-worker, CPU-only web entry point for Render."""

import os


def main():
    os.environ["TURINGTINT_DEPLOYMENT"] = "render"
    port = int(os.getenv("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    import uvicorn
    uvicorn.run("turingtint.app:app", host="0.0.0.0", port=port,
                workers=1, access_log=False)


if __name__ == "__main__":
    main()
