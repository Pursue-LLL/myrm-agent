"""SFTP Explorer and File Transfer Bridge for Host Assets.

[INPUT]
- .models::SFTPFileEntry, SFTPTransferRequest, SFTPTransferResponse, HostAsset
- .vault::HostAssetVault

[OUTPUT]
- SFTPBridge: Explores remote directories and transfers files with progress tracking

[POS]
Domain service in app/services/host_assets/sftp_bridge.py.
"""

from __future__ import annotations

import time
from typing import Callable
from app.services.host_assets.models import (
    SFTPFileEntry,
    SFTPTransferRequest,
    SFTPTransferResponse,
)
from app.services.host_assets.vault import HostAssetVault


class SFTPBridge:
    """Provides remote directory listing and bidirectional file transfer via SFTP."""

    def __init__(
        self,
        vault: HostAssetVault,
        explorer_func: Callable[[dict[str, str], str], list[SFTPFileEntry]] | None = None,
        transfer_func: Callable[[dict[str, str], str, str, str], tuple[bool, int, str | None]] | None = None,
    ) -> None:
        self._vault = vault
        self._explorer_func = explorer_func or self._mock_list_dir
        self._transfer_func = transfer_func or self._mock_transfer

    def list_remote_directory(self, host_id_or_alias: str, remote_path: str = ".") -> list[SFTPFileEntry]:
        """List files and folders in the target remote path."""
        asset = self._vault.get_asset(host_id_or_alias)
        if not asset:
            raise ValueError(f"Host asset '{host_id_or_alias}' not found in vault.")

        secrets = self._vault.get_decrypted_secrets(asset.id)
        connection_params = {
            "hostname": asset.hostname,
            "port": str(asset.port),
            "username": asset.username,
            "auth_type": asset.auth_type.value,
            "password": secrets.get("password", ""),
            "private_key": secrets.get("private_key", ""),
        }

        return self._explorer_func(connection_params, remote_path)

    def transfer_file(self, request: SFTPTransferRequest) -> SFTPTransferResponse:
        """Upload or download a file between local and remote server."""
        start_time = time.time()
        asset = self._vault.get_asset(request.host_id_or_alias)
        if not asset:
            return SFTPTransferResponse(
                success=False,
                bytes_transferred=0,
                remote_path=request.remote_path,
                local_path=request.local_path,
                elapsed_time_ms=0,
                error_message=f"Host asset '{request.host_id_or_alias}' not found in vault.",
            )

        secrets = self._vault.get_decrypted_secrets(asset.id)
        connection_params = {
            "hostname": asset.hostname,
            "port": str(asset.port),
            "username": asset.username,
            "auth_type": asset.auth_type.value,
            "password": secrets.get("password", ""),
            "private_key": secrets.get("private_key", ""),
        }

        success, transferred, err = self._transfer_func(
            connection_params,
            request.direction,
            request.local_path,
            request.remote_path,
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        return SFTPTransferResponse(
            success=success,
            bytes_transferred=transferred,
            remote_path=request.remote_path,
            local_path=request.local_path,
            elapsed_time_ms=elapsed_ms,
            error_message=err,
        )

    @staticmethod
    def _mock_list_dir(params: dict[str, str], path: str) -> list[SFTPFileEntry]:
        return [
            SFTPFileEntry(
                filename="logs",
                path=f"{path}/logs",
                is_dir=True,
                size_bytes=4096,
                modified_time=time.time(),
                permissions="drwxr-xr-x",
            ),
            SFTPFileEntry(
                filename="config.yaml",
                path=f"{path}/config.yaml",
                is_dir=False,
                size_bytes=1024,
                modified_time=time.time(),
                permissions="-rw-r--r--",
            ),
        ]

    @staticmethod
    def _mock_transfer(
        params: dict[str, str],
        direction: str,
        local_path: str,
        remote_path: str,
    ) -> tuple[bool, int, str | None]:
        return True, 1024 * 1024, None
