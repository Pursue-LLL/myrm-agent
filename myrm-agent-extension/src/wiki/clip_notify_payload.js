/**
 * Pure clip notification payload resolution (testable without chrome.* APIs).
 */

/**
 * @typedef {"success" | "success_no_origin" | "duplicate" | "security" | "error"} ClipNotifyKind
 */

/**
 * @param {ClipNotifyKind} kind
 * @param {{ openUrl?: string, errorMessage?: string }} options
 * @param {(key: string) => string} translate
 * @returns {{ titleKey: string, body: string }}
 */
export function resolveClipNotifyPayload(kind, options, translate) {
  const openUrl = options.openUrl ?? "";
  const errorMessage = options.errorMessage ?? "";

  switch (kind) {
    case "success":
      return {
        titleKey: "notifyClipSuccessTitle",
        body: translate("notifyClipSuccessBody"),
      };
    case "success_no_origin":
      return {
        titleKey: "notifyClipSuccessTitle",
        body: translate("clipSavedWithoutOrigin"),
      };
    case "duplicate":
      return {
        titleKey: "notifyClipDuplicateTitle",
        body: openUrl
          ? translate("notifyClipDuplicateBody")
          : translate("notifyClipDuplicateBodyNoLink"),
      };
    case "security":
      return {
        titleKey: "notifyClipSecurityTitle",
        body: openUrl
          ? translate("notifyClipSecurityBody")
          : translate("notifyClipSecurityBodyNoLink"),
      };
    default:
      return {
        titleKey: "notifyClipErrorTitle",
        body: errorMessage.trim() || translate("errClipFailed"),
      };
  }
}

/**
 * @param {string} openUrl
 * @returns {boolean}
 */
export function shouldStoreClipNotifyDeepLink(openUrl) {
  return Boolean(openUrl && openUrl.trim());
}
