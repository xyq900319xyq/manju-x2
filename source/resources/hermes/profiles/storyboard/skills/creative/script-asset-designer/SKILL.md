---
name: script-asset-designer
description: "从剧本中提取人物、场景、物品资产，并设计全中文AI生图指令词。"
version: 2.2.0
category: creative
---

# 剧本资产设计助手

从剧本中提取所有视觉资产——人物、场景、物品——并为每个资产生成可直接用于AI绘图工具的中文指令词，格式遵循标准的AI生图指令体系规范。

## 核心铁律

1. **禁止输出推理过程**：回复中不得出现任何分析、推理、计划、拆解过程。只输出最终结果。回复第一个字必须是"## 人物资产"。
2. **只输出全局资产清单**：所有人物、场景、物品合并为一个总清单，不按集/场拆分。同一实体跨越多集只出现一次。
3. **人物只描述常规状态**：只包含角色的固定/永久视觉特征。禁止事件性/情绪性/临时状态描述。

## 人物资产条目格式

```
### 人物N：角色名
- 身份：在剧中的角色/职位/社会关系
- 年龄/性别：年龄段标签（child/teen/young-adult/adult/middle-aged/senior）+ 性别
- 标签：角色类型（protagonist/antagonist/supporting/minor）+ 出场频率
- 人物关系：与其他角色的固定关系（师徒/对手/恋人/亲属等）
- 身份锚点：
  - 脸型：描述+性格因果
  - 下颌：描述+性格因果
  - 颧骨：描述+气质因果
  - 眼型：形状+眼尾走向+单/双眼皮
  - 眼细节：瞳孔质感（清澈/深邃/浑浊）+ 眼神中融入的身份特质
  - 鼻型：鼻梁+鼻尖+线条描述
  - 唇型：厚薄+唇线+默认表情习惯
  - 肤色：具体描述
  - 发色/发型：发色+完整发型结构+发饰
  - 发际线细节：美人尖/美人尖缺失/高发际线/自然等
  - 体型：身高+胖瘦+骨架
  - 皮肤纹理：具象到毛孔层面的质感描述
- 独特标记：永久性痣/疤痕/纹身/胎记等。每条标记必须包含：精确位置(含距离)+大小+颜色+成因（四要素齐全）
- 色彩锚点：瞳色#HEX 色名，发色#HEX 色名，肤色#HEX 色名，唇色#HEX 色名（hex在前）
- 服装：默认常规服装。款式+材质+颜色+每件的设计逻辑/功能理由+配饰+一句话整体概括
- 性格特征：从剧本中提取的固定性格，用概括词
- 中文指令词：完整AI生图指令词（格式见下文模板）
- 负向提示词：
  - 具体排除项：与该角色设定冲突的具体元素
  - 风格排除项：要排除的艺术风格
```

## 场景资产条目格式（含电影摄影参数）

```
### 场景N：场景名
- 类型：室内/室外，具体空间类型
- 时间段：典型时间段
- 氛围：光影/天气/情绪基调
- 色温：warm-3200K / neutral-5600K / cool-7500K / golden-hour / blue-hour / mixed
- 灯光风格：natural / high-key / low-key / silhouette / chiaroscuro / neon / rim
- 灯光方向：front / side / back / top / bottom / rim
- 景深：shallow / medium / deep
- 拍摄角度：eye-level / low-angle / high-angle / birds-eye / worms-eye / dutch-angle
- 大气效果：雾气/烟尘/光晕/雨丝/雪粒等 + 强度(subtle/moderate/heavy)
- 空间描述：大小、布局、前后景层次
- 材质：建筑/地形的具体材质（如"青石地面""木质梁柱""琉璃瓦顶""夯土墙壁"）
- 核心元素：场景中最重要的3-5个视觉元素
- 中文指令词：完整AI生图指令词（格式见下文模板）
- 负向提示词：需要排除的元素
```

## 物品资产条目格式

