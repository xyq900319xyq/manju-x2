# AI Drama Tools Comparison (May 2026)

Comparison of open-source AI short drama/comic production tools evaluated during the waoowaoo → 魔因 migration.

## Tools Compared

### 1. waoowaoo (saturndec/waoowaoo)
- **Type**: Web (Next.js + Docker)
- **Stars**: ~20
- **License**: MIT
- **Pipeline**: Script → Storyboard → Characters → Images → Video
- **Strengths**: Docker one-click deploy, multi-tenant SaaS, billing system
- **Weaknesses**: Limited art style control, character consistency issues, no director panel, basic prompt pipeline

### 2. AIComicBuilder (twwch/AIComicBuilder)
- **Type**: Web (Next.js 16 + React 19)
- **Stars**: 16 | **Commits**: 417
- **License**: Apache 2.0 (commercial-friendly)
- **Pipeline**: Script import → Character 4-view extraction → Smart storyboard → Keyframes → Video
- **Strengths**: Character 4-view consistency (front/¾/side/back), storyboard kanban, multi-language (CN/EN/JP/KR), multi-ratio support
- **Weaknesses**: No TTS/dubbing, no agent architecture

### 3. Huobao Drama 火宝短剧 (chatfire-AI/huobao-drama)
- **Type**: Web (Nuxt 3 + Vue 3)
- **Stars**: 16 | **Commits**: 275
- **License**: CC BY-NC-SA 4.0 (NO commercial use)
- **Pipeline**: Novel → 5 Agent agents → Storyboard → Video + TTS
- **Strengths**: 5 Mastra AI agents with clear division, TTS dubbing + subtitles, grid image generation
- **Weaknesses**: License prohibits commercial use, open-source version lags behind commercial version (marketing funnel)

### 4. Moyin Creator 魔因漫创 (memecalculate/moyin-creator)
- **Type**: Desktop (Electron 30 + React 18)
- **Stars**: ~30 | **Commits**: 417
- **License**: AGPL-3.0 (dual-licensed with commercial option)
- **Pipeline**: Script → Characters → Scenes → Director → S-Class (Seedance 2.0)
- **Code**: 285 files, 104K lines TypeScript, production-grade
- **Strengths**: Most professional pipeline — character 6-layer identity anchors, film-grade cinematography parameters, Seedance 2.0 multi-modal (@Image/@Video/@Audio), task queue with retry, multi-provider scheduling
- **Weaknesses**: AGPL copyleft, dev activity slowed (Mar 2026+), Electron desktop only (no web/SaaS)

## Recommendation

For the user (professional AI short drama creator with own API infrastructure at chuanggwei.cyou):
- **魔因 > AIComicBuilder > Huobao** in terms of production quality
- 魔因's prompt pipeline, director panel, and Seedance integration are closest to professional standards
- AIComicBuilder is the best fully-open alternative if AGPL is a concern
- Huobao is effectively crippleware (CC BY-NC-SA + commercial lag)

## waoowaoo Deletion

waoowaoo was fully deleted on May 22, 2026. All content exported to `D:\魔音提示词\waoowaoo_export\`:
- 28 images (13 character + 6 location + 9 storyboard)
- 12 episodes screenplay (113KB text)
