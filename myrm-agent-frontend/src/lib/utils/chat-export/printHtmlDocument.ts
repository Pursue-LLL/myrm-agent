/**
 * [INPUT] A complete HTML document (the export of one chat).
 * [OUTPUT] printHtmlDocument.
 * [POS] Opens the browser print dialog for an exported document from a hidden iframe, which a popup blocker does not stop.
 */

/** The load event of a document written into an iframe does not reach every engine, so the wait has a ceiling. */
const LOAD_WAIT_MS = 1500;
/** A document's fonts are embedded, so they are ready within milliseconds; the ceiling only keeps a broken one from blocking the print. */
const FONT_WAIT_MS = 3000;
/** Some browsers return from `print()` before the dialog is done with the document, so the iframe outlives the call. */
const FRAME_LIFETIME_MS = 3000;

/** Resolves once the fonts the document uses have loaded, or after `FONT_WAIT_MS`. */
async function fontsReady(doc: Document): Promise<void> {
  if (!('fonts' in doc)) {
    return;
  }
  let timer: ReturnType<typeof setTimeout> | undefined;
  const ceiling = new Promise<void>((resolve) => {
    timer = setTimeout(resolve, FONT_WAIT_MS);
  });
  await Promise.race([doc.fonts.ready, ceiling]);
  clearTimeout(timer);
}

export async function printHtmlDocument(html: string): Promise<void> {
  const iframe = document.createElement('iframe');
  iframe.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:0;height:0;border:none';
  document.body.appendChild(iframe);

  const iframeDoc = iframe.contentDocument ?? iframe.contentWindow?.document;
  if (!iframeDoc) {
    document.body.removeChild(iframe);
    throw new Error('Failed to access iframe document');
  }

  iframeDoc.open();
  iframeDoc.write(html);
  iframeDoc.close();

  await new Promise<void>((resolve) => {
    iframe.onload = () => resolve();
    setTimeout(resolve, LOAD_WAIT_MS);
  });
  // The fonts of a formula decode after the load event; printing before they are ready prints fallback glyphs.
  await fontsReady(iframeDoc);

  iframe.contentWindow?.print();
  setTimeout(() => document.body.removeChild(iframe), FRAME_LIFETIME_MS);
}
