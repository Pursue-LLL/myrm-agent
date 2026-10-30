"""Pins what the extractors write into the index to ``INDEX_FORMAT_VERSION``.

A source file whose fingerprint is unchanged is never parsed again, so an extractor change (or a grammar upgrade) that
alters its output without a version bump leaves stale rows in every index that already exists. This test fails on any
such change: when it does, increase ``INDEX_FORMAT_VERSION`` in ``models.py`` and set ``EXPECTED`` to the new pair.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from app.services.code_graph.ast_extractor import PythonAstExtractor
from app.services.code_graph.js_ts_extractor import JsTsTreeSitterExtractor
from app.services.code_graph.models import INDEX_FORMAT_VERSION

EXPECTED = (1, "86813c131c4eb026cfea1f6d830f390db5823ec1928ac48aeceacafb11c631c4")

_PANEL_TSX = """import { useCallback, useEffect, useState } from "react";

type PanelProps = { id: string; onClose?: () => void };

export default function Panel({ id, onClose }: PanelProps) {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    loadRows(id).then(setRows);
  }, [id]);

  const handleClose = useCallback(async () => {
    await api.post<void>(`/panels/${id}/close`, { force: true });
    onClose?.();
  }, [id, onClose]);

  const total = (items: Row[]): number => items.reduce((sum, row) => sum + row.size, 0);

  return (
    <section onClick={() => track("panel")}>
      <button onClick={handleClose}>{label(total(rows))}</button>
    </section>
  );
}
"""

_API_TS = """@Injectable()
export class ApiClient<T> extends BaseClient implements Disposable {
  @Input(flag()) timeout = defaultTimeout();
  static #count = 0;

  constructor(private readonly http: Http) {
    super(http);
  }

  get size() { return this.cache.size(); }

  async load(key: string): Promise<T | undefined> {
    const hit = this.cache?.get(key)!;
    return hit ?? (await this.http.get<T>(`/items/${key}`));
  }

  load(key: number): void;
  dispose = () => { this.http.close(); };
}

export class Store extends ns.Base {}
export const Alias = class extends ApiClient<string> {};
export function build<T>(options: Options<T>) { return new ApiClient<T>(make(options)); }
"""

_HELPERS_JS = """function debounce(fn, wait) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), wait);
  };
}
const merge = (a, b) => Object.assign({}, a, b);
module.exports = { debounce, merge, local: () => debounce(noop, 10) };
"""

_VIEW_JSX = """export const View = ({ items }) => (
  <ul>{items.map((item) => <li key={item.id}>{format(item)}</li>)}</ul>
);
"""

_PARTIAL_TS = """export function before() { ok(); }
const broken = ;
if (a {
export function after() { done(); }
"""

_USER_PY = """class BaseService:
    def execute(self):
        pass


class UserService(BaseService):
    def get_user(self, user_id: str):
        return self.verify(user_id)

    def verify(self, uid):
        return True


def standalone_helper():
    from services import audit
    s = UserService()
    s.get_user("123", strict=True)
    audit.record(s)
"""

_SAMPLES = {
    "web/Panel.tsx": _PANEL_TSX,
    "web/api.ts": _API_TS,
    "web/helpers.js": _HELPERS_JS,
    "web/View.jsx": _VIEW_JSX,
    "web/partial.ts": _PARTIAL_TS,
    "services/user.py": _USER_PY,
}


def _extraction_digest() -> str:
    extracted: dict[str, dict[str, object]] = {}
    for path, source in _SAMPLES.items():
        extractor = PythonAstExtractor(path, source) if path.endswith(".py") else JsTsTreeSitterExtractor(path, source)
        assert extractor.extract() is True
        extracted[path] = {
            "symbols": [asdict(item) for item in extractor.symbols],
            "calls": [asdict(item) for item in extractor.calls],
            "inheritances": [asdict(item) for item in extractor.inheritances],
            "imports": [asdict(item) for item in extractor.imports],
        }
    return hashlib.sha256(json.dumps(extracted, sort_keys=True).encode("utf-8")).hexdigest()


def test_extraction_output_is_pinned_to_the_index_format_version() -> None:
    assert (INDEX_FORMAT_VERSION, _extraction_digest()) == EXPECTED, (
        "Extraction output changed: increase INDEX_FORMAT_VERSION in models.py, then set EXPECTED to the new pair"
    )
