"""Run the API: `python -m app`.

Exists because of one Windows-specific problem. uvicorn chooses its event loop
with an explicit `loop_factory`, which bypasses `asyncio.set_event_loop_policy`
entirely, and on Windows that factory is `ProactorEventLoop` unless uvicorn
happens to be running its reloader:

    def asyncio_loop_factory(use_subprocess: bool = False):
        if sys.platform == "win32" and not use_subprocess:
            return asyncio.ProactorEventLoop
        return asyncio.SelectorEventLoop

psycopg's async mode refuses to run on `ProactorEventLoop`, so
`uvicorn app.main:app` on Windows fails on the first database call -- while
`uvicorn app.main:app --reload` works, purely as a side effect of the
reloader. Depending on that is a trap: the same command behaves differently
with and without a flag that is supposed to be about convenience.

This entry point runs the server on a loop psycopg can use, on every platform.
On Linux it is equivalent to running uvicorn directly.
"""

import asyncio
import os
import sys

import uvicorn


def _default_host() -> str:
    """Loopback locally, all interfaces on a platform that routes to us.

    Render requires a web service to bind `0.0.0.0` ("Every Render web service
    must bind to a port on host 0.0.0.0") and kills the deploy after a five
    minute port scan if it does not. Defaulting to `0.0.0.0` everywhere would
    put a development server on every interface of the machine it runs on,
    which is a worse default for the case that runs a hundred times a day.

    `RENDER` is set to "true" on every Render service, which is exactly the
    "am I in a container that routes traffic to me" signal needed here. An
    explicit `HOST` still wins, so nothing that sets it today changes.
    """
    if host := os.environ.get("HOST"):
        return host
    return "0.0.0.0" if os.environ.get("RENDER") else "127.0.0.1"  # noqa: S104


def main() -> None:
    config = uvicorn.Config(
        "app.main:app",
        host=_default_host(),
        # Render's default is 10000 and it is supplied in the environment; the
        # 8000 fallback is for a local run, where nothing sets PORT.
        port=int(os.environ.get("PORT", "8000")),
        log_config=None,  # the app installs its own JSON logging
    )
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        # `asyncio.Runner` rather than `asyncio.run(loop_factory=...)`, which
        # only accepts that argument from 3.12; this keeps the 3.11 floor in
        # pyproject.toml honest.
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(server.serve())
    else:
        server.run()


if __name__ == "__main__":
    main()
