import os

import uvicorn

from app.main import app


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "53111")),
        log_level=os.getenv("LOG_LEVEL", "info"),
        access_log=False,
    )
