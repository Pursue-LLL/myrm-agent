"""Benchmark the instrumentation cost of one logical model call.

Times the ``ModelCall`` lifecycle (begin, finish, close) on the calling thread in two setups, each in its
own process because an OpenTelemetry provider can be installed only once per process: ``noop`` (no
provider, which is what runs when no OTLP endpoint is configured) and ``sdk`` (the pipeline
``setup_tracing`` installs: a request-id trace id generator, a batch span processor behind the privacy
guard, plus a metric reader, with in-memory sinks instead of the network). Output is JSON.

[INPUT]
- infra.tracing.gen_ai.model_call::ModelCall (POS: the instrumented unit of one model call)
- infra.tracing.id_generator::ContextTraceIdGenerator (POS: trace id of a root span from the request id)
- infra.tracing.otlp.privacy::PrivacyGuardExporter (POS: export-boundary sanitizer)
- observability.tracing::TracingContext (POS: request id carrier)

[OUTPUT]
- main: CLI entrypoint printing the microseconds one call costs (median, minimum, maximum over the rounds).

[POS]
Instrumentation overhead probe: the figures quoted in ``infra/tracing/TRACE_STORAGE_SYSTEM.md`` come from
it. It reports and does not gate, because a threshold on a wall-clock figure fails on a busy machine.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import time

_SCENARIOS = ("noop", "sdk")
_WARMUP_CALLS = 2_000
_DEFAULT_ROUNDS = 20
_DEFAULT_CALLS_PER_ROUND = 2_000
_MODEL = "gpt-4o-mini"
_PROVIDER = "openai"
_PARAMS: dict[str, object] = {"temperature": 0.2, "max_tokens": 1024}
_MESSAGES: list[dict[str, object]] = [{"role": "user", "content": "Summarise the attached report in three points."}]
_RESPONSE: dict[str, object] = {
    "model": _MODEL,
    "choices": [{"finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1200, "completion_tokens": 180, "prompt_tokens_details": {"cached_tokens": 800}},
}
# The probe must not drop spans: the processor's queue limit is not what is measured.
_QUEUE_SIZE = 1_000_000


def _install_sdk_pipeline() -> None:
    """Install the providers the way ``setup_tracing`` does, with in-memory sinks in place of the OTLP exporters."""
    from opentelemetry import metrics, trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from myrm_agent_harness.infra.tracing.id_generator import ContextTraceIdGenerator
    from myrm_agent_harness.infra.tracing.otlp.privacy import PrivacyGuardExporter
    from myrm_agent_harness.observability.tracing import TracingContext

    TracingContext.set_trace_id(TracingContext.generate_trace_id())
    provider = TracerProvider(id_generator=ContextTraceIdGenerator(TracingContext.get_trace_id))
    provider.add_span_processor(
        BatchSpanProcessor(PrivacyGuardExporter(InMemorySpanExporter()), max_queue_size=_QUEUE_SIZE)
    )
    trace.set_tracer_provider(provider)
    metrics.set_meter_provider(MeterProvider(metric_readers=[InMemoryMetricReader()]))


def _measure(rounds: int, calls_per_round: int) -> list[float]:
    """Mean microseconds per call of every round."""
    from myrm_agent_harness.infra.tracing.gen_ai.model_call import ModelCall

    def lifecycle() -> None:
        call = ModelCall(model=_MODEL, provider=_PROVIDER, stream=False, params=_PARAMS, message_dicts=_MESSAGES)
        call.begin(1)
        call.finish(_RESPONSE, time_to_first_chunk_s=0.4)
        call.close()

    for _ in range(_WARMUP_CALLS):
        lifecycle()
    per_call_us: list[float] = []
    for _ in range(rounds):
        started = time.perf_counter_ns()
        for _ in range(calls_per_round):
            lifecycle()
        per_call_us.append((time.perf_counter_ns() - started) / calls_per_round / 1_000)
    return per_call_us


def _run_scenario(name: str, rounds: int, calls_per_round: int) -> dict[str, object]:
    if name == "sdk":
        _install_sdk_pipeline()
    per_call_us = _measure(rounds, calls_per_round)
    return {
        "scenario": name,
        "median_us": round(statistics.median(per_call_us), 1),
        "min_us": round(min(per_call_us), 1),
        "max_us": round(max(per_call_us), 1),
        "rounds": rounds,
        "calls_per_round": calls_per_round,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=_DEFAULT_ROUNDS)
    parser.add_argument("--calls", type=int, default=_DEFAULT_CALLS_PER_ROUND, help="calls timed per round")
    parser.add_argument("--scenario", choices=_SCENARIOS, help="run one scenario in this process")
    args = parser.parse_args(argv)

    if args.scenario:
        print(json.dumps(_run_scenario(args.scenario, args.rounds, args.calls)))
        return 0

    results: list[object] = []
    for name in _SCENARIOS:
        command = [
            sys.executable,
            __file__,
            "--scenario",
            name,
            "--rounds",
            str(args.rounds),
            "--calls",
            str(args.calls),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=True)
        results.append(json.loads(completed.stdout.strip().splitlines()[-1]))
    report = {"python": platform.python_version(), "platform": platform.platform(), "results": results}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
