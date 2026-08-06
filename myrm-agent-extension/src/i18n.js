/**
 * Chrome extension i18n helper (MV3 _locales SSOT).
 *
 * [INPUT]
 * - Chrome `_locales/*/messages.json` (POS: extension UI copy catalog)
 *
 * [OUTPUT]
 * - msg: resolve localized string with optional substitution
 * - applyDocumentI18n: apply data-i18n attributes in popup HTML
 *
 * [POS] Extension UI localization adapter. Wraps chrome.i18n for popup, background, and clip client.
 */

/**
 * @param {string} key
 * @param {string | number | undefined} [substitution]
 * @returns {string}
 */
export function msg(key, substitution) {
  if (substitution === undefined) {
    return chrome.i18n.getMessage(key) || key;
  }
  return chrome.i18n.getMessage(key, String(substitution)) || key;
}

/**
 * Apply data-i18n attributes in the current document.
 * Supports data-i18n (text), data-i18n-placeholder, data-i18n-title.
 */
export function applyDocumentI18n(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) el.textContent = msg(key);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key && "placeholder" in el) el.placeholder = msg(key);
  });
  root.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const key = el.getAttribute("data-i18n-title");
    if (key) el.title = msg(key);
  });
}
