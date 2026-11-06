"""[INPUT]
- app.core.cron.blueprints.i18n.types::BlueprintLocaleSupplement (POS: 蓝图 i18n 子包共用类型；不包含任何具体文案。)

[OUTPUT]
- （仅导出常量/类型）

[POS]
蓝图 i18n 子包的一部分；由 __init__.py 合并。
"""

from __future__ import annotations

from .types import BlueprintLocaleSupplement

SUPPLEMENTAL_BY_ID: dict[str, BlueprintLocaleSupplement] = {'read_it_later': {'title': {'ja': '後で読む取り込み', 'de': 'Später-lesen-Erfassung', 'ko': '나중에 읽기 수집'},
                   'description': {'ja': '保存記事を毎日ナレッジベースに自動取り込み',
                                   'de': 'Gespeicherte Artikel täglich in die Wissensbasis übernehmen',
                                   'ko': '저장한 기사를 매일 지식 베이스에 자동 수집'},
                   'prompt_template': {'ja': '後で読むパイプラインを実行：未処理項目を取得し Wiki に取り込み、処理済みタグを付与。既処理はスキップ。最大10件。',
                                       'de': 'Führe die Später-lesen-Pipeline aus: unverarbeitete Einträge holen, ins '
                                             'Wiki übernehmen, als verarbeitet markieren. Bereits verarbeitete '
                                             'überspringen. Max. 10 pro Lauf.',
                                       'ko': '나중에 읽기 파이프라인 실행: 미처리 항목을 가져와 위키에 수집하고 처리 완료 태그를 붙이세요. 처리된 항목은 건너뛰기. 실행당 '
                                             '최대 10개.'}},
 'wiki_morning_delta': {'title': {'ja': 'Wiki 朝のデルタ', 'de': 'Wiki-Morgen-Delta', 'ko': '위키 모닝 델타'},
                        'description': {'ja': '新規 raw ノートを整理し、Vault の変更を短く要約',
                                        'de': 'Neue Raw-Notizen ordnen und Vault-Änderungen kurz zusammenfassen',
                                        'ko': '새 raw 노트를 정리하고 vault 변경을 짧게 요약'},
                        'prompt_template': {'ja': '過去24時間の Wiki 朝次ルーチンを実行：raw/ の新規・更新ファイルを確認し、wiki_query_tool '
                                                  'で関連概念を調べ、必要時のみ wiki_apply_tool で軽微更新。Vault の変化を最大3行で要約。実質的な変化がなければ '
                                                  '[SILENT] のみ。',
                                            'de': 'Führe die Wiki-Morgen-Delta-Routine der letzten 24 Stunden aus: '
                                                  'prüfe raw/ auf neue oder aktualisierte Dateien, nutze '
                                                  'wiki_query_tool, wiki_apply_tool nur bei klarem Bedarf. Fasse '
                                                  'Vault-Änderungen in max. 3 Zeilen zusammen. Ohne relevante Änderung '
                                                  'nur [SILENT].',
                                            'ko': '지난 24시간 위키 모닝 델타 루틴 실행: raw/ 신규·갱신 파일 확인, wiki_query_tool로 관련 개념 '
                                                  '조회, 필요할 때만 wiki_apply_tool로 경미 업데이트. vault 변화를 최대 3줄로 요약. 실질 변화 없으면 '
                                                  '[SILENT]만 반환.'}},
 'wiki_maintain': {'title': {'ja': 'Wiki 自動メンテ', 'de': 'Wiki-Wartung', 'ko': '위키 자동 유지보수'},
                   'description': {'ja': '断链・stale raw・vault 衛生の定期構造 lint と自動修復',
                                   'de': 'Geplante strukturelle Lint- und Auto-Reparatur für Links, stale Raw und '
                                         'Vault-Hygiene',
                                   'ko': '깨진 링크, stale raw, vault 위생을 위한 정기 구조 lint 및 자동 복구'},
                   'prompt_template': {'ja': 'Wiki メンテ job（router モード）。サーバー生成の要約をそのまま配信。変更がなければ [SILENT] のみ。',
                                       'de': 'Wiki-Wartungsjob (Router-Modus). Server-Zusammenfassung unverändert '
                                             'ausliefern. Bei keiner Änderung nur [SILENT].',
                                       'ko': '위키 유지보수 작업(router モード). 서버 요약을 그대로 전달. 변경 없으면 [SILENT]만 반환.'}},
 'wiki_vault_weekly_health': {'title': {'ja': 'Wiki 週次健全性チェック（リストのみ）',
                                        'de': 'Wöchentliche Wiki-Gesundheitsprüfung (Nur Liste)',
                                        'ko': '위키 주간 건강 점검 (목록 전용)'},
                              'description': {'ja': '毎週日曜日に Wiki を読み取り専用で巡回し、壊れたリンクや古い情報の一覧を生成（自動変更なし）',
                                              'de': 'Wöchentliche schreibgeschützte Prüfung auf defekte Links und '
                                                    'veraltete Quellen ohne automatische Änderungen',
                                              'ko': '매주 일요일 읽기 전용으로 위키를 점검하여 깨진 링크/오래된 사실 목록 생성 (자동 수정 없음)'},
                              'prompt_template': {'ja': 'Wiki 健全性チェックジョブ（router モード、リストのみ）。サーバー生成のリストをそのまま配信。',
                                                  'de': 'Wiki-Gesundheitsprüfungsjob (Router-Modus, nur Liste). '
                                                        'Server-Liste direkt ausliefern.',
                                                  'ko': '위키 건강 점검 작업(router 모드, 목록 전용). 서버 생성 목록을 그대로 전달.'}},
 'daily_review_compounding': {'title': {'ja': 'デイリーレビューの知識化', 'de': 'Tagesreview-Veredelung', 'ko': '일일 회고 지식화'},
                              'description': {'ja': '当日のデイリーレビューを Projects/Knowledge/Methods/Comparisons '
                                                    'の四次元ドラフトに編訳し、人間レビュー待ちに',
                                              'de': 'Tagesreviews abends zu vierdimensionalen Wissensentwürfen '
                                                    '(Projekte/Wissen/Methoden/Vergleiche) verdichten, wartend auf '
                                                    'Prüfung',
                                              'ko': '당일 회고를 프로젝트/지식/방법/비교 4차원 지식 초안으로 편찬하여 인간 검토 대기'},
                              'prompt_template': {'ja': 'デイリーレビュー知識化ジョブ（router モード）。サーバー生成の要約をそのまま配信。入力がなければ [SILENT] '
                                                        'のみ。',
                                                  'de': 'Tagesreview-Veredelungsjob (Router-Modus). '
                                                        'Server-Zusammenfassung unverändert ausliefern. Ohne Eingabe '
                                                        'nur [SILENT].',
                                                  'ko': '일일 회고 지식화 작업(router 모드). 서버 요약을 그대로 전달. 입력이 없으면 [SILENT]만 '
                                                        '반환.'}},
 'wiki_corpus_dedup': {'title': {'ja': 'Wiki コーパス重複スキャン', 'de': 'Wiki-Korpus-Duplikat-Scan', 'ko': '위키 코퍼스 중복 스캔'},
                       'description': {'ja': 'raw ソースの完全/正規化/近似重複を定期スキャンし、レビュー待ちキューに書き込み',
                                       'de': 'Geplanter Scan auf exakte, normalisierte und annähernde Duplikate mit '
                                             'Review-Warteschlange',
                                       'ko': 'raw 소스의 정확/정규화/유사 중복을 정기 스캔하여 검토 대기열에 등록'},
                       'prompt_template': {'ja': 'Wiki コーパス重複排除ジョブ（router モード）。サーバー生成の要約をそのまま配信。レビュー対象がなければ [SILENT] '
                                                 'のみ。',
                                           'de': 'Wiki-Korpus-Deduplizierungsjob (Router-Modus). '
                                                 'Server-Zusammenfassung unverändert ausliefern. Bei keinen '
                                                 'Duplikatgruppen nur [SILENT].',
                                           'ko': '위키 코퍼스 중복 제거 작업(router 모드). 서버 요약을 그대로 전달. 검토 대상 중복 그룹 없으면 [SILENT]만 '
                                                 '반환.'}}}
