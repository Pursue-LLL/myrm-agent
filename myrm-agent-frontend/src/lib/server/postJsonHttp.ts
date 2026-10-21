import { request } from 'node:http';
import type { IncomingMessage } from 'node:http';
import { URL } from 'node:url';

/**
 * Minimal JSON POST helper for Route Handlers. Avoids intermittent `fetch failed`
 * against local FastAPI from some Next/Turbopack + undici stacks.
 */
export async function postJsonHttp(urlStr: string, body: unknown): Promise<{ status: number; text: string }> {
  const u = new URL(urlStr);
  if (u.protocol !== 'http:') {
    throw new Error(`postJsonHttp only supports http:, got ${u.protocol}`);
  }

  const payload = JSON.stringify(body);
  const len = Buffer.byteLength(payload, 'utf8');

  return new Promise((resolve, reject) => {
    const req = request(
      {
        hostname: u.hostname,
        port: u.port === '' ? 80 : Number(u.port),
        path: `${u.pathname}${u.search}`,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': String(len),
        },
      },
      (res: IncomingMessage) => {
        const chunks: Buffer[] = [];
        res.on('data', (d: Buffer) => chunks.push(d));
        res.on('end', () => {
          resolve({
            status: res.statusCode ?? 500,
            text: Buffer.concat(chunks).toString('utf8'),
          });
        });
      },
    );
    req.on('error', reject);
    req.write(payload, 'utf8');
    req.end();
  });
}
