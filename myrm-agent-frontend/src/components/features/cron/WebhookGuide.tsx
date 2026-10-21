'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Copy, ChevronDown, ChevronUp } from 'lucide-react';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

export function WebhookGuide({ secret }: { secret: string }) {
  const t = useTranslations('cron');
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const copySecret = async () => {
    try {
      await writeToClipboard(secret);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = secret;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="border-t border-border/50 pt-2 mt-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
      >
        {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        {t('webhookGuideTitle')}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2 text-[11px]">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground shrink-0">Secret:</span>
            <code className="bg-muted px-1.5 py-0.5 rounded text-[10px] font-mono truncate flex-1">{secret}</code>
            <button onClick={copySecret} className="shrink-0 text-muted-foreground hover:text-foreground">
              <Copy className="h-3 w-3" />
            </button>
            {copied && <span className="text-green-500 text-[10px] shrink-0">{t('copied')}</span>}
          </div>
          <div className="text-muted-foreground">{t('webhookGuideDesc')}</div>
          <pre className="bg-muted rounded p-2 text-[10px] font-mono overflow-x-auto whitespace-pre leading-relaxed">
            {`# Python
import hmac, hashlib
	def verify(body: bytes, secret: str, signature: str) -> bool:
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)

# Node.js
const crypto = require('crypto');
function verify(body, secret, signature) {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(body).digest('hex');
  return signature === \`sha256=\${expected}\`;
}`}
          </pre>
        </div>
      )}
    </div>
  );
}
