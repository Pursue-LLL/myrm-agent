/**
 * Public theme marketplace API (Control Plane).
 */

import { getApiUrl } from '@/lib/api';
import { resolveCpBaseUrl } from '@/lib/cp-base-url';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

export interface ThemeMarketplaceListing {
  id: string;
  slug: string;
  name: string;
  tagline: string;
  description: string;
  creatorUserId: string;
  origin: string;
  layoutId: string;
  mediaKind: string;
  priceCents: number;
  vipOnly: boolean;
  status: string;
  packageSha256: string;
  previewThumbnail: string | null;
  installCount: number;
  publishedAt: number | null;
  isOwned: boolean;
  reviewReason?: string | null;
}

export interface ThemeDownloadToken {
  listingId: string;
  packageSha256: string;
  transportSignature: string;
  expiresAt: number;
}

const BASE = '/api/theme-marketplace';

function tmUrl(path: string): string {
  return `${resolveCpBaseUrl()}${BASE}${path}`;
}

function parseListing(raw: Record<string, unknown>): ThemeMarketplaceListing {
  return {
    id: String(raw.id),
    slug: String(raw.slug),
    name: String(raw.name),
    tagline: String(raw.tagline ?? ''),
    description: String(raw.description ?? ''),
    creatorUserId: String(raw.creatorUserId ?? raw.creator_user_id ?? ''),
    origin: String(raw.origin ?? 'community'),
    layoutId: String(raw.layoutId ?? raw.layout_id ?? 'chat-first'),
    mediaKind: String(raw.mediaKind ?? raw.media_kind ?? 'none'),
    priceCents: Number(raw.priceCents ?? raw.price_cents ?? 0),
    vipOnly: Boolean(raw.vipOnly ?? raw.vip_only),
    status: String(raw.status ?? 'published'),
    packageSha256: String(raw.packageSha256 ?? raw.package_sha256 ?? ''),
    previewThumbnail: (raw.previewThumbnail ?? raw.preview_thumbnail ?? null) as string | null,
    installCount: Number(raw.installCount ?? raw.install_count ?? 0),
    publishedAt: (raw.publishedAt ?? raw.published_at ?? null) as number | null,
    isOwned: Boolean(raw.isOwned ?? raw.is_owned),
    reviewReason: (raw.reviewReason ?? raw.review_reason ?? null) as string | null,
  };
}

