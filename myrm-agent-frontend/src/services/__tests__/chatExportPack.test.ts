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
	const originalDocument = globalThis.document;

	beforeEach(() => {
		globalThis.fetch = vi.fn();
		URL.createObjectURL = vi.fn(() => "blob:mock-url");
		URL.revokeObjectURL = vi.fn();

		if (typeof document === "undefined") {
			const mockElement = { click: vi.fn(), setAttribute: vi.fn(), style: {} };
			globalThis.document = {
				createElement: vi.fn().mockReturnValue(mockElement),
				body: {
					appendChild: vi.fn(),
					removeChild: vi.fn(),
				},
			} as unknown as Document;
		}
	});

	afterEach(() => {
		globalThis.fetch = originalFetch;
		URL.createObjectURL = originalCreateObjectURL;
		URL.revokeObjectURL = originalRevokeObjectURL;
		if (originalDocument === undefined) {
			delete (globalThis as { document?: unknown }).document;
		} else {
			globalThis.document = originalDocument;
		}
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

	it("ignores concurrent duplicate export calls for the same session", async () => {
		let resolvePreflight: ((value: Response) => void) | undefined;
		const preflightPromise = new Promise<Response>((resolve) => {
			resolvePreflight = resolve;
		});

		const mockBlob = new Blob(["zip-data"], { type: "application/zip" });
		const mockFetch = vi
			.fn()
			.mockImplementation((_url: string, init?: RequestInit) => {
				if (init?.method === "HEAD") {
					return preflightPromise;
				}
				return Promise.resolve({
					ok: true,
					status: 200,
					headers: new Headers({
						"content-disposition": 'attachment; filename="dup.zip"',
					}),
					blob: () => Promise.resolve(mockBlob),
				});
			});
		globalThis.fetch = mockFetch as unknown as typeof fetch;

		// 触发第一次导出（进入等待 preflight 挂起）
		const call1 = exportSessionZipPack("chat-duplicate");
		// 紧接着触发第二次导出（应当被 activeExports 拦截而直接返回）
		const call2 = exportSessionZipPack("chat-duplicate");

		// 释放第一次请求
		if (resolvePreflight) {
			resolvePreflight(
				new Response(null, {
					status: 200,
					headers: { "content-type": "application/zip" },
				}),
			);
		}

		await Promise.all([call1, call2]);

		// mockFetch 总共只应该被调用 2 次（1 次 HEAD，1 次 GET），第二次调用被静默丢弃
		expect(mockFetch).toHaveBeenCalledTimes(2);
	});

	it("does nothing when chatId is empty string", async () => {
		const mockFetch = vi.fn();
		globalThis.fetch = mockFetch as unknown as typeof fetch;

		await exportSessionZipPack("");
		expect(mockFetch).not.toHaveBeenCalled();
	});

	it("releases mutex lock on error so subsequent exports can retry", async () => {
		const mockFetch = vi
			.fn()
			.mockResolvedValueOnce({
				ok: false,
				status: 500,
			})
			.mockImplementation((_url: string, init?: RequestInit) => {
				if (init?.method === "HEAD") {
					return Promise.resolve({ ok: true, status: 200 });
				}
				return Promise.resolve({
					ok: true,
					status: 200,
					headers: new Headers({
						"content-disposition": 'attachment; filename="retry.zip"',
					}),
					blob: () =>
						Promise.resolve(
							new Blob(["retry-data"], { type: "application/zip" }),
						),
				});
			});
		globalThis.fetch = mockFetch as unknown as typeof fetch;

		// 第一次调用因 500 报错
		await expect(exportSessionZipPack("chat-retry")).rejects.toThrow("预检失败");
		expect(mockFetch).toHaveBeenCalledTimes(1);

		// 第二次重试调用，应正常放行并成功
		await exportSessionZipPack("chat-retry");
		expect(mockFetch).toHaveBeenCalledTimes(3); // 1 失败 + 1 成功 HEAD + 1 成功 GET
	});
});

