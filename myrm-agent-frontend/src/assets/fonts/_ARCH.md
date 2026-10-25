# Fonts

Self-hosted webfont assets. Next.js embeds them at build time through `src/app/fonts.ts`
(`next/font/local`); nothing is fetched from a CDN at runtime or during the build.

| File                           | Purpose                                                                                                                                                                      |
| :----------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `InterVariable-latin.woff2`    | Inter variable font (weights 400–600, latin subset) backing `--font-inter` / `--font-sans`. CJK falls through to PingFang SC / Noto Sans SC / Microsoft YaHei.               |
| `AtkinsonVariable-latin.woff2` | Atkinson Hyperlegible Next variable font (400–700, latin subset) behind `--font-atkinson`; used by the `preset-atkinson-*` profiles and loaded on demand (`preload: false`). |
| `LICENSE.txt`                  | SIL Open Font License 1.1 for Inter.                                                                                                                                         |
| `LICENSE-Atkinson.txt`         | SIL Open Font License 1.1 for Atkinson Hyperlegible Next.                                                                                                                    |
