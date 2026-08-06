/**
 * Extension wiki clip REST client (capture → multipart POST → job poll).
 */

import { buildWikiClipPostUrl, wikiHttpBaseFromServerUrl } from "./deep_links.js";

async function ensureClipContentScript(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["src/content/clip.js"],
  });
}

export async function pollClipJob(baseUrl, token, jobId) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  for (let i = 0; i < 60; i += 1) {
    const resp = await fetch(`${baseUrl.replace(/\/$/, "")}/api/v1/wiki/clip/${jobId}`, { headers });
    if (!resp.ok) throw new Error(`Clip status failed (${resp.status})`);
    const data = await resp.json();
    if (data.state === "succeeded") return data;
    if (data.state === "failed") throw new Error(data.error_message || "Clip failed");
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("Clip timed out");
}

/**
 * @returns {Promise<{ ok: boolean, conflict?: boolean, security_blocked?: boolean, relative_path?: string, error?: string }>}
 */
export async function submitClipToWiki(tab, mode, clipConfig) {
  const { serverUrl, authToken, clipAgentId } = clipConfig;
  if (!serverUrl) {
    return { ok: false, error: "Configure server URL in extension popup" };
  }
  try {
    await ensureClipContentScript(tab.id);
    const captured = await chrome.tabs.sendMessage(tab.id, { type: "clip_to_wiki", mode });
    if (!captured?.ok) throw new Error(captured?.error || "Capture failed");
    const payload = captured.payload;
    const form = new FormData();
    form.append("source_url", payload.source_url);
    form.append("title", payload.title);
    form.append("clip_mode", payload.clip_mode);
    form.append("html", payload.html);
    form.append("markdown", payload.markdown || "");
    form.append("folder_path", payload.folder_path || "");
    form.append("queue_compile", payload.queue_compile ? "true" : "false");
    const assetUrls = (payload.assets || []).map((a) => a.source_url);
    form.append("asset_urls", JSON.stringify(assetUrls));
    for (const asset of payload.assets || []) {
      const blob = new Blob([asset.data], { type: asset.content_type });
      form.append("asset_files", blob, "asset.bin");
    }
    const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};
    const postResp = await fetch(buildWikiClipPostUrl(serverUrl, clipAgentId), {
      method: "POST",
      headers,
      body: form,
    });
    if (!postResp.ok) {
      const text = await postResp.text();
      throw new Error(text || `Clip upload failed (${postResp.status})`);
    }
    const accepted = await postResp.json();
    const result = await pollClipJob(
      wikiHttpBaseFromServerUrl(serverUrl),
      authToken,
      accepted.job_id,
    );
    if (result.conflict) {
      return { ok: false, conflict: true, error: "Already clipped — open Duplicate Review in Settings Wiki" };
    }
    if (result.security_blocked) {
      return { ok: false, security_blocked: true, error: "Clip blocked by security scan" };
    }
    return { ok: true, relative_path: result.relative_path || "" };
  } catch (err) {
    return { ok: false, error: err?.message || String(err) };
  }
}
