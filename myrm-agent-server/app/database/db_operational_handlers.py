"""FastAPI handlers for database operational errors (SQLite busy/lock, PostgreSQL transient)."""

from __future__ import annotations

import logging
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError

from app.database.postgres_transient import (
    is_postgres_transient_operational,
    postgres_transient_retry_after_seconds,
)
from app.database.sqlite_storage_busy import is_sqlite_storage_busy, sqlite_busy_retry_after_seconds
from app.database.standard_responses import BusinessCode, create_error_response

logger = logging.getLogger(__name__)

_SQLITE_BUSY_MESSAGE = "Database is temporarily busy. Please retry shortly."
_PG_TRANSIENT_MESSAGE = "Database temporarily unavailable. Please retry shortly."


def _sqlite_busy_json_response() -> JSONResponse:
    sec = sqlite_busy_retry_after_seconds()
    return JSONResponse(
        status_code=503,
        content=create_error_response(
            code=BusinessCode.DB_STORAGE_BUSY,
            message=_SQLITE_BUSY_MESSAGE,
        ).model_dump(mode="json"),
        headers={"Retry-After": str(sec)},
    )


def _postgres_transient_json_response() -> JSONResponse:
    sec = postgres_transient_retry_after_seconds()
    return JSONResponse(
        status_code=503,
        content=create_error_response(
            code=BusinessCode.DB_TRANSIENT_RETRY,
            message=_PG_TRANSIENT_MESSAGE,
        ).model_dump(mode="json"),
        headers={"Retry-After": str(sec)},
    )


def register_database_operational_handlers(app: FastAPI) -> None:
    """Register ``sqlite3`` and SQLAlchemy ``OperationalError`` handlers."""

    @app.exception_handler(sqlite3.OperationalError)
    async def _sqlite3_operational_handler(_request: Request, exc: sqlite3.OperationalError) -> JSONResponse:
        if is_sqlite_storage_busy(exc):
            logger.warning("SQLite busy or locked (raw): %s", exc)
            return _sqlite_busy_json_response()
        logger.error("SQLite operational error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=create_error_response(
                code=BusinessCode.DB_QUERY_ERROR,
                message="Database operation failed",
            ).model_dump(mode="json"),
        )

    @app.exception_handler(SQLAlchemyOperationalError)
    async def _sqlalchemy_operational_handler(
        _request: Request,
        exc: SQLAlchemyOperationalError,
    ) -> JSONResponse:
        if is_sqlite_storage_busy(exc):
            logger.warning("SQLite busy or locked (SQLAlchemy): %s", exc)
            return _sqlite_busy_json_response()
        if is_postgres_transient_operational(exc):
            logger.warning("PostgreSQL transient operational error: %s", exc)
            return _postgres_transient_json_response()
        logger.error("Database operational error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=create_error_response(
                code=BusinessCode.DB_QUERY_ERROR,
                message="Database operation failed",
            ).model_dump(mode="json"),
        )


__all__ = ["register_database_operational_handlers"]
