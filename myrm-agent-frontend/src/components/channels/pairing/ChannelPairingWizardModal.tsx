/**
 * Model-Agnostic Channel Token Binding & Visual Pairing Wizard Modal.
 *
 * Provides a deterministic, zero-CLI pairing workflow for WeChat,
 * WeCom, Feishu, DingTalk, and external channels, decoupled completely
 * from LLM chat turns and prompt interpretations.
 */

import React, { useEffect, useState } from 'react';
import Image from 'next/image';
import { useTranslations } from 'next-intl';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  QrCode,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react';

import type {
  ChannelPlatform,
  PairingSessionResponse,
  PairingWizardStep,
  PlatformMetadata,
} from './channelPairingTypes';
import {
  ChannelPairingService,
  SUPPORTED_PAIRING_PLATFORMS,
} from './channelPairingService';
import { ChannelHealthCheckCard } from './ChannelHealthCheckCard';

export interface ChannelPairingWizardModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialPlatform?: ChannelPlatform;
  onPairingComplete?: (session: PairingSessionResponse) => void;
}

export const ChannelPairingWizardModal: React.FC<ChannelPairingWizardModalProps> = ({
  isOpen,
  onClose,
  initialPlatform = 'wechat',
  onPairingComplete,
}) => {
  let t: (key: string, fallback?: string) => string;
  try {
    const intlT = useTranslations('channelPairing');
    t = (key: string, fallback?: string) => {
      try {
        const val = intlT(key);
        return val || (fallback ?? key);
      } catch {
        return fallback ?? key;
      }
    };
  } catch {
    t = (_key: string, fallback?: string) => fallback ?? _key;
  }

  const [currentStep, setCurrentStep] = useState<PairingWizardStep>('select_platform');
  const [selectedPlatform, setSelectedPlatform] = useState<ChannelPlatform>(initialPlatform);
  const [session, setSession] = useState<PairingSessionResponse | null>(null);
  const [isInitializing, setIsInitializing] = useState<boolean>(false);
  const [pollError, setPollError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setSelectedPlatform(initialPlatform);
      setCurrentStep('select_platform');
      setSession(null);
      setPollError(null);
    }
  }, [isOpen, initialPlatform]);

  const startPairingFlow = async (platform: ChannelPlatform): Promise<void> => {
    setIsInitializing(true);
    setPollError(null);
    try {
      const newSession = await ChannelPairingService.createPairingSession({
        platform,
        custom_label: `${platform} connection`,
      });
      setSession(newSession);
      setCurrentStep('scan_handshake');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setPollError(msg);
    } finally {
      setIsInitializing(false);
    }
  };

  const handleSimulateScanConfirm = async (): Promise<void> => {
    if (!session) {
      return;
    }
    try {
      const confirmed = await ChannelPairingService.confirmPairing(session.session_id, {
        auth_token: `${session.platform}_token_${Date.now().toString(16)}`,
        user_identity: `${session.platform}_user_${session.session_id.slice(-4)}`,
      });
      if (confirmed.status === 'authenticated') {
        const updated = await ChannelPairingService.getPairingSessionStatus(session.session_id);
        setSession(updated);
        setCurrentStep('confirm_binding');
        if (onPairingComplete) {
          onPairingComplete(updated);
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setPollError(msg);
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <dialog
      open
      aria-modal="true"
      data-testid="channel-pairing-modal"
      className="fixed inset-0 z-50 m-0 flex h-full w-full max-h-none max-w-none items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm"
    >
      <div className="flex max-h-[90vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400">
              <QrCode className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">
                {t('wizard.title', '外部渠道可视化配对向导')}
              </h2>
              <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
                <span>
                  {t(
                    'wizard.modelAgnosticBadge',
                    '模型无关解耦 · 零命令确定性配对'
                  )}
                </span>
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            data-testid="modal-close-button"
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {currentStep === 'select_platform' && (
            <div className="space-y-4">
              <div className="rounded-lg bg-blue-50/70 p-3.5 text-xs text-blue-800 dark:bg-blue-950/40 dark:text-blue-300">
                <div className="flex items-center gap-1.5 font-medium">
                  <Sparkles className="h-3.5 w-3.5 text-blue-500" />
                  {t('wizard.antiWorkbuddyNote', '彻底告别手敲 acquire_token')}
                </div>
                <p className="mt-1 opacity-90">
                  {t(
                    'wizard.antiWorkbuddyDesc',
                    '无需切换昂贵模型或在聊天框输入配置命令，点击渠道即可直接生成动态二维码一键连通。'
                  )}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {SUPPORTED_PAIRING_PLATFORMS.map((item: PlatformMetadata) => {
                  const isSelected = selectedPlatform === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => {
                        setSelectedPlatform(item.id);
                      }}
                      data-testid={`platform-card-${item.id}`}
                      className={`flex flex-col items-start rounded-xl border p-4 text-left transition ${
                        isSelected
                          ? 'border-blue-500 bg-blue-50/30 ring-2 ring-blue-500/20 dark:bg-blue-950/20'
                          : 'border-slate-200 hover:border-slate-300 dark:border-slate-800 dark:hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between w-full">
                        <span className="font-semibold text-slate-800 dark:text-slate-100">
                          {t(`platforms.${item.id}.name`, item.id.toUpperCase())}
                        </span>
                        {isSelected && (
                          <CheckCircle2 className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                        )}
                      </div>
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                        {t(`platforms.${item.id}.desc`, '即时扫码或 Webhook 鉴权')}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {currentStep === 'scan_handshake' && session && (
            <div className="flex flex-col items-center text-center">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-800">
                {session.qr_code && (
                  <Image
                    src={session.qr_code.qr_matrix_base64}
                    alt="Channel Pairing QR Code"
                    width={192}
                    height={192}
                    unoptimized
                    data-testid="pairing-qr-image"
                    className="h-48 w-48 rounded-lg object-contain"
                  />
                )}
              </div>

              <div className="mt-4 flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                <RefreshCw className="h-3.5 w-3.5 animate-spin text-blue-500" />
                <span>
                  {t(
                    'wizard.waitingScan',
                    '请使用对应客户端扫描上方动态二维码...'
                  )}
                </span>
              </div>

              <p className="mt-2 text-xs text-slate-400">
                {t('wizard.sessionExpiry', '凭证有效时长: 300 秒')} ·{' '}
                <code>{session.session_id}</code>
              </p>

              {pollError && (
                <div className="mt-3 flex items-center gap-1.5 text-xs text-rose-600">
                  <AlertCircle className="h-3.5 w-3.5" />
                  <span>{pollError}</span>
                </div>
              )}
            </div>
          )}

          {currentStep === 'confirm_binding' && session && (
            <div className="space-y-4 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400">
                <CheckCircle2 className="h-8 w-8" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">
                  {t('wizard.bindingSuccess', '渠道鉴权与 Token 绑定成功！')}
                </h3>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {t(
                    'wizard.bindingSuccessDesc',
                    '凭证已安全加密写入本地沙箱，渠道已准备就绪。'
                  )}
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-left text-xs dark:border-slate-800 dark:bg-slate-800/60">
                <div className="flex justify-between py-1">
                  <span className="text-slate-500">平台:</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">
                    {session.platform.toUpperCase()}
                  </span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-500">绑定身份:</span>
                  <span className="font-mono text-slate-800 dark:text-slate-200">
                    {session.user_identity || 'auto_detected'}
                  </span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-500">安全凭证:</span>
                  <span className="font-mono text-slate-800 dark:text-slate-200">
                    {session.bound_token_masked || '********'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {currentStep === 'health_check' && (
            <ChannelHealthCheckCard
              platform={selectedPlatform}
              defaultRecipient={session?.user_identity ?? undefined}
            />
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/50 px-6 py-4 dark:border-slate-800 dark:bg-slate-900/50">
          {currentStep === 'select_platform' && (
            <>
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                {t('common.cancel', '取消')}
              </button>
              <button
                type="button"
                onClick={() => {
                  void startPairingFlow(selectedPlatform);
                }}
                disabled={isInitializing}
                data-testid="start-pairing-btn"
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
              >
                <span>{t('wizard.startPairing', '开始扫码配对')}</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            </>
          )}

          {currentStep === 'scan_handshake' && (
            <>
              <button
                type="button"
                onClick={() => {
                  setCurrentStep('select_platform');
                }}
                className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                <ArrowLeft className="h-4 w-4" />
                <span>{t('common.back', '上一步')}</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  void handleSimulateScanConfirm();
                }}
                data-testid="simulate-scan-btn"
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
              >
                <CheckCircle2 className="h-4 w-4" />
                <span>{t('wizard.confirmScanned', '模拟完成扫码')}</span>
              </button>
            </>
          )}

          {currentStep === 'confirm_binding' && (
            <>
              <div />
              <button
                type="button"
                onClick={() => {
                  setCurrentStep('health_check');
                }}
                data-testid="go-to-healthcheck-btn"
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                <span>{t('wizard.proceedPing', '一键连通性自测')}</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            </>
          )}

          {currentStep === 'health_check' && (
            <>
              <button
                type="button"
                onClick={() => {
                  setCurrentStep('confirm_binding');
                }}
                className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                <ArrowLeft className="h-4 w-4" />
                <span>{t('common.back', '上一步')}</span>
              </button>
              <button
                type="button"
                onClick={onClose}
                data-testid="finish-wizard-btn"
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-700"
              >
                <CheckCircle2 className="h-4 w-4" />
                <span>{t('wizard.done', '完成并关闭')}</span>
              </button>
            </>
          )}
        </div>
      </div>
    </dialog>
  );
};
