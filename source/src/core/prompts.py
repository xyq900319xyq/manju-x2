"""manju 业务 prompt 构造函数 + 风格/渲染类型配置。

**v0.6.17 全面复刻自原软件 D:\\剧本分镜助手\\server.py**：
    - STYLES 字典 (server.py:185-202) 16 个
    - RENDER_TYPES 字典 (server.py:204-257) 41 个
    - build_storyboard_prompt (server.py:267-312)
    - _filter_storyboard_output (server.py:338-356)
    - convert_to_standard_format (server.py:883-912)
    - run_seedance_agent 的 prompt 构造部分 (server.py:1316-1351)

约束：
- 与 D:\\剧本分镜助手\\ 无**运行时**依赖（不 import 也不调它的代码）
- 上述函数**手工翻译**到本文件，所有复刻必须标"复刻自 server.py:XXX"
- STYLES / RENDER_TYPES 写死在本文件（跟原软件一致），
  不读 config 文件——原软件也是硬编码
"""
import logging
import os
import re
import tempfile
from typing import List, Optional, Tuple

log = logging.getLogger("manju.prompts")


# =================================================================
# 视觉风格（STYLES）— 复刻自 server.py:185-202
# =================================================================

STYLES: dict = {
    "classic-cinematic": {"name": "经典电影", "en": "Classic Cinematic", "guidance": "经典好莱坞叙事风格，深景深构图，三点布光，轨道平稳移动，暖色温，端庄华丽的画面。"},
    "film-noir": {"name": "黑色电影", "en": "Film Noir", "guidance": "高对比度黑白或低饱和度画面，大面积阴影，百叶窗条纹光，烟雾缭绕。倾斜构图制造不安感。"},
    "epic-blockbuster": {"name": "史诗大片", "en": "Epic Blockbuster", "guidance": "大景别全景航拍，壮观的自然光或金色时刻光线，慢动作升格，恢弘配乐感画面。"},
    "intimate-drama": {"name": "亲密剧情", "en": "Intimate Drama", "guidance": "浅景深特写，自然柔光，手持轻微晃动增加亲密感。焦点紧跟人物面部微表情，暖色调。"},
    "romantic-film": {"name": "浪漫爱情", "en": "Romantic Film", "guidance": "柔光镜效果，暖金色光线，浅景深虚化背景，粉色调。慢动作、逆光剪影、镜头光晕。"},
    "documentary-raw": {"name": "纪实手持", "en": "Raw Documentary", "guidance": "手持摄影的轻微晃动，完全自然光，焦点偶尔偏移增加真实感。跟焦跟随人物运动。"},
    "news-report": {"name": "新闻纪实", "en": "News Report", "guidance": "固定机位或平稳肩扛，标准镜头（35-50mm），正面布光。冷静客观的视角，干净清晰的构图。"},
    "cyberpunk-neon": {"name": "赛博朋克", "en": "Cyberpunk Neon", "guidance": "霓虹紫红与冰蓝同框，轮廓光把人物从暗色背景中剥离。浅景深将霓虹灯化为迷幻光斑。"},
    "wuxia-classic": {"name": "古典武侠", "en": "Classic Wuxia", "guidance": "山间薄雾与落叶营造江湖苍茫感。摇臂从高处缓缓降至人物。自然侧光模拟竹林斑驳光影。"},
    "horror-thriller": {"name": "恐怖惊悚", "en": "Horror Thriller", "guidance": "低角度仰拍制造压迫感，暗角画面，蓝绿冷色调。突然的跳切和快速摇镜制造惊吓。"},
    "music-video": {"name": "MV风格", "en": "Music Video", "guidance": "快节奏剪辑，频闪灯光效果，超广角变形，色彩高度饱和或高对比。升格慢动作与降格快放。"},
    "family-warmth": {"name": "家庭温情", "en": "Family Warmth", "guidance": "温暖柔和的黄昏光线，浅景深突出人物互动。固定或缓慢推轨，轻微暖色调，画面干净明亮。"},
    "action-intense": {"name": "动作激烈", "en": "Intense Action", "guidance": "快速手持跟拍，急促变焦推拉，多角度快速切换。低角度仰拍强化力量感，碎片飞溅。"},
    "suspense-mystery": {"name": "悬疑推理", "en": "Suspense Mystery", "guidance": "低照度环境，指向性光源（手电、台灯），大量特写和插入镜头。浅景深限制观众视野。"},
    "hk-retro-90s": {"name": "90s港片", "en": "90s Hong Kong", "guidance": "偏黄绿色调，柔光镜或轻微过曝，手持跟拍。快速变焦推拉、倾斜构图制造动感。"},
    "golden-age-hollywood": {"name": "好莱坞黄金时代", "en": "Golden Age Hollywood", "guidance": "完美三点布光消除一切不美的阴影，深景深精心构图。轨道缓慢优雅移动如华尔兹。"},
}


# =================================================================
# 渲染类型（RENDER_TYPES）— 复刻自 server.py:204-257
# =================================================================

