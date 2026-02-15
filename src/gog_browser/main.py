"""Run the GOG Games Browser server."""

import uvicorn


def run():
    """Entry point for gog-browser CLI."""
    uvicorn.run(
        "gog_browser.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()
