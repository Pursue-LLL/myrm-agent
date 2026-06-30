'use client';

import React, { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  IconFileText,
  IconClock,
  IconShieldCheck,
  IconAlertCircle,
  IconDownload,
  IconEye,
} from '@/components/features/icons/PremiumIcons';
import { formatDistanceToNow } from 'date-fns';
import { enUS, zhCN } from 'date-fns/locale';

interface ArtifactVersion {
  id: string;
  vault_uri: string;
  sha256_hash: string;
  creator_id: string;
  commit_message: string;
  created_at: string;
}

interface Artifact {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  versions?: ArtifactVersion[];
}

export const ArtifactsCenter: React.FC = () => {
  const t = useTranslations('artifacts');
  const locale = useLocale();
  const distanceLocale = locale.startsWith('zh') ? zhCN : enUS;
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<{ [key: string]: boolean }>({});

  useEffect(() => {
    fetchArtifacts();
  }, []);

  const fetchArtifacts = async () => {
    try {
      const res = await fetch('/api/v1/files/artifacts/');
      const data = await res.json();
      setArtifacts(data.artifacts || []);
    } catch (error) {
      console.error('Failed to fetch artifacts', error);
    } finally {
      setLoading(false);
    }
  };

  const loadVersions = async (artifact: Artifact) => {
    setSelectedArtifact(artifact);
    try {
      const res = await fetch(`/api/v1/files/artifacts/${artifact.id}/versions`);
      const data = await res.json();
      setSelectedArtifact((prev) => (prev ? { ...prev, versions: data.versions } : null));
    } catch (error) {
      console.error('Failed to fetch versions', error);
    }
  };

  const verifyHash = async (artifactId: string, versionId: string) => {
    setVerifying(versionId);
    try {
      const res = await fetch(`/api/v1/files/artifacts/${artifactId}/verify/${versionId}`, { method: 'POST' });
      const data = await res.json();
      setVerifyResult((prev) => ({ ...prev, [versionId]: data.is_valid }));
    } catch (error) {
      console.error('Verification failed', error);
      setVerifyResult((prev) => ({ ...prev, [versionId]: false }));
    } finally {
      setVerifying(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse w-8 h-8 bg-primary/20 rounded-full" />
      </div>
    );
  }

  return (
    <div className="flex h-full w-full bg-background border rounded-xl overflow-hidden">
      {/* Sidebar: List of Artifacts */}
      <div className="w-1/3 border-r bg-muted/10 overflow-y-auto p-4">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <IconFileText className="w-5 h-5 text-primary" />
          {t('title', { defaultMessage: '企业工件库' })}
        </h2>
        <div className="space-y-2">
          {artifacts.map((a) => (
            <div
              key={a.id}
              onClick={() => loadVersions(a)}
              className={`p-3 rounded-lg cursor-pointer transition-all duration-200 border ${selectedArtifact?.id === a.id ? 'bg-primary/5 border-primary/30' : 'bg-background hover:bg-muted/50 border-transparent'}`}
            >
              <h3 className="font-medium text-sm truncate">{a.name}</h3>
              <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                <IconClock className="w-3 h-3" />
                {formatDistanceToNow(new Date(a.updated_at), { addSuffix: true, locale: distanceLocale })}
              </p>
            </div>
          ))}
          {artifacts.length === 0 && (
            <div className="text-sm text-muted-foreground text-center py-8">
              {t('empty', { defaultMessage: '暂无工件资产' })}
            </div>
          )}
        </div>
      </div>

      {/* Main Content: Timeline & Versions */}
      <div className="w-2/3 bg-background overflow-y-auto p-6">
        {selectedArtifact ? (
          <div>
            <h2 className="text-2xl font-bold mb-2">{selectedArtifact.name}</h2>
            <p className="text-sm text-muted-foreground mb-8">
              {selectedArtifact.description || t('no_desc', { defaultMessage: '无描述' })}
            </p>

            <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-4">
              {t('version_history', { defaultMessage: '版本时间线 (不可篡改)' })}
            </h3>

            <div className="space-y-6 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-border before:to-transparent">
              {selectedArtifact.versions?.map((v, index) => (
                <div
                  key={v.id}
                  className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active"
                >
                  {/* Timeline dot */}
                  <div className="flex items-center justify-center w-10 h-10 rounded-full border-4 border-background bg-primary/10 text-primary shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10">
                    <IconFileText className="w-4 h-4" />
                  </div>

                  {/* Card */}
                  <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border bg-card transition-all hover:shadow-md">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-primary px-2 py-1 bg-primary/10 rounded-full">
                        v{selectedArtifact.versions!.length - index}
                      </span>
                      <span className="text-xs text-muted-foreground">{new Date(v.created_at).toLocaleString()}</span>
                    </div>
                    <p className="text-sm mb-3">{v.commit_message || t('auto_saved_version', { defaultMessage: '自动保存的版本' })}</p>

                    <div className="flex items-center justify-between mt-4 pt-3 border-t border-border/50">
                      <div className="flex items-center gap-2">
                        {verifyResult[v.id] === true ? (
                          <span className="flex items-center gap-1 text-xs text-green-600 bg-green-500/10 px-2 py-1 rounded-full">
                            <IconShieldCheck className="w-3 h-3" />
                            {t('tamper_free', { defaultMessage: '防篡改校验通过' })}
                          </span>
                        ) : verifyResult[v.id] === false ? (
                          <span className="flex items-center gap-1 text-xs text-red-600 bg-red-500/10 px-2 py-1 rounded-full">
                            <IconAlertCircle className="w-3 h-3" />
                            {t('corrupted', { defaultMessage: '文件已被篡改！' })}
                          </span>
                        ) : (
                          <button
                            onClick={() => verifyHash(selectedArtifact.id, v.id)}
                            disabled={verifying === v.id}
                            className="text-xs text-muted-foreground hover:text-primary transition-colors flex items-center gap-1"
                          >
                            <IconShieldCheck className="w-3 h-3" />
                            {verifying === v.id
                              ? t('verifying', { defaultMessage: '校验中...' })
                              : t('verify_hash', { defaultMessage: '验证完整性' })}
                          </button>
                        )}
                      </div>
                      <div
                        className="text-[10px] text-muted-foreground/50 font-mono truncate w-24"
                        title={v.sha256_hash}
                      >
                        {v.sha256_hash.substring(0, 8)}...
                      </div>
                      <a
                        href={`/api/v1/files/vault/${v.vault_uri.replace('vault://', '')}/content`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-primary hover:bg-primary/10 px-2 py-1 rounded transition-colors flex items-center gap-1 ml-2"
                      >
                        <IconEye className="w-3 h-3" />
                        {t('preview', { defaultMessage: '预览' })}
                      </a>
                      <a
                        href={`/api/v1/files/vault/${v.vault_uri.replace('vault://', '')}/content?download=1`}
                        className="text-xs text-primary hover:bg-primary/10 px-2 py-1 rounded transition-colors flex items-center gap-1"
                      >
                        <IconDownload className="w-3 h-3" />
                        {t('download', { defaultMessage: '下载' })}
                      </a>
                    </div>
                  </div>
                </div>
              ))}
              {!selectedArtifact.versions && (
                <div className="text-center py-4 text-sm text-muted-foreground animate-pulse">
                  {t('loading_versions', { defaultMessage: '加载版本中...' })}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
            <IconShieldCheck className="w-16 h-16 mb-4 opacity-20" />
            <p>{t('select_prompt', { defaultMessage: '选择左侧工件查看不可变时间线' })}</p>
          </div>
        )}
      </div>
    </div>
  );
};