RENDER_TYPES: dict = {
    # === 3D动画 ===
    "3d_xuanhuan": {"name": "3D玄幻", "category": "3D动画", "guidance": "东方玄幻3D风格。仙气飘渺氛围，粒子光效丰富，法术特效华丽璀璨。场景宏大壮阔，角色身姿飘逸。色彩以金、紫、青为主调，光影通透富有层次感。画面需有CG动画电影的精致度。"},
    "3d_american": {"name": "3D美式", "category": "3D动画", "guidance": "美式3D动画风格（皮克斯/迪士尼质感）。夸张的肢体动作和生动表情，鲜明的色彩对比，角色造型风格化。画面干净明亮，适合全年龄段审美。"},
    "3d_q_version": {"name": "3DQ版", "category": "3D动画", "guidance": "3D Q版可爱风格。大头小身体比例（约1:2头身），圆润造型无锐角。明亮活泼的糖果色系，可爱的表情和夸张的动作设计。场景道具同样圆润化处理。"},
    "3d_realistic": {"name": "3D写实", "category": "3D动画", "guidance": "3D超写实风格。逼真材质纹理（PBR渲染），接近真人比例和皮肤质感。物理级光照模拟，电影级景深和运动模糊。追求以假乱真的画面效果。"},
    "3d_block": {"name": "3D块面", "category": "3D动画", "guidance": "3D低多边形几何风格。角色和场景由多面体构成，强调硬朗的体块感和结构性。色彩使用扁平化纯色块，光影以面为单位，类似几何雕塑的3D化呈现。"},
    "3d_voxel": {"name": "3D方块世界", "category": "3D动画", "guidance": "3D方块像素世界风格（Minecraft质感）。所有元素由小立方体构成，像素化的纹理贴图。角色、建筑、植被均为方块造型，充满手工搭建的童趣感。"},
    "3d_mobile": {"name": "3D手游", "category": "3D动画", "guidance": "3D手游画面风格。为移动端优化的卡通渲染，简洁的模型面和贴图精度。色彩明快饱和度高，角色造型偏向日系/韩系手游美术，特效华丽但不复杂。"},
    "3d_render_2d": {"name": "3D渲染2D", "category": "3D动画", "guidance": "三渲二技术（3D建模2D渲染）。保留3D的立体透视和运镜自由度，但渲染成2D动画的平面绘画质感。色彩分层明确，光影简化，类似高预算2D动画电影。"},
    "jp_3d_render_2d": {"name": "日式3D渲染2D", "category": "3D动画", "guidance": "日式三渲二风格。动漫赛璐珞着色，清晰的黑色勾线轮廓，色彩填充扁平化。光影以二分法为主（亮面/暗面），保留日系动画的手绘感但具备3D的空间纵深。"},
    # === 2D动画 ===
    "2d_animation": {"name": "2D动画", "category": "2D动画", "guidance": "传统手绘2D动画。流畅的逐帧动画质感，自然的线条变化，平面化分层上色。色彩柔和过渡，画面有温度的手工绘画痕迹。"},
    "2d_movie": {"name": "2D电影", "category": "2D动画", "guidance": "2D电影级动画。精致的场景绘制和细节刻画，电影级构图和光影设计。类似吉卜力/迪士尼手绘动画长片的质量，色彩丰富且和谐，画面有油画般的厚重感。"},
    "2d_fantasy": {"name": "2D奇幻动画", "category": "2D动画", "guidance": "2D奇幻风格。魔法元素、奇异生物和壮丽场景。色彩偏向紫、蓝、金色的幻彩组合，有发光和粒子效果。画面充满想象力和神秘氛围。"},
    "2d_retro": {"name": "2D复古动画", "category": "2D动画", "guidance": "2D复古怀旧动画。80-90年代电视动画质感，赛璐珞胶片上色风格，略微褪色的暖色调。画面有轻微的颗粒感和胶片特有的柔和质感，唤起童年回忆。"},
    "2d_american": {"name": "2D美式动画", "category": "2D动画", "guidance": "美式2D卡通风格。夸张变形的人物造型，大胆奔放的线条，高饱和度色彩。动作弹性十足（squash & stretch），表情极度夸张，喜剧感强。"},
    "2d_ghibli": {"name": "2D吉卜力", "category": "2D动画", "guidance": "吉卜力工作室风格。细腻的水彩手绘背景，柔和的自然光线，温暖治愈的整体氛围。角色动作真实细腻，场景充满生活气息和细节，天空和绿植刻画尤其精美。色彩偏向柔和的自然色系。"},
    "2d_retro_girl": {"name": "2D复古少女", "category": "2D动画", "guidance": "复古少女漫画风格。星星眼、飘逸长发、华丽繁复的服饰。粉嫩梦幻色调，大量花卉、星星、闪光等装饰元素。纤细优雅的线条，浪漫柔美的整体氛围。"},
    "2d_korean": {"name": "2D韩式动画", "category": "2D动画", "guidance": "韩式动画/webtoon风格。精致的人物设计注重时尚感和美型度，干净的线条和配色。肤色偏白皙，五官精致，发型服饰紧跟潮流。画面通透明亮，高级灰调配色。"},
    "2d_shonen": {"name": "2D热血动画", "category": "2D动画", "guidance": "热血少年动画风格。激烈战斗场面，速度线和冲击波效果丰富。爆炸和烟尘特效大量运用，角色表情夸张充满张力。色彩高饱和，对比强烈，画面充满爆发力。"},
    "2d_akira": {"name": "2D鸟山明", "category": "2D动画", "guidance": "鸟山明漫画风格。圆润饱满的角色造型，Q弹的肢体比例，简洁有力的线条。头发造型夸张呈锯齿状，机械设计精巧（胶囊公司风格）。场景有广阔的荒野和科幻元素。"},
    "2d_doraemon": {"name": "2D哆啦A梦", "category": "2D动画", "guidance": "哆啦A梦/藤子不二雄风格。圆润可爱的角色设计，简洁明快的线条和色彩。日常温馨的日式街道和家庭场景，蓝天白云的明亮色调。画面充满童趣和温暖。"},
    "2d_fujimoto": {"name": "2D藤本树", "category": "2D动画", "guidance": "藤本树（链锯人/炎拳）风格。电影感分镜构图，写实的表情刻画和肢体动作。粗犷有力的线条，大量阴影和留白对比。独特的叙事节奏和视觉冲击力，画面有粗粝质感。"},
    "2d_mob": {"name": "2D灵能百分百", "category": "2D动画", "guidance": "灵能百分百（ONE）风格。简约甚至粗糙的人物线条，但爆发场景时极致华丽的作画。强烈的反差感：平时朴素的画风在超能力发动时转变为绚丽的特效作画。色彩在爆发时极度饱和。"},
    "2d_jojo": {"name": "2D JOJO风", "category": "2D动画", "guidance": "JOJO的奇妙冒险风格。夸张扭曲的人物pose（JOJO立），强烈的黑色粗轮廓线，独特的时装设计感配色。经常使用高对比度的异色搭配，画面充满时尚感和戏剧性。"},
    "2d_detective": {"name": "2D日式侦探", "category": "2D动画", "guidance": "日式侦探/悬疑风格。阴郁沉重的氛围，硬朗写实的线条。大量阴影和暗部处理，有限光源（窗户光、台灯）。色调偏冷灰和深蓝，画面有强烈的悬疑感和压迫感。"},
    "2d_slamdunk": {"name": "2D灌篮高手", "category": "2D动画", "guidance": "灌篮高手（井上雄彦）风格。写实的运动描绘和人体结构，充满力量感的动态姿势。细腻的汗水和肌肉刻画，篮球场光影真实。90年代日本动画的经典质感，偏写实人物比例。"},
    "2d_astroboy": {"name": "2D手冢治虫", "category": "2D动画", "guidance": "手冢治虫经典漫画风格。圆润可爱的大眼睛角色，简洁优雅的线条，黑白为主但有层次。复古的未来主义设计，经典的日本漫画始祖画风，有温度的手绘质感。"},
    "2d_deathnote": {"name": "2D死亡笔记", "category": "2D动画", "guidance": "死亡笔记风格。暗黑哥特美学，精细繁复的阴影排线。灰黑主色调，偶尔的红色点缀。人物瘦削修长，眼神锐利。画面充满压抑感和心理战的紧张氛围。"},
    "2d_thick_line": {"name": "2D粗线条", "category": "2D动画", "guidance": "粗线条卡通风格。醒目的加粗轮廓线（2-3倍常规粗细），强烈的视觉冲击力。色彩填充简单直接，阴影用硬边黑色块。类似成人向卡通或街头涂鸦风格。"},
    "2d_rubberhose": {"name": "2D橡皮管动画", "category": "2D动画", "guidance": "1930年代橡皮管动画风格。角色四肢如橡皮管般弹性弯曲，没有关节限制。黑白或复古棕褐色调，画面有老电影的噪点和划痕质感。动作夸张滑稽，充满早期动画的纯真趣味。"},
    "2d_q_version": {"name": "2DQ版", "category": "2D动画", "guidance": "2D Q版可爱风格。大眼睛小嘴巴的萌系角色，圆润饱满的短小身体。粉嫩明亮的配色，大量爱心、星星等可爱装饰元素。画面充满治愈和欢乐感。"},
    "2d_pixel": {"name": "2D像素", "category": "2D动画", "guidance": "像素艺术风格。低分辨率复古游戏画面质感，8bit/16bit时代的美学。马赛克化的角色和场景，有限的色盘（尤其是16色或256色）。画面有怀旧电子游戏的感觉。"},
    "2d_gongbi": {"name": "2D工笔风", "category": "2D动画", "guidance": "中国传统工笔画风格。精致细腻的线条勾勒，层层渲染的色彩过渡。典雅的中国古典配色（朱砂、石青、藤黄），绢本或宣纸质感。画面有中国传统美学的端庄和雅致。"},
    "2d_stick": {"name": "2D简笔画", "category": "2D动画", "guidance": "极简简笔画风格。最少的线条表达人物和场景，火柴人级别的简约。但通过巧妙的动态设计和微表情让画面生动有趣。色彩极简，通常只用2-3种颜色。"},
    "2d_watercolor": {"name": "2D水彩", "category": "2D动画", "guidance": "水彩晕染风格。柔和的色彩边界，自然的颜料渗透和渐变效果。透明的色彩叠加，纸张纹理可见。画面有艺术插画的精致感，色彩清新淡雅，留白恰到好处。"},
    "2d_simple_line": {"name": "2D简单线条", "category": "2D动画", "guidance": "极简单线条风格。只有干净的轮廓线条，少量或没有色彩填充。依赖线条的粗细变化表达形体，留白面积大。画面优雅简洁，类似插画式的极简表达。"},
    "2d_comic": {"name": "2D美式漫画", "category": "2D动画", "guidance": "美式超级英雄漫画风格。网点纸阴影，爆炸状对话框和拟声词。高对比度的上色，肌肉线条分明。画面充满戏剧张力和动作感，典型的Marvel/DC漫画视觉。"},
    "2d_shoujo": {"name": "2D少女漫画", "category": "2D动画", "guidance": "日式少女漫画风格。纤细优美的线条，大量花卉和闪亮网点效果。人物身材修长（8-9头身），发型华丽飘逸。浪漫的构图方式，画面充满粉色泡泡般的梦幻氛围。"},
    "2d_horror": {"name": "2D诡异惊悚", "category": "2D动画", "guidance": "诡异惊悚风格（伊藤润二式）。扭曲变形的角色造型，密集繁复的线条排布。黑白色调为主，大量阴影和暗部。画面制造深层的不安和恐惧，日常场景中侵入异常元素。细节过度描写强化恐怖感。"},
    # === 真人影视 ===
    "real_movie": {"name": "真人电影", "category": "真人影视", "guidance": "真人电影质感。真实的人类演员和物理场景，电影级摄影构图和调色。自然的皮肤纹理和环境光，注意避免CG感。画面有电影胶片的色彩科学和动态范围。"},
    "real_costume": {"name": "真人古装", "category": "真人影视", "guidance": "真人古装影视风格。真实考究的古代服饰（汉服等）和道具，古建筑实景或精致搭景。服化道细节丰富，注重历史质感和年代氛围。古典中式美学色彩搭配。"},
    "real_hk_retro": {"name": "真人复古港片", "category": "真人影视", "guidance": "90年代香港电影风格。偏黄绿色调的画面，略微的柔光或过曝效果。胶片颗粒感，手持摄影的临场感。港式动作片的运镜节奏和构图。"},
    "real_wuxia": {"name": "真人复古武侠", "category": "真人影视", "guidance": "真人武侠影视风格。真实的武打动作和江湖场景，竹林天际、大漠客栈等武侠标志性景观。自然的微风和衣袂飘动，武侠世界的真实质感和意境。"},
    "real_bloom": {"name": "真实光晕", "category": "真人影视", "guidance": "光晕美学风格。柔和的镜头光晕和逆光拍摄效果，梦幻的画面氛围。暖金色光线透过树叶或窗纱的斑驳感。画面有朦胧的美感和浪漫气息。"},
    # === 定格动画 ===
    "stop_motion": {"name": "定格动画", "category": "定格动画", "guidance": "经典定格动画风格。逐帧拍摄的实体模型，微妙的帧间抖动感和手工操作痕迹。实体材质的光影质感（非CG的完美平滑），有温度和工匠精神的手工艺术美感。"},
    "figure_stop_motion": {"name": "手办定格动画", "category": "定格动画", "guidance": "手办/可动人偶定格动画。使用Action Figure和场景模型逐帧拍摄。关节可动范围的限制感也是特色，手办的涂装质感可见。适合超级英雄或机甲类题材。"},
    "clay_stop_motion": {"name": "粘土定格动画", "category": "定格动画", "guidance": "粘土/橡皮泥定格动画。柔软可变形的角色材质，手工捏制的痕迹和指纹。形态可以逐帧变形（transform），色彩鲜艳的橡皮泥质感。充满童趣和创意的手工艺术。"},
    "lego_stop_motion": {"name": "积木定格动画", "category": "定格动画", "guidance": "乐高/积木定格动画。标准的乐高小人仔和积木构建的场景。方块化的世界，乐高特有的卡扣结构。色彩鲜明块状分明，有玩具世界的独特魅力和趣味性。"},
    "felt_stop_motion": {"name": "毛绒定格动画", "category": "定格动画", "guidance": "毛绒布偶定格动画。柔软的毛绒布料质感，温暖可爱的布偶角色。布料纹理和缝线可见，动作幅度受布料限制而显得笨拙可爱。整体色调柔和温暖，适合低幼或治愈题材。"},
}


