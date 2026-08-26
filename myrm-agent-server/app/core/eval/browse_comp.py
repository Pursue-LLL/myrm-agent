"""BrowseComp adapter — OpenAI's web-research benchmark for the Eval Lab.

[INPUT]
- httpx: HTTP client for the official encrypted CSV download
- myrm_agent_harness.eval::BenchmarkSpec, register_benchmark
- myrm_agent_harness.eval::MultiTurnEvalCase, EvalCase, SemanticAssertion

[OUTPUT]
- list_browse_comp_source(): catalog entry with local availability
- ensure_browse_comp_source(): download the official CSV (retry + abort)
- build_browse_comp_cases(): decrypt rows into runnable MultiTurnEvalCases

[POS]
Business-layer adapter that turns the public BrowseComp test set (OpenAI's
encrypted CSV at ``openaipublic.blob.core.windows.net``) into Eval Lab
runnable cases. All BrowseComp-specific knowledge — the official URL, the
canary XOR decryption scheme, the LLM-judge grading prompt — stays in this
adapter, keeping the harness eval framework benchmark-agnostic.

Grading is an LLM-as-a-Judge via the harness ``SemanticAssertion``:
BrowseComp answers are open-form research questions without a deterministic
verifier, so the official simple-evals workflow uses an LLM judge. The
question + reference answer are packed into the assertion criteria and the
judge prompt mirrors the official BrowseComp grading rubric (semantic
agreement, bracket-group interchangeability, contradiction/omission rules).
The benchmark declares ``required_tools=("web_search",)`` so
``benchmark_mode`` injects web search while keeping the rest of the baseline
user-config-free.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from myrm_agent_harness.eval import (
    BenchmarkSpec,
    EvalCase,
    MultiTurnEvalCase,
    SemanticAssertion,
    register_benchmark,
)

logger = logging.getLogger(__name__)

BROWSECOMP_ROOT = Path(".myrm/browsecomp")
BROWSECOMP_CSV = BROWSECOMP_ROOT / "browse_comp_test_set.csv"

BROWSECOMP_URL = (
    "https://openaipublic.blob.core.windows.net/simple-evals/browse_comp_test_set.csv"
)
DOWNLOAD_TIMEOUT_S = 120
CHUNK_SIZE = 1024 * 256
DOWNLOAD_MAX_RETRIES = 2
DOWNLOAD_BACKOFF_BASE_S = 2

# Official test-set size (1266 research questions).
BROWSECOMP_TASK_COUNT = 1266

BROWSECOMP_JUDGE_PROMPT = """You are grading whether a model's answer correctly answers a research question, based only on the given question and reference answer.

{criteria}

Model Prediction: {output}

Judge strictly by semantic agreement with the reference answer. The prediction is CORRECT when it fully includes the important information in the reference answer and contains no contradiction. Language, capitalization, punctuation, grammar, order, equivalent translations, and harmless uncertainty do not matter. Alternative descriptions grouped together in one pair of brackets are interchangeable; answers to distinct aspects in separate brackets must all be present.

The prediction is INCORRECT when it omits a required aspect, adds a contradictory fact, merely repeats the question, provides no direct answer, or lists multiple incompatible candidate answers. For numerical answers, ordinary rounding that preserves the value is acceptable. If the reference answer contains more detail than the question asks for, only the requested part is required.

