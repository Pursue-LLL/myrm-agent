import zhMetadata from '../../../locales/namespaces/zh/metadata.json';

type MetadataNamespace = typeof zhMetadata;

export function getBuildTimeMetadataMessages(): MetadataNamespace {
  return zhMetadata;
}