def get_style_block(style_id: Optional[str]) -> str:
    """复刻自 server.py:276-284。"""
    if not style_id or style_id not in STYLES:
        return ""
    s = STYLES[style_id]
    return f"""【视觉风格指定】
使用「{s['name']}」({s['en']})视觉风格：
{s['guidance']}
请在分镜中严格遵循此视觉风格的构图、光影、色调和运镜方式。

"""


def get_render_block(render_type: Optional[str]) -> str:
    """复刻自 server.py:286-294。"""
    if not render_type or render_type not in RENDER_TYPES:
        return ""
    r = RENDER_TYPES[render_type]
    guidance_text = r.get("guidance", "")
    return f"""【渲染类型指定】
使用「{r['name']}」({r['category']})渲染风格。
视觉特征：{guidance_text}
请在分镜的画面描述中严格遵循以上渲染类型的视觉特征进行描绘，确保每一个镜头的画面描述都与该渲染风格一致。
"""


# =================================================================
# 分镜 prompt 构造 — 复刻自 server.py:267-312
# =================================================================

def build_storyboard_prompt(
    script: str,
    previous_summaries: Optional[List[dict]] = None,
    style_id: Optional[str] = None,
    render_type: Optional[str] = None,
) -> str:
    """复刻自 D:\\剧本分镜助手\\server.py:267 `build_storyboard_prompt()`。

    Args:
        script: 当前剧集剧本
        previous_summaries: 续集上下文，list of {episode_num, title, summary}
        style_id: STYLES 字典 key（如 'classic-cinematic'）
        render_type: RENDER_TYPES 字典 key（如 '3d_xuanhuan'）

    Returns:
        完整的分镜生成 prompt。固定以"## 🎬 导演核算报告"为输出格式起点。
    """
    context_block = ""
    if previous_summaries:
        context_block = "【前序剧集摘要 - 请保持连贯性】\n"
        for s in previous_summaries:
            context_block += f"第{s['episode_num']}集「{s['title']}」剧情概要：{s['summary']}\n"
        context_block += "\n"

    style_block = get_style_block(style_id)
    render_block = get_render_block(render_type)

    is_sequel = bool(previous_summaries)
    sequel_clause = (
        "注意：这是续集，请严格参照前序剧集的人物、世界观、剧情伏笔，确保连贯。"
        if is_sequel else ""
    )

    return f"""【重要：必须全部使用中文输出，包括所有术语和描述】
【关键：直接在回复中输出完整分镜脚本文字，禁止使用 write_file 或其他工具写入文件。分镜内容必须出现在你的回复正文中。】

{render_block}{style_block}请为以下剧本生成完整的分镜脚本。{sequel_clause}

【导演硬约束 — 必须遵守，优先级高于剧本内的任何数字】
1. 剧本中可能包含"本集时长预估""预估镜头数"等编剧估算数据——请完全忽略这些数字。它们不是分镜依据，只是编剧的个人估算。
2. 你以导演身份独立重新规划：根据故事的情绪密度、动作复杂度、对话层次，重新判断合理的总镜头数。
3. 硬性底线：对于正常剧情的 2-4 分钟视频，总镜头数不得低于 100 镜。165 秒的视频，按每秒至少 0.6 镜计算，最少 100 镜起步，上不封顶。
4. 如果剧本内容较少导致难以达到 100 镜，你需要通过增补镜头（场景建立、反应链、情绪留白、细节拆分、角色铺垫）来补足——这恰恰是分镜师 90% 的价值所在。
5. 交付前必须执行两轮自检：(1) 数镜头总数，不够 100 就回头补；(2) 逐条核对剧本，确保零遗漏。

{context_block}【本次剧本】
{script}

请严格按照以下固定格式输出分镜（全部使用中文，不要在正文中使用 Markdown 表格）：

**输出结构：**
```
## 🎬 导演核算报告
（导演核算内容：总镜头数、情绪曲线、增补策略等）

# 第X集：标题 — 完整分镜脚本

## 【整体风格说明】
（渲染类型、视觉风格、色调、光影、运镜、角色视觉字典）

═══════════════════════════════════════════════════════
场景 1: 场景名称 — 时间 — 内/外
氛围: xxx | 色调: xxx | 场景时长: xx秒
═══════════════════════════════════════════════════════

镜头001

时长：1秒

景别：特写

角度：平视

运镜：固定

画面描述(Prompt)：（纯中文，主体+动作+环境+光影+风格）

对白/旁白：（标说话人，无对白则写 "—"）

音效/音乐：（环境音+动作音+情绪音，含该镜头台词对话内容）

衔接逻辑：【主逻辑+次逻辑】（如【动作顺接+视线引导】）

备注：（该镜头服务目的：五大支柱覆盖/叙事/角色/情绪）

（1）秒

───

镜头002
（同上结构）

───
```

**格式铁律：**
1. 每个镜头必须以 11 个字段独立成块（镜头号→时长→景别→角度→运镜→画面描述→对白/旁白→音效/音乐→衔接逻辑→备注→累计时间），禁止合并或省略任何字段。
2. 镜头之间用 `───` 分隔。
3. 每个场景独立编号，从镜头001重新开始。每个场景末尾标注 `（xx）秒 (场景x结束)`。
4. **绝对禁止使用 Markdown 表格**（`| --- | --- |` 格式）。分镜内容必须用逐行块格式，不是表格。
5. 所有内容使用纯中文，衔接逻辑标签也用中文。
6. 直接输出在回复正文中，不写入文件。"""