```
### 物品N：物品名
- 类型：武器/法宝/日常用品/科技装置/交通工具等
- 外观：尺寸+材质+颜色+纹理+细节特征
- 用途/意义：在剧本中的功能与象征
- 中文指令词：完整AI生图指令词
- 负向提示词：需要排除的元素
```

## 人物提取规则

### 判定标准
- **主要角色**：有名字、有台词、影响剧情走向 → 独立条目，标签 protagonist
- **有名角色**：有名字但台词少 → 独立条目，标签 supporting
- **标签角色**：无名字但反复出现，有固定标签 → 独立条目，标签 minor
- **群众/路人**：一次性出现 → 归入场景资产，不单独列出

### 全局合并规则
- 同一角色多集出现，但年龄/形象基本不变 → 只列一次
- 同一角色多个称呼 → 合并，使用主要称呼
- **不同年龄段视为独立资产**：如果角色在剧本中跨越明显的年龄阶段（如青年期和老年期），必须拆分为两个独立条目，各自拥有完整的外貌描述和指令词
  - 命名格式：`人物N：角色名（青年期）` 和 `人物N+1：角色名（老年期）`
  - 各自的年龄标签、外貌特征、发型发色、服装完全不同，独立设计
  - 辨识标记中的永久性特征（如泪痣、疤痕）可跨年龄段保留

### 年龄段标签规范
child(3-12)、teen(13-17)、young-adult(18-30)、adult(31-45)、middle-aged(46-60)、senior(60+)

### 视觉推断原则
1. 身份/职业 → 典型外貌  2. 时代背景 → 发型/服装  3. 性格特征 → 五官附带性格因果  4. 剧情功能 → 视觉符号

## 场景提取规则

### 判定标准与合并规则
- 以空间为单位去重，同一空间只列一次
- 同一空间不同时间段合并描述
- 不同空间各自独立

### 电影摄影参数推断原则
根据剧本场景的氛围和情绪自动匹配参数：
- **色温**：温馨/怀旧→warm-3200K或golden-hour，紧张/悬疑→cool-7500K，日常→neutral-5600K
- **灯光风格**：明亮开阔→high-key，阴暗压迫→low-key，逆光剪影→silhouette，霓虹都市→neon，明暗对比→chiaroscuro
- **灯光方向**：人物主场→front/side，反派/恐怖→bottom/back，神圣感→top
- **景深**：大场景→deep，中景→medium，聚焦特定元素→shallow
- **拍摄角度**：建立场景→eye-level或birds-eye，压迫感→low-angle，脆弱感→high-angle，不安→dutch-angle
- **大气效果**：根据天气和氛围匹配（雾气/烟尘/光晕/雨丝/雪粒）+ 强度

### 材质描述标准
建筑和地形的材质必须具体到可感知的层面，使用具象词汇：
- 墙面：夯土/青砖/粉墙/石砌/木格栅/竹编
- 地面：青石板/木地板/夯土/碎石/玉石/砖铺
- 屋顶：琉璃瓦/茅草/木顶/石板
- 自然地形：岩石/草地/沙地/雪地/沼泽

## 物品提取规则

### 判定标准
- 剧本明确命名或描述的道具 → 独立条目
- 多集出现 → 只列一次
- 日常物件 → 归入场景核心元素

## AI生图指令词设计规范

### 风格核心特征

1. 五官附带性格因果  2. 眼细节独立描述  3. 辨识标记四要素(位置+大小+颜色+成因)
4. 色彩锚点 hex 在前  5. 皮肤纹理具象到毛孔  6. 发际线细节  7. 服装带设计逻辑
8. 画龙点睛的概括  9. 负向提示词分两段(avoid+styleExclusions)
10. 场景带电影摄影参数(色温+灯光+景深+角度+大气效果+材质)

### 人物指令词模板

