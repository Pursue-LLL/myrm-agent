# Douyin / Short Video (抖音短视频) Distribution Guide

## Platform Characteristics & Retention Rules

Short video algorithms on Douyin / TikTok rely heavily on **3-Second Retention (完播率与前3秒跳出率)**. If the first 3 seconds fail to hook the viewer, the video will not enter higher traffic pools.

- **Golden 3 Seconds**: The opening sentence MUST contain a high-stakes hook, conflict, or direct warning.
- **Pacing**: Fast-paced, spoken colloquial tone, rhythmic sentences without filler words.
- **Duration**: Target 15-45 seconds for maximum completion rate.

---

## Deliverable Standard

Every Douyin short video adaptation task MUST produce `douyin/script.md` containing:

1. **Golden 3-Second Hook Selection**: 3 candidate opening hooks.
2. **Shot-by-shot Script Table**: Pacing, spoken audio (逐字稿), visual camera action, and on-screen B-roll text.
3. **9:16 Vertical Cover Prompt**: Visual prompt for image/video generation tools.

---

## 4 Golden Hook Categories

1. **Warning & Emergency Stop (紧急劝阻型)**:
   - "先别急着下单！看完这3点再做决定，能帮你省下大几千！"
   - "千万别再盲目用旧方法了！90%的人一上来就踩了这个大坑！"
2. **Cognitive Contrast (反直觉反差型)**:
   - "如果你还在花两小时手动排版，那你可能完全落伍了！"
   - "同样是一篇文章，别人发全网能爆，你发却零阅读？关键全在这一步！"
3. **Pain-point Interrogation (精准扎心型)**:
   - "做自媒体每天写稿改稿改到崩溃？"
   - "是不是每次分发不同平台都要重写一遍？累不累啊？"
4. **Curiosity & Secret Reveal (揭秘悬念型)**:
   - "全网头部博主从不公开的一键分发秘密，今天一次性拆给你看！"

---

## Shot-by-Shot Script Table Format

```markdown
# 视频主题：[主题名称]
- 目标时长：30s
- 核心受众：[受众画像]
- 情绪基调：节奏明快 / 极度吸睛 / 价值感强

### 黄金前3秒备选 Hooks
1. [Hook 选项 1 - 紧急劝阻]
2. [Hook 选项 2 - 反直觉反差]
3. [Hook 选项 3 - 揭秘悬念]

### 分镜与口播逐字稿

| 镜头编号 | 预估时长 | 画面/动作 (Visual & B-roll) | 口播台词 (Spoken Script) | 屏幕花字/音效 |
| :--- | :--- | :--- | :--- | :--- |
| 镜头 1 (Hook) | 0~3s | 主播严肃面对镜头 / 快速切换传统繁琐操作红叉特写 | 「先别急着手动改稿！看完这招，你的效率直接翻10倍！」 | 醒目大字：千万别踩坑 / 警报音效 |
| 镜头 2 (痛点) | 3~10s | 屏幕录制：展示传统多平台繁琐复制、排版混乱的崩溃场景 | 「每次写好一篇内容，小红书要重写，抖音要写脚本，微信要排版，大半天全耗进去了！」 | 痛点关键词标红闪烁 |
| 镜头 3 (解法) | 10~22s | 动态演示：一键输入母素材，多任务图并行秒级产出全套成品 | 「其实现在只需要把母稿丢进去，小红书双版本、抖音分镜、公众号排版一键全搞定！」 | 绿勾动效 / 画面加速 / 欢快节奏 |
| 镜头 4 (CTA) | 22~30s | 展示最终多平台精美交付物合集 / 引导点赞收藏 | 「工具链接和保姆级提示词都整理好了，赶紧点赞收藏，马上去试试！」 | 右下角关注引导 / 收藏箭头 |

### 9:16 竖屏封面提示词 (Visual Prompt)
- **Ratio**: 9:16 vertical
- **Style**: Bold graphic with high contrast neon accents
- **Headline**: "一键全网分发 / 效率提升10倍"
```
