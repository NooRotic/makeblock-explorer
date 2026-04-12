"""FastAPI application factory and server entry point."""

from __future__ import annotations

import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from makeblock_explorer.device.registry import DeviceRegistry
from makeblock_explorer.api.routes import devices, commands, stream

logger = logging.getLogger(__name__)


def create_app(registry: DeviceRegistry | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        registry: Optional DeviceRegistry to inject. A new one is created
                  automatically when *None* is passed (production default).

    Returns:
        Configured FastAPI application instance.
    """
    if registry is None:
        registry = DeviceRegistry()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: nothing special needed
        yield
        # Shutdown: cleanly disconnect all devices
        logger.info("Shutting down — disconnecting all devices")
        try:
            await registry.disconnect_all()
        except Exception:
            logger.exception("Error during disconnect_all on shutdown")

    app = FastAPI(
        title="MakeBlock Explorer API",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3333"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    devices.init_router(registry)

    app.include_router(devices.router)
    app.include_router(commands.router)
    app.include_router(stream.router)

    return app


def run() -> None:
    """Entry point for the ``mbx-server`` console script."""
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8333)
