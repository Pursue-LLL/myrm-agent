import deMessages from '#locales/de.json';
import enMessages from '#locales/en.json';
import jaMessages from '#locales/ja.json';
import koMessages from '#locales/ko.json';
import zhMessages from '#locales/zh.json';

import { defaultLocale } from '@/i18n/config';

type MetadataNamespace = typeof zhMessages.metadata;

const metadataByLocale: Record<string, MetadataNamespace> = {
  zh: zhMessages.metadata,
  en: enMessages.metadata as MetadataNamespace,
  ja: jaMessages.metadata as MetadataNamespace,
  ko: koMessages.metadata as MetadataNamespace,
  de: deMessages.metadata as MetadataNamespace,
};

export function getBuildTimeMetadataMessages(): MetadataNamespace {
  return metadataByLocale[defaultLocale] ?? zhMessages.metadata;
}