```
专业角色设计参考图，"角色名"，【身份/背景】身份简述，融合身份与性格的一句话气质概括。【外貌特征】脸型描述+下颌特征并赋予性格因果，颧骨特征并赋予气质因果，眼型+眼尾走向+单双眼皮+瞳孔质感+眼神中融入身份特质（独立写眼细节），鼻型+鼻尖+线条，唇型+唇线+默认静态表情。【辨识标记】精确位置(含距离)+大小+颜色+成因。【色彩锚点】瞳色#HEX 色名，发色#HEX 色名，肤色#HEX 色名，唇色#HEX 色名。【皮肤纹理】具象到毛孔的质感描述。【发型】完整发型结构+发饰+发际线特征(美人尖/自然/高发际线等)。【服装】款式+材质+颜色+每件的设计逻辑/功能理由+配饰+一句话整体概括。【人物关系】剧中关系。three-view turnaround (front view, side view, back view), expression sheet with multiple facial expressions (happy, sad, angry, surprised, neutral), body proportion reference, height chart, head-to-body ratio guide, pose sheet with various action poses (standing, sitting, running, jumping), 角色参考图版式, pure solid white background, isolated character on white background, absolutely no background scenery, (best quality, masterpiece, 8k, high detailed:1.2), (stunning stylized 3D Chinese animation character render:1.3), (Unreal Engine 5 style:1.2), (cinematic lighting, soft volumetric fog:1.1), (smooth porcelain skin texture:1.1), (intricate traditional Chinese fabric details, fine embroidery, flowing robes:1.1), ethereal atmosphere, glowing spiritual energy, beautiful facial features, (delicate body proportions), sharp focus, detailed illustration, concept art, character model sheet
```

### 场景指令词模板（含电影摄影参数）

```
场景概念设计图，"场景名"，【空间描述】空间类型+大小+布局结构+前后景层次+材质(墙面/地面/屋顶的具体材质)。【电影摄影】色温参数 灯光风格 灯光方向 景深 拍摄角度 大气效果+强度。【光影氛围】光源方向+光质+色调+天气/时间，可与场景戏剧功能关联。【核心元素】元素1，元素2，元素3，元素4，元素5。【整体氛围】氛围关键词。wide establishing shot, cinematic wide angle, (best quality, masterpiece, 8k, high detailed:1.2), (stunning stylized 3D Chinese animation environment render:1.3), (Unreal Engine 5 style:1.2), (cinematic lighting, volumetric atmospheric fog:1.1), ethereal atmosphere, ancient Chinese fantasy architecture, detailed environment, sharp focus, concept art, environment design, Multi-angle view, detailed perspective, scene design drawing
```

场景指令词示例：
```
场景概念设计图，"青云宗洞府"，【空间描述】室内修仙洞府，约30平米不规则石窟空间，前景为炼丹炉台区域散落青铜齿轮和瓷瓶碎片，中景为石壁凿出的壁龛书架和药材柜，背景为深邃的洞府通道渐入黑暗，墙面为粗凿青石岩壁带着凿痕纹理，地面为不平整的青石板，洞顶悬挂几盏灵力驱动的青铜油灯。【电影摄影】warm-3200K low-key rim（侧逆光勾勒陈戈轮廓） medium eye-level 烟尘 moderate。【光影氛围】青铜油灯从上方投下暖黄光晕，爆炸后的烟尘在光柱中形成可见的颗粒，侧逆光勾勒人物轮廓形成剪影感，洞府深处完全隐入黑暗。【核心元素】炼丹炉残骸、散落青铜齿轮、壁龛书架、悬浮青铜油灯、弥漫烟尘。【整体氛围】古旧神秘的修仙洞府，爆炸后的狼藉与荒诞并存。wide establishing shot...
```

### 物品指令词模板

```
物品概念设计图，"物品名"，【类型】物品类型。【外观】尺寸+材质+颜色+表面纹理+细节特征，可附带设计逻辑（如"剑格云纹造型象征宗门身份"）。【功能】用途/象征意义。【展示方式】展示角度。product shot, isolated object on white background, (best quality, masterpiece, 8k, high detailed:1.2), (stunning stylized 3D Chinese animation prop render:1.3), (Unreal Engine 5 style:1.2), (cinematic lighting:1.1), intricate details, sharp focus, concept art, prop design, detailed craftsmanship, Multi-angle view, detailed perspective, prop design drawing
```

