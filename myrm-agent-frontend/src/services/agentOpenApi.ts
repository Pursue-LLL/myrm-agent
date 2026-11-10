import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

export interface ParsedEndpoint {
  operation_id: string;
  method: string;
  path: string;
  summary: string;
  description: string;
  tags: string[];
  deprecated: boolean;
}

export interface ParseSpecResponse {
  title: string;
  version: string;
  description: string;
  base_url: string;
  spec_version: string;
  endpoints: ParsedEndpoint[];
  tags: Record<string, string>;
  endpoint_count: number;
}

export interface SaaSPreset {
  name: string;
  description: string;
  spec_url: string;
  auth_type: string;
  icon_url?: string;
  selected_endpoints?: string[];
}

export async function getSaaSPresets(): Promise<SaaSPreset[]> {
  const response = await fetch(`${getBackendUrl()}/api/v1/agents/openapi-services/presets`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch presets: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data ?? result;
}

export async function parseOpenAPISpec(params: {
  spec_url?: string;
  spec_content?: string;
}): Promise<ParseSpecResponse> {
  const response = await fetch(`${getBackendUrl()}/api/v1/agents/openapi-services/parse-spec`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to parse spec: ${response.statusText}`);
  }

  const result = await response.json();
  return result.data ?? result;
}
