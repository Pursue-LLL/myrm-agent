export interface CredentialField {
  key: string;
  label: string;
  labelZh: string;
  inject: 'arg_placeholder' | 'env' | 'header';
}

export interface CatalogEntry {
  id: string;
  name: string;
  nameZh: string;
  description: string;
  descriptionZh: string;
  icon: string;
  category: string;
  connectorType: string;
  authType: string;
  helpUrl: string | null;
  helpText: string | null;
  helpTextZh: string | null;
  envKey: string | null;
  credentialFields: CredentialField[] | null;
  tags: string[];
  website: string | null;
  mcpConfig: Record<string, unknown> | null;
  postConnectGuide: string | null;
  postConnectGuideZh: string | null;
}

export interface CatalogResponse {
  entries: CatalogEntry[];
  categories: string[];
  total: number;
}