### 负向提示词模板（分为两段）

```
具体排除项（avoid）：blurry, low quality, watermark, text, cropped, 金色头发, 蓝色眼睛, 眼镜, 现代手表, 拉链, 西装, T恤, 运动鞋, 手机, 现代实验室器材
风格排除项（styleExclusions）：动漫风格, Q版, 抽象艺术, 油画厚涂, 赛博朋克霓虹灯
```

根据剧本背景追加标签。仙侠剧本必须追加现代元素排除项。

### 色温速查

| 氛围 | 色温参数 |
|------|---------|
| 温馨/怀旧/黄昏 | warm-3200K 或 golden-hour |
| 日常/中性 | neutral-5600K |
| 冷峻/悬疑/夜晚 | cool-7500K 或 blue-hour |
| 混合光源 | mixed |

### 灯光风格速查

| 场景类型 | 灯光风格 |
|---------|---------|
| 明亮开阔/喜剧 | high-key |
| 阴暗压迫/恐怖 | low-key |
| 逆光剪影/神圣 | silhouette |
| 霓虹都市/赛博 | neon |
| 明暗对比/戏剧 | chiaroscuro |
| 自然光/户外 | natural |
| 边缘光/人物突出 | rim |

### 风格标签速查

| 剧本类型 | SD风格标签 |
|---------|-----------|
| 仙侠/玄幻 | (stunning stylized 3D Chinese animation character render:1.3), ancient Chinese fantasy art, ethereal atmosphere |
| 都市/现代 | realistic rendering, cinematic photography style, urban environment |
| 科幻 | sci-fi concept art, futuristic design, cyberpunk influence |
| 历史/古装 | historical Chinese aesthetics, classical composition |
| 悬疑/恐怖 | dark atmospheric art, dramatic shadows, high contrast |

### 渲染类型标签映射

**3D动画**：`(Unreal Engine 5 style:1.2), (stunning stylized 3D Chinese animation character render:1.3), 3D render`
**2D动画**：`(2D animation style:1.2), (hand-drawn illustration:1.3), cel shading, anime style`（2D人物去掉 three-view turnaround）
**真人影视**：`(cinematic photography:1.2), (photorealistic:1.3), live action, film grain, realistic skin texture`
**定格动画**：`(stop motion animation style:1.2), (claymation:1.3), miniature photography, practical effects`

### 关键规则

1. SD触发词保留英文原样
2. 主体描述用中文，信息密度高
3. 色彩锚点 hex 在前、中文色名在后
4. 五官附带性格/气质因果
5. 辨识标记四要素齐全
6. 眼细节独立于眼型单独描述
7. 发际线细节独立描述
8. 皮肤纹理具象到毛孔
9. 服装必须有设计逻辑或功能理由
10. 场景必须有：色温+灯光风格+灯光方向+景深+拍摄角度+大气效果+材质
11. 指令词一段连续文本，逗号分隔，不换行
12. 人物纯白底，场景不需要白底
13. 负向提示词分 avoid + styleExclusions 两段
14. 年龄用标准段标签

## 交付前自检清单

- [ ] 输出直接以"## 人物资产"开头？
- [ ] 所有角色全局去重，只列固定特征？
- [ ] 年龄用标签（young-adult等）？
- [ ] 身份锚点有完整9项（含眼细节+发际线）？
- [ ] 色彩锚点 hex 在前？
- [ ] 辨识标记四要素齐全？皮肤纹理到毛孔？服装有设计逻辑？
- [ ] 每个场景有色温+灯光风格+灯光方向+景深+拍摄角度+大气效果+材质？
- [ ] 场景材质具体到可感知层面（青石板/夯土墙/琉璃瓦）？
- [ ] 色温参数匹配场景氛围？
- [ ] 负向提示词分两段？
- [ ] 指令词可完整复制使用？
