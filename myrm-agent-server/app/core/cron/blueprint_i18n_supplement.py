"""Supplemental UI locales (ja/de/ko) for cron blueprint catalog fields.

Merged into ``BUILTIN_BLUEPRINTS`` at import time so the ``/cron/blueprints`` API
serves five-locale title/description/prompt_template without duplicating en/zh in
this file.

[POS]
ja/de/ko supplemental strings for cron blueprint SSOT.
"""

from __future__ import annotations

from typing import TypedDict


class BlueprintLocaleSupplement(TypedDict):
    title: dict[str, str]
    description: dict[str, str]
    prompt_template: dict[str, str]


BLUEPRINT_UI_LOCALES: tuple[str, ...] = ("en", "zh", "ja", "de", "ko")

SUPPLEMENTAL_BY_ID: dict[str, BlueprintLocaleSupplement] = {
    "morning_briefing": {
        "title": {
            "ja": "モーニングブリーフィング",
            "de": "Morgen-Briefing",
            "ko": "모닝 브리핑",
        },
        "description": {
            "ja": "ニュース、天気、予定のデイリーダイジェスト",
            "de": "Tägliche Zusammenfassung von Nachrichten, Wetter und Terminen",
            "ko": "뉴스, 날씨, 일정 하이라이트 데일리 다이제스트",
        },
        "prompt_template": {
            "ja": (
                "簡潔なモーニングブリーフィングを提供してください：重要ニュースの見出し、"
                "天気の見通し、今日の重要なリマインダー。短く実行可能に。"
            ),
            "de": (
                "Erstelle ein kompaktes Morgen-Briefing: wichtige Schlagzeilen, "
                "Wetterausblick und wichtige Erinnerungen für heute. Kurz und umsetzbar."
            ),
            "ko": (
                "간결한 모닝 브리핑을 제공하세요: 주요 뉴스 헤드라인, 날씨 전망, "
                "오늘의 중요 알림. 짧고 실행 가능하게."
            ),
        },
    },
    "weekly_review": {
        "title": {
            "ja": "週次レビュー",
            "de": "Wochenrückblick",
            "ko": "주간 리뷰",
        },
        "description": {
            "ja": "週末の成果まとめと来週の計画",
            "de": "Wochenend-Zusammenfassung mit Erfolgen und Plänen",
            "ko": "주말 성과 요약 및 다음 주 계획",
        },
        "prompt_template": {
            "ja": (
                "包括的な週次レビューを実施：今週の主要な成果、直面した障害や課題、"
                "来週の優先事項の提案。カテゴリ別に整理。"
            ),
            "de": (
                "Führe einen umfassenden Wochenrückblick durch: wichtige Erfolge, "
                "Blocker oder Herausforderungen, Prioritäten für die kommende Woche. "
                "Nach Kategorien ordnen."
            ),
            "ko": (
                "포괄적인 주간 리뷰를 진행하세요: 주요 성과, 직면한 장애물이나 과제, "
                "다음 주 우선순위 제안. 카테고리별로 정리."
            ),
        },
    },
    "custom_reminder": {
        "title": {
            "ja": "カスタムリマインダー",
            "de": "Eigene Erinnerung",
            "ko": "맞춤 알림",
        },
        "description": {
            "ja": "パーソナライズされたメッセージの日次リマインダー",
            "de": "Tägliche Erinnerung mit persönlicher Nachricht",
            "ko": "개인화된 메시지로 매일 알림",
        },
        "prompt_template": {
            "ja": "リマインド：{message}",
            "de": "Erinnere mich: {message}",
            "ko": "알림: {message}",
        },
    },
    "news_digest": {
        "title": {
            "ja": "ニュースダイジェスト",
            "de": "Nachrichtenübersicht",
            "ko": "뉴스 다이제스트",
        },
        "description": {
            "ja": "選択したトピックの厳選ニュースまとめ",
            "de": "Kuratierte Nachrichtenzusammenfassung zum gewählten Thema",
            "ko": "선택한 주제의 큐레이션된 뉴스 요약",
        },
        "prompt_template": {
            "ja": (
                "「{topic}」に関する最新ニュースと動向を検索し、簡潔なダイジェストを作成。"
                "3〜5件の要点と短い要約を含め、速報と重要な進展を優先。"
            ),
            "de": (
                "Suche im Web und erstelle eine kompakte Übersicht der neuesten Nachrichten "
                "zu: {topic}. 3–5 Kernpunkte mit kurzen Zusammenfassungen. "
                "Breaking News und wichtige Entwicklungen priorisieren."
            ),
            "ko": (
                "웹에서 {topic}에 관한 최신 뉴스와 동향을 검색해 간결한 다이제스트를 작성하세요. "
                "3–5개 핵심 항목과 짧은 요약 포함. 속보와 중요 진전 우선."
            ),
        },
    },
    "evening_winddown": {
        "title": {
            "ja": "イブニング振り返り",
            "de": "Abend-Rückblick",
            "ko": "저녁 회고",
        },
        "description": {
            "ja": "一日の振り返りとリラクゼーション提案",
            "de": "Tagesrückblick und Entspannungsvorschläge",
            "ko": "하루 리뷰 및 휴식 제안",
        },
        "prompt_template": {
            "ja": (
                "穏やかなイブニングサマリーを提供：今日のハイライトの簡潔な振り返り、"
                "明日の予定と優先事項のプレビュー、リラックスのヒントや励ましの一言。"
            ),
            "de": (
                "Gib eine beruhigende Abendzusammenfassung: kurze Highlights des Tages, "
                "Vorschau auf morgen, Entspannungstipp oder inspirierender Gedanke."
            ),
            "ko": (
                "차분한 저녁 요약을 제공하세요: 오늘 하이라이트 간략 회고, "
                "내일 일정과 우선순위 미리보기, 휴식 팁이나 격려 한마디."
            ),
        },
    },
    "local_health_check": {
        "title": {
            "ja": "ローカルヘルスチェック",
            "de": "Lokaler Gesundheitscheck",
            "ko": "로컬 상태 점검",
        },
        "description": {
            "ja": "CPU・メモリ・ディスクの状態を監視",
            "de": "Überwacht CPU, Speicher und Festplattenstatus",
            "ko": "CPU, 메모리, 디스크 상태 모니터링",
        },
        "prompt_template": {
            "ja": (
                "システムの健康状態を確認し、CPU・メモリ・ディスクと異常サービスを報告。"
                "注意が必要な問題のみ——正常なら簡潔に。"
            ),
            "de": (
                "Prüfe den aktuellen Systemzustand. Melde CPU-, Speicher- und "
                "Festplattenauslastung sowie nicht gesunde Dienste. "
                "Bei normalem Zustand kurz halten."
            ),
            "ko": (
                "현재 시스템 상태를 확인하세요. CPU, 메모리, 디스크 사용량과 "
                "비정상 서비스를 보고하세요. 정상이면 간단히 요약."
            ),
        },
    },
    "competitor_watch": {
        "title": {
            "ja": "競合ウォッチ",
            "de": "Wettbewerber-Monitoring",
            "ko": "경쟁사 모니터링",
        },
        "description": {
            "ja": "競合のニュースと製品更新を毎週追跡",
            "de": "Wöchentliche Nachrichten und Produktupdates von Wettbewerbern",
            "ko": "경쟁사 뉴스와 제품 업데이트를 주간 추적",
        },
        "prompt_template": {
            "ja": (
                "次の競合の最新ニュース・製品更新・発表を検索：{competitors}。"
                "新機能、価格変更、提携、資金調達、注目ブログを含む簡潔な競合ブリーフィング。"
                "戦略に影響しうる項目を強調。"
            ),
            "de": (
                "Suche im Web nach neuesten Nachrichten und Produktupdates von: {competitors}. "
                "Kurzes Wettbewerbsbriefing mit Features, Preisen, Partnerschaften, "
                "Finanzierung und Blogs. Strategisch relevante Punkte hervorheben."
            ),
            "ko": (
                "다음 경쟁사의 최신 뉴스, 제품 업데이트, 발표를 검색하세요: {competitors}. "
                "신기능, 가격 변경, 파트너십, 투자, 주목 블로그를 포함한 간결한 브리핑. "
                "전략에 영향을 줄 항목 강조."
            ),
        },
    },
    "habit_checkin": {
        "title": {
            "ja": "習慣チェックイン",
            "de": "Gewohnheits-Check-in",
            "ko": "습관 체크인",
        },
        "description": {
            "ja": "習慣とルーティンの毎日の記録リマインダー",
            "de": "Tägliche Erinnerung, Gewohnheiten und Routinen zu tracken",
            "ko": "습관과 루틴을 매일 기록하도록 알림",
        },
        "prompt_template": {
            "ja": (
                "毎日の習慣チェックインです。{habits} の進捗を確認し、"
                "励ましと継続記録をお願いします。漏れがあれば優しくリマインド。"
            ),
            "de": (
                "Zeit für den täglichen Gewohnheits-Check-in! Frage nach Fortschritt bei: "
                "{habits}. Ermutigung und Serie verfolgen. Bei Lücken sanft erinnern."
            ),
            "ko": (
                "매일 습관 체크인 시간입니다. {habits} 진행 상황을 물어보고 "
                "격려와 연속 기록을 추적하세요. 누락 시 부드럽게 알려주세요."
            ),
        },
    },
    "learn_daily": {
        "title": {
            "ja": "毎日の学習",
            "de": "Tägliches Lernen",
            "ko": "매일 학습",
        },
        "description": {
            "ja": "毎日キュレーションされた学習トピックを配信",
            "de": "Täglich ein kuratiertes Lernthema erhalten",
            "ko": "매일 큐레이션된 학습 주제 제공",
        },
        "prompt_template": {
            "ja": (
                "{subject} について有益な内容を2–3段落で教え、実践例を含めてください。"
                "分かりやすく、かつ浅薄でない説明に。"
            ),
            "de": (
                "Bringe etwas Nützliches über: {subject}. Ein Konzept in 2–3 Absätzen "
                "mit praktischem Beispiel. Zugänglich, aber nicht oberflächlich."
            ),
            "ko": (
                "{subject}에 대해 유익한 내용을 2–3문단으로 설명하고 실용 예시를 포함하세요. "
                "이해하기 쉽지만 피상적이지 않게."
            ),
        },
    },
    "social_media_watch": {
        "title": {
            "ja": "ソーシャルメディア監視",
            "de": "Social-Media-Monitoring",
            "ko": "소셜 미디어 모니터링",
        },
        "description": {
            "ja": "ブランド言及・感情変化・トレンドを監視",
            "de": "Markenerwähnungen, Stimmungswechsel und Trends überwachen",
            "ko": "브랜드 언급, 감성 변화, 트렌드 추적",
        },
        "prompt_template": {
            "ja": (
                "プラットフォーム {platforms} で {brand} の言及を監視。キーワード {keywords}。"
                "過去24時間の投稿を収集し、感情分類・トレンド検出・構造化レポートを作成。"
                "即時対応が必要な強いネガティブをフラグ。"
            ),
            "de": (
                "Überwache Plattformen {platforms} auf Erwähnungen von: {brand}. "
                "Schlüsselwörter: {keywords}. Posts der letzten 24h sammeln, "
                "Sentiment klassifizieren, Trends erkennen, strukturierten Bericht erstellen. "
                "Starke Negative sofort markieren."
            ),
            "ko": (
                "플랫폼 {platforms}에서 {brand} 언급을 모니터링하세요. 키워드: {keywords}. "
                "최근 24시간 게시물 수집, 감성 분류, 트렌드 감지, 구조화 보고서 작성. "
                "즉시 대응이 필요한 강한 부정 게시물 표시."
            ),
        },
    },
    "read_it_later": {
        "title": {
            "ja": "後で読む取り込み",
            "de": "Später-lesen-Erfassung",
            "ko": "나중에 읽기 수집",
        },
        "description": {
            "ja": "保存記事を毎日ナレッジベースに自動取り込み",
            "de": "Gespeicherte Artikel täglich in die Wissensbasis übernehmen",
            "ko": "저장한 기사를 매일 지식 베이스에 자동 수집",
        },
        "prompt_template": {
            "ja": (
                "後で読むパイプラインを実行：未処理項目を取得し Wiki に取り込み、"
                "処理済みタグを付与。既処理はスキップ。最大10件。"
            ),
            "de": (
                "Führe die Später-lesen-Pipeline aus: unverarbeitete Einträge holen, "
                "ins Wiki übernehmen, als verarbeitet markieren. Bereits verarbeitete "
                "überspringen. Max. 10 pro Lauf."
            ),
            "ko": (
                "나중에 읽기 파이프라인 실행: 미처리 항목을 가져와 위키에 수집하고 "
                "처리 완료 태그를 붙이세요. 처리된 항목은 건너뛰기. 실행당 최대 10개."
            ),
        },
    },
}