def _filter_storyboard_output(output: str) -> str:
    """复刻自 D:\\剧本分镜助手\\server.py:338-356 `_filter_storyboard_output()`。

    过滤 hermes 推理块和 session_id，从「## 🎬 导演核算报告」行开始提取。
    """
    # 优先：找 "## 🎬 导演核算报告" 起点
    m = re.search(r'(?:^|\n)(##\s*🎬\s*导演核算报告[^\n]*)', output)
    if m:
        body = output[m.start():].strip()
        body = re.sub(r'\n{3,}', '\n\n', body)
        body = re.sub(r'\n---\s*\n', '\n\n', body)
        return body.strip()
    # 兜底：去推理块和 session_id
    if "┌─ Reason" in output:
        nl = output.find("\n", output.find("┌─ Reason"))
        if nl > 0:
            output = output[nl + 1:].strip()
    sid_pos = output.rfind("session_id:")
    # 注意：rfind 返回 -1 当找不到；当 output 太短时 -1 > len-100 仍为 True，
    # 错误截断。修法：sid_pos >= 0 且 sid_pos > len-100 才截断
    if sid_pos >= 0 and sid_pos > len(output) - 100:
        output = output[:sid_pos].strip()
    return output


# =================================================================
# 资产生图 prompt（中文 8 段 bullet 格式）— 复刻自 server.py:883-912
# =================================================================

