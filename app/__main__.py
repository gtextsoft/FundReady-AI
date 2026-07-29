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


def main() -> None:
    config = uvicorn.Config(
        "app.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
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
