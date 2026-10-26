"""A network write sent from page JS is spelled by its method literal, not by where it sits in the call.

The evaluate guard asks a person before a mutating expression runs; a write that merely puts `method`
after another option, uses PUT/PATCH/DELETE, or goes through `sendBeacon` must be asked about the same
as the one spelled `fetch(url, {method: 'POST'})`. Anything that only reads must pass untouched.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.browser.tools._semantic_risk import SemanticRiskLevel, classify_js_eval_risk


@pytest.mark.parametrize(
    "expression",
    [
        "fetch('/api/orders', {method: 'POST', body: '{}'})",
        'fetch("/api/orders", {method: "POST"})',
        "fetch('/api/orders', {method:'post'})",
        "fetch('/api/orders', {headers: {}, body: JSON.stringify({a: 1}), method: 'POST'})",
        "fetch(getUrl(), {method: 'POST'})",
        "fetch('/api/orders', {method: `POST`})",
        'fetch("/api/orders", {"method": "POST"})',
        "fetch('/api/orders', {'method': 'put'})",
        "fetch('/api/drafts/7', {method: 'PUT', body: '{}'})",
        "fetch('/api/drafts/7', {method: 'PATCH', body: '{}'})",
        "fetch('/api/items/7', {method: 'DELETE'})",
        "(async () => { const r = await fetch('/api/items/7', {method: 'DELETE'}); return r.status })()",
        "navigator.sendBeacon('/api/log', 'x')",
        "var x = new XMLHttpRequest(); x.open('POST', '/a'); x.send()",
    ],
)
def test_js_eval_network_writes_high_risk(expression: str):
    verdict = classify_js_eval_risk(expression)
    assert verdict.level is SemanticRiskLevel.HIGH


@pytest.mark.parametrize(
    "expression",
    [
        "fetch('/api/prices').then(r => r.text())",
        "fetch('/api/prices', {method: 'GET'}).then(r => r.json())",
        "fetch('/x', {method: 'head'})",
        "fetch('/x', {method: 'OPTIONS'})",
        "document.querySelector('[data-method=\"delete\"]').textContent",
        "document.querySelector('form').getAttribute('method')",
        "[...document.querySelectorAll('a')].map(a => a.href)",
        "document.body.innerText.includes('payment method: card')",
    ],
)
def test_js_eval_network_reads_safe(expression: str):
    verdict = classify_js_eval_risk(expression)
    assert verdict.level is SemanticRiskLevel.SAFE
