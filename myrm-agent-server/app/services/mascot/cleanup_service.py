"""Mascot temporary plots cache cleanup service.

Ensures that the sandbox's temporary plotted WebP files do not exceed
storage capacity. Implements a standard time-based LRU cleanup algorithm.
"""

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Max lifetime for temporary matplotlib plots (24 hours)
MAX_PLOT_LIFETIME_SECONDS = 24 * 3600


class MascotLRUCacheCleanupService:
    """Service to automatically prune expired plotted WebP files in sandbox."""

    @staticmethod
    def run_cleanup(workspace_dir: str | Path) -> int:
        """Scan .myrm_plots in the workspace and prune files older than 24 hours.

        Args:
            workspace_dir: The user's active workspace directory path.

        Returns:
            The number of successfully cleaned-up plot files.
        """
        plots_dir = Path(workspace_dir) / ".myrm_plots"
        if not plots_dir.exists() or not plots_dir.is_dir():
            return 0

        now = time.time()
        removed_count = 0

        try:
            for entry in plots_dir.iterdir():
                if entry.is_file() and entry.suffix.lower() == ".webp":
                    # Check age
                    stat = entry.stat()
                    file_age = now - stat.st_mtime
                    if file_age > MAX_PLOT_LIFETIME_SECONDS:
                        try:
                            entry.unlink(missing_ok=True)
                            removed_count += 1
                        except OSError as e:
                            logger.error(f"Failed to delete expired plot file {entry}: {e}")

            if removed_count > 0:
                logger.info(f"MascotLRUCacheCleanupService: Cleaned up {removed_count} expired plot files.")
        except Exception as e:
            logger.error(f"Error during mascot plot cache cleanup: {e}", exc_info=True)

        return removed_count
