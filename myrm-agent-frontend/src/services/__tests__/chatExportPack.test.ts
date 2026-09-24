import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	exportSessionZipPack,
	parseContentDispositionFilename,
} from "../chatExportPack";

describe("parseContentDispositionFilename", () => {
	it("parses RFC 5987 UTF-8 filename correctly", () => {
		const header =
			"attachment; filename=\"session_test.zip\"; filename*=UTF-8''session_%E6%B5%8B%E8%AF%95_123.zip";
		expect(parseContentDispositionFilename(header, "fallback.zip")).toBe(
			"session_测试_123.zip",
		);
	});

	it("parses standard ASCII filename when RFC 5987 is absent", () => {
		const header = 'attachment; filename="session_archive.zip"';
		expect(parseContentDispositionFilename(header, "fallback.zip")).toBe(
			"session_archive.zip",
		);
	});

	it("uses fallback when header is null or malformed", () => {
		expect(parseContentDispositionFilename(null, "default.zip")).toBe(
			"default.zip",
		);
		expect(parseContentDispositionFilename("attachment", "default.zip")).toBe(
			"default.zip",
		);
	});
});

describe("exportSessionZipPack", () => {
	const originalFetch = globalThis.fetch;
	const originalCreateObjectURL = URL.createObjectURL;
	const originalRevokeObjectURL = URL.revokeObjectURL;

	beforeEach(() => {
		globalThis.fetch = vi.fn();
		URL.createObjectURL = vi.fn(() => "blob:mock-url");
		URL.revokeObjectURL = vi.fn();
	});

	afterEach(() => {
		globalThis.fetch = originalFetch;
		URL.createObjectURL = originalCreateObjectURL;
		URL.revokeObjectURL = originalRevokeObjectURL;
		vi.restoreAllMocks();
	});

	it("performs HEAD preflight then GET streaming and triggers download", async () => {
		const mockBlob = new Blob(["mock-zip-bytes"], { type: "application/zip" });
		const mockFetch = vi
			.fn()
			.mockImplementation((_url: string, init?: RequestInit) => {
				if (init?.method === "HEAD") {
					return Promise.resolve({
						ok: true,
						status: 200,
					});
				}
				return Promise.resolve({
					ok: true,
					status: 200,
					headers: new Headers({
						"content-disposition":
							"attachment; filename=\"test.zip\"; filename*=UTF-8''test_%E5%BD%92%E6%A1%A3.zip",
					}),
					blob: () => Promise.resolve(mockBlob),
				});
			});
		globalThis.fetch = mockFetch as unknown as typeof fetch;

		const appendChildSpy = vi.spyOn(document.body, "appendChild");
		const removeChildSpy = vi.spyOn(document.body, "removeChild");

		await exportSessionZipPack("chat-123");

		expect(mockFetch).toHaveBeenCalledTimes(2);
		expect(mockFetch.mock.calls[0][1]?.method).toBe("HEAD");
		expect(mockFetch.mock.calls[1][1]?.method).toBe("GET");

		expect(appendChildSpy).toHaveBeenCalled();
		expect(removeChildSpy).toHaveBeenCalled();
	});

	it("aborts when HEAD preflight returns 404", async () => {
		const mockFetch = vi.fn().mockResolvedValue({
			ok: false,
			status: 404,
		});
		globalThis.fetch = mockFetch as unknown as typeof fetch;

		await expect(exportSessionZipPack("non-existent")).rejects.toThrow(
			"会话不存在或已被删除",
		);
		expect(mockFetch).toHaveBeenCalledTimes(1);
	});
});
