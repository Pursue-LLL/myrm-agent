#!/usr/bin/env node
/**
 * [INPUT] /tmp/de_all_shells.json + locales/en.json + optional flat overrides JSON
 * [OUTPUT] updates locales/de.json leaf values for shell keys
 * [POS] Bulk de shell filler — applies Sie-Form translations from override map, then phrase rules.
 */

import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { collectTranslationShells, loadShellAllowlist, resolvePath } from './i18n-shell-core.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, '..');

const overridesPath = process.argv[2];
const overrides = overridesPath
  ? JSON.parse(readFileSync(resolve(overridesPath), 'utf-8'))
  : {};

const en = JSON.parse(readFileSync(resolve(rootDir, 'locales/en.json'), 'utf-8'));
const dePath = resolve(rootDir, 'locales/de.json');
const de = JSON.parse(readFileSync(dePath, 'utf-8'));
const allowlists = loadShellAllowlist(rootDir);

/** @type {Record<string, string>} */
const EXACT = {
  Backend: 'Server-Backend',
  Frontend: 'Client-Frontend',
  Version: 'Versionsnummer',
  Analyst: 'Analytiker',
  Reviewer: 'Prüfer',
  Worker: 'Mitarbeiter',
  Browser: 'Webbrowser',
  Normal: 'Normal',
  Team: 'Team',
  Tags: 'Schlagwörter',
  Online: 'Online',
  Name: 'Name',
  Persistent: 'Dauerhaft',
  Agent: 'Agent',
  Desktop: 'Desktop',
  Namespace: 'Namensraum',
  Catgirl: 'Catgirl',
  Hype: 'Hype',
  Kawaii: 'Kawaii',
  Noir: 'Noir',
  Shakespeare: 'Shakespeare',
  Surfer: 'Surfer',
  Lean: 'Schlank',
  Naked: 'Minimal',
  Secrets: 'Geheimnisse',
  Details: 'Details',
  Close: 'Schließen',
  Code: 'Code',
  Copied: 'Kopiert',
  'Basic Auth': 'Basic-Authentifizierung',
  'OAuth2 Client Credentials': 'OAuth2-Client-Anmeldedaten',
  'Open Settings': 'Einstellungen öffnen',
  'Capture Anyway': 'Trotzdem erfassen',
  'Screen capture failed': 'Bildschirmaufnahme fehlgeschlagen',
  'Maximum number of captures reached': 'Maximale Anzahl an Aufnahmen erreicht',
  'Accessibility permission required for text extraction': 'Bedienungshilfen-Berechtigung für Textextraktion erforderlich',
  'This app is excluded from screen capture for privacy protection.':
    'Diese App ist aus Datenschutzgründen von der Bildschirmaufnahme ausgeschlossen.',
  'Failed to load audio': 'Audio konnte nicht geladen werden',
  'Auto-saved version': 'Automatisch gespeicherte Version',
  'Copy Code': 'Code kopieren',
  'Copy File Path': 'Dateipfad kopieren',
  'File has been tampered with!': 'Datei wurde manipuliert!',
  'Created At': 'Erstellt am',
  'Deploy Now': 'Jetzt bereitstellen',
};

const WORD = [
  ['Failed to ', 'Fehler beim '],
  [' failed', ' fehlgeschlagen'],
  ['Please ', 'Bitte '],
  ['Click ', 'Klicken Sie '],
  ['Select ', 'Wählen Sie '],
  ['Enter ', 'Geben Sie '],
  ['Save ', 'Speichern '],
  ['Delete ', 'Löschen '],
  ['Cancel', 'Abbrechen'],
  ['Confirm', 'Bestätigen'],
  ['Settings', 'Einstellungen'],
  ['Loading', 'Wird geladen'],
  ['Error', 'Fehler'],
  ['Warning', 'Warnung'],
  ['Success', 'Erfolg'],
  ['Optional', 'Optional'],
  ['Required', 'Erforderlich'],
  ['Enabled', 'Aktiviert'],
  ['Disabled', 'Deaktiviert'],
  ['Search', 'Suche'],
  ['Import', 'Importieren'],
  ['Export', 'Exportieren'],
];

function setLeaf(obj, dottedPath, value) {
  const parts = dottedPath.split('.');
  let node = obj;
  for (let i = 0; i < parts.length - 1; i += 1) {
    const part = parts[i];
    if (typeof node[part] !== 'object' || node[part] === null || Array.isArray(node[part])) {
      node[part] = {};
    }
    node = node[part];
  }
  node[parts[parts.length - 1]] = value;
}

function ruleTranslate(enValue) {
  if (EXACT[enValue]) return EXACT[enValue];
  let out = enValue;
  for (const [from, to] of WORD) {
    if (out.includes(from)) out = out.split(from).join(to);
  }
  if (out !== enValue) return out;
  return null;
}

function translate(enValue, key) {
  if (overrides[key]) return overrides[key];
  if (overrides[enValue]) return overrides[enValue];
  const ruled = ruleTranslate(enValue);
  if (ruled && ruled !== enValue) return ruled;
  return null;
}

let shells = collectTranslationShells(en, de, allowlists);
let applied = 0;
let skipped = 0;

for (const { key, en: enValue } of shells) {
  const next = translate(enValue, key);
  if (!next || next === enValue) {
    skipped += 1;
    continue;
  }
  setLeaf(de, key, next);
  applied += 1;
}

writeFileSync(dePath, `${JSON.stringify(de, null, 2)}\n`);

shells = collectTranslationShells(en, de, allowlists);
console.log(`applied=${applied} skipped=${skipped} remaining_shells=${shells.length}`);
