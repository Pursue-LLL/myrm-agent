'use client';

/**
 * Channel Async Login Dialog
 *
 * Unified UI for external channel authentication (QR + OAuth2)
 * Supports real-time state updates via SSE
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, QrCode, ExternalLink, X, CheckCircle, AlertCircle, Clock } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Alert, AlertDescription } from '@/components/primitives/alert';
import { toast } from 'sonner';
import { type ChannelInfo, type LoginEvent, LoginMethod, LoginStatus } from '@/types/channels';
import { startLogin as startLoginAPI, subscribeLoginStream, cancelLogin as cancelLoginAPI } from '@/services/channels';

interface ChannelLoginDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  channel: ChannelInfo;
  onSuccess?: (credentials: Record<string, unknown>) => void;
}

export default function ChannelLoginDialog({ open, onOpenChange, channel, onSuccess }: ChannelLoginDialogProps) {
  const t = useTranslations('channels');

  const [selectedMethod, setSelectedMethod] = useState<LoginMethod | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentState, setCurrentState] = useState<LoginEvent | null>(null);
  const [qrCodeData, setQrCodeData] = useState<string | null>(null);
  const [oauthUrl, setOauthUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      setSelectedMethod(null);
      setSessionId(null);
      setCurrentState(null);
      setQrCodeData(null);
      setOauthUrl(null);
      setLoading(false);
      setError(null);
    }
  }, [open]);

  // Handle SSE events
  const handleLoginEvent = useCallback(
    (event: LoginEvent) => {
      setCurrentState(event);
      setError(null);

      const { state } = event;

      // Update QR code if available
      if (state.qr_code_base64) {
        setQrCodeData(`data:image/png;base64,${state.qr_code_base64}`);
      }

      // Update OAuth URL if available
      if (state.oauth_authorization_url) {
        setOauthUrl(state.oauth_authorization_url);
      }

      // Handle terminal states
      if (state.status === LoginStatus.SUCCESS) {
        toast.success(t('loginSuccess'));
        if (onSuccess && event.credentials) {
          onSuccess(event.credentials);
        }
        onOpenChange(false);
      } else if (state.status === LoginStatus.FAILED) {
        setError(state.error_message || t('loginFailed'));
        toast.error(t('loginFailed'));
      } else if (state.status === LoginStatus.TIMEOUT) {
        setError(t('loginTimeout'));
        toast.error(t('loginTimeout'));
      } else if (state.status === LoginStatus.CANCELLED) {
        toast.info(t('loginCancelled'));
        onOpenChange(false);
      }
    },
    [t, onSuccess, onOpenChange],
  );

  // Start login flow
  const startLogin = useCallback(
    async (method: LoginMethod) => {
      setLoading(true);
      setError(null);
      setSelectedMethod(method);

      try {
        const response = await startLoginAPI(channel.channel_id, method);
        setSessionId(response.session_id);

        // Subscribe to SSE
        const eventSource = subscribeLoginStream(response.session_id, handleLoginEvent, (error) => {
          console.error('SSE error:', error);
          setError(t('connectionError'));
        });

        // Cleanup on unmount
        return () => {
          eventSource.close();
        };
      } catch (err) {
        console.error('Failed to start login:', err);
        setError(err instanceof Error ? err.message : t('unknownError'));
        toast.error(t('startLoginFailed'));
      } finally {
        setLoading(false);
      }
    },
    [channel, handleLoginEvent, t],
  );

  // Cancel login
  const cancelLogin = useCallback(async () => {
    if (!sessionId) return;

    try {
      await cancelLoginAPI(sessionId);
      onOpenChange(false);
    } catch (err) {
      console.error('Failed to cancel login:', err);
      toast.error(t('cancelLoginFailed'));
    }
  }, [sessionId, onOpenChange, t]);

  // Render method selection
  if (!selectedMethod) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>{t('selectLoginMethod')}</DialogTitle>
          </DialogHeader>

          <div className="space-y-3 py-4">
            {channel.supported_methods.includes(LoginMethod.QR_CODE) && (
              <Button
                variant="outline"
                className="w-full justify-start gap-3 h-auto py-4"
                onClick={() => startLogin(LoginMethod.QR_CODE)}
                disabled={loading}
              >
                <QrCode className="h-5 w-5" />
                <div className="text-left">
                  <div className="font-medium">{t('qrCodeLogin')}</div>
                  <div className="text-xs text-muted-foreground">{t('qrCodeLoginDesc')}</div>
                </div>
              </Button>
            )}

            {channel.supported_methods.includes(LoginMethod.OAUTH2) && (
              <Button
                variant="outline"
                className="w-full justify-start gap-3 h-auto py-4"
                onClick={() => startLogin(LoginMethod.OAUTH2)}
                disabled={loading}
              >
                <ExternalLink className="h-5 w-5" />
                <div className="text-left">
                  <div className="font-medium">{t('oauth2Login')}</div>
                  <div className="text-xs text-muted-foreground">{t('oauth2LoginDesc')}</div>
                </div>
              </Button>
            )}
          </div>

          {loading && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              <span className="ml-2 text-sm text-muted-foreground">{t('initializing')}</span>
            </div>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </DialogContent>
      </Dialog>
    );
  }

  // Render active login flow
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t(`${selectedMethod}LoginTitle`)}</DialogTitle>
        </DialogHeader>

        <div className="py-6">
          {/* QR Code Display */}
          {selectedMethod === LoginMethod.QR_CODE && (
            <div className="space-y-4">
              {qrCodeData ? (
                <div className="flex flex-col items-center space-y-4">
                  <div className="relative p-4 bg-white rounded-lg border-2 border-border">
                    <img src={qrCodeData} alt="QR Code" className="w-64 h-64" />
                  </div>

                  <div className="text-center space-y-2">
                    <p className="text-sm text-muted-foreground">{t('scanQrCode')}</p>
                    {currentState?.state.qr_expires_at && (
                      <div className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
                        <Clock className="h-3.5 w-3.5" />
                        <span>
                          {t('qrExpiresAt', {
                            time: new Date(currentState.state.qr_expires_at).toLocaleTimeString(),
                          })}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 space-y-3">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">{t('generatingQrCode')}</p>
                </div>
              )}
            </div>
          )}

          {/* OAuth2 Flow */}
          {selectedMethod === LoginMethod.OAUTH2 && (
            <div className="space-y-4">
              {oauthUrl ? (
                <div className="space-y-4">
                  <Alert>
                    <ExternalLink className="h-4 w-4" />
                    <AlertDescription>{t('oauth2Instructions')}</AlertDescription>
                  </Alert>

                  <Button
                    className="w-full"
                    size="lg"
                    onClick={() => window.open(oauthUrl, '_blank', 'noopener,noreferrer')}
                  >
                    <ExternalLink className="h-4 w-4 mr-2" />
                    {t('authorizeNow')}
                  </Button>

                  <p className="text-xs text-center text-muted-foreground">{t('oauth2Wait')}</p>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 space-y-3">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">{t('preparingOauth2')}</p>
                </div>
              )}
            </div>
          )}

          {/* Status Display */}
          {currentState && (
            <div className="mt-6">
              {currentState.state.status === LoginStatus.WAITING_USER_ACTION && (
                <Alert>
                  <Clock className="h-4 w-4" />
                  <AlertDescription>{t('waitingForUser')}</AlertDescription>
                </Alert>
              )}

              {currentState.state.status === LoginStatus.VALIDATING && (
                <Alert>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <AlertDescription>{t('validating')}</AlertDescription>
                </Alert>
              )}

              {currentState.state.status === LoginStatus.SUCCESS && (
                <Alert variant="default" className="border-green-500 bg-green-50 dark:bg-green-950">
                  <CheckCircle className="h-4 w-4 text-green-600" />
                  <AlertDescription className="text-green-600">{t('loginSuccess')}</AlertDescription>
                </Alert>
              )}
            </div>
          )}

          {/* Error Display */}
          {error && (
            <Alert variant="destructive" className="mt-6">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-4 border-t">
          <Button variant="outline" onClick={cancelLogin} disabled={loading}>
            <X className="h-4 w-4 mr-2" />
            {t('cancel')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
