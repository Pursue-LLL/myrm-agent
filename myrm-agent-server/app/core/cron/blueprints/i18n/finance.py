"""[INPUT]
- app.core.cron.blueprints.i18n.types::BlueprintLocaleSupplement (POS: 蓝图 i18n 子包共用类型；不包含任何具体文案。)

[OUTPUT]
- （仅导出常量/类型）

[POS]
蓝图 i18n 子包的一部分；由 __init__.py 合并。
"""

from __future__ import annotations

from .types import BlueprintLocaleSupplement

SUPPLEMENTAL_BY_ID: dict[str, BlueprintLocaleSupplement] = {'financial_monitor_simple': {'title': {'ja': '金融モニター（シンプル）', 'de': 'Finanz-Monitor (Einfach)', 'ko': '금융 모니터 (심플)'},
                              'description': {'ja': 'Python 事前プローブで動くゼロLLMしきい値アラート',
                                              'de': 'Zero-LLM-Schwellwertalarm mit Python-Preflight-Probe',
                                              'ko': 'Python 사전 점검으로 동작하는 제로 LLM 임계치 알림'},
                              'prompt_template': {'ja': 'このジョブは router モードです。事前プローブ出力を最終メッセージとしてそのまま配信します。プローブが [SKIP] '
                                                        'を出した場合は通知しません。',
                                                  'de': 'Dieser Job läuft im Router-Modus. Nutze die Ausgabe der '
                                                        'Preflight-Probe als finale Nachricht. Wenn die Probe [SKIP] '
                                                        'ausgibt, bleibe still.',
                                                  'ko': '이 작업은 router 모드로 실행됩니다. 사전 점검 출력값을 최종 메시지로 그대로 전달합니다. 프로브가 '
                                                        '[SKIP]를 출력하면 알림을 보내지 않습니다.'}},
 'financial_monitor_advanced': {'title': {'ja': '金融モニター（アドバンスド）',
                                          'de': 'Finanz-Monitor (Erweitert)',
                                          'ko': '금융 모니터 (고급)'},
                                'description': {'ja': '重複抑制・増分監視・障害アラート付きの複合シグナル監視',
                                                'de': 'Multi-Signal-Finanzüberwachung mit Dedupe, Baseline-Monitoring '
                                                      'und Fehleralarm',
                                                'ko': '중복 억제·증분 모니터링·실패 알림을 포함한 멀티 시그널 금융 모니터링'},
                                'prompt_template': {'ja': '次の資産を継続監視：{watchlist}。価格、デリバティブ/資金調達、センチメント（X/ニュース）、マクロ、オンチェーン資金流を評価。次の条件 '
                                                          '{signal_rules} '
                                                          'に対して、独立したリスク信号が2つ以上一致したときのみアラート。ポートフォリオ文脈：{portfolio_context}。実行可能な変化がなければ必ず '
                                                          '[SILENT] のみを返す。',
                                                    'de': 'Überwache diese Assets kontinuierlich: {watchlist}. Bewerte '
                                                          'Preisverhalten, Derivate/Funding, Stimmung (X + News), '
                                                          'Makro-Katalysatoren und On-Chain-Flow-Proxys. Alarme nur, '
                                                          'wenn mindestens zwei unabhängige Risikosignale mit '
                                                          '{signal_rules} übereinstimmen. Portfolio-Kontext: '
                                                          '{portfolio_context}. Wenn keine umsetzbare Änderung '
                                                          'vorliegt, antworte exakt mit [SILENT].',
                                                    'ko': '다음 자산을 지속 모니터링하세요: {watchlist}. 가격 흐름, 파생/펀딩, 감성(X+뉴스), 거시 '
                                                          '촉매, 온체인 자금 흐름을 함께 평가합니다. {signal_rules} 기준과 독립된 리스크 신호 2개 '
                                                          '이상이 동시에 맞을 때만 알림합니다. 포트폴리오 컨텍스트: {portfolio_context}. 실행 '
                                                          '가능한 변화가 없으면 반드시 [SILENT]만 반환하세요.'}},
 'seo_weekly_audit': {'title': {'ja': 'SEO とサイト健全性の週次監査',
                                'de': 'Wöchentliches SEO- & Website-Gesundheitsaudit',
                                'ko': 'SEO 및 사이트 상태 주간 감사'},
                      'description': {'ja': 'テクニカルSEO、robots、sitemap、メタタグ、AI検索準備状況の定期監査と優先ロードマップ生成',
                                      'de': 'Regelmäßiges Audit für technisches SEO, robots, sitemap, Meta-Tags und '
                                            'KI-Suchbereitschaft mit Roadmap',
                                      'ko': '기술적 SEO, robots, sitemap, 메타 태그 및 AI 검색 준비 상태 정기 감사 및 로드맵 생성'},
                      'prompt_template': {'ja': '{target_url}（深さ: {depth}）のテクニカルSEOおよびサイト健全性の包括的な監査を実行してください。\n'
                                                '1. robots.txt、sitemap.xml、/llms.txt を取得して検証。\n'
                                                '2. 主要なレンダリング済みページで title、meta '
                                                'description、canonical、H1、JSON-LD、OpenGraph、hreflang を検査。\n'
                                                '3. 内部リンク切れや画像の alt 属性の有無をサンプリング確認。\n'
                                                '4. 証拠付きの優先度 P0-P3 SEO-OPTIMIZATION-ROADMAP.md アーティファクトを artifacts/ '
                                                'に生成。\n'
                                                '5. 重要な課題と実行可能な次のステップをまとめたエグゼクティブサマリーを提示。',
                                          'de': 'Führe ein umfassendes technisches SEO- und Website-Gesundheitsaudit '
                                                'für {target_url} (Tiefe: {depth}) durch.\n'
                                                '1. robots.txt, sitemap.xml und /llms.txt abrufen und überprüfen.\n'
                                                '2. Wichtige Seiten auf Title, Meta Description, Canonical, H1, '
                                                'JSON-LD, OpenGraph und hreflang prüfen.\n'
                                                '3. Auf defekte interne Links und fehlende Alt-Texte bei Bildern '
                                                'prüfen.\n'
                                                '4. Ein priorisiertes P0-P3 SEO-OPTIMIZATION-ROADMAP.md-Artefakt in '
                                                'artifacts/ mit Nachweisen erstellen.\n'
                                                '5. Eine prägnante Zusammenfassung der kritischen Punkte und nächsten '
                                                'Schritte liefern.',
                                          'ko': '{target_url}(깊이: {depth})에 대한 종합적인 기술적 SEO 및 사이트 상태 감사를 실행하세요.\n'
                                                '1. robots.txt, sitemap.xml 및 /llms.txt를 확인 및 검증.\n'
                                                '2. 주요 렌더링 페이지의 title, meta description, canonical, H1, JSON-LD, '
                                                'OpenGraph, hreflang 검사.\n'
                                                '3. 내부 깨진 링크 및 이미지 alt 태그 누락 샘플링 검사.\n'
                                                '4. 실제 증거가 포함된 P0-P3 우선순위 SEO-OPTIMIZATION-ROADMAP.md 아티팩트를 '
                                                'artifacts/에 생성.\n'
                                                '5. 핵심 문제점과 실행 가능한 다음 조치를 담은 요약 보고서 제공.'}}}
