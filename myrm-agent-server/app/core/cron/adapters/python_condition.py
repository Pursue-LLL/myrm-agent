"""Sandboxed Python pre-flight condition execution.

Provides an isolated environment to execute a user-provided Python script.
If the script prints `[SKIP]` or outputs `{"action": "skip"}`, the job execution
is gracefully aborted (preventing unnecessary LLM wakeups).
Otherwise, the captured standard output is returned as `injected_context`.

[INPUT]
- toolkits.cron.protocols::PreFlightCondition (POS: Evaluates whether a job should run and returns injected context.)
- toolkits.cron.types::CronJob (POS: In-memory representation of a cron job.)

[OUTPUT]
- SandboxedPythonCondition: Executes Python scripts in a sandboxed subprocess.

[POS]
Sandboxed Python condition execution. Implements PreFlightCondition.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from myrm_agent_harness.toolkits.cron.protocols import PreFlightCondition
from myrm_agent_harness.toolkits.cron.types import CronJob

logger = logging.getLogger(__name__)


class SandboxedPythonCondition(PreFlightCondition):
    """Executes a Python script in an isolated subprocess with a strict timeout.
    
    If the script prints `[SKIP]` or `{"action": "skip"}`, aborts job execution.
    Otherwise, the entire stdout is collected and returned as `injected_context`.
    """

    def __init__(self, timeout_seconds: int = 10) -> None:
        self.timeout_seconds = timeout_seconds

    async def evaluate(self, job: CronJob) -> tuple[bool, str]:
        if not job.pre_condition_script:
            return True, ""
            
        script = job.pre_condition_script.strip()
        if not script:
            return True, ""

        logger.debug("Executing pre-flight condition script for job %s", job.id)
        
        script_path = None
        try:
            # Write script to a temporary file
            with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(script)
                f.flush()
                script_path = Path(f.name)

            # Execute in an isolated subprocess
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), 
                timeout=self.timeout_seconds
            )

            if proc.returncode != 0:
                stderr = stderr_bytes.decode(errors="replace").strip()
                logger.warning(
                    "Pre-flight condition for job %s failed with exit code %d: %s. "
                    "Treating as SKIPPED to prevent cascading failures.",
                    job.id,
                    proc.returncode,
                    stderr
                )
                return False, f"Probe Failed: {stderr}"

            stdout = stdout_bytes.decode(errors="replace").strip()

            # Parse signal (either simple string or JSON)
            lines = stdout.splitlines()
            if any(line.strip() == "[SKIP]" for line in lines):
                return False, ""
                
            try:
                if lines:
                    last_line = lines[-1].strip()
                    if last_line.startswith("{") and last_line.endswith("}"):
                        data = json.loads(last_line)
                        if data.get("action") == "skip":
                            return False, ""
            except json.JSONDecodeError:
                pass

            return True, stdout
                
        except asyncio.TimeoutError:
            logger.warning(
                "Pre-flight condition for job %s timed out after %ds. Skipping.", 
                job.id, 
                self.timeout_seconds
            )
            return False, f"Probe Timeout ({self.timeout_seconds}s)"
        except Exception as e:
            logger.error("Error executing pre-flight condition for job %s: %s", job.id, e)
            return False, f"Probe Error: {e}"
        finally:
            if script_path and script_path.exists():
                script_path.unlink(missing_ok=True)