export async function getThemeListing(listingId: string): Promise<ThemeMarketplaceListing> {
  const res = await fetch(tmUrl(`/listing/${listingId}`), { headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Theme listing fetch failed: ${res.status}`);
  const raw = (await res.json()) as Record<string, unknown>;
  return parseListing(raw);
}

const sleep = (ms: number) => new Promise<void>((resolve) => {
  window.setTimeout(resolve, ms);
});

/** Poll until Stripe webhook grants entitlement (typical delay 1–5s). */
export async function waitForThemeListingOwnership(
  listingId: string,
  options?: { attempts?: number; delayMs?: number },
): Promise<ThemeMarketplaceListing> {
  const attempts = options?.attempts ?? 10;
  const delayMs = options?.delayMs ?? 1500;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const listing = await getThemeListing(listingId);
    if (listing.isOwned) {
      return listing;
    }
    if (attempt + 1 < attempts) {
      await sleep(delayMs);
    }
  }
  throw new Error('Theme entitlement not ready');
}

export async function listThemeMarketplace(options?: {
  origin?: 'official' | 'community';
}): Promise<ThemeMarketplaceListing[]> {
  const params = new URLSearchParams();
  if (options?.origin) params.set('origin', options.origin);
  const qs = params.toString();
  const res = await fetch(tmUrl(`/list${qs ? `?${qs}` : ''}`), {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Theme marketplace list failed: ${res.status}`);
  const data = (await res.json()) as Record<string, unknown>[];
  return data.map((row) => parseListing(row));
}

export async function acquireThemeListing(listingId: string): Promise<void> {
  const res = await fetch(tmUrl(`/listing/${listingId}/acquire`), {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Theme acquire failed: ${res.status}`);
}

export async function issueThemeDownloadToken(listingId: string): Promise<ThemeDownloadToken> {
  const res = await fetch(tmUrl(`/listing/${listingId}/download-token`), {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Theme download token failed: ${res.status}`);
  const raw = (await res.json()) as Record<string, unknown>;
  return {
    listingId: String(raw.listingId ?? raw.listing_id),
    packageSha256: String(raw.packageSha256 ?? raw.package_sha256),
    transportSignature: String(raw.transportSignature ?? raw.transport_signature),
    expiresAt: Number(raw.expiresAt ?? raw.expires_at),
  };
}

export async function downloadThemePackage(
  listingId: string,
  token: ThemeDownloadToken,
): Promise<Blob> {
  const params = new URLSearchParams({
    signature: token.transportSignature,
    expires_at: String(token.expiresAt),
  });
  const res = await fetch(tmUrl(`/listing/${listingId}/package?${params.toString()}`), {
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Theme package download failed: ${res.status}`);
  return res.blob();
}

export async function checkoutThemeListing(
  listingId: string,
): Promise<{ checkoutUrl: string; sessionId: string }> {
  const res = await fetch(tmUrl(`/listing/${listingId}/checkout`), {
    method: 'POST',
    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(`Theme checkout failed: ${res.status}`);
  const raw = (await res.json()) as Record<string, unknown>;
  return {
    checkoutUrl: String(raw.checkoutUrl ?? raw.checkout_url),
    sessionId: String(raw.sessionId ?? raw.session_id),
  };
}

export async function submitThemeListing(options: {
  file: File;
  name: string;
  slug: string;
  tagline?: string;
  description?: string;
  priceCents?: number;
}): Promise<{ listingId: string; slug: string; status: string }> {
  const fd = new FormData();
  fd.append('package', options.file);
  fd.append('name', options.name);
  fd.append('slug', options.slug);
  fd.append('tagline', options.tagline ?? '');
  fd.append('description', options.description ?? '');
  fd.append('price_cents', String(options.priceCents ?? 0));
  const res = await fetch(tmUrl('/submit'), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: fd,
  });
  if (!res.ok) throw new Error(`Theme submit failed: ${res.status}`);
  const raw = (await res.json()) as Record<string, unknown>;
  return {
    listingId: String(raw.listingId ?? raw.listing_id),
    slug: String(raw.slug),
    status: String(raw.status),
  };
}

export async function listMyThemeListings(): Promise<ThemeMarketplaceListing[]> {
  const res = await fetch(tmUrl('/creator/mine'), { headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Theme creator list failed: ${res.status}`);
  const data = (await res.json()) as Record<string, unknown>[];
  return data.map((row) => parseListing(row));
}

export async function fetchCreatorThemeStats(): Promise<{ totalEarnedCents: number }> {
  const res = await fetch(tmUrl('/creator/stats'), { headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Theme creator stats failed: ${res.status}`);
  const raw = (await res.json()) as Record<string, unknown>;
  return {
    totalEarnedCents: Number(raw.totalEarnedCents ?? raw.total_earned_cents ?? 0),
  };
}

export async function listPendingThemeListings(): Promise<ThemeMarketplaceListing[]> {
  const res = await fetch(tmUrl('/admin/pending'), { headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Theme admin list failed: ${res.status}`);
  const data = (await res.json()) as Record<string, unknown>[];
  return data.map((row) => parseListing(row));
}

export async function reviewThemeListing(
  listingId: string,
  options: { action: 'approve' | 'reject'; reason: string },
): Promise<void> {
  const res = await fetch(tmUrl(`/admin/listing/${listingId}/review`), {
    method: 'POST',
    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: options.action, reason: options.reason }),
  });
  if (!res.ok) throw new Error(`Theme review failed: ${res.status}`);
}

export async function listAdminThemeCatalog(): Promise<ThemeMarketplaceListing[]> {
  const res = await fetch(tmUrl('/admin/catalog'), { headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Theme admin catalog failed: ${res.status}`);
  const data = (await res.json()) as Record<string, unknown>[];
  return data.map((row) => parseListing(row));
}

export async function suspendThemeListing(listingId: string, reason: string): Promise<void> {
  const res = await fetch(tmUrl(`/admin/listing/${listingId}/suspend`), {
    method: 'POST',
    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) throw new Error(`Theme suspend failed: ${res.status}`);
}

export async function restoreThemeListing(listingId: string, reason: string): Promise<void> {
  const res = await fetch(tmUrl(`/admin/listing/${listingId}/restore`), {
    method: 'POST',
    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) throw new Error(`Theme restore failed: ${res.status}`);
}

/** Idempotent install counter (Local/WebUI path; sandbox may also record via server internal API). */
export async function recordThemeInstall(listingId: string): Promise<void> {
  const res = await fetch(tmUrl(`/listing/${listingId}/record-install`), {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Theme record-install failed: ${res.status}`);
  }
}

export async function installThemeFromMarketplace(options: {
  listingId: string;
  listingOrigin: string;
  token: ThemeDownloadToken;
  packageBlob: Blob;
  setActive?: boolean;
  existingProfileIds?: string[];
}): Promise<Record<string, unknown>> {
  const fd = new FormData();
  fd.append('file', options.packageBlob, 'theme.myrmtheme');
  fd.append('listing_id', options.listingId);
  fd.append('listing_origin', options.listingOrigin);
  fd.append('package_sha256', options.token.packageSha256);
  fd.append('transport_signature', options.token.transportSignature);
  fd.append('expires_at', String(options.token.expiresAt));
  fd.append('set_active', String(options.setActive ?? true));
  fd.append('existing_profile_ids', JSON.stringify(options.existingProfileIds ?? []));

  const res = await fetch(getApiUrl('/theme/packages/install-from-marketplace'), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: fd,
  });
  if (!res.ok) throw new Error(`Theme marketplace install failed: ${res.status}`);
  const payload = (await res.json()) as {
    data?: { install?: { profile?: Record<string, unknown> } };
    success?: boolean;
  };
  const profile = payload.data?.install?.profile;
  if (!profile || typeof profile !== 'object') {
    throw new Error('Theme marketplace install returned no profile');
  }
  return profile;
}
