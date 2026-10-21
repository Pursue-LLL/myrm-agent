#!/usr/bin/env node
/** Fix remaining de translation shells + glossary forbidden violations. */
import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { collectTranslationShells, loadShellAllowlist } from './i18n-shell-core.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, '..');
const dePath = resolve(rootDir, 'locales/de.json');
const en = JSON.parse(readFileSync(resolve(rootDir, 'locales/en.json'), 'utf-8'));
let de = JSON.parse(readFileSync(dePath, 'utf-8'));
const allow = loadShellAllowlist(rootDir);

function setLeaf(obj, path, value) {
  const parts = path.split('.');
  let node = obj;
  for (let i = 0; i < parts.length - 1; i += 1) {
    const p = parts[i];
    if (typeof node[p] !== 'object' || node[p] === null || Array.isArray(node[p])) node[p] = {};
    node = node[p];
  }
  node[parts[parts.length - 1]] = value;
}

/** @type {Record<string, string>} */
const EXACT = {
  Agent: 'KI-Agent',
  Aliyun: 'Alibaba Cloud',
  Audio: 'Ton',
  Backend: 'Server-Backend',
  'Backend offline': 'Server offline',
  Benchmark: 'Leistungstest',
  Browser: 'Webbrowser',
  Chaos: 'Chaos-Level',
  Chats: 'Unterhaltungen',
  China: 'China-Region',
  'China (iFlytek SkillHub)': 'China (iFlytek SkillHub)',
  Code: 'Quellcode',
  Design: 'Gestaltung',
  Detail: 'Einzelheiten',
  Desktop: 'Desktop-App',
  Diff: 'Unterschied',
  Domain: 'Domäne',
  Ellipse: 'Ellipsenform',
  Evolution: 'Weiterentwicklung',
  Filter: 'Filterkriterium',
  Frontend: 'Client-Frontend',
  Global: 'Globaler Bereich',
  Graph: 'Beziehungsgraph',
  Hype: 'Hype-Stil',
  Index: 'Indizierung',
  'International (clawhub.ai)': 'International (clawhub.ai)',
  Kawaii: 'Kawaii-Stil',
  Layout: 'Layout-Ansicht',
  Limit: 'Obergrenze',
  Links: 'Verknüpfungen',
  Live: 'Live-Modus',
  Migration: 'Datenmigration',
  Name: 'Bezeichnung',
  'Name:': 'Bezeichnung:',
  Noir: 'Noir-Stil',
  Normal: 'Normalmodus',
  Offline: 'Nicht erreichbar',
  Online: 'Erreichbar',
  Optional: 'Optional',
  optional: 'optional',
  Orchestrator: 'Orchestrator-Rolle',
  Original: 'Originalversion',
  Phase: 'Ausführungsphase',
  Pipeline: 'Pipeline-Ansicht',
  Prompt: 'Eingabeaufforderung',
  Region: 'Region',
  Routine: 'Routine-Modus',
  Server: 'Serverinstanz',
  Shakespeare: 'Shakespeare-Stil',
  Snark: 'Snark-Level',
  Standard: 'Standardmodus',
  Surfer: 'Surfer-Stil',
  System: 'Systemeinstellung',
  Team: 'Team-Modus',
  Tests: 'Prüfungen',
  Text: 'Textinhalt',
  Token: 'Zugriffstoken',
  Transport: 'Übertragungsart',
  Triage: 'Eingangsprüfung',
  Upgrade: 'Upgrade',
  Veto: 'Veto-Regel',
  Version: 'Versionsnummer',
  Video: 'Videodatei',
  Videos: 'Videodateien',
  Web: 'Web-Bereich',
  TestConnect: 'Verbindung testen',
};

function translateChannel(enVal) {
  if (enVal.endsWith('ConnectFailed')) return `${enVal.replace(/ ConnectFailed$/, '')}-Verbindung fehlgeschlagen`;
  if (enVal.endsWith('ConnectSuccess')) return `${enVal.replace(/ ConnectSuccess$/, '')}-Verbindung erfolgreich`;
  if (enVal.endsWith('ConfigurationFailed')) {
    return `${enVal.replace(/^Save/, '').replace(/ConfigurationFailed$/, '')}-Konfiguration konnte nicht gespeichert werden`;
  }
  if (enVal === 'SaveGroupSettingsFailed') return 'Gruppeneinstellungen konnten nicht gespeichert werden';
  if (enVal === 'Historical conversation content and context') return 'Historische Gesprächsinhalte und Kontext';
  if (enVal.startsWith('For mTLS:')) {
    return 'Für mTLS: Client-Zertifikat bereitstellen und optional einen separaten Schlüssel. Pfade unterstützen ~-Expansion.';
  }
  return null;
}

function translateShell(enVal) {
  return EXACT[enVal] ?? translateChannel(enVal);
}

const glossaryFixes = {
  'settings.dlq.retryAllConfirmDesc': 'Dies wiederholt alle fehlgeschlagenen Zustellungen. Fortfahren?',
  'memory.noMemoriesDesc': 'Der Agent hat noch nichts über Sie gelernt. Starten Sie ein Gespräch!',
  'auth.oauth.title': 'Melden Sie sich an, um fortzufahren',
  'companion.thinking.23': 'Einen Moment…',
  'companion.evolution.reactions.snark.error.0': 'Das hat nicht geklappt. Versuchen Sie es erneut.',
  'companion.evolution.reactions.snark.error.1': 'Fehler. Ihr Versuch war… mutig.',
  'companion.evolution.reactions.snark.error.3': 'Das war nicht Ihr bester Moment.',
  'companion.evolution.reactions.snark.general.1': 'Interessante Wahl.',
  'companion.evolution.reactions.patience.success.2': 'Gut gemacht — Sie haben es geschafft.',
  'companion.evolution.reactions.patience.general.0': 'Ich warte auf Sie.',
};

let shells = collectTranslationShells(en, de, allow);
let fixed = 0;
for (const { key, en: enVal } of shells) {
  const next = translateShell(enVal);
  if (next && next !== enVal) {
    setLeaf(de, key, next);
    fixed += 1;
  }
}
for (const [key, value] of Object.entries(glossaryFixes)) {
  setLeaf(de, key, value);
}

writeFileSync(dePath, `${JSON.stringify(de, null, 2)}\n`);
de = JSON.parse(readFileSync(dePath, 'utf-8'));
shells = collectTranslationShells(en, de, allow);
console.log(`shell_fixes=${fixed} remaining_shells=${shells.length}`);
