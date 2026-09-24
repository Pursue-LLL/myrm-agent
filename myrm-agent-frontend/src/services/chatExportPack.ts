/**
 * Session event logs and artifacts ZIP export pack client service.
 *
 * [INPUT]
 * - '@/lib/api'::API_BASE_URL (POS: API base URL provider)
 *
 * [OUTPUT]
 * - parseContentDispositionFilename: parse RFC 5987 / standard content-disposition header safely
 * - checkExportPackAvailable: preflight HEAD request to check availability
 * - downloadChatExportPack: download zipped event log & artifacts pack
 *
 * [POS]
 * - services.chatExportPack: Client download service for session event logs & artifacts ZIP packs.
 */

import { API_BASE_URL } from "@/lib/api";

const activeExports = new Set<string>();

/**
 * Parse RFC 5987 / standard Content-Disposition filename safely.
 */
export function parseContentDispositionFilename(
	dispositionHeader: string | null,
	fallback: string,
): string {
	if (!dispositionHeader) {
		return fallback;
	}

	// Check RFC 5987 filename* (UTF-8)
	const rfc5987Match = dispositionHeader.match(/filename\*=UTF-8''([^;]+)/i);
	if (rfc5987Match?.[1]) {
		try {
			return decodeURIComponent(rfc5987Match[1]);
		} catch {
			// ignore and try standard filename
		}
	}

	// Check standard filename
	const standardMatch = dispositionHeader.match(/filename="?([^";]+)"?/i);
	if (standardMatch?.[1]) {
		return standardMatch[1].trim();
	}

	return fallback;
}

export interface ExportPackOptions {
	redactSecrets?: boolean;
	includeArtifacts?: boolean;
	includeSubagents?: boolean;
}

/**
 * Export complete session event log, subagents, and artifacts as a ZIP pack.
 */
export async function exportSessionZipPack(
	chatId: string,
	options: ExportPackOptions = {},
): Promise<void> {
	if (!chatId || activeExports.has(chatId)) {
		return;
	}

	activeExports.add(chatId);

	const {
		redactSecrets = true,
		includeArtifacts = true,
		includeSubagents = true,
	} = options;
	const params = new URLSearchParams({
		redact_secrets: String(redactSecrets),
		include_artifacts: String(includeArtifacts),
		include_subagents: String(includeSubagents),
	});

	const url = `${API_BASE_URL}/chats/${encodeURIComponent(chatId)}/export-pack?${params.toString()}`;

	try {
		// 1. HEAD Preflight
		const preflight = await fetch(url, {
			method: "HEAD",
			credentials: "include",
		});

		if (!preflight.ok) {
			if (preflight.status === 404) {
				throw new Error("会话不存在或已被删除，无法导出会话包");
			}
			throw new Error(`预检失败 (HTTP ${preflight.status})`);
		}

		// 2. GET Streaming download
		const response = await fetch(url, {
			method: "GET",
			credentials: "include",
		});

		if (!response.ok) {
			throw new Error(`导出会话包失败 (HTTP ${response.status})`);
		}

		const disposition = response.headers.get("content-disposition");
		const fallbackFilename = `session_${chatId.slice(0, 8)}.zip`;
		const filename = parseContentDispositionFilename(
			disposition,
			fallbackFilename,
		);

		const blob = await response.blob();
		const objectUrl = URL.createObjectURL(blob);
		const anchor = document.createElement("a");
		anchor.href = objectUrl;
		anchor.download = filename;
		document.body.appendChild(anchor);
		anchor.click();
		document.body.removeChild(anchor);
		URL.revokeObjectURL(objectUrl);
	} finally {
		activeExports.delete(chatId);
	}
}
