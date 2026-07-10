# Contact Sheet Prompt — Character Leak Analysis

## Root Cause Chain

1. **viewpoint-analyzer.ts** (line 67-80): AI receives shot data INCLUDING character info:
   - `shot.actionSummary`, `shot.visualDescription`, `shot.visualFocus`
   - `shot.dialogue`, `shot.characterBlocking`
   - All may contain character names, actions, emotions

2. AI generates viewpoint descriptions like:
   - `nameEn: "Conversation Area"` → but `descriptionEn` may be "where the old man sits talking"
   - `nameEn: "Seating Area"` → description "the protagonist's seat near the window"

3. **scene-viewpoint-generator.ts** (line 595-599): Panel descriptions directly use AI output:
   ```
   Panel [row 1, col 1] (no people): SITTING AREA: where the elderly man sits [same style]
   ```

4. Image model sees "elderly man sits" and draws a person despite `(no people)` prefix — the descriptive content overrides the constraint tag.

## Two-Layer Fix

### Layer 1: viewpoint-analyzer.ts (line 117-118)
Added to system prompt:
```
5. **严格禁止人物信息**：视角名称(name/nameEn)、描述(description/descriptionEn)、
   道具(keyProps/keyPropsEn) 中均不得包含任何人物相关信息，包括但不限于：角色名、
   人称（他/她/主角/老人/女人）、职业、年龄、服装、表情、动作。只描述场景空间和物品。
```

### Layer 2: scene-viewpoint-generator.ts (after line 557)
Injected regex filter before panel prompt assembly:
```javascript
var _cte = /\b(man|woman|boy|girl|person|people|character|protagonist|elderly|...)\b/gi;
var _ctz = /(男人|女人|男孩|女孩|人物|角色|主角|老人|...)/g;
viewpoints.forEach(function(vp) {
  vp.descriptionEn = vp.descriptionEn.replace(_cte, 'scene');
  vp.description = vp.description.replace(_ctz, '场景');
  vp.nameEn = vp.nameEn.replace(_cte, 'Area');
  vp.name = vp.name.replace(_ctz, '区域');
  vp.keyPropsEn = vp.keyPropsEn.map(p => p.replace(_cte, 'item'));
  vp.keyProps = vp.keyProps.map(p => p.replace(_ctz, '物品'));
});
```

## ASAR Injection

In 0.2.8 bundled `out/renderer/assets/index-BTBs57B6.js`, the filter was injected right after `vp.descriptionEn = ...` assignment inside `generateContactSheetPrompt`. The bundled code is ~8MB minified JS — string patterns are findable, but the structure differs from v0.2.3 source.