def build_asset_image_prompt(
    kind: str,
    name: str,
    description: str,
    render_type: Optional[str] = None,
) -> str:
    """构造**中文 8 段 bullet 格式**资产生图 prompt。

    复刻自原软件 D:\\剧本分镜助手\\server.py:883 `convert_to_standard_format()`
    的输入端。原软件把资产 cache 里的中文 8 段 bullet 喂给 dreamina，
    manju 在生成资产时就**直接**让 LLM 输出这种格式。

    8 段 bullet：
        【身份/背景】 【外貌特征】 【辨识标记】 【色彩锚点】
        【皮肤纹理】 【发型】 【服装】 【人物关系】

    不同 kind 的开头标签：
        character → 专业角色设计参考图，"{name}"
        scene     → 场景概念设计图，"{name}"
        prop      → 物品概念设计图，"{name}"

    Args:
        kind: "character" | "scene" | "prop"
        name: 资产名
        description: 资产描述（来自 AssetExtractTask 解析结果）
        render_type: RENDER_TYPES key，注入到 bullet 段尾

    Returns:
        完整的中文 bullet prompt（dreamina 调通的指令词格式）
    """
    kind_label = {
        "character": "专业角色设计参考图",
        "scene": "场景概念设计图",
        "prop": "物品概念设计图",
    }.get(kind, "资产参考图")

    # 8 段 bullet
    desc = (description or "").strip()
    # 渲染类型注入
    render_suffix = ""
    if render_type and render_type in RENDER_TYPES:
        r = RENDER_TYPES[render_type]
        render_suffix = f"\n【渲染类型】{r['name']}（{r['category']}）：{r['guidance']}"

    if kind == "character":
        bullets = f"""专业角色设计参考图，"{name}"，
【身份/背景】{desc}
【外貌特征】
【辨识标记】
【色彩锚点】
【皮肤纹理】
【发型】
【服装】
【人物关系】{render_suffix}"""
    elif kind == "scene":
        bullets = f"""场景概念设计图，"{name}"，
【场景描述】{desc}
【构图视角】
【色彩光线】
【氛围调性】{render_suffix}"""
    else:  # prop
        bullets = f"""物品概念设计图，"{name}"，
【物品描述】{desc}
【材质工艺】
【使用场景】
【细节纹理】{render_suffix}"""
    return bullets


