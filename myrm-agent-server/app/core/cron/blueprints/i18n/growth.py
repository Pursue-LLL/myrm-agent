"""蓝图补充文案：growth 组。

[POS]
蓝图 i18n 子包的一部分；由 __init__.py 合并。
"""

from __future__ import annotations

from .types import BlueprintLocaleSupplement

SUPPLEMENTAL_BY_ID: dict[str, BlueprintLocaleSupplement] = {'viral_quote_discovery': {'title': {'ja': 'バイラル金句＆フック発掘',
                                     'de': 'Virale Zitate & Hooks entdecken',
                                     'ko': '바이럴 문구 및 훅 발굴'},
                           'description': {'ja': 'SNSと業界ブログを毎日巡回し、拡散力の高いフック、反常識論調、金句を発掘',
                                           'de': 'Tägliche Überwachung von sozialen Netzwerken und Branchenblogs zur '
                                                 'Gewinnung viraler Hooks, Kontra-Argumente und Zitate',
                                           'ko': '소셜 네트워크와 업계 블로그를 매일 순회하며 바이럴 훅, 반합의 논조, 문구를 발굴'},
                           'prompt_template': {'ja': 'テーマ【{topic}】のバイラル金句＆フック発掘を、対象チャネル（{channels}）で実行してください。\n'
                                                     '1. 過去24〜48時間の人気議論から高エンゲージメント投稿を検索。\n'
                                                     '2. 反直感的な洞察や強い感情的反響を備えた金句候補トップ5を抽出。\n'
                                                     '3. 各金句がなぜ機能するかを分解（フック公式、刺さった痛点、読者の反応）。\n'
                                                     '4. Xスレッド、小紅書ノート、WeChatレター向けの派生アイデアを設計。\n'
                                                     '5. 厳選した金句を `docs/marketing/viral_quotes_{topic}.md` '
                                                     'に保存し、最有力候補を要約。',
                                               'de': 'Führe die Entdeckung viraler Zitate und Gold-Hooks für Thema '
                                                     '{topic} über die Zielkanäle {channels} durch.\n'
                                                     '1. Suche aktuelle populäre Diskussionen (letzte 24-48 Stunden) '
                                                     'nach Beiträgen mit hoher Interaktion.\n'
                                                     '2. Extrahiere die Top-5-Kandidaten mit kontraintuitiven '
                                                     'Einblicken oder starker emotionaler Resonanz.\n'
                                                     '3. Dekonstruiere, warum jedes Zitat funktioniert (Hook-Formel, '
                                                     'adressierter Schmerzpunkt, Publikumsreaktion).\n'
                                                     '4. Synthese angepasster Derivatideen für X-Threads, '
                                                     'Xiaohongshu-Notes und WeChat-Newsletter.\n'
                                                     '5. Speichere die kuratierten Zitate in '
                                                     '`docs/marketing/viral_quotes_{topic}.md` und fasse den '
                                                     'Top-Kandidaten zusammen.',
                                               'ko': '주제 {topic}에 대한 바이럴 문구 및 골든 훅 발굴을 대상 채널 {channels}에서 실행하세요.\n'
                                                     '1. 최근 24-48시간 인기 논의에서 높은 반응을 얻은 게시물 검색.\n'
                                                     '2. 반직관적 통찰이나 강렬한 정서적 울림을 지닌 문구 후보 Top 5 추출.\n'
                                                     '3. 각 문구가 작동하는 이유 해부(훅 공식, 겨냥한 페인포인트, 독자 반응).\n'
                                                     '4. X 스레드, 샤오홍슈 노트, 위챗 뉴스레터용 파생 아이디어 설계.\n'
                                                     '5. 엄선한 문구를 `docs/marketing/viral_quotes_{topic}.md`에 저장하고 최고 후보 '
                                                     '요약.'}},
 'commerce_morning_digest': {'title': {'ja': '店舗運営モーニングダイジェスト',
                                       'de': 'Täglicher Commerce-Morgen-Digest',
                                       'ko': '상점 운영 모닝 다이제스트'},
                             'description': {'ja': 'GMV・コンバージョン率・在庫切れリスク・段階的値下げ提案を分析する自動モーニングブリーフィング',
                                             'de': 'Automatisiertes Morgen-Briefing mit Analyse von GMV, '
                                                   'Konversionsraten, Lieferrisiken und gestuften Preisanpassungen',
                                             'ko': 'GMV, 전환율, 품절 위험, 단계적 가격 조정 제안을 분석하는 자동 모닝 브리핑'},
                             'prompt_template': {'ja': '店舗「{store_name}」の本日運営モーニングダイジェストを作成：前日のGMV、注文件数、コンバージョン率の変動、在庫健全性を分析。深刻な在庫切れ警報と承認待ちの段階的価格変更を強調し、優先度付きの対応提案を提示してください。',
                                                 'de': 'Erstelle den morgendlichen Commerce-Digest für den Laden '
                                                       "'{store_name}': Analysiere GMV, Bestellvolumen, "
                                                       'Konversionsrate und Lagerbestand des Vortags. Hebe kritische '
                                                       'Lückenbestände und ausstehende gestufte Preisänderungen '
                                                       'hervor, die eine Freigabe erfordern, und gib priorisierte '
                                                       'Handlungsempfehlungen.',
                                                 'ko': "상점 '{store_name}'의 오늘 운영 모닝 다이제스트를 생성하세요: 전일 GMV, 주문량, 전환율 변동 "
                                                       '및 재고 건강도를 분석하고, 심각한 품절 경고와 승인 대기 중인 단계적 가격 변경을 강조하며, 우선순위가 있는 '
                                                       '조치 권고를 제공하세요.'}}}
