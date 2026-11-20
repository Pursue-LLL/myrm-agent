"""Backend selection: the ComputerBackend native to the OS this process runs on.

[INPUT]
- backends.protocols::ComputerBackend (POS: platform I/O protocol)
- code_execution.platform::detect_platform (POS: host OS detection shared with the code executors)

[OUTPUT]
- create_native_backend: the platform's own backend, never wrapped

[POS]
The one place that maps the host OS to its ComputerBackend. A session that reads the foreground application, the
accessibility tree and the sensitive-application guards through its backend (DesktopSession) holds this backend
itself: those reads route on the backend's own class, so a proxy in front of it would read as an unsupported platform.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.computer_use.backends.protocols import ComputerBackend


def create_native_backend() -> ComputerBackend:
    """Create the backend of the current OS: macOS, Windows, or Linux (X11) for any other."""
    from myrm_agent_harness.toolkits.code_execution.platform import detect_platform

    os_type = detect_platform().os_type
    if os_type == "macos":
        from myrm_agent_harness.toolkits.computer_use.backends.macos.backend import MacOSBackend

        return MacOSBackend()
    if os_type == "windows":
        from myrm_agent_harness.toolkits.computer_use.backends.windows.backend import WindowsBackend

        return WindowsBackend()
    from myrm_agent_harness.toolkits.computer_use.backends.linux.backend import LinuxBackend

    return LinuxBackend()
