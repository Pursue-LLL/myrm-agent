"""[INPUT]
- app.core.cron.blueprints.core.types::_CAP_RESEARCH / _TOOLS_RESEARCH / BlueprintFailureAlertDefaults / BlueprintJobDefaults / BlueprintMonitorDefaults / BlueprintSlot / CronBlueprint (POS: 蓝图目录（blueprints/catalog/）与注册表（blueprints/core/registry.py）共用的类型和纯函数；不包含任何具体蓝图。)

[OUTPUT]
- （仅导出常量/类型）

[POS]
Cron 蓝图目录的一部分；由 app/core/cron/blueprints/ 的注册表按声明顺序拼成内置清单。
"""

from app.core.cron.blueprints.core.types import (
    _CAP_RESEARCH,
    _TOOLS_RESEARCH,
    BlueprintFailureAlertDefaults,
    BlueprintJobDefaults,
    BlueprintMonitorDefaults,
    BlueprintSlot,
    CronBlueprint,
)

BLUEPRINTS: tuple[CronBlueprint, ...] = (
    CronBlueprint(
        id="financial_monitor_simple",
        icon="Activity",
        title={"en": "Financial Monitor (Simple)", "zh": "金融监控（简单版）"},
        description={
            "en": "Zero-LLM threshold alert using a Python pre-flight probe",
            "zh": "使用 Python 预检脚本的零 LLM 阈值告警",
        },
        prompt_template={
            "en": (
                "This job runs in router mode. Use the pre-flight probe output as the final message. "
                "If the probe prints [SKIP], stay silent."
            ),
            "zh": ("该任务运行在 router 模式。将预检脚本输出作为最终消息。如果预检脚本输出 [SKIP]，保持静默。"),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="08:00"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="weekdays",
                options=("everyday", "weekdays", "weekends"),
            ),
            BlueprintSlot(name="asset", type="text", label="asset", default="bitcoin"),
            BlueprintSlot(
                name="quote_currency",
                type="enum",
                label="quote_currency",
                default="usd",
                options=("usd", "usdt", "eur", "cny"),
            ),
            BlueprintSlot(name="lower_bound", type="text", label="lower_bound", default="58000"),
            BlueprintSlot(name="upper_bound", type="text", label="upper_bound", default="68000"),
            BlueprintSlot(
                name="source",
                type="enum",
                label="source",
                default="coingecko",
                options=("coingecko", "binance"),
            ),
        ),
        category="business",
        tags=("finance", "monitoring", "threshold", "low-cost"),
        sort_order=10,
        job_defaults=BlueprintJobDefaults(
            job_type="router",
            session_target="isolated",
            deduplicate=True,
            skip_if_active=True,
            timeout_seconds=90,
            failure_alert=BlueprintFailureAlertDefaults(enabled=True, after=2, cooldown_seconds=900),
            pre_condition_script_template={
                "en": (
                    "import json\n"
                    "import urllib.request\n"
                    "from datetime import datetime, timezone\n"
                    "\n"
                    'asset_id = "{asset}".strip().lower()\n'
                    'vs_currency = "{quote_currency}".strip().lower()\n'
                    'lower_bound = float("{lower_bound}")\n'
                    'upper_bound = float("{upper_bound}")\n'
                    'source = "{source}".strip().lower()\n'
                    "\n"
                    "def _fetch_from_binance() -> float:\n"
                    "    symbol = asset_id.upper() + vs_currency.upper()\n"
                    '    url = "https://api.binance.com/api/v3/ticker/price?symbol=" + symbol\n'
                    "    with urllib.request.urlopen(url, timeout=12) as resp:\n"
                    '        data = json.loads(resp.read().decode("utf-8"))\n'
                    '    return float(data["price"])\n'
                    "\n"
                    "def _fetch_from_coingecko() -> float:\n"
                    '    url = "https://api.coingecko.com/api/v3/simple/price?ids=" + asset_id + "&vs_currencies=" + vs_currency\n'
                    "    with urllib.request.urlopen(url, timeout=12) as resp:\n"
                    '        data = json.loads(resp.read().decode("utf-8"))\n'
                    "    if asset_id not in data or vs_currency not in data[asset_id]:\n"
                    '        raise RuntimeError("No quote returned for " + asset_id + "/" + vs_currency)\n'
                    "    return float(data[asset_id][vs_currency])\n"
                    "\n"
                    "def _fetch_price() -> tuple[float, str]:\n"
                    "    providers = [source]\n"
                    '    if source == "binance":\n'
                    '        providers.append("coingecko")\n'
                    "    else:\n"
                    '        providers.append("binance")\n'
                    "    errors = []\n"
                    "    for provider in providers:\n"
                    "        try:\n"
                    '            if provider == "binance":\n'
                    "                return _fetch_from_binance(), provider\n"
                    "            return _fetch_from_coingecko(), provider\n"
                    "        except Exception as exc:\n"
                    '            errors.append(provider + ":" + str(exc))\n'
                    '    raise RuntimeError("all_sources_failed: " + " | ".join(errors))\n'
                    "\n"
                    "price, resolved_source = _fetch_price()\n"
                    "timestamp = datetime.now(timezone.utc).isoformat()\n"
                    "\n"
                    "if price < lower_bound or price > upper_bound:\n"
                    '    direction = "below" if price < lower_bound else "above"\n'
                    "    print(\n"
                    '        "[ALERT] "\n'
                    "        + asset_id.upper()\n"
                    '        + "/"\n'
                    "        + vs_currency.upper()\n"
                    '        + " is "\n'
                    "        + direction\n"
                    '        + " threshold (price="\n'
                    '        + ("%.4f" % price)\n'
                    '        + ", range="\n'
                    '        + ("%.4f" % lower_bound)\n'
                    '        + "-"\n'
                    '        + ("%.4f" % upper_bound)\n'
                    '        + ", source="\n'
                    "        + resolved_source\n"
                    '        + ", ts="\n'
                    "        + timestamp\n"
                    '        + ")"\n'
                    "    )\n"
                    "else:\n"
                    '    print("[SKIP]")\n'
                ),
                "zh": (
                    "import json\n"
                    "import urllib.request\n"
                    "from datetime import datetime, timezone\n"
                    "\n"
                    'asset_id = "{asset}".strip().lower()\n'
                    'vs_currency = "{quote_currency}".strip().lower()\n'
                    'lower_bound = float("{lower_bound}")\n'
                    'upper_bound = float("{upper_bound}")\n'
                    'source = "{source}".strip().lower()\n'
                    "\n"
                    "def _fetch_from_binance() -> float:\n"
                    "    symbol = asset_id.upper() + vs_currency.upper()\n"
                    '    url = "https://api.binance.com/api/v3/ticker/price?symbol=" + symbol\n'
                    "    with urllib.request.urlopen(url, timeout=12) as resp:\n"
                    '        data = json.loads(resp.read().decode("utf-8"))\n'
                    '    return float(data["price"])\n'
                    "\n"
                    "def _fetch_from_coingecko() -> float:\n"
                    '    url = "https://api.coingecko.com/api/v3/simple/price?ids=" + asset_id + "&vs_currencies=" + vs_currency\n'
                    "    with urllib.request.urlopen(url, timeout=12) as resp:\n"
                    '        data = json.loads(resp.read().decode("utf-8"))\n'
                    "    if asset_id not in data or vs_currency not in data[asset_id]:\n"
                    '        raise RuntimeError("No quote returned for " + asset_id + "/" + vs_currency)\n'
                    "    return float(data[asset_id][vs_currency])\n"
                    "\n"
                    "def _fetch_price() -> tuple[float, str]:\n"
                    "    providers = [source]\n"
                    '    if source == "binance":\n'
                    '        providers.append("coingecko")\n'
                    "    else:\n"
                    '        providers.append("binance")\n'
                    "    errors = []\n"
                    "    for provider in providers:\n"
                    "        try:\n"
                    '            if provider == "binance":\n'
                    "                return _fetch_from_binance(), provider\n"
                    "            return _fetch_from_coingecko(), provider\n"
                    "        except Exception as exc:\n"
                    '            errors.append(provider + ":" + str(exc))\n'
                    '    raise RuntimeError("all_sources_failed: " + " | ".join(errors))\n'
                    "\n"
                    "price, resolved_source = _fetch_price()\n"
                    "timestamp = datetime.now(timezone.utc).isoformat()\n"
                    "\n"
                    "if price < lower_bound or price > upper_bound:\n"
                    '    direction = "below" if price < lower_bound else "above"\n'
                    "    print(\n"
                    '        "[ALERT] "\n'
                    "        + asset_id.upper()\n"
                    '        + "/"\n'
                    "        + vs_currency.upper()\n"
                    '        + " is "\n'
                    "        + direction\n"
                    '        + " threshold (price="\n'
                    '        + ("%.4f" % price)\n'
                    '        + ", range="\n'
                    '        + ("%.4f" % lower_bound)\n'
                    '        + "-"\n'
                    '        + ("%.4f" % upper_bound)\n'
                    '        + ", source="\n'
                    "        + resolved_source\n"
                    '        + ", ts="\n'
                    "        + timestamp\n"
                    '        + ")"\n'
                    "    )\n"
                    "else:\n"
                    '    print("[SKIP]")\n'
                ),
            },
        ),
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="financial_monitor_advanced",
        icon="Eye",
        title={"en": "Financial Monitor (Advanced)", "zh": "金融监控（高级版）"},
        description={
            "en": "Multi-signal financial watch with dedupe, monitor baseline, and failure alerts",
            "zh": "带去重、增量监控与失败告警的多信号金融监控",
        },
        prompt_template={
            "en": (
                "Monitor these assets continuously: {watchlist}. "
                "Evaluate each run with five lenses: price action, derivatives/funding, sentiment (X + news), "
                "macro catalysts, and on-chain flow proxies. "
                "Alert only when at least two independent risk signals align with: {signal_rules}. "
                "Portfolio context: {portfolio_context}. "
                "If there is no actionable change, reply with exactly [SILENT]. "
                "If alerting, return ONLY a minified JSON array sorted by asset symbol. "
                "Each item must contain keys: asset, trigger_reason, confidence, invalidation_level, follow_up_checks. "
                "Do not include timestamps or any prose outside JSON."
            ),
            "zh": (
                "持续监控以下资产：{watchlist}。"
                "每次运行按五个维度评估：价格行为、衍生品/资金费率、情绪（X+新闻）、宏观催化、链上资金流。"
                "仅当至少两个独立风险信号与以下规则同时成立时告警：{signal_rules}。"
                "组合上下文：{portfolio_context}。"
                "若无可执行变化，必须仅回复 [SILENT]。"
                "若触发告警，只输出按资产符号排序的最小化 JSON 数组。"
                "每个元素仅包含键：asset、trigger_reason、confidence、invalidation_level、follow_up_checks。"
                "禁止输出时间戳和 JSON 之外的说明文字。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="09:00"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="weekdays",
                options=("everyday", "weekdays", "weekends"),
            ),
            BlueprintSlot(name="watchlist", type="text", label="watchlist", default="BTC,ETH,SOL"),
            BlueprintSlot(
                name="signal_rules",
                type="text",
                label="signal_rules",
                default="price breakdown + funding flip + sentiment deterioration",
            ),
            BlueprintSlot(
                name="portfolio_context",
                type="text",
                label="portfolio_context",
                default="",
                optional=True,
            ),
        ),
        category="business",
        tags=("finance", "monitoring", "multi-signal", "advanced"),
        sort_order=11,
        default_required_capabilities=_CAP_RESEARCH,
        default_tools_allowed=_TOOLS_RESEARCH,
        job_defaults=BlueprintJobDefaults(
            job_type="agent",
            session_target="daily",
            deduplicate=True,
            skip_if_active=True,
            timeout_seconds=240,
            monitor_config=BlueprintMonitorDefaults(monitor_type="hash", ttl_days=14, enabled=True),
            failure_alert=BlueprintFailureAlertDefaults(enabled=True, after=2, cooldown_seconds=900),
        ),
        _schedule_builder="time_weekdays",
    ),
)
