import crypto from 'crypto';

/** Agent stream request id (`r-…`) used as REST user message id for a single turn. */
export function generateStreamRequestMessageId(): string {
  const timestamp = Date.now().toString(36);
  const microTime = (performance.now() * 1000).toString(36).replace('.', '');
  const randomBytes = crypto.randomBytes(6).toString('hex');
  const counter = ((Math.random() * 0xffff) | 0).toString(36);
  return `r-${timestamp}-${microTime}-${randomBytes}-${counter}`;
}
