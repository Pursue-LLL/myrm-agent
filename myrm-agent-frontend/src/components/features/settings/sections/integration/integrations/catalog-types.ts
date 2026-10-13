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
  deploymentScope: 'all_modes' | 'local_tauri_only' | null;
  postConnectGuide: string | null;
  postConnectGuideZh: string | null;
}

/** Typed view of a catalog entry's `mcpConfig`: the template the connect dialog turns into a saved MCP service. */
export interface CatalogMcpDialogConfig {
  name: string;
  type: 'sse' | 'stdio' | 'streamable_http';
  url?: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  headers?: Record<string, string>;
  description?: string;
}

export interface CatalogResponse {
  entries: CatalogEntry[];
  categories: string[];
  total: number;
}
