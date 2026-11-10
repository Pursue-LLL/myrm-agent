/**
 * The fake server of the edit dialog tests: the answers it can give and a record of what it was asked.
 */
import { expect, vi } from 'vitest';

export const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>();

export const json = (body: object, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

export const stream = (...chunks: string[]) => {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
        controller.close();
      },
    }),
  );
};

export const sse = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`;

export const completePreview = {
  inline_count: 3,
  hidden_count: 2,
  overflow_count: 1,
  catalog_tokens: 120,
  search_mounted: true,
};

export const estimate = (overrides: object = {}) =>
  json({
    data: {
      accuracy_level: 64,
      ascs_score: 900,
      max_safe_score: 1200,
      is_high: true,
      is_critical: false,
      catalog_preview: completePreview,
      ...overrides,
    },
  });

export const requests = (needle: string) => fetchMock.mock.calls.filter(([url]) => url.includes(needle));

export const bodyOf = (call: [string, RequestInit?]): unknown => JSON.parse(String(call[1]?.body));

/**
 * A response whose reading can be waited for: `settled()` resolves once the code under test has read the body and
 * run everything that follows, so a test can assert that a late answer changed nothing instead of passing too early.
 */
export function watched(response: Response): { response: Response; settled: () => Promise<void> } {
  const read = vi.spyOn(response, 'json');
  return {
    response,
    settled: async () => {
      await vi.waitFor(() => expect(read).toHaveBeenCalled(), { timeout: 10_000 });
      await read.mock.results[0].value;
      await new Promise((resolve) => setTimeout(resolve, 0));
    },
  };
}

/** Answers like an idle server (no history, no estimate) until a test says otherwise. */
export function installFakeServer(): void {
  fetchMock.mockImplementation(async (url) => (url.includes('/history') ? json({ data: [] }) : json({ data: null })));
  vi.stubGlobal('fetch', fetchMock);
}