Reply EXACTLY with 'PASS' if the prediction is correct, or 'FAIL: <reason>' if it is incorrect."""


BROWSECOMP_SPEC = BenchmarkSpec(
    id="browsecomp",
    display_name="BrowseComp",
    description=(
        "OpenAI's web-research benchmark — answer difficult, multi-step research questions using the web."
    ),
    download_url=BROWSECOMP_URL,
    task_count=BROWSECOMP_TASK_COUNT,
    approx_size_mb=1,
    scoring="llm_judge",
    required_tools=("web_search",),
    supports_memory_ab=True,
    canary_protected=True,
    # Web research is multi-hop and exploratory: BrowseComp-Plus reports an
    # average of ~20 search calls on failed runs and >20 on strong models
    # (GPT-5/o3), with search+verify pipelines reaching ~75 tool calls on hard
    # questions. Pinning generous budgets (100 tool calls / 150 iterations)
    # keeps a scored run measuring the model instead of the engine limit, and
    # stays comparable to the official reference agent's unconstrained loop.
    max_tool_calls=100,
    max_iterations=150,
    # Official scoring reference is OpenAI's simple-evals harness; our run
    # grades with the identical BrowseComp judge rubric above.
    harness="official",
    judge_prompt=BROWSECOMP_JUDGE_PROMPT,
)

# Registers the spec so /eval/benchmarks lists BrowseComp alongside WBBench.
register_benchmark(BROWSECOMP_SPEC)


class DownloadAbortedError(RuntimeError):
    """Raised when the user cancels an in-progress BrowseComp download."""


def _decrypt(ciphertext: str, password: str) -> str:
    """Decrypt a BrowseComp field using the official canary XOR scheme.

    The official simple-evals release encrypts the ``problem`` and ``answer``
    columns with a per-row canary: base64-decode the ciphertext, expand
    SHA256(canary) to the ciphertext length, and XOR byte-wise.
    """
    encrypted = base64.b64decode(ciphertext)
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    key = (digest * (len(encrypted) // len(digest) + 1))[: len(encrypted)]
    return bytes(a ^ b for a, b in zip(encrypted, key, strict=True)).decode("utf-8")


def _verify_sha256(path: Path, expected: str) -> bool:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest() == expected


@dataclass(frozen=True, slots=True)
class _CatalogEntry:
    """Local availability snapshot for the frontend catalog."""

    is_downloaded: bool
    local_size_bytes: int


def list_browse_comp_source() -> dict[str, object]:
    """Return the BrowseComp catalog entry with local availability flags."""
    return {
        **BROWSECOMP_SPEC.to_dict(),
        "is_downloaded": BROWSECOMP_CSV.is_file(),
        "local_size_bytes": (
            BROWSECOMP_CSV.stat().st_size if BROWSECOMP_CSV.is_file() else 0
        ),
    }


async def _fetch_expected_sha256() -> str | None:
    """Best-effort fetch of the official SHA256 manifest for the CSV.

    The simple-evals release publishes ``browse_comp_test_set.sha256`` next to
    the CSV; when unavailable the download still proceeds (soft verification).
    """
    sha_url = f"{BROWSECOMP_URL}.sha256"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(sha_url)
            resp.raise_for_status()
            return resp.text.strip().split()[0]
    except Exception as exc:  # noqa: BLE001 - network failures degrade gracefully
        logger.warning("Failed to fetch BrowseComp SHA256 manifest: %s", exc)
    return None


async def ensure_browse_comp_source(
    *,
    max_retries: int = DOWNLOAD_MAX_RETRIES,
    progress_callback: Callable[[int, int], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> Path:
    """Download (if needed) and verify the official BrowseComp CSV.

    Returns the CSV path. When the file already exists locally this is a
    no-op (offline-friendly). ``progress_callback(downloaded, total)`` streams
    download progress; ``should_abort()`` cancels the stream and raises
    ``DownloadAbortedError``.
    """
    if BROWSECOMP_CSV.is_file():
        logger.info("BrowseComp source already installed: %s", BROWSECOMP_CSV)
        return BROWSECOMP_CSV

    BROWSECOMP_ROOT.mkdir(parents=True, exist_ok=True)
    expected = await _fetch_expected_sha256()
    if should_abort and should_abort():
        raise DownloadAbortedError("BrowseComp download aborted")

    tmp = BROWSECOMP_CSV.with_name(f"{BROWSECOMP_CSV.name}.part")
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(DOWNLOAD_TIMEOUT_S),
                follow_redirects=True,
            ) as client:
                async with client.stream("GET", BROWSECOMP_URL) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", "0") or 0)
                    downloaded = 0
                    with tmp.open("wb") as f:
                        async for chunk in resp.aiter_bytes(CHUNK_SIZE):
                            if should_abort and should_abort():
                                raise DownloadAbortedError(
                                    "BrowseComp download aborted"
                                )
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(downloaded, total)
            if expected is None or _verify_sha256(tmp, expected):
                tmp.replace(BROWSECOMP_CSV)
                return BROWSECOMP_CSV
            last_error = ValueError("Checksum mismatch for BrowseComp CSV")
            logger.warning(
                "Checksum mismatch for BrowseComp CSV (attempt %d/%d)",
                attempt + 1,
                max_retries + 1,
            )
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            logger.warning(
                "Download attempt %d/%d failed for BrowseComp: %s",
                attempt + 1,
                max_retries + 1,
                exc,
            )
        finally:
            tmp.unlink(missing_ok=True)
        if attempt < max_retries:
            import asyncio

            await asyncio.sleep(DOWNLOAD_BACKOFF_BASE_S * (2**attempt))
    raise ValueError(
        f"Failed to download BrowseComp CSV after {max_retries + 1} attempts: {last_error}"
    )


def _load_tasks() -> list[dict[str, str]]:
    """Read and decrypt all BrowseComp rows into plain question/answer tasks.

    Rows that fail to decrypt (corrupt base64 or undecodable plaintext) are
    skipped so a single bad row cannot abort the whole benchmark build.
    """
    tasks: list[dict[str, str]] = []
    with BROWSECOMP_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            canary = str(row.get("canary") or "")
            problem = str(row.get("problem") or "")
            answer = str(row.get("answer") or "")
            if not problem or not answer or not canary:
                continue
            try:
                question = _decrypt(problem, canary)
                reference = _decrypt(answer, canary)
            except (ValueError, UnicodeDecodeError):
                logger.warning("Skipping BrowseComp row with undecryptable payload")
                continue
            tasks.append(
                {
                    "question": question,
                    "answer": reference,
                    "problem_topic": str(row.get("problem_topic") or ""),
                }
            )
    return tasks


def build_browse_comp_cases(
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> tuple[list[MultiTurnEvalCase], dict[str, str]]:
    """Build runnable cases for the BrowseComp test set.

    Returns ``(cases, {})`` — BrowseComp is web research with no seeded
    workspace, so the seed map is empty (the executor starts from an empty
    sandbox). Downloads the official CSV on first run and forwards progress /
    abort callbacks to the download stream.
    """
    import asyncio

    asyncio.run(
        ensure_browse_comp_source(
            progress_callback=progress_callback,
            should_abort=should_abort,
        )
    )

    cases: list[MultiTurnEvalCase] = []
    for index, task in enumerate(_load_tasks(), start=1):
        criteria = (
            f"Question:\n{task['question']}\n\nReference Answer:\n{task['answer']}"
        )
        semantic = SemanticAssertion(
            type="llm_judge",
            expected=criteria,
            threshold=1.0,
            judge_prompt=BROWSECOMP_JUDGE_PROMPT,
        )
        case = EvalCase(
            message=task["question"],
            semantic_assertions=[semantic],
            metadata={"browse_comp_task_id": str(index)},
        )
        if task["problem_topic"]:
            case.metadata["problem_topic"] = task["problem_topic"]
        cases.append(
            MultiTurnEvalCase(
                turns=[case],
                metadata={"browse_comp_source": "browsecomp"},
            )
        )

    if not cases:
        raise ValueError("No runnable BrowseComp tasks found")

    logger.info("Built %d BrowseComp cases", len(cases))
    return cases, {}
