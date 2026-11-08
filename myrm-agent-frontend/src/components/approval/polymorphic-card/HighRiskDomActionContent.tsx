'use client';

import { useTranslations } from 'next-intl';
import { AlertTriangle, Globe, Monitor, MousePointerClick } from 'lucide-react';
import HighRiskEvidenceScreenshot from '@/components/approval/HighRiskEvidenceScreenshot';
import type { ApprovalPayload } from '@/store/useApprovalStore';

const KeyboardIcon = ({ className = 'h-3.5 w-3.5' }: { className?: string }) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden="true"
  >
    <rect width="20" height="16" x="2" y="4" rx="2" />
    <path d="M6 8h.001M10 8h.001M14 8h.001M18 8h.001M8 12h.001M12 12h.001M16 12h.001M7 16h10" />
  </svg>
);

/** Review body of a high-risk browser or desktop UI action: the target, the evidence screenshot and what will run. */
export function HighRiskDomActionContent({ approval }: { approval: ApprovalPayload }) {
  const t = useTranslations('toolApproval');
  const element = approval.payload?.element as { role?: string; name?: string; ref?: string; key?: string } | undefined;
  const pageUrl = (approval.payload?.page_url as string) || '';
  const desktopApp = (approval.payload?.app_name as string) || '';
  const desktopWindow = (approval.payload?.window_title as string) || '';
  const screenshotBase64 = (approval.payload?.screenshot_base64 as string) || '';
  const screenshotSize = approval.payload?.screenshot_size as [number, number] | undefined;
  const highlightCoordinate = approval.payload?.highlight_coordinate as [number, number] | undefined;
  const toolInput = approval.payload?.tool_input as
    | {
        action?: string;
        ref?: string;
        text?: string;
        expression?: string;
      }
    | undefined;
  const reason = approval.reason || (approval.payload?.reason as string) || '';
  const isKeyActivation = toolInput?.action === 'press' || Boolean(element?.key);
  const activationKey = toolInput?.text || element?.key;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3">
        <AlertTriangle className="h-5 w-5 flex-shrink-0 text-destructive-text" />
        <div>
          <h4 className="font-semibold text-sm text-destructive-text">{t('highRiskDomAction')}</h4>
          <p className="text-xs text-destructive-text mt-0.5">{reason}</p>
        </div>
      </div>

      <div className="space-y-3">
        {element && (
          <div className="rounded-lg border bg-muted/50 p-3">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-2">
              {isKeyActivation ? (
                <KeyboardIcon className="h-3.5 w-3.5 text-destructive-text" />
              ) : (
                <MousePointerClick className="h-3.5 w-3.5" />
              )}
              {t('targetElement')}
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-mono font-medium text-primary">
                {element.role}
              </span>
              <span className="font-medium text-foreground">&quot;{element.name}&quot;</span>
              <span className="text-muted-foreground text-xs">ref: {element.ref}</span>
              {activationKey && (
                <kbd className="inline-flex items-center rounded border border-border bg-background px-2 py-0.5 text-xs font-mono font-semibold text-foreground shadow-xs">
                  {activationKey}
                </kbd>
              )}
            </div>
          </div>
        )}

        {(desktopApp || desktopWindow) && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground px-1 min-w-0">
            <Monitor className="h-3 w-3 flex-shrink-0" />
            <span className="truncate" title={desktopWindow ? `${desktopApp} — ${desktopWindow}` : desktopApp}>
              {[desktopApp, desktopWindow].filter(Boolean).join(' — ')}
            </span>
          </div>
        )}

        {screenshotBase64 && screenshotSize && (
          <HighRiskEvidenceScreenshot
            screenshotBase64={screenshotBase64}
            screenshotWidth={screenshotSize[0]}
            screenshotHeight={screenshotSize[1]}
            highlightX={highlightCoordinate?.[0]}
            highlightY={highlightCoordinate?.[1]}
          />
        )}

        {toolInput?.expression ? (
          <div className="rounded-lg border bg-muted/50 p-3">
            <div className="text-xs font-medium text-muted-foreground mb-2">{t('jsExpression')}</div>
            <pre className="font-mono text-xs sm:text-sm whitespace-pre-wrap break-all overflow-x-auto max-h-48 rounded-md bg-background/80 p-2 border">
              {toolInput.expression}
            </pre>
          </div>
        ) : toolInput?.action ? (
          <div className="rounded-lg border bg-muted/50 p-3">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-2">
              {isKeyActivation ? (
                <>
                  <KeyboardIcon className="h-3.5 w-3.5 text-destructive-text" />
                  <span>{t('keyActivation')}</span>
                </>
              ) : (
                t('action')
              )}
            </div>
            <div className="font-mono text-sm break-all">
              {toolInput.action}({toolInput.ref ?? ''}
              {toolInput.text ? `, "${toolInput.text}"` : ''})
            </div>
          </div>
        ) : null}

        {pageUrl && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground px-1">
            <Globe className="h-3 w-3 flex-shrink-0" />
            <span className="truncate" title={pageUrl}>
              {pageUrl}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