def convert_to_standard_format(text: str) -> str:
    """复刻自 D:\\剧本分镜助手\\server.py:883-912 `convert_to_standard_format()`。

    把中文 8 段 bullet 翻译成英文 dot-separated 格式给 dreamina 用。
    用于：`AssetExtractTask` 跑完后，把 assets markdown 转成 dreamina 友好格式
    存到数据库，**生图时直接用**。
    """
    t = text
    t = re.sub(r'专业角色设计参考图，"([^"]+)"',
               r'professional character design sheet for "\1"', t)
    t = re.sub(r'，【身份/背景】', r',\n【身份/背景】\n', t)
    t = re.sub(r'，【外貌特征】', r'\n\n【外貌特征】\n', t)
    t = re.sub(r'，【辨识标记】', r'\n【辨识标记】\n', t)
    t = re.sub(r'，【色彩锚点】', r'\n【色彩锚点】\n', t)
    t = re.sub(r'，【皮肤纹理】', r'\n【皮肤纹理】\n', t)
    t = re.sub(r'，【发型】', r'\n【发型】\n', t)
    t = re.sub(r'，【服装】', r'\n【服装】\n', t)
    t = re.sub(r'，【人物关系】', r'\n\n【人物关系】\n', t)
    t = re.sub(r'角色参考图版式', 'character reference sheet layout', t)
    t = re.sub(
        r'pure solid white background, isolated character on white background, '
        r'absolutely no background scenery',
        'white background, clean presentation', t)
    t = re.sub(r'场景概念设计图，"([^"]+)"',
               r'scene concept design for "\1"', t)
    t = re.sub(r'物品概念设计图，"([^"]+)"',
               r'prop concept design for "\1"', t)
    if 'detailed background' not in t:
        for tag in [
            'detailed illustration, concept art, character model sheet',
            'detailed illustration, concept art, environment design',
            'detailed illustration, concept art, prop design',
        ]:
            if tag in t:
                t = t.replace(tag, 'detailed background, ' + tag)
                break
    # 去掉中文指令词前缀
    t = re.sub(r'- 中文指令词：', '', t)
    t = re.sub(r'- 负向提示词：\n[^\n]*\n(?:  -[^\n]*\n)*', '', t)
    return t


