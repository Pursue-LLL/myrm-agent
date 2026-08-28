#!/usr/bin/env python3
"""Apply DPSEAG delegation locale keys + verify-i18n gap fixes (idempotent)."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locales"

DPSEAG: dict[str, dict[str, object]] = {
    "en": {
        "delegationPermissionsGuide": {
            "title": "About delegation permissions",
            "internalDesc": "Spins up a helper agent inside Myrm for research, audit, or parallel work.",
            "externalDesc": "Runs Claude Code, Codex, or another CLI program on your computer.",
            "bindingHint": "To limit which custom agents a main agent can spawn, configure sub-agent bindings under Settings → Agents → Subagents.",
        },
        "permissionTypes": {
            "spawn_subagent": "Internal sub-agent",
            "invoke_external_agent": "External CLI agent",
        },
    },
    "zh": {
        "delegationPermissionsGuide": {
            "title": "委派权限说明",
            "internalDesc": "在 Myrm 内启动辅助智能体，用于调研、审计或并行任务。",
            "externalDesc": "在本机运行 Claude Code、Codex 或其他 CLI 程序。",
            "bindingHint": "如需限制主智能体可派生的自定义子智能体，请在「设置 → 智能体 → 子智能体」中配置绑定。",
        },
        "permissionTypes": {
            "spawn_subagent": "内部子智能体",
            "invoke_external_agent": "外部 CLI 智能体",
        },
    },
    "zh-TW": {
        "delegationPermissionsGuide": {
            "title": "委派權限說明",
            "internalDesc": "在 Myrm 內啟動輔助智慧體，用於調研、審計或並行任務。",
            "externalDesc": "在本機執行 Claude Code、Codex 或其他 CLI 程式。",
            "bindingHint": "如需限制主智慧體可派生的自訂子智慧體，請在「設定 → 智慧體 → 子智慧體」中設定綁定。",
        },
        "permissionTypes": {
            "spawn_subagent": "內部子智慧體",
            "invoke_external_agent": "外部 CLI 智慧體",
        },
    },
    "ja": {
        "delegationPermissionsGuide": {
            "title": "委任権限について",
            "internalDesc": "Myrm 内で調査・監査・並列作業用の補助エージェントを起動します。",
            "externalDesc": "Claude Code、Codex などの CLI プログラムをお使いのコンピュータで実行します。",
            "bindingHint": "メインエージェントが起動できるカスタムエージェントを制限するには、「設定 → エージェント → サブエージェント」でバインディングを設定してください。",
        },
        "permissionTypes": {
            "spawn_subagent": "内部サブエージェント",
            "invoke_external_agent": "外部 CLI エージェント",
        },
    },
    "ko": {
        "delegationPermissionsGuide": {
            "title": "위임 권한 안내",
            "internalDesc": "Myrm 내부에서 조사, 감사 또는 병렬 작업용 보조 에이전트를 실행합니다.",
            "externalDesc": "Claude Code, Codex 또는 다른 CLI 프로그램을 사용자 컴퓨터에서 실행합니다.",
            "bindingHint": "메인 에이전트가 실행할 수 있는 사용자 정의 에이전트를 제한하려면 설정 → 에이전트 → 서브에이전트에서 바인딩을 구성하세요.",
        },
        "permissionTypes": {
            "spawn_subagent": "내부 서브 에이전트",
            "invoke_external_agent": "외부 CLI 에이전트",
        },
    },
    "de": {
        "delegationPermissionsGuide": {
            "title": "Informationen zu Delegierungsberechtigungen",
            "internalDesc": "Startet einen Hilfsagenten innerhalb von Myrm für Recherche, Prüfung oder parallele Arbeit.",
            "externalDesc": "Führt Claude Code, Codex oder ein anderes CLI-Programm auf Ihrem Computer aus.",
            "bindingHint": "Um festzulegen, welche benutzerdefinierten Agenten ein Hauptagent starten darf, konfigurieren Sie Subagent-Bindings unter Einstellungen → Agenten → Subagenten.",
        },
        "permissionTypes": {
            "spawn_subagent": "Interner Sub-Agent",
            "invoke_external_agent": "Externer CLI-Agent",
        },
    },
}

FONT: dict[str, dict[str, str]] = {
    "ja": {
        "popularDeveloperFonts": "人気の開発者向けフォント",
        "scanAllSystemFonts": "ローカルインストールフォントをスキャン（Local Font API）",
        "scanningFonts": "システムフォントをスキャン中...",
        "allInstalledFonts": "すべてのローカルフォント",
        "selectFontPlaceholder": "ローカルインストールフォントから選択...",
        "customFontPlaceholder": "または任意のローカルフォント名を入力（例: JetBrains Mono）",
        "apply": "適用",
        "activeCustomFont": "適用中のカスタムフォント",
        "resetToDefault": "リセット",
    },
    "ko": {
        "popularDeveloperFonts": "인기 개발자 폰트",
        "scanAllSystemFonts": "로컬 설치 폰트 스캔 (Local Font API)",
        "scanningFonts": "시스템 폰트 스캔 중...",
        "allInstalledFonts": "모든 로컬 폰트",
        "selectFontPlaceholder": "로컬 설치 폰트에서 선택...",
        "customFontPlaceholder": "또는 로컬 폰트 이름 입력 (예: JetBrains Mono)",
        "apply": "적용",
        "activeCustomFont": "적용된 사용자 지정 폰트",
        "resetToDefault": "초기화",
    },
    "de": {
        "popularDeveloperFonts": "Beliebte Entwicklerschriften",
        "scanAllSystemFonts": "Installierte lokale Schriften scannen (Local Font API)",
        "scanningFonts": "Systemschriften werden gescannt...",
        "allInstalledFonts": "Alle lokalen Schriften",
        "selectFontPlaceholder": "Aus lokal installierten Schriften wählen...",
        "customFontPlaceholder": "Oder lokalen Schriftnamen eingeben (z. B. JetBrains Mono)",
        "apply": "Anwenden",
        "activeCustomFont": "Aktive benutzerdefinierte Schrift",
        "resetToDefault": "Zurücksetzen",
    },
    "zh-TW": {
        "popularDeveloperFonts": "常用開發者字體",
        "scanAllSystemFonts": "掃描本機已安裝字體（Local Font API）",
        "scanningFonts": "正在掃描系統字體...",
        "allInstalledFonts": "所有本機字體",
        "selectFontPlaceholder": "從本機已安裝字體中選擇...",
        "customFontPlaceholder": "或輸入任意本機字體名（如 JetBrains Mono）",
        "apply": "套用",
        "activeCustomFont": "目前套用字體",
        "resetToDefault": "恢復預設",
    },
}

REPLAY: dict[str, str] = {
    "ja": "前の音声を再生",
    "ko": "이전 음성 다시 재생",
    "de": "Letzte Sprachausgabe wiederholen",
    "zh-TW": "重播上一句語音",
}

DE_GAP: dict[str, str] = {
    "agent.busyInputMode": "Eingabeverhalten bei laufender Ausführung",
    "agent.busyInputModeDesc": "Standardaktion beim Senden einer Nachricht, während der Agent arbeitet.",
    "agent.busyInputRedirect": "Umleiten",
    "agent.busyInputSteer": "Steuern",
    "agent.busyInputQueue": "Warteschlange",
    "agent.browserConfig": "Browser-Konfiguration",
    "agent.browserConfigDesc": "Browserquelle, Dialoge und Sitzungsaufzeichnung konfigurieren. Anti-Bot-Stealth wird automatisch aktiviert, wenn das Browser-Tool eingeschaltet ist.",
    "agent.dialogPolicy.label": "Dialogbehandlung",
    "agent.sessionRecording.label": "Sitzungsaufzeichnung",
    "agent.notifyTargetsScopeHint": "Nur Agent-Push: Der Agent darf diese Ziele während einer Aufgabe benachrichtigen. Systemwarnungen (OAuth, Budget, Pairing) nutzen Einstellungen → Benachrichtigungszustellung.",
    "agent.notifySelectRecipient": "Empfänger auswählen",
    "agent.notifyManualRecipient": "ID manuell eingeben…",
    "agent.noPairingsForNotify": "Kontakt in den Kanaleinstellungen koppeln oder Empfänger-ID manuell eingeben.",
    "agent.dismissRebindHint": "Schließen",
    "agent.allowDiscovery.title": "Entdeckung und Delegation durch andere Agenten erlauben",
    "agent.allowDiscovery.description": "Wenn aktiviert, können andere Agenten diesen Agenten bei der automatischen Teambildung entdecken und aufrufen. Wenn deaktiviert, wird er nicht automatisch entdeckt, kann aber weiterhin explizit mit @ referenziert werden.",
    "agent.readiness.ready": "Bereit",
    "agent.readiness.warning": "Einige Konfigurationen erfordern Aufmerksamkeit",
    "agent.readiness.blocked": "Agent kann nicht ausgeführt werden — Korrektur erforderlich",
    "agent.idleCompact.minutes": "Leerlaufdauer (Minuten)",
    "agent.idleCompact.minutesDesc": "Wartezeit nach der letzten Nachricht, bevor die automatische Komprimierung startet.",
    "agent.idleCompact.hint": "Standardmäßig aus. Ersetzt weder manuelle noch automatische Komprimierung bei hoher Token-Nutzung.",
    "common.forkBranch": "Zweig abzweigen",
}


def set_path(data: dict[str, object], dotted: str, value: object) -> None:
    parts = dotted.split(".")
    cur: dict[str, object] = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, path)


def main() -> None:
    for lang in ("en", "zh", "zh-TW", "ja", "ko", "de"):
        path = LOCALES / f"{lang}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        sec = data.setdefault("settings", {}).setdefault("securityPolicy", {})
        sec.update(DPSEAG[lang])
        if lang in FONT:
            data.setdefault("settings", {}).setdefault("fontOptions", {}).update(FONT[lang])
            data.setdefault("companion", {}).setdefault("sprite", {})["replayVoice"] = REPLAY[lang]
        if lang == "de":
            agent = data.setdefault("agent", {})
            if isinstance(agent.get("busyInputMode"), dict):
                agent.pop("busyInputMode", None)
            for dotted, value in DE_GAP.items():
                set_path(data, dotted, value)
        atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        print(f"patched {lang}")


if __name__ == "__main__":
    main()