# =================================================================
# Seedance 视频 prompt 构造 — 复刻自 server.py:1316-1351
# =================================================================

# hermes.exe 是 PyInstaller 打包，-q argv 传 >22000 字节会段错误（C 层）
# 复刻自 server.py:1315
HERMES_ARGV_LIMIT = 20000  # 留余量


def build_seedance_prompt(
    episode_title: str,
    storyboard: str,
    asset_names: str = "",
    style_id: Optional[str] = None,
    render_type: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """复刻自 D:\\剧本分镜助手\\server.py:1316-1351 `run_seedance_agent` 的
    prompt 构造部分（**不**含 subprocess.run / 队列管理，那些走 manju
    自己的 TaskQueue）。

    v0.7.8.21:manju 改架构走 urllib 直连 LLM,LLM 没有 Read tool,不能读本地文件。
    老 hermes 走文件方式的逻辑(HERMES_ARGV_LIMIT > 20000 chars 时写 tmp file +
    让 hermes 读)对 manju 直连无效——LLM 看不到文件,只瞎编。
    修法:不再写临时文件,storyboard 始终内联进 prompt。

    Args:
        episode_title: 剧集标题
        storyboard: 完整分镜文本
        asset_names: 资产名列表（人/场/物三段纯文本，由 v0.6.16 的
                     `format_asset_list_text()` 生成）
        style_id: STYLES 字典 key
        render_type: RENDER_TYPES 字典 key

    Returns:
        (prompt_text, None) 元组。第二个元素总返回 None（保留兼容）。
    """
    style_info = ""
    if style_id and style_id in STYLES:
        s = STYLES[style_id]
        style_info = f"\n指定视觉风格：「{s['name']}」({s['en']})"
    if render_type and render_type in RENDER_TYPES:
        r = RENDER_TYPES[render_type]
        style_info += f"\n指定渲染类型：「{r['name']}」({r['category']})"

    # v0.7.8.22:asset_block 只传**资产名字列表**(人名/场名/物名逗号拼接),
    # 不传完整资产描述。复刻老软件 D:\剧本分镜助手\server.py:1307-1310:
    #   asset_block = f"\n\n【项目资产】\n{asset_names}\n"
    # `asset_names` 由 main_window._get_asset_list_for_current_project() 返回,
    # 走的是 `format_asset_list_text()`(asset_parser.py:248),只输出名字,
    # 形如:"人物资产:陈戈、师尊\n场景资产:青云宗洞府\n物品资产:丹炉"。
    # seedance agent 看名字 → @陈戈 引用资产库里的资产,资产外貌描述由
    # asset-designer profile 的 seedance 库做视觉锚点,**不是**靠本 prompt 注入。
    asset_block = ""
    if asset_names:
        asset_block = f"\n\n【项目资产】\n{asset_names}\n"

    # v0.7.8.22:恢复老软件 D:\剧本分镜助手\server.py:1312-1351 的临时文件逻辑。
    # hermes.exe 是 PyInstaller 打包,-q argv 传 >22000 字节会段错误(0xC0000005)。
    # 超过 HERMES_ARGV_LIMIT 时,把 storyboard 写到临时文件,prompt 改为
    # "请读取分镜脚本文件: <path>",hermes 用 file:read_file 工具自己读。
    # **manju 走 hermes 子进程** -- 复刻老软件架构。
    prompt = f"""【重要：全部使用中文输出，直接在回复正文中输出完整提示词，不要写入文件】

为以下分镜脚本生成 Seedance 2.0 视频生成提示词。{style_info}

剧集：{episode_title}
{asset_block}
【分镜脚本 — 完整版】
{storyboard}

请严格按照 seedance-prompt-generator skill 的 Director Angel 编译格式输出，包括：
1. 导演核算报告（总时长+拆段说明）
2. 每个 Segment 含 Asset Definitions / Global Style / Base Compiled Prompt / Director's Shot Matrix / Native Audio
3. 全中文输出，运镜术语保留英文
4. **严格按照 seedance-prompt-generator skill 的拆段规则执行：每个 Segment ≤5 镜，进位后总时长 ≤15s。场景若超过 5 镜或 15 秒，必须按 skill 规则拆分为多个 Segment。禁止将整个场景（如 26 镜）塞进一个 Segment。**"""

    if len(prompt) <= HERMES_ARGV_LIMIT:
        return prompt, None

    # 长:写临时文件 + 短 prompt
    try:
        import tempfile as _tmp
        import os as _os
        tmp_sb_file = _os.path.join(
            _tmp.gettempdir(),
            f"_manju_seedance_sb_{abs(hash(storyboard)) & 0xFFFFFFFF}.md",
        )
        with open(tmp_sb_file, "w", encoding="utf-8") as f:
            f.write(f"# {episode_title} — 完整分镜脚本\n\n{storyboard}")
        short_prompt = f"""【重要：全部使用中文输出，直接在回复正文中输出完整提示词，不要写入文件】

请读取分镜脚本文件：{tmp_sb_file}

然后按照 seedance-prompt-generator skill 的 Director Angel 编译格式，为该剧集生成完整 Seedance 2.0 视频生成提示词。

剧集：{episode_title}{style_info}
{asset_block}

要求：
1. 完整读取该文件内的分镜脚本（包含所有分镜镜头的画面/对白/动作/时序），然后直接输出导演核算报告 + Segment 矩阵 + 全部 Segment 内容。"""
        logging.getLogger("manju.prompts").info(
            "长 storyboard (%dB) 改用文件方式：%s", len(storyboard), tmp_sb_file,
        )
        return short_prompt, tmp_sb_file
    except Exception as _e:
        logging.getLogger("manju.prompts").warning(
            "写 seedance 临时文件失败,回退为 argv 方式: %s", _e,
        )
        return prompt, None


# =================================================================
# 资产抽取 prompt 构造 — 复刻自 server.py:359-378 build_project_asset_prompt
# =================================================================

def build_project_asset_prompt(
    script_text: str,
    style_id: Optional[str] = None,
    render_type: Optional[str] = None,
    project_name: str = "",
) -> Tuple[str, Optional[str]]:
    """v0.7.3 复刻自原软件 D:\\剧本分镜助手\\server.py:359-378 `build_project_asset_prompt`。

    拼接发给 hermes asset-designer 的 prompt：
    - 标题行
    - 【渲染类型指定】块（用 RENDER_TYPES 字典 name + category + "指令词中的渲染标签必须匹配此类型"）
    - 【视觉风格指定】块（用 STYLES 字典 name + en + guidance，v0.7.3 新增，老软件没注入）
    - 【重要规则】3 条
    - 完整剧本内容（直接拼，小数据集时）
    - 末尾 "请严格按照 script-asset-designer skill 的格式输出。"

    **不**加 manju 之前自己写的硬约束（中文 8 段 bullet 模板、write_file 硬约束、严格遵守）。

    Args:
        script_text: 完整剧本内容（多集拼接：每个集一段 "【第N集「标题」】\\n集标题\\n剧本..."）
        style_id: STYLES 字典 key（v0.7.3 新增，可选）
        render_type: RENDER_TYPES 字典 key（可选）
        project_name: 项目名（v0.7.3 不嵌入 prompt，但保留参数对齐其他函数）

    Returns:
        (prompt_text, tmp_script_file_path) 元组。
        - script_text <= 20000 字符时：tmp_script_file_path 为 None，prompt 直接含剧本
        - script_text > 20000 字符时：写到临时文件，prompt 改为 "请读取剧本文件：{path}"
    """
    del project_name  # 老软件 prompt 不用项目名

    parts: List[str] = []

    # 1. 标题行
    parts.append("请提取以下剧本的全局资产清单：人物资产、场景资产、物品资产。")
    parts.append("")

    # 2. 渲染类型块（用 RENDER_TYPES 字典全名 + 渲染标签硬规则）
    if render_type and render_type in RENDER_TYPES:
        r = RENDER_TYPES[render_type]
        parts.append("【渲染类型指定】")
        parts.append(
            f"使用「{r['name']}」({r['category']})渲染风格。"
            "指令词中的渲染标签必须匹配此类型。"
        )
        parts.append("")

    # 3. 视觉风格块（v0.7.3 新增，复刻 get_style_block 格式）
    if style_id and style_id in STYLES:
        s = STYLES[style_id]
        parts.append("【视觉风格指定】")
        parts.append(f"使用「{s['name']}」({s['en']})视觉风格：")
        parts.append(s["guidance"])
        parts.append("请在分镜中严格遵循此视觉风格的构图、光影、色调和运镜方式。")
        parts.append("")

    # 4. 重要规则（老软件原版 3 条）
    parts.append("【重要规则】")
    parts.append("- 直接输出结果，不要任何分析推理过程")
    parts.append("- 人物只描述常规默认状态，禁止事件性/情绪性/临时状态描述")
    parts.append("- 人物/场景/物品全局去重合并，同一实体只出现一次")
    parts.append("")

    # 5. 剧本内容（直接拼）
    parts.append(script_text)
    parts.append("")

    # 6. 末尾指令
    parts.append("请严格按照 script-asset-designer skill 的格式输出。")

    prompt = "\n".join(parts)

    # 7. 大数据集走临时文件
    tmp_script_file: Optional[str] = None
    if len(prompt) > HERMES_ARGV_LIMIT:
        try:
            tmp_script_file = os.path.join(
                tempfile.gettempdir(),
                f"_manju_asset_script_{abs(hash(script_text))}.md",
            )
            with open(tmp_script_file, "w", encoding="utf-8") as f:
                f.write(f"# 完整剧本（用于资产抽取）\n\n{script_text}")
            # 用文件引用替换内联剧本
            parts_replaced: List[str] = []
            for item in parts:
                if item is script_text:
                    parts_replaced.append(f"请先完整读取剧本文件：{tmp_script_file}")
                else:
                    parts_replaced.append(item)
            prompt = "\n".join(parts_replaced)
            log.info(
                "长剧本 (%dB) 改用文件方式：%s",
                len(script_text), tmp_script_file,
            )
        except OSError as e:
            log.warning("写临时文件失败，回退为 argv 方式：%s", e)
            tmp_script_file = None

    return prompt, tmp_script_file
