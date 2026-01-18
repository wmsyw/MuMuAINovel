"""提示词管理服务"""
from typing import Dict, Any, Optional
import json


# Genre Strategy Matrix for Long-Form Novels (1M+ words)
GENRE_STRATEGIES = {
    "history": {
        "keywords": ["历史", "权谋", "架空历史", "穿越", "三国", "大秦", "大明"],
        "instruction": """
【长篇驱动模式：推演与势】
- 核心动力：从"棋子"到"棋手"的转变，积蓄力量 -> 改变大势 -> 遭遇反噬 -> 建立新秩序。
- 关键节点：
  * 100万字：必须完成阶级跨越，成为一方诸侯或朝堂大佬。
  * 300万字：必须涉及改朝换代或文明路线的分歧（如：工业革命 vs 传统皇权）。
- 爽点来源：种田建设的成就感、运筹帷幄的智商碾压、改变历史意难平。
- 写作风格：厚重、考究。多用侧面描写烘托大势，对话需符合时代阶级特征，权谋要草蛇灰线。
"""
    },
    "scifi": {
        "keywords": ["科幻", "星际", "赛博朋克", "末世", "机甲", "未来"],
        "instruction": """
【长篇驱动模式：尺度跃迁】
- 核心动力：技术奇点与文明冲突，从"行星地表"走向"宇宙深空"。
- 关键节点：
  * 100万字：接触第一类外星文明或完成关键技术飞跃（如可控核聚变）。
  * 300万字：涉及维度战争、宇宙社会学或时间悖论。
  * 500万字：探讨存在意义、创世/灭世的哲学命题。
- 写作风格：冷峻、理性。注重技术细节的逻辑自洽（Hard Sci-Fi）或社会学推演（Soft Sci-Fi）。
"""
    },
    "supernatural": {
        "keywords": ["灵异", "惊悚", "恐怖", "神秘复苏", "克苏鲁", "怪谈"],
        "instruction": """
【长篇驱动模式：拼图与规则】
- 核心动力：从"求生者"变为"驾驭者"，建立自己的势力/禁区。
- 关键节点：
  * 100万字：主角建立安全区/驭鬼者组织。
  * 300万字：世界观彻底崩坏，从解决灵异事件变成对抗末日/旧日支配者。
- 恐怖维持：随着主角变强，恐怖源从"具体的鬼"升级为"无法理解的规则"或"因果律"。
- 写作风格：压抑、诡谲。多用环境描写烘托氛围，强调未知的恐惧，少用热血词汇。
"""
    },
    "suspense": {
        "keywords": ["悬疑", "刑侦", "推理", "侦探", "犯罪"],
        "instruction": """
【长篇驱动模式：剥洋葱引擎】
- 核心动力：案中案，局中局，阴谋的无限嵌套。
- 关键节点：
  * 100万字：揭开第一个大BOSS，却发现他只是某个庞大组织的棋子。
  * 300万字：主角发现自己也是阴谋的一部分（身世之谜/记忆修改）。
- 续航关键：永远不要让读者看到真相的全貌，每解决一个谜题，要引出两个新谜题。
- 写作风格：紧凑、高智商。强调逻辑链条，伏笔回收必须严丝合缝，反转要震撼。
"""
    },
    "western_fantasy": {
        "keywords": ["西幻", "奇幻", "DND", "魔法", "龙与地下城", "领主"],
        "instruction": """
【长篇驱动模式：史诗构建】
- 核心动力：探索地图 + 收集神器 + 阵营战争 + 封神之路。
- 关键节点：
  * 100万字：完成小队集结，解决王国危机/深渊入侵。
  * 300万字：点燃神火，参与位面战争/深渊血战。
  * 500万字：建立神系，重塑晶壁系规则。
- 写作风格：史诗感、咏叹调。注重种族习俗、宗教历史、魔法原理的深度描写。
"""
    },
    "eastern_fantasy": {
        "keywords": ["玄幻", "仙侠", "修真", "高武", "洪荒", "东方玄幻"],
        "instruction": """
【长篇驱动模式：位面飞升】
- 核心动力：生命层次的进化，换地图（新手村->主城->新位面->神界）。
- 关键节点：
  * 100万字：称霸本位面/人界，准备飞升。
  * 300万字：在更高位面建立宗门/天庭，参与大道之争。
- 爽点来源：境界突破、宝物争夺、跨阶杀敌、众生膜拜。
- 写作风格：热血、宏大。强调战斗画面的破坏力，等级森严的社会结构。
"""
    },
    "urban": {
        "keywords": ["都市", "言情", "职场", "现实", "生活", "娱乐", "重生", "神豪", "校花"],
        "instruction": """
【长篇驱动模式：圈层与欲望】
- 核心动力：社会地位的提升、财富/权力的积累、情感的圆满。
- 关键节点：
  * 50万字（积累期）：第一桶金，初识关键人脉，解决生存危机。
  * 200万字（扩张期）：行业博弈，资本运作，确立行业地位。
  * 500万字（巅峰期）：改变世界/行业规则，从棋子变成棋手。
- 写作重点：
  * 去翻译腔：对话符合当代口语，多用潜台词。
  * 细节质感：具体描写品牌、车型、食物、穿搭，增加真实感。
  * 爽点：并非单纯打脸，而是通过"人脉网"和"资源调动"降维打击对手。
"""
    }
}


class WritingStyleManager:
    """写作风格管理器"""
    
    @staticmethod
    def apply_style_to_prompt(base_prompt: str, style_content: str) -> str:
        """
        将写作风格应用到基础提示词中
        
        Args:
            base_prompt: 基础提示词
            style_content: 风格要求内容
            
        Returns:
            组合后的提示词
        """
        # 在基础提示词末尾添加风格要求
        return f"{base_prompt}\n\n{style_content}\n\n请直接输出章节正文内容，不要包含章节标题和其他说明文字。"


class PromptService:
    """提示词模板管理"""
    
    # ========== V2版本提示词模板（RTCO框架）==========
    
    # 世界构建提示词 V2（RTCO框架）
    WORLD_BUILDING = """<system>
你是资深的世界观设计师，擅长为{genre}类型的小说构建真实、自洽的世界观。
</system>

<task>
【设计任务】
为小说《{title}》构建完整的世界观设定。

【核心要求】
- 主题契合：世界观必须支撑主题"{theme}"
- 简介匹配：为简介中的情节提供合理背景
- 类型适配：符合{genre}类型的特征
- 规模适当：根据题材选择合适的设定尺度
</task>

<strategy priority="P0">
【长篇类型策略 - 核心指导】
{genre_strategy}
</strategy>

<input priority="P0">
【项目信息】
书名：{title}
类型：{genre}
主题：{theme}
简介：{description}
</input>

<guidelines priority="P1">
【类型指导原则】

**现代都市/言情/青春**：
- 时间：当代社会（2020年代）或近未来（2030-2050年）
- 避免：大崩解、纪元、末日等宏大概念
- 重点：具体城市环境、职场文化、社会现状

**历史/古代**：
- 时间：明确的历史朝代或虚构古代
- 重点：时代特征、礼教制度、阶级分化

**玄幻/仙侠/修真**：
- 时间：修炼文明的特定时期
- 重点：修炼规则、灵气环境、门派势力

**科幻**：
- 时间：未来明确时期（如2150年、星际时代初期）
- 重点：科技水平、社会形态、文明转折

**奇幻/魔法**：
- 时间：魔法文明的特定阶段
- 重点：魔法体系、种族关系、大陆格局

**设定尺度控制**：
- 现代都市：聚焦某个城市、行业、阶层
- 校园青春：学校环境、学生生活、成长困境
- 职场言情：公司文化、行业特点、职业压力
- 史诗题材：才需要宏大的世界观架构
</guidelines>

<output priority="P0">
【输出格式】
生成包含以下四个字段的JSON对象，每个字段300-500字：

1. **time_period**（时间背景与社会状态）
   - 根据类型设定合适规模的时间背景
   - 现代题材：具体社会特征（如：2024年北京，互联网行业高速发展）
   - 历史题材：明确朝代和阶段（如：明朝嘉靖年间，海禁政策下的沿海）
   - 幻想题材：文明发展阶段，具体而非空泛
   - 阐明时代核心矛盾和社会焦虑

2. **location**（空间环境与地理特征）
   - 故事主要发生的空间环境
   - 现代题材：具体城市名或类型
   - 环境如何影响居民生存方式
   - 标志性场景描述

3. **atmosphere**（感官体验与情感基调）
   - 身临其境的感官细节（视觉、听觉、嗅觉）
   - 美学风格和色彩基调
   - 居民心理状态和情绪氛围
   - 与主题情感呼应

4. **rules**（世界规则与社会结构）
   - 世界运行的核心法则
   - 现代题材：社会规则、行业潜规则、人际法则
   - 幻想题材:力量体系、社会等级、资源分配
   - 权力结构和利益格局
   - 社会禁忌及后果

【格式规范】
- 纯JSON输出，以{{开始、}}结束
- 无markdown标记、代码块符号
- 字段值为完整段落文本
- 不使用特殊符号包裹内容
- 提供充实原创内容

【JSON示例】
{{
  "time_period": "时间背景与社会状态的详细描述（300-500字）",
  "location": "空间环境与地理特征的详细描述（300-500字）",
  "atmosphere": "感官体验与情感基调的详细描述（300-500字）",
  "rules": "世界规则与社会结构的详细描述（300-500字）"
}}
</output>

<constraints>
【必须遵守】
✅ 简介契合：为简介情节提供合理背景
✅ 类型适配：符合{genre}的特征
✅ 主题贴合：支撑主题"{theme}"
✅ 具象化：用具体细节而非空洞概念
✅ 逻辑自洽：所有设定相互支撑

【禁止事项】
❌ 生成与类型不匹配的设定
❌ 为小规模题材使用宏大世界观
❌ 使用模板化、空泛的表达
❌ 输出markdown或代码块标记
</constraints>"""

    # 世界扩展提示词 V2（RTCO框架 - 换地图/升级）
    WORLD_EXPANSION = """<system>
你是资深的世界观架构师，擅长设计宏大的多层级世界体系。
</system>

<task>
【扩展任务】
为小说《{title}》设计更高层级的世界地图（换地图/版本升级）。
当前剧情已达到【{current_level}】层级的巅峰，主角需要进入更广阔的舞台。
</task>

<strategy priority="P0">
【长篇类型策略 - 扩展指导】
{genre_strategy}
</strategy>

<context priority="P0">
【旧世界档案】
核心力量：{old_power_system}
核心冲突：{old_conflict} (已解决/已超越)
当前状态：主角已成为旧世界的巅峰/霸主
</context>

<output priority="P0">
【输出格式】
生成新世界的详细设定JSON：
{{
  "world_name": "新世界/新地图名称",
  "entry_method": "主角如何进入该世界（飞升/偷渡/被抓/意外）",
  "power_system_upgrade": "力量体系的升级路径（如何从旧体系过渡）",
  "core_conflict": "新世界的核心矛盾（比旧世界更宏大、更本质）",
  "social_structure": "新世界的势力格局（300字）",
  "connection": "与旧世界的联系（传说/下界/故人）",
  "locations": ["关键地点1", "关键地点2"],
  "factions": [
    {{"name": "势力A", "description": "势力描述", "stance": "敌对/中立/友善"}}
  ]
}}
</output>
"""

    # 批量角色生成提示词 V2（RTCO框架）
    CHARACTERS_BATCH_GENERATION = """<system>
你是专业的角色设定师，擅长为{genre}类型的小说创建立体丰满的角色。
</system>

<task>
【生成任务】
生成{count}个角色和组织实体。

【数量要求 - 严格遵守】
数组中必须精确包含{count}个对象，不多不少。

【实体类型分配】
- 至少1个主角（protagonist）
- 多个配角（supporting）
- 可包含反派（antagonist）
- 可包含1-2个高影响力组织（power_level: 70-95）
</task>

<worldview priority="P0">
【世界观信息】
时间背景：{time_period}
地理位置：{location}
氛围基调：{atmosphere}
世界规则：{rules}

主题：{theme}
类型：{genre}
</worldview>

<requirements priority="P1">
【特殊要求】
{requirements}
</requirements>

<output priority="P0">
【输出格式】
返回纯JSON数组，每个对象包含：

**角色对象**：
{{
  "name": "角色姓名",
  "age": 25,
  "gender": "男/女/其他",
  "is_organization": false,
  "role_type": "protagonist/supporting/antagonist",
  "personality": "性格特点（100-200字）：核心性格、优缺点、特殊习惯",
  "background": "背景故事（100-200字）：家庭背景、成长经历、重要转折",
  "appearance": "外貌描述（50-100字）：身高、体型、面容、着装风格",
  "traits": ["特长1", "特长2", "特长3"],
  "relationships_array": [
    {{
      "target_character_name": "已生成的角色名称",
      "relationship_type": "关系类型",
      "intimacy_level": 75,
      "description": "关系描述"
    }}
  ],
  "organization_memberships": [
    {{
      "organization_name": "已生成的组织名称",
      "position": "职位",
      "rank": 5,
      "loyalty": 80
    }}
  ]
}}

**组织对象**：
{{
  "name": "组织名称",
  "is_organization": true,
  "role_type": "supporting",
  "personality": "组织特性（100-200字）：运作方式、核心理念、行事风格",
  "background": "组织背景（100-200字）：建立历史、发展历程、重要事件",
  "appearance": "外在表现（50-100字）：总部位置、标志性建筑",
  "organization_type": "组织类型",
  "organization_purpose": "组织目的",
  "organization_members": ["成员1", "成员2"],
  "power_level": 85,
  "location": "所在地或主要活动区域",
  "motto": "组织格言、口号或宗旨",
  "color": "代表颜色",
  "traits": []
}}

【关系类型参考】
- 家族：父亲、母亲、兄弟、姐妹、子女、配偶、恋人
- 社交：师父、徒弟、朋友、同学、同事、邻居、知己
- 职业：上司、下属、合作伙伴
- 敌对：敌人、仇人、竞争对手、宿敌

【数值范围】
- intimacy_level：-100到100（负值表示敌对）
- loyalty：0到100
- rank：0到10（职位等级）
- power_level：70到95（组织影响力）
</output>

<constraints>
【必须遵守】
✅ 数量精确：数组必须包含{count}个对象
✅ 符合世界观：角色设定与世界观一致
✅ 有深度：性格和背景要立体
✅ 关系网络：角色间形成合理关系
✅ 组织合理：组织是推动剧情的关键力量

【关系约束】
✅ relationships_array只能引用本批次已出现的角色
✅ organization_memberships只能引用本批次的组织
✅ 第一个角色的relationships_array必须为空[]
✅ 禁止幻觉：不引用不存在的角色或组织

【格式约束】
✅ 纯JSON数组输出，无markdown标记
✅ 内容描述中严禁使用特殊符号（引号、方括号、书名号等）
✅ 专有名词直接书写，不使用符号包裹

【禁止事项】
❌ 生成数量不符（多于或少于{count}个）
❌ 引用不存在的角色或组织
❌ 生成低影响力的无关紧要组织
❌ 使用markdown或代码块标记
❌ 在描述中使用特殊符号
</constraints>"""

    # 大纲生成提示词 V2（RTCO框架）
    OUTLINE_CREATE = """<system>
你是经验丰富的小说作家和编剧，擅长为{genre}类型的小说设计精彩开篇。
</system>

<task>
【创作任务】
为小说《{title}》生成开篇{chapter_count}章的大纲。

【重要说明】
这是项目初始化的开头部分，不是完整大纲：
- 完成开局设定和世界观展示
- 引入主要角色，建立初始关系
- 埋下核心矛盾和悬念钩子
- 为后续剧情发展打下基础
- 不需要完整闭环，为续写留空间
</task>

<strategy priority="P0">
【长篇类型策略 - 核心指导】
{genre_strategy}
</strategy>

<project priority="P0">
【项目信息】
书名：{title}
主题：{theme}
类型：{genre}
开篇章节数：{chapter_count}
叙事视角：{narrative_perspective}
全书目标字数：{target_words}
</project>

<worldview priority="P1">
【世界观】
时间背景：{time_period}
地理位置：{location}
氛围基调：{atmosphere}
世界规则：{rules}
</worldview>

<characters priority="P1">
【角色信息】
{characters_info}
</characters>

<mcp_context priority="P2">
{mcp_references}
</mcp_context>

<requirements priority="P1">
【其他要求】
{requirements}
</requirements>

<output priority="P0">
【输出格式】
返回包含{chapter_count}个章节对象的JSON数组：

[
  {{
    "chapter_number": 1,
    "title": "章节标题",
    "summary": "章节概要（300-500字）：主要情节、冲突、转折",
    "scenes": ["场景1描述", "场景2描述", "场景3描述"],
    "characters": ["角色1", "角色2"],
    "key_points": ["情节要点1", "情节要点2"],
    "emotion": "本章情感基调",
    "goal": "本章叙事目标"
  }},
  {{
    "chapter_number": 2,
    "title": "章节标题",
    "summary": "章节概要...",
    "scenes": ["场景1", "场景2"],
    "characters": ["角色1", "角色2"],
    "key_points": ["要点1", "要点2"],
    "emotion": "情感基调",
    "goal": "叙事目标"
  }}
]

【格式规范】
- 纯JSON数组输出，无markdown标记
- 内容描述中严禁使用特殊符号（引号、方括号、书名号等）
- 专有名词、事件名直接书写
</output>

<constraints>
【开篇大纲要求】
✅ 开局设定：前几章完成世界观呈现、主角登场、初始状态
✅ 矛盾引入：引出核心冲突，但不急于展开
✅ 角色亮相：主要角色依次登场，展示性格和关系
✅ 节奏控制：开篇不宜过快，给读者适应时间
✅ 悬念设置：埋下伏笔和钩子，为续写预留空间
✅ 视角统一：采用{narrative_perspective}视角
✅ 留白艺术：结尾不收束过紧，留发展空间

【必须遵守】
✅ 数量精确：数组包含{chapter_count}个章节对象
✅ 符合类型：情节符合{genre}类型特征
✅ 主题贴合：体现主题"{theme}"
✅ 开篇定位：是开局而非完整故事

【禁止事项】
❌ 输出markdown或代码块标记
❌ 在描述中使用特殊符号
❌ 试图在开篇完结故事
❌ 节奏过快，信息过载
</constraints>"""
    
    # 大纲续写提示词 V2（RTCO框架 + 记忆增强）
    OUTLINE_CONTINUE = """<system>
你是经验丰富的小说作家和编剧，擅长续写{genre}类型的小说大纲。
</system>

<task>
【续写任务】
基于已有{current_chapter_count}章内容，续写第{start_chapter}章到第{end_chapter}章的大纲（共{chapter_count}章）。

【当前情节阶段】
{plot_stage_instruction}

【故事发展方向】
{story_direction}
</task>

<project priority="P0">
【项目信息】
书名：{title}
主题：{theme}
类型：{genre}
叙事视角：{narrative_perspective}
</project>

<worldview priority="P2">
【世界观】
时间背景：{time_period}
地理位置：{location}
氛围基调：{atmosphere}
世界规则：{rules}
</worldview>

<characters priority="P1">
【角色信息】
{characters_info}
</characters>

<previous_context priority="P0">
【已有章节概览】（共{current_chapter_count}章）
{all_chapters_brief}

【最近剧情】
{recent_plot}
</previous_context>

<memory priority="P1">
【🧠 智能记忆系统 - 续写参考】
以下是从故事记忆库中检索到的相关信息：

{memory_context}
</memory>

<mcp_context priority="P2">
{mcp_references}
</mcp_context>

<requirements priority="P1">
【其他要求】
{requirements}
</requirements>

<output priority="P0">
【输出格式】
返回第{start_chapter}到第{end_chapter}章的JSON数组（共{chapter_count}个对象）：

[
  {{
    "chapter_number": {start_chapter},
    "title": "章节标题",
    "summary": "章节概要（300-500字）：主要情节、角色互动、关键事件、冲突与转折",
    "scenes": ["场景1描述", "场景2描述", "场景3描述"],
    "characters": ["涉及角色1", "涉及角色2"],
    "key_points": ["情节要点1", "情节要点2"],
    "emotion": "本章情感基调",
    "goal": "本章叙事目标"
  }},
  {{
    "chapter_number": {start_chapter} + 1,
    "title": "章节标题",
    "summary": "章节概要...",
    "scenes": ["场景1", "场景2"],
    "characters": ["角色1", "角色2"],
    "key_points": ["要点1", "要点2"],
    "emotion": "情感基调",
    "goal": "叙事目标"
  }}
]

【格式规范】
- 纯JSON数组输出，无markdown标记
- 内容描述中严禁使用特殊符号
- 专有名词直接书写
- 字段结构与已有章节完全一致
</output>

<constraints>
【续写要求】
✅ 剧情连贯：与前文自然衔接，保持连贯性
✅ 记忆参考：适当参考记忆中的伏笔、钩子、情节点
✅ 伏笔回收：考虑回收未完结伏笔，制造呼应
✅ 角色发展：遵循角色成长轨迹
✅ 情节阶段：遵循{plot_stage_instruction}的要求
✅ 风格一致：保持与已有章节相同风格和详细程度

【必须遵守】
✅ 数量精确：数组包含{chapter_count}个章节
✅ 编号正确：从第{start_chapter}章开始
✅ 描述详细：每个summary 100-200字
✅ 承上启下：自然衔接前文

【禁止事项】
❌ 输出markdown或代码块标记
❌ 在描述中使用特殊符号
❌ 与前文矛盾或脱节
❌ 忽略已有角色发展
</constraints>"""

    # 分卷规划提示词 V2（RTCO框架 - 50-100万字规划）
    VOLUME_PLANNING = """<system>
你是掌控全局的小说主编，擅长规划长篇小说的宏观结构（分卷/大篇章）。
</system>

<task>
【规划任务】
为小说《{title}》规划第 {volume_number} 卷的核心架构。
本卷预计篇幅：{volume_word_count}字（约50-100章）。

【核心目标】
这一卷必须是一个完整的"起承转合"闭环，同时推动全书主线。
</task>

<strategy priority="P0">
【长篇类型策略 - 分卷指导】
{genre_strategy}
</strategy>

<context priority="P0">
【当前进度】
主角现状：{mc_status}
上一卷结局：{prev_volume_summary}
全书主线进度：{main_story_progress}%
</context>

<output priority="P0">
【输出格式】
生成分卷规划JSON：
{{
  "volume_title": "卷名（富有史诗感或悬念）",
  "core_theme": "本卷探讨的核心主题",
  "main_antagonist": "本卷最终BOSS或核心阻碍",
  "key_events": [
    {{"phase": "开篇（切入）", "content": "事件简述"}},
    {{"phase": "发展（铺垫）", "content": "事件简述"}},
    {{"phase": "高潮（爆发）", "content": "事件简述"}},
    {{"phase": "结局（余韵）", "content": "事件简述"}}
  ],
  "mc_growth": {{
    "power": "力量/能力提升",
    "status": "地位/声望提升",
    "relationship": "关键关系的突破"
  }},
  "hooks": ["留给下一卷的伏笔1", "留给下一卷的伏笔2"]
}}
</output>
"""

    # 状态管理提示词 (用于清理记忆/更新状态)
    STATE_MANAGER = """<system>
你是小说世界的"逻辑维护者"。你的职责不是创作，而是维护数据的逻辑一致性。
</system>

<task>
根据最新的剧情发展，更新【世界状态表】。
检查范围：第 {start_chapter} 章 到 第 {end_chapter} 章。
</task>

<input>
【当前状态】
{current_state_json}

【最新剧情摘要】
{recent_plot_summary}
</input>

<actions>
请执行以下维护操作：
1. **标记死亡**：将剧情中明确死亡的角色标记为 "status": "DEAD"。
2. **关系变更**：更新角色间的关系（如从"盟友"变为"死敌"）。
3. **物品归档**：将已消耗或遗弃的关键物品标记为 "archived": true。
4. **伏笔回收**：将已解决的伏笔标记为 "resolved": true。
</actions>

<output>
返回更新后的状态JSON。仅返回有变更的字段。
</output>
"""

    # 章节生成V2 - 无前置章节版本（用于第1章）
    CHAPTER_GENERATION_V2 = """<system>
你是《{project_title}》的作者，一位专注于{genre}类型的网络小说家。
</system>

<task>
【创作任务】
撰写第{chapter_number}章《{chapter_title}》的完整正文。

【基本要求】
- 目标字数：{target_word_count}字（允许±200字浮动）
- 叙事视角：{narrative_perspective}
</task>

<strategy priority="P0">
【长篇类型策略 - 写作指导】
{genre_strategy}
</strategy>

<outline priority="P0">
【本章大纲 - 必须遵循】
{chapter_outline}
</outline>

<characters priority="P1">
【本章角色】
{characters_info}
</characters>

<constraints>
【必须遵守】
✅ 严格按照大纲推进情节
✅ 保持角色性格、说话方式一致
✅ 字数控制在目标范围内

【禁止事项】
❌ 输出章节标题、序号等元信息
❌ 使用"总之"、"综上所述"等AI常见总结语
❌ 在结尾处使用开放式反问
❌ 添加作者注释或创作说明
</constraints>

<output>
【输出规范】
直接输出小说正文内容，从故事场景或动作开始。
无需任何前言、后记或解释性文字。

现在开始创作：
</output>"""

    # 章节生成V2 - 带前置章节版本（用于第2章及以后）
    CHAPTER_GENERATION_V2_WITH_CONTEXT = """<system>
你是《{project_title}》的作者，一位专注于{genre}类型的网络小说家。
</system>

<task>
【创作任务】
撰写第{chapter_number}章《{chapter_title}》的完整正文。

【基本要求】
- 目标字数：{target_word_count}字（允许±500字浮动）
- 叙事视角：{narrative_perspective}
</task>

<strategy priority="P0">
【长篇类型策略 - 写作指导】
{genre_strategy}
</strategy>

<outline priority="P0">
【本章大纲 - 必须遵循】
{chapter_outline}
</outline>

<continuation priority="P0">
【衔接锚点 - 必须承接】
上一章结尾：
「{continuation_point}」

⚠️ 要求：从此处自然续写，不得重复上述内容
</continuation>

<characters priority="P1">
【本章角色】
{characters_info}
</characters>

<memory priority="P2">
【相关记忆 - 参考】
{relevant_memories}
</memory>

<skeleton priority="P2">
【故事骨架 - 背景】
{story_skeleton}
</skeleton>

<constraints>
【必须遵守】
✅ 严格按照大纲推进情节
✅ 自然承接上一章结尾，不重复已发生事件
✅ 保持角色性格、说话方式一致
✅ 字数控制在目标范围内

【禁止事项】
❌ 输出章节标题、序号等元信息
❌ 使用"总之"、"综上所述"等AI常见总结语
❌ 在结尾处使用开放式反问
❌ 添加作者注释或创作说明
❌ 重复叙述上一章已发生的事件
</constraints>

<output>
【输出规范】
直接输出小说正文内容，从故事场景或动作开始。
无需任何前言、后记或解释性文字。

现在开始创作：
</output>"""

    # 单个角色生成提示词 V2（RTCO框架）
    SINGLE_CHARACTER_GENERATION = """<system>
你是专业的角色设定师，擅长创建立体饱满的小说角色。
</system>

<task>
【设计任务】
根据用户需求和项目上下文，创建一个完整的角色设定。
</task>

<context priority="P0">
【项目上下文】
{project_context}

【用户需求】
{user_input}
</context>

<output priority="P0">
【输出格式】
生成完整的角色卡片JSON对象：

{{
  "name": "角色姓名（如用户未提供则生成符合世界观的名字）",
  "age": "年龄（具体数字或年龄段）",
  "gender": "男/女/其他",
  "appearance": "外貌描述（100-150字）：身高体型、面容特征、着装风格",
  "personality": "性格特点（150-200字）：核心性格特质、优缺点、特殊习惯",
  "background": "背景故事（200-300字）：家庭背景、成长经历、重要转折、与主题关联",
  "traits": ["特长1", "特长2", "特长3"],
  "relationships_text": "人际关系的自然语言描述",
  "relationships": [
    {{
      "target_character_name": "已存在的角色名称",
      "relationship_type": "关系类型",
      "intimacy_level": 75,
      "description": "关系的详细描述",
      "started_at": "关系开始的故事时间点（可选）"
    }}
  ],
  "organization_memberships": [
    {{
      "organization_name": "已存在的组织名称",
      "position": "职位名称",
      "rank": 8,
      "loyalty": 80,
      "joined_at": "加入时间（可选）",
      "status": "active"
    }}
  ],
  "career_info": {{
    "main_career_name": "从可用主职业列表中选择的职业名称",
    "main_career_stage": 5,
    "sub_careers": [
      {{
        "career_name": "从可用副职业列表中选择的职业名称",
        "stage": 3
      }}
    ]
  }}
}}

【职业信息说明】
如果项目上下文包含职业列表：
- 主职业：从"可用主职业"列表中选择最符合角色的职业
- 主职业阶段：根据角色实力设定合理阶段（1到max_stage）
- 副职业：可选择0-2个副职业
- ⚠️ 填写职业名称而非ID，系统会自动匹配
- 职业选择必须与角色背景、能力和定位高度契合

【关系类型参考】
- 家族：父亲、母亲、兄弟、姐妹、子女、配偶、恋人
- 社交：师父、徒弟、朋友、同学、同事、邻居、知己
- 职业：上司、下属、合作伙伴
- 敌对：敌人、仇人、竞争对手、宿敌

【数值范围】
- intimacy_level：-100到100（负值表示敌对）
- loyalty：0到100
- rank：0到10
</output>

<constraints>
【必须遵守】
✅ 符合世界观：角色设定与项目世界观一致
✅ 主题关联：背景故事与项目主题关联
✅ 立体饱满：性格复杂有矛盾性，不脸谱化
✅ 为故事服务：设定要推动剧情发展
✅ 职业匹配：职业选择与角色高度契合

【角色定位要求】
✅ 主角：有成长空间和目标动机
✅ 反派：有合理动机，不脸谱化
✅ 配角：有独特性，不是工具人

【关系约束】
✅ relationships只引用已存在的角色
✅ organization_memberships只引用已存在的组织
✅ 无关系或组织时对应数组为空[]

【格式约束】
✅ 纯JSON对象输出，无markdown标记
✅ 内容描述中严禁使用特殊符号
✅ 专有名词直接书写

【禁止事项】
❌ 输出markdown或代码块标记
❌ 在描述中使用特殊符号（引号、方括号等）
❌ 引用不存在的角色或组织
❌ 脸谱化的角色设定
</constraints>"""

    # 单个组织生成提示词 V2（RTCO框架）
    SINGLE_ORGANIZATION_GENERATION = """<system>
你是专业的组织设定师，擅长创建完整的组织/势力设定。
</system>

<task>
【设计任务】
根据用户需求和项目上下文，创建一个完整的组织/势力设定。
</task>

<context priority="P0">
【项目上下文】
{project_context}

【用户需求】
{user_input}
</context>

<output priority="P0">
【输出格式】
生成完整的组织设定JSON对象：

{{
  "name": "组织名称（如用户未提供则生成符合世界观的名称）",
  "is_organization": true,
  "organization_type": "组织类型（帮派/公司/门派/学院/政府机构/宗教组织等）",
  "personality": "组织特性（150-200字）：核心理念、行事风格、文化价值观、运作方式",
  "background": "组织背景（200-300字）：建立历史、发展历程、重要事件、当前地位",
  "appearance": "外在表现（100-150字）：总部位置、标志性建筑、组织标志、制服等",
  "organization_purpose": "组织目的和宗旨：明确目标、长期愿景、行动准则",
  "power_level": 75,
  "location": "所在地点：主要活动区域、势力范围",
  "motto": "组织格言或口号",
  "traits": ["特征1", "特征2", "特征3"],
  "color": "组织代表颜色（如：深红色、金色、黑色等）",
  "organization_members": ["重要成员1", "重要成员2", "重要成员3"]
}}

【字段说明】
- power_level：0-100的整数，表示在世界中的影响力
- organization_members：组织内重要成员名字列表（可关联已有角色）
- 成立时间：在background中描述
</output>

<constraints>
【必须遵守】
✅ 符合世界观：组织设定与项目世界观一致
✅ 主题关联：背景与项目主题关联
✅ 推动剧情：组织能推动故事发展
✅ 有层级结构：内部有明确的层级和结构
✅ 势力互动：与其他势力有互动关系

【组织定位要求】
✅ 有存在必要性：不是可有可无的背景板
✅ 目标合理：不过于理想化或脸谱化
✅ 具体细节：描述详细具体，避免空泛

【格式约束】
✅ 纯JSON对象输出，无markdown标记
✅ 内容描述中严禁使用特殊符号
✅ 专有名词直接书写

【禁止事项】
❌ 输出markdown或代码块标记
❌ 在描述中使用特殊符号（引号、方括号等）
❌ 过于理想化或脸谱化的设定
❌ 空泛的描述
</constraints>"""

    # 情节分析提示词 V2（RTCO框架）
    PLOT_ANALYSIS = """<system>
你是专业的小说编辑和剧情分析师，擅长深度剖析章节内容。
</system>

<task>
【分析任务】
全面分析第{chapter_number}章《{title}》的剧情要素、钩子、伏笔、冲突和角色发展。
</task>

<chapter priority="P0">
【章节信息】
章节：第{chapter_number}章
标题：{title}
字数：{word_count}字

【章节内容】
{content}
</chapter>

<analysis_framework priority="P0">
【分析维度】

**1. 剧情钩子 (Hooks)**
识别吸引读者的关键元素：
- 悬念钩子：未解之谜、疑问、谜团
- 情感钩子：引发共鸣的情感点
- 冲突钩子：矛盾对抗、紧张局势
- 认知钩子：颠覆认知的信息

每个钩子需要：
- 类型分类
- 具体内容描述
- 强度评分(1-10)
- 出现位置(开头/中段/结尾)
- **关键词**：【必填】从原文逐字复制8-25字的文本片段，用于精确定位

**2. 伏笔分析 (Foreshadowing)**
- 埋下的新伏笔：内容、预期作用、隐藏程度(1-10)
- 回收的旧伏笔：呼应哪一章、回收效果
- 伏笔质量：巧妙性和合理性
- **关键词**：【必填】从原文逐字复制8-25字

**3. 冲突分析 (Conflict)**
- 冲突类型：人与人/人与己/人与环境/人与社会
- 冲突各方及立场
- 冲突强度(1-10)
- 解决进度(0-100%)

**4. 情感曲线 (Emotional Arc)**
- 主导情绪（最多10字）
- 情感强度(1-10)
- 情绪变化轨迹

**5. 角色状态追踪 (Character Development)**
对每个出场角色分析：
- 心理状态变化(前→后)
- 关系变化
- 关键行动和决策
- 成长或退步
- **💼 职业变化（可选）**：
  - 仅当章节明确描述职业进展时填写
  - main_career_stage_change: 整数(+1晋升/-1退步/0无变化)
  - sub_career_changes: 副职业变化数组
  - new_careers: 新获得职业
  - career_breakthrough: 突破过程描述

**6. 关键情节点 (Plot Points)**
列出3-5个核心情节点：
- 情节内容
- 类型(revelation/conflict/resolution/transition)
- 重要性(0.0-1.0)
- 对故事的影响
- **关键词**：【必填】从原文逐字复制8-25字

**7. 场景与节奏**
- 主要场景
- 叙事节奏(快/中/慢)
- 对话与描写比例

**8. 质量评分（支持小数，严格区分度）**
评分范围：1.0-10.0，支持一位小数（如 6.5、7.8）
每个维度必须根据以下标准严格评分，避免所有内容都打中等分数：

**节奏把控 (pacing)**：
- 1.0-3.9（差）：节奏混乱，该快不快该慢不慢；场景切换生硬；大段无意义描写拖沓
- 4.0-5.9（中下）：节奏基本可读但有明显问题；部分场景过于冗长或仓促
- 6.0-7.9（中上）：节奏整体流畅，偶有小问题；张弛有度但不够精妙
- 8.0-9.4（优秀）：节奏把控精准，高潮迭起；场景切换自然，详略得当
- 9.5-10.0（完美）：节奏大师级，每个段落都恰到好处

**吸引力 (engagement)**：
- 1.0-3.9（差）：内容乏味，缺乏钩子；读者难以继续阅读
- 4.0-5.9（中下）：有基本情节但缺乏亮点；钩子设置生硬或缺失
- 6.0-7.9（中上）：有一定吸引力，钩子有效但不够巧妙
- 8.0-9.4（优秀）：引人入胜，钩子设置精妙；让人欲罢不能
- 9.5-10.0（完美）：极具吸引力，每个段落都有阅读动力

**连贯性 (coherence)**：
- 1.0-3.9（差）：逻辑混乱，前后矛盾；角色行为不合理
- 4.0-5.9（中下）：基本连贯但有明显漏洞；部分情节衔接生硬
- 6.0-7.9（中上）：整体连贯，偶有小瑕疵；角色行为基本合理
- 8.0-9.4（优秀）：逻辑严密，衔接自然；角色行为高度一致
- 9.5-10.0（完美）：无懈可击的连贯性

**整体质量 (overall)**：
- 计算公式：(pacing + engagement + coherence) / 3，保留一位小数
- 可根据综合印象±0.5调整，必须与各项分数保持一致性

**9. 改进建议（与分数关联）**
建议数量必须与整体质量分数关联：
- overall < 4.0：必须提供4-5条具体改进建议，指出严重问题
- overall 4.0-5.9：必须提供3-4条改进建议，指出主要问题
- overall 6.0-7.9：提供1-2条优化建议，指出可提升之处
- overall ≥ 8.0：提供0-1条锦上添花的建议

每条建议必须：
- 指出具体问题位置或类型
- 说明为什么是问题
- 给出明确的改进方向
</analysis_framework>

<output priority="P0">
【输出格式】
返回纯JSON对象（无markdown标记）：

{{
  "hooks": [
    {{
      "type": "悬念",
      "content": "具体描述",
      "strength": 8,
      "position": "中段",
      "keyword": "从原文逐字复制的8-25字文本"
    }}
  ],
  "foreshadows": [
    {{
      "content": "伏笔内容",
      "type": "planted",
      "strength": 7,
      "subtlety": 8,
      "reference_chapter": null,
      "keyword": "从原文逐字复制的8-25字文本"
    }}
  ],
  "conflict": {{
    "types": ["人与人", "人与己"],
    "parties": ["主角-复仇", "反派-维护现状"],
    "level": 8,
    "description": "冲突描述",
    "resolution_progress": 0.3
  }},
  "emotional_arc": {{
    "primary_emotion": "紧张焦虑",
    "intensity": 8,
    "curve": "平静→紧张→高潮→释放",
    "secondary_emotions": ["期待", "焦虑"]
  }},
  "character_states": [
    {{
      "character_name": "张三",
      "state_before": "犹豫",
      "state_after": "坚定",
      "psychological_change": "心理变化描述",
      "key_event": "触发事件",
      "relationship_changes": {{"李四": "关系改善"}},
      "career_changes": {{
        "main_career_stage_change": 1,
        "sub_career_changes": [{{"career_name": "炼丹", "stage_change": 1}}],
        "new_careers": [],
        "career_breakthrough": "突破描述"
      }}
    }}
  ],
  "plot_points": [
    {{
      "content": "情节点描述",
      "type": "revelation",
      "importance": 0.9,
      "impact": "推动故事发展",
      "keyword": "从原文逐字复制的8-25字文本"
    }}
  ],
  "scenes": [
    {{
      "location": "地点",
      "atmosphere": "氛围",
      "duration": "时长估计"
    }}
  ],
  "pacing": "varied",
  "dialogue_ratio": 0.4,
  "description_ratio": 0.3,
  "scores": {{
    "pacing": 6.5,
    "engagement": 5.8,
    "coherence": 7.2,
    "overall": 6.5,
    "score_justification": "节奏整体流畅但中段略显拖沓；钩子设置有效但不够巧妙；逻辑连贯无明显漏洞"
  }},
  "plot_stage": "发展",
  "suggestions": [
    "【节奏问题】第三场景的心理描写过长（约500字），建议精简至200字以内，保留核心情感即可",
    "【吸引力不足】章节中段缺乏有效钩子，建议在主角发现线索后增加一个小悬念"
  ]
}}
</output>

<constraints>
【必须遵守】
✅ keyword字段必填：钩子、伏笔、情节点的keyword不能为空
✅ 逐字复制：keyword必须从原文复制，长度8-25字
✅ 精确定位：keyword能在原文中精确找到
✅ 职业变化可选：仅当章节明确描述时填写

【评分约束 - 严格执行】
✅ 严格按评分标准打分，支持小数（如6.5、7.2、8.3）
✅ 不要默认给7.0-8.0分，差的内容必须给低分（1.0-5.0），好的内容才给高分（8.0-10.0）
✅ score_justification必填：简要说明各项评分的依据
✅ 建议数量必须与overall分数关联：
   - overall≤4.0 → 4-5条建议
   - overall 4.0-6.0 → 3-4条建议
   - overall 6.0-8.0 → 1-2条建议
   - overall≥8.0 → 0-1条建议
✅ 每条建议必须标注问题类型（如【节奏问题】【描写不足】等）

【禁止事项】
❌ keyword使用概括或改写的文字
❌ 输出markdown标记
❌ 遗漏必填的keyword字段
❌ 无根据地添加职业变化
❌ 所有章节都打7-8分的"安全分"
❌ 高分章节给大量建议，或低分章节不给建议
</constraints>"""

    # 大纲单批次展开提示词 V2（RTCO框架）
    OUTLINE_EXPAND_SINGLE = """<system>
你是专业的小说情节架构师，擅长将大纲节点展开为详细章节规划。
</system>

<task>
【展开任务】
将第{outline_order_index}节大纲《{outline_title}》展开为{target_chapter_count}个章节的详细规划。

<strategy priority="P0">
【长篇类型策略 - 核心指导】
{genre_strategy}
</strategy>

【展开策略】
{strategy_instruction}
</task>

<project priority="P1">
【项目信息】
小说名称：{project_title}
类型：{project_genre}
主题：{project_theme}
叙事视角：{project_narrative_perspective}

【世界观背景】
时间背景：{project_world_time_period}
地理位置：{project_world_location}
氛围基调：{project_world_atmosphere}
</project>

<characters priority="P1">
【角色信息】
{characters_info}
</characters>

<outline_node priority="P0">
【当前大纲节点 - 展开对象】
序号：第 {outline_order_index} 节
标题：{outline_title}
内容：{outline_content}
</outline_node>

<context priority="P2">
【上下文参考】
{context_info}
</context>

<output priority="P0">
【输出格式】
返回{target_chapter_count}个章节规划的JSON数组：

[
  {{
    "sub_index": 1,
    "title": "章节标题（体现核心冲突或情感）",
    "plot_summary": "剧情摘要（200-300字）：详细描述该章发生的事件，仅限当前大纲内容",
    "key_events": ["关键事件1", "关键事件2", "关键事件3"],
    "character_focus": ["角色A", "角色B"],
    "emotional_tone": "情感基调（如：紧张、温馨、悲伤）",
    "narrative_goal": "叙事目标（该章要达成的叙事效果）",
    "conflict_type": "冲突类型（如：内心挣扎、人际冲突）",
    "estimated_words": 3000{scene_field}
  }}
]

【格式规范】
- 纯JSON数组输出，无其他文字
- 内容描述中严禁使用特殊符号
</output>

<constraints>
【⚠️ 内容边界约束 - 必须严格遵守】
✅ 只能展开当前大纲节点的内容
✅ 深化当前大纲，而非跨越到后续
✅ 放慢叙事节奏，充分体验当前阶段

❌ 绝对不能推进到后续大纲内容
❌ 不要让剧情快速推进
❌ 不要提前展开【后一节】的内容

【展开原则】
✅ 将单一事件拆解为多个细节丰富的章节
✅ 深入挖掘情感、心理、环境、对话
✅ 每章是当前大纲内容的不同侧面或阶段

【🔴 相邻章节差异化约束（防止重复）】
✅ 每章有独特的开场方式（不同场景、时间点、角色状态）
✅ 每章有独特的结束方式（不同悬念、转折、情感收尾）
✅ key_events在相邻章节间绝不重叠
✅ plot_summary描述该章独特内容，不与其他章雷同
✅ 同一事件的不同阶段要明确区分"前、中、后"

【章节间要求】
✅ 衔接自然流畅（每章从不同起点开始）
✅ 剧情递进合理（但不超出当前大纲边界）
✅ 节奏张弛有度
✅ 每章有明确且独特的叙事价值
✅ 最后一章结束时恰好完成当前大纲内容
✅ 关键事件无重叠：检查相邻章节key_events

【禁止事项】
❌ 输出非JSON格式
❌ 剧情越界到后续大纲
❌ 相邻章节内容重复
❌ 关键事件雷同
</constraints>"""

    # 大纲分批展开提示词 V2（RTCO框架）
    OUTLINE_EXPAND_MULTI = """<system>
你是专业的小说情节架构师，擅长分批展开大纲节点。
</system>

<task>
【展开任务】
继续展开第{outline_order_index}节大纲《{outline_title}》，生成第{start_index}-{end_index}节（共{target_chapter_count}个章节）的详细规划。

【分批说明】
- 这是整个展开的一部分
- 必须与前面已生成的章节自然衔接
- 从第{start_index}节开始编号
- 继续深化当前大纲内容

<strategy priority="P0">
【长篇类型策略 - 核心指导】
{genre_strategy}
</strategy>

【展开策略】
{strategy_instruction}
</task>

<project priority="P1">
【项目信息】
小说名称：{project_title}
类型：{project_genre}
主题：{project_theme}
叙事视角：{project_narrative_perspective}

【世界观背景】
时间背景：{project_world_time_period}
地理位置：{project_world_location}
氛围基调：{project_world_atmosphere}
</project>

<characters priority="P1">
【角色信息】
{characters_info}
</characters>

<outline_node priority="P0">
【当前大纲节点 - 展开对象】
序号：第 {outline_order_index} 节
标题：{outline_title}
内容：{outline_content}
</outline_node>

<context priority="P2">
【上下文参考】
{context_info}

【已生成的前序章节】
{previous_context}
</context>

<output priority="P0">
【输出格式】
返回第{start_index}-{end_index}节章节规划的JSON数组（共{target_chapter_count}个对象）：

[
  {{
    "sub_index": {start_index},
    "title": "章节标题",
    "plot_summary": "剧情摘要（200-300字）：详细描述该章发生的事件",
    "key_events": ["关键事件1", "关键事件2", "关键事件3"],
    "character_focus": ["角色A", "角色B"],
    "emotional_tone": "情感基调",
    "narrative_goal": "叙事目标",
    "conflict_type": "冲突类型",
    "estimated_words": 3000{scene_field}
  }}
]

【格式规范】
- 纯JSON数组输出，无其他文字
- 内容描述中严禁使用特殊符号
- sub_index从{start_index}开始
</output>

<constraints>
【⚠️ 内容边界约束】
✅ 只能展开当前大纲节点的内容
✅ 深化当前大纲，而非跨越到后续
✅ 放慢叙事节奏

❌ 绝对不能推进到后续大纲内容
❌ 不要让剧情快速推进

【分批连续性约束】
✅ 与前面已生成章节自然衔接
✅ 从第{start_index}节开始编号
✅ 保持叙事连贯性

【🔴 相邻章节差异化约束（防止重复）】
✅ 每章有独特的开场和结束方式
✅ key_events在相邻章节间绝不重叠
✅ plot_summary描述该章独特内容
✅ 特别注意与前序章节的差异化
✅ 避免重复已有内容

【章节间要求】
✅ 与前面章节衔接自然流畅
✅ 剧情递进合理（但不超出当前大纲边界）
✅ 节奏张弛有度
✅ 每章有明确且独特的叙事价值
✅ 关键事件无重叠：检查本批次和前序章节的key_events

【禁止事项】
❌ 输出非JSON格式
❌ 剧情越界到后续大纲
❌ 相邻章节内容重复
❌ 与前序章节key_events雷同
</constraints>"""

    # 章节重写系统提示词 V2（RTCO框架）
    CHAPTER_REGENERATION_SYSTEM = """<system>
你是经验丰富的专业小说编辑和作家，擅长根据反馈意见重新创作章节。
你的任务是根据修改指令，对原始章节进行深度改写和优化。
</system>

<task>
【重写任务】
1. 仔细理解原始章节的内容、情节走向和叙事意图
2. 认真分析所有的修改要求，包括AI分析建议和用户自定义指令
3. 针对每一条修改建议，在新版本中进行具体改进
4. 在保持故事连贯性和角色一致性的前提下，创作改进后的新版本
5. 确保新版本在艺术性、可读性和叙事质量上都有明显提升
</task>

<guidelines>
【改写原则】
- **问题导向**：针对修改指令中指出的每个问题进行改进
- **保持精华**：保留原章节中优秀的描写、对话和情节设计
- **深化细节**：增强场景描写、情感渲染和人物刻画
- **节奏优化**：调整叙事节奏，避免拖沓或过快
- **风格一致**：如果提供了写作风格要求，必须严格遵循

【重点关注】
- 如果修改指令提到"节奏"问题，重点调整叙事速度和场景切换
- 如果修改指令提到"情感"问题，重点深化人物内心戏和情感表达
- 如果修改指令提到"描写"问题，重点丰富环境和动作细节
- 如果修改指令提到"对话"问题，重点让对话更自然、更有个性
- 如果修改指令提到"冲突"问题，重点强化矛盾和戏剧张力
</guidelines>

<output>
【输出规范】
直接输出重写后的章节正文内容。
- 不要包含章节标题、序号或其他元信息
- 不要输出任何解释、注释或创作说明
- 从故事内容直接开始，保持叙事的连贯性
</output>
"""
    # MCP工具测试提示词
    MCP_TOOL_TEST = """你是MCP插件测试助手，需要测试插件 '{plugin_name}' 的功能。

⚠️ 重要规则：生成参数时，必须严格使用工具 schema 中定义的原始参数名称，不要转换为 snake_case 或其他格式。
例如：如果 schema 中是 'nextThoughtNeeded'，就必须使用 'nextThoughtNeeded'，不能改成 'next_thought_needed'。

请选择一个合适的工具进行测试，优先选择搜索、查询类工具。
生成真实有效的测试参数（例如搜索"人工智能最新进展"而不是"test"）。

现在开始测试这个插件。"""

    MCP_TOOL_TEST_SYSTEM = """你是专业的API测试工具。当给定工具列表时，选择一个工具并使用合适的参数调用它。

⚠️ 关键规则：调用工具时，必须严格使用 schema 中定义的原始参数名，不要自行转换命名风格。
- 如果参数名是 camelCase（如 nextThoughtNeeded），就使用 camelCase
- 如果参数名是 snake_case（如 next_thought），就使用 snake_case
- 保持与 schema 中定义的完全一致，包括大小写和命名风格"""
    
    # 灵感模式 - 书名生成（系统提示词）
    INSPIRATION_TITLE_SYSTEM = """你是一位专业的小说创作顾问。
用户的原始想法：{initial_idea}

请根据用户的想法，生成6个吸引人的书名建议，要求：
1. 紧扣用户的原始想法和核心故事构思
2. 富有创意和吸引力
3. 涵盖不同的风格倾向
4. 书名中不要带有"《》"符号

返回JSON格式：
{{
    "prompt": "根据你的想法，我为你准备了几个书名建议：",
    "options": ["书名1", "书名2", "书名3", "书名4", "书名5", "书名6"]
}}

只返回纯JSON，不要有其他文字。"""

    # 灵感模式 - 书名生成（用户提示词）
    INSPIRATION_TITLE_USER = "用户的想法：{initial_idea}\n请生成6个书名建议"

    # 灵感模式 - 简介生成（系统提示词）
    INSPIRATION_DESCRIPTION_SYSTEM = """你是一位专业的小说创作顾问。
用户的原始想法：{initial_idea}
已确定的书名：{title}

请生成6个精彩的小说简介，要求：
1. 必须紧扣用户的原始想法，确保简介是原始想法的具体展开
2. 符合已确定的书名风格
3. 简洁有力，每个50-100字
4. 包含核心冲突
5. 涵盖不同的故事走向，但都基于用户的原始构思

返回JSON格式：
{{"prompt":"选择一个简介：","options":["简介1","简介2","简介3","简介4","简介5","简介6"]}}

只返回纯JSON，不要有其他文字，不要换行。"""

    # 灵感模式 - 简介生成（用户提示词）
    INSPIRATION_DESCRIPTION_USER = "原始想法：{initial_idea}\n书名：{title}\n请生成6个简介选项"

    # 灵感模式 - 主题生成（系统提示词）
    INSPIRATION_THEME_SYSTEM = """你是一位专业的小说创作顾问。
用户的原始想法：{initial_idea}
小说信息：
- 书名：{title}
- 简介：{description}

请生成6个深刻的主题选项，要求：
1. 必须与用户的原始想法保持高度一致
2. 符合书名和简介的风格
3. 有深度和思想性
4. 每个50-150字
5. 涵盖不同角度（如：成长、复仇、救赎、探索等），但都围绕用户的核心构思

返回JSON格式：
{{"prompt":"这本书的核心主题是什么？","options":["主题1","主题2","主题3","主题4","主题5","主题6"]}}

只返回纯JSON，不要有其他文字，不要换行。"""

    # 灵感模式 - 主题生成（用户提示词）
    INSPIRATION_THEME_USER = "原始想法：{initial_idea}\n书名：{title}\n简介：{description}\n请生成6个主题选项"

    # 灵感模式 - 类型生成（系统提示词）
    INSPIRATION_GENRE_SYSTEM = """你是一位专业的小说创作顾问。
用户的原始想法：{initial_idea}
小说信息：
- 书名：{title}
- 简介：{description}
- 主题：{theme}

请生成6个合适的类型标签（每个2-4字），要求：
1. 必须符合用户原始想法中暗示的类型倾向
2. 符合小说整体风格
3. 可以多选组合

常见类型：玄幻、都市、科幻、武侠、仙侠、历史、言情、悬疑、奇幻、修仙等

返回JSON格式：
{{"prompt":"选择类型标签（可多选）：","options":["类型1","类型2","类型3","类型4","类型5","类型6"]}}

只返回紧凑的纯JSON，不要换行，不要有其他文字。"""

    # 灵感模式 - 类型生成（用户提示词）
    INSPIRATION_GENRE_USER = "原始想法：{initial_idea}\n书名：{title}\n简介：{description}\n主题：{theme}\n请生成6个类型标签"

    # 灵感模式 - 世界观设定生成
    INSPIRATION_WORLD_SYSTEM = """你是一位专业的小说创作顾问。
用户的原始想法：{initial_idea}
小说信息：
- 书名：{title}
- 简介：{description}
- 类型：{genre}

请生成6个具体的世界观设定方案（Flavor），要求：
1. 基于类型（{genre}）进行细化
2. 描述世界的特殊规则、时代背景或独特氛围
3. 每个选项20-50字，简洁有力

返回JSON格式：
{{"prompt":"这个故事发生在一个什么样的世界？","options":["设定1","设定2","设定3","设定4","设定5","设定6"]}}

只返回纯JSON。"""

    INSPIRATION_WORLD_USER = "书名：{title}\n类型：{genre}\n请生成6个世界观设定方案"

    # 灵感模式 - 核心冲突生成
    INSPIRATION_CONFLICT_SYSTEM = """你是一位专业的小说创作顾问。
小说信息：
- 书名：{title}
- 类型：{genre}
- 世界观：{world_setting}

请生成6个核心冲突（Core Conflict）选项，要求：
1. 必须是推动整本书（100万字以上）的终极矛盾
2. 具有张力和紧迫感
3. 涵盖复仇、生存、探索、守护等不同维度

返回JSON格式：
{{"prompt":"推动故事发展的核心冲突是什么？","options":["冲突1","冲突2","冲突3","冲突4","冲突5","冲突6"]}}

只返回纯JSON。"""

    INSPIRATION_CONFLICT_USER = "书名：{title}\n世界观：{world_setting}\n请生成6个核心冲突选项"

    # 灵感模式 - 主角人设生成
    INSPIRATION_PROTAGONIST_SYSTEM = """你是一位专业的小说创作顾问。
小说信息：
- 书名：{title}
- 类型：{genre}
- 核心冲突：{core_conflict}

请生成6个主角人设原型（Archetype），要求：
1. 与核心冲突形成张力（如：弱小的复仇者，贪财的救世主）
2. 包含性格关键词和核心身份
3. 有鲜明的记忆点

返回JSON格式：
{{"prompt":"主角是什么样的人？","options":["人设1","人设2","人设3","人设4","人设5","人设6"]}}

只返回纯JSON。"""

    INSPIRATION_PROTAGONIST_USER = "书名：{title}\n核心冲突：{core_conflict}\n请生成6个主角人设选项"

    # 灵感模式 - 金手指/优势生成
    INSPIRATION_GOLDEN_FINGER_SYSTEM = """你是一位专业的小说创作顾问。
小说信息：
- 书名：{title}
- 类型：{genre}
- 主角：{protagonist}

请生成6个主角的特殊优势（金手指/Golden Finger），要求：
1. 符合网文爽点逻辑
2. 能帮助主角打破常规，解决难题
3. 形式多样（系统、老爷爷、异能、重生先知、特殊背景）

返回JSON格式：
{{"prompt":"主角的特殊优势（金手指）是什么？","options":["金手指1","金手指2","金手指3","金手指4","金手指5","金手指6"]}}

只返回纯JSON。"""

    INSPIRATION_GOLDEN_FINGER_USER = "书名：{title}\n主角：{protagonist}\n请生成6个金手指选项"

    # 灵感模式 - 动态引导代理 (Auto Mode)
    INSPIRATION_DYNAMIC_SYSTEM = """你是一位专业的小说创作顾问。你的目标是通过 8-10 轮循序渐进的对话，引导用户构建出完整且深度的小说设定方案。

当前已收集的信息（上下文）：
{context_json}

【你的预设引导图谱】（仅供参考，请根据实际情况灵活调整顺序）：
1. 核心创意 (initial_idea) - 种子
2. 书名 (title) - 门面
3. 类型 (genre) - 基调
4. 核心主题 (theme) - 灵魂
5. 世界观/地图 (world_setting) - 舞台
6. 力量体系/金手指 (power_system) - 玩法
7. 主角人设 (protagonist) - 核心驱动
8. 核心冲突/反派 (conflict) - 阻力
9. 故事节奏/风格 (pacing) - 体验
10. 开篇切入点 (opening_hook) - 抓手

【任务】
1. 分析【上下文】，判断当前已有哪些信息，还缺哪些关键信息。
2. 决定**下一个**最需要确定的关键设定（Next Best Action）。
3. 针对该设定，设计一个引导问题（Prompt）。
4. 生成 6 个具有启发性、具体且符合已有逻辑的选项（Options）。
5. 确定该设定的字段键名（Key）。

【返回格式】
{{
    "next_step_key": "字段英文键名（如 world_setting, conflict 等）",
    "prompt": "引导问题（如：这个故事发生在一个什么样的世界？）",
    "options": ["选项1", "选项2", "选项3", "选项4", "选项5", "选项6"]
}}

【注意】
- 如果上下文为空，默认从"书名"或"核心创意"开始。
- 选项要与已有信息（如类型、题材）高度自洽。
- 只有当所有关键信息都收集完毕，才建议结束（此时 key 返回 "finish"）。
- 只返回纯 JSON。
"""

    INSPIRATION_DYNAMIC_USER = "请分析当前进度，生成下一步的引导问题和选项。"

    # 灵感模式智能补全提示词
    INSPIRATION_QUICK_COMPLETE = """你是一位专业的小说创作顾问。用户提供了部分小说信息，请补全缺失的字段。

用户已提供的信息：
{existing}

请生成完整的小说方案，包含：
1. title: 书名（3-6字，如果用户已提供则保持原样）
2. description: 简介（50-100字，必须基于用户提供的信息，不要偏离原意）
3. theme: 核心主题（30-50字，必须与用户提供的信息保持一致）
4. genre: 类型标签数组（2-3个）

重要：所有补全的内容都必须与用户提供的信息保持高度关联，确保前后一致性。

返回JSON格式：
{{
    "title": "书名",
    "description": "简介内容...",
    "theme": "主题内容...",
    "genre": ["类型1", "类型2"]
}}

只返回纯JSON，不要有其他文字。"""
    # 世界观资料收集提示词（MCP增强用）
    MCP_WORLD_BUILDING_PLANNING = """你正在为小说《{title}》设计世界观。

【小说信息】
- 题材：{genre}
- 主题：{theme}
- 简介：{description}

【任务】
请使用可用工具搜索相关背景资料，帮助构建更真实、更有深度的世界观设定。
你可以查询：
1. 历史背景（如果是历史题材）
2. 地理环境和文化特征
3. 相关领域的专业知识
4. 类似作品的设定参考

请查询最关键的1个问题（不要超过1个）。"""

    # 角色资料收集提示词（MCP增强用）
    MCP_CHARACTER_PLANNING = """你正在为小说《{title}》设计角色。

【小说信息】
- 题材：{genre}
- 主题：{theme}
- 时代背景：{time_period}
- 地理位置：{location}

【任务】
请使用可用工具搜索相关参考资料，帮助设计更真实、更有深度的角色。
你可以查询：
1. 该时代/地域的真实历史人物特征
2. 文化背景和社会习俗
3. 职业特点和生活方式
4. 相关领域的人物原型

请查询最关键的1个问题（不要超过1个）。"""

    # 自动角色引入 - 预测性分析提示词 V2（RTCO框架）
    AUTO_CHARACTER_ANALYSIS = """<system>
你是专业的小说角色设计顾问，擅长预测剧情发展对角色的需求。
</system>

<task>
【分析任务】
预测在接下来的{chapter_count}章续写中，根据剧情发展方向和阶段，是否需要引入新角色。

【重要说明】
这是预测性分析，而非基于已生成内容的事后分析。
</task>

<project priority="P1">
【项目信息】
书名：{title}
类型：{genre}
主题：{theme}

【世界观】
时间背景：{time_period}
地理位置：{location}
氛围基调：{atmosphere}
</project>

<context priority="P0">
【已有角色】
{existing_characters}

【已有章节概览】
{all_chapters_brief}

【续写计划】
- 起始章节：第{start_chapter}章
- 续写数量：{chapter_count}章
- 剧情阶段：{plot_stage}
- 发展方向：{story_direction}
</context>

<analysis_framework priority="P0">
【预测分析维度】

**1. 剧情需求预测**
根据发展方向，哪些场景、冲突需要新角色参与？

**2. 角色充分性**
现有角色是否足以支撑即将发生的剧情？

**3. 引入时机**
新角色应该在哪个章节登场最合适？

**4. 重要性判断**
新角色对后续剧情的影响程度如何？

【预测依据】
- 剧情阶段的典型角色需求（如：高潮阶段可能需要强力对手）
- 故事发展方向的逻辑需要（如：进入新地点需要当地角色）
- 冲突升级的角色需求（如：更强的反派、意外的盟友）
- 世界观扩展的需要（如：新组织、新势力的代表）
</analysis_framework>

<output priority="P0">
【输出格式】
返回纯JSON对象（两种情况之一）：

**情况A：需要新角色**
{{
  "needs_new_characters": true,
  "reason": "预测分析原因（150-200字），说明为什么即将的剧情需要新角色",
  "character_count": 2,
  "character_specifications": [
    {{
      "name": "建议的角色名字（可选）",
      "role_description": "角色在剧情中的定位和作用（100-150字）",
      "suggested_role_type": "supporting/antagonist/protagonist",
      "importance": "high/medium/low",
      "appearance_chapter": {start_chapter},
      "key_abilities": ["能力1", "能力2"],
      "plot_function": "在剧情中的具体功能",
      "relationship_suggestions": [
        {{
          "target_character": "现有角色名",
          "relationship_type": "建议的关系类型",
          "reason": "为什么建立这种关系"
        }}
      ]
    }}
  ]
}}

**情况B：不需要新角色**
{{
  "needs_new_characters": false,
  "reason": "现有角色足以支撑即将的剧情发展，说明理由"
}}
</output>

<constraints>
【必须遵守】
✅ 这是预测性分析，面向未来剧情
✅ 考虑剧情的自然发展和节奏
✅ 确保引入必要性，不为引入而引入
✅ 优先考虑角色的长期作用

【禁止事项】
❌ 输出markdown标记
❌ 基于已生成内容做事后分析
❌ 为了引入角色而强行引入
❌ 设计一次性功能角色
</constraints>"""

    # 自动角色引入 - 生成提示词 V2（RTCO框架）
    AUTO_CHARACTER_GENERATION = """<system>
你是专业的角色设定师，擅长根据剧情需求创建完整的角色设定。
</system>

<task>
【生成任务】
为小说生成新角色的完整设定，包括基本信息、性格背景、关系网络和职业信息。
</task>

<project priority="P1">
【项目信息】
书名：{title}
类型：{genre}
主题：{theme}

【世界观】
时间背景：{time_period}
地理位置：{location}
氛围基调：{atmosphere}
世界规则：{rules}
</project>

<context priority="P0">
【已有角色】
{existing_characters}

【剧情上下文】
{plot_context}

【角色规格要求】
{character_specification}
</context>

<mcp_context priority="P2">
【MCP工具参考】
{mcp_references}
</mcp_context>

<requirements priority="P0">
【核心要求】
1. 角色必须符合剧情需求和世界观设定
2. **必须分析新角色与已有角色的关系**，至少建立1-3个有意义的关系
3. 性格、背景要有深度和独特性
4. 外貌描写要具体生动
5. 特长和能力要符合角色定位
6. **如果【已有角色】中包含职业列表，必须为角色设定职业**

【关系建立指导】
- 仔细审视【已有角色】列表，思考新角色与哪些现有角色有联系
- 根据剧情需求，建立合理的角色关系
- 每个关系都要有明确的类型、亲密度和描述
- 关系应该服务于剧情发展
- 如果新角色是组织成员，记得填写organization_memberships

【职业信息要求】
如果【已有角色】部分包含"可用主职业列表"或"可用副职业列表"：
- 仔细查看可用的主职业和副职业列表
- 根据角色的背景、能力、故事定位，选择最合适的职业
- 主职业：从"可用主职业列表"中选择一个，填写职业名称
- 主职业阶段：根据职业的阶段信息和角色实力，设定合理的当前阶段
- 副职业：可选择0-2个副职业
- ⚠️ 重要：必须填写职业的名称而非ID
</requirements>

<output priority="P0">
【输出格式】
返回纯JSON对象：

{{
  "name": "角色姓名",
  "age": 25,
  "gender": "男/女/其他",
  "role_type": "supporting",
  "personality": "性格特点的详细描述（100-200字）",
  "background": "背景故事的详细描述（100-200字）",
  "appearance": "外貌描述（50-100字）",
  "traits": ["特长1", "特长2", "特长3"],
  "relationships_text": "用自然语言描述该角色与其他角色的关系网络",
  
  "relationships": [
    {{
      "target_character_name": "已存在的角色名称",
      "relationship_type": "关系类型",
      "intimacy_level": 75,
      "description": "关系的具体描述",
      "status": "active"
    }}
  ],
  "organization_memberships": [
    {{
      "organization_name": "已存在的组织名称",
      "position": "职位",
      "rank": 5,
      "loyalty": 80
    }}
  ],
  
  "career_info": {{
    "main_career_name": "从可用主职业列表中选择的职业名称",
    "main_career_stage": 5,
    "sub_careers": [
      {{
        "career_name": "从可用副职业列表中选择的职业名称",
        "stage": 3
      }}
    ]
  }}
}}

【关系类型参考】
家族、社交、职业、敌对等各类关系

【数值范围】
- intimacy_level：-100到100（负值表示敌对）
- loyalty：0到100
- rank：0到10
</output>

<constraints>
【必须遵守】
✅ 符合剧情需求和世界观设定
✅ relationships数组必填：至少1-3个关系
✅ target_character_name必须精确匹配【已有角色】
✅ organization_memberships只能引用已存在的组织
✅ 职业选择必须从可用列表中选择

【禁止事项】
❌ 输出markdown标记
❌ 在描述中使用特殊符号
❌ 引用不存在的角色或组织
❌ 使用职业ID而非职业名称
</constraints>"""

    # 自动组织引入 - 预测性分析提示词（RTCO框架）
    AUTO_ORGANIZATION_ANALYSIS = """<system>
你是专业的小说世界构建顾问，擅长预测剧情发展对组织/势力的需求。
</system>

<task>
【分析任务】
预测在接下来的{chapter_count}章续写中，根据剧情发展方向和阶段，是否需要引入新的组织或势力。

【重要说明】
这是预测性分析，而非基于已生成内容的事后分析。
组织包括：帮派、门派、公司、政府机构、神秘组织、家族等。
</task>

<project priority="P1">
【项目信息】
书名：{title}
类型：{genre}
主题：{theme}

【世界观】
时间背景：{time_period}
地理位置：{location}
氛围基调：{atmosphere}
</project>

<context priority="P0">
【已有组织】
{existing_organizations}

【已有角色】
{existing_characters}

【已有章节概览】
{all_chapters_brief}

【续写计划】
- 起始章节：第{start_chapter}章
- 续写数量：{chapter_count}章
- 剧情阶段：{plot_stage}
- 发展方向：{story_direction}
</context>

<analysis_framework priority="P0">
【预测分析维度】

**1. 世界观扩展需求**
根据发展方向，是否需要新的势力或组织来丰富世界观？

**2. 冲突升级需求**
剧情是否需要新的对立势力、竞争组织或神秘集团？

**3. 角色归属需求**
现有角色是否需要加入或对抗某个新组织？

**4. 剧情推动需求**
新组织能否成为推动剧情的关键力量？

**5. 引入时机**
新组织应该在哪个章节出现最合适？

【预测依据】
- 剧情阶段的典型组织需求（如：高潮阶段可能需要强大的敌对势力）
- 故事发展方向的逻辑需要（如：进入新地点需要当地势力）
- 世界观完整性需要（如：权力格局需要多方势力）
- 角色成长需要（如：主角需要加入或创建组织）
</analysis_framework>

<output priority="P0">
【输出格式】
返回纯JSON对象（两种情况之一）：

**情况A：需要新组织**
{{
"needs_new_organizations": true,
"reason": "预测分析原因（150-200字），说明为什么即将的剧情需要新组织",
"organization_count": 1,
"organization_specifications": [
{{
  "name": "建议的组织名字（可选）",
  "organization_description": "组织在剧情中的定位和作用（100-150字）",
  "organization_type": "帮派/门派/公司/政府/家族/神秘组织等",
  "importance": "high/medium/low",
  "appearance_chapter": {start_chapter},
  "power_level": 70,
  "plot_function": "在剧情中的具体功能",
  "location": "组织所在地或活动区域",
  "motto": "组织口号或宗旨（可选）",
  "initial_members": [
    {{
      "character_name": "现有角色名（如需加入）",
      "position": "职位",
      "reason": "为什么加入"
    }}
  ],
  "relationship_suggestions": [
    {{
      "target_organization": "已有组织名",
      "relationship_type": "建议的关系类型（盟友/敌对/竞争/合作等）",
      "reason": "为什么建立这种关系"
    }}
  ]
}}
]
}}

**情况B：不需要新组织**
{{
"needs_new_organizations": false,
"reason": "现有组织足以支撑即将的剧情发展，说明理由"
}}
</output>

<constraints>
【必须遵守】
✅ 这是预测性分析，面向未来剧情
✅ 考虑世界观的丰富性和完整性
✅ 确保引入必要性，不为引入而引入
✅ 优先考虑组织的长期作用
✅ 组织应该是推动剧情的关键力量

【禁止事项】
❌ 输出markdown标记
❌ 基于已生成内容做事后分析
❌ 为了引入组织而强行引入
❌ 设计一次性功能组织
❌ 创建与现有组织功能重复的组织
</constraints>"""

    # 自动组织引入 - 生成提示词（RTCO框架）
    AUTO_ORGANIZATION_GENERATION = """<system>
你是专业的世界构建师，擅长根据剧情需求创建完整的组织/势力设定。
</system>

<task>
【生成任务】
为小说生成新组织的完整设定，包括基本信息、组织特性、背景历史和成员结构。
</task>

<project priority="P1">
【项目信息】
书名：{title}
类型：{genre}
主题：{theme}

【世界观】
时间背景：{time_period}
地理位置：{location}
氛围基调：{atmosphere}
世界规则：{rules}
</project>

<context priority="P0">
【已有组织】
{existing_organizations}

【已有角色】
{existing_characters}

【剧情上下文】
{plot_context}

【组织规格要求】
{organization_specification}
</context>

<mcp_context priority="P2">
【MCP工具参考】
{mcp_references}
</mcp_context>

<requirements priority="P0">
【核心要求】
1. 组织必须符合剧情需求和世界观设定
2. 组织要有明确的目的、结构和特色
3. 组织特性、背景要有深度和独特性
4. 外在表现要具体生动
5. 考虑与已有组织的关系和互动
6. 如果需要，可以建议将现有角色加入组织
</requirements>

<output priority="P0">
【输出格式】
返回纯JSON对象：

{{
"name": "组织名称",
"is_organization": true,
"role_type": "supporting",
"organization_type": "组织类型（帮派/门派/公司/政府/家族/神秘组织等）",
"personality": "组织特性的详细描述（150-200字）：运作方式、核心理念、行事风格、文化价值观",
"background": "组织背景故事（200-300字）：建立历史、发展历程、重要事件、当前地位",
"appearance": "外在表现（100-150字）：总部位置、标志性建筑、组织标志、成员着装",
"organization_purpose": "组织目的和宗旨：明确目标、长期愿景、行动准则",
"power_level": 75,
"location": "所在地点：主要活动区域、势力范围",
"motto": "组织格言或口号",
"color": "组织代表颜色",
"traits": ["特征1", "特征2", "特征3"],

"initial_members": [
{{
  "character_name": "已存在的角色名称",
  "position": "职位名称",
  "rank": 8,
  "loyalty": 80,
  "joined_at": "加入时间（可选）",
  "status": "active"
}}
],

"organization_relationships": [
{{
  "target_organization_name": "已存在的组织名称",
  "relationship_type": "盟友/敌对/竞争/合作/从属等",
  "description": "关系的具体描述"
}}
]
}}

【数值范围】
- power_level：0-100的整数，表示在世界中的影响力
- rank：0到10（职位等级）
- loyalty：0到100（成员忠诚度）
</output>

<constraints>
【必须遵守】
✅ 符合剧情需求和世界观设定
✅ 组织要有独特的定位和价值
✅ character_name必须精确匹配【已有角色】
✅ target_organization_name必须精确匹配【已有组织】
✅ 组织能够推动剧情发展

【禁止事项】
❌ 输出markdown标记
❌ 在描述中使用特殊符号
❌ 引用不存在的角色或组织
❌ 创建功能与现有组织重复的组织
❌ 创建对剧情没有实际作用的组织
</constraints>"""

    # 职业体系生成提示词 V2（RTCO框架）
    CAREER_SYSTEM_GENERATION = """<system>
你是专业的职业体系设计师，擅长为不同世界观设计完整的职业体系。
</system>

<task>
【设计任务】
根据世界观信息，设计一个完整且合理的职业体系，包括主职业和副职业。
</task>

<worldview priority="P0">
【项目信息】
书名：{title}
类型：{genre}
主题：{theme}
时间背景：{time_period}
地理位置：{location}
氛围基调：{atmosphere}
世界规则：{rules}
</worldview>

<design_requirements priority="P0">
【设计要求】

**1. 主职业（main_careers）**
- 根据世界观特点，决定需要多少个主职业
- 主职业是角色的核心发展方向
- 必须严格符合世界观规则
- 每个主职业的阶段数量可以不同（体现职业复杂度差异）

**2. 副职业（sub_careers）**
- 根据世界需要，决定需要多少个副职业
- 副职业包含生产、辅助、特殊技能类
- 每个副职业的阶段数量可以不同
- 不要让所有副职业都是相同的阶段数

**3. 阶段设计（stages）**
- 每个职业的stages数组长度必须等于max_stage
- 阶段名称要符合世界观文化背景
- 阶段描述要体现明确的能力提升路径
- 确保职业间的阶段数量有差异
</design_requirements>

<output priority="P0">
【输出格式】
返回纯JSON对象：

{{
"main_careers": [
{{
  "name": "职业名称",
  "description": "职业描述（100-150字）",
  "category": "职业分类",
  "stages": [
    {{"level": 1, "name": "阶段1名称", "description": "阶段描述"}},
    {{"level": 2, "name": "阶段2名称", "description": "阶段描述"}}
  ],
  "max_stage": 整数,
  "requirements": "职业要求和前置条件",
  "special_abilities": "职业特殊能力",
  "worldview_rules": "与世界观规则的关联",
  "attribute_bonuses": {{"strength": "+10%"}}
}}
],
"sub_careers": [
{{
  "name": "副职业名称",
  "description": "职业描述（80-120字）",
  "category": "生产系/辅助系/特殊系",
  "stages": [
    {{"level": 1, "name": "阶段1名称", "description": "阶段描述"}}
  ],
  "max_stage": 整数,
  "requirements": "职业要求",
  "special_abilities": "特殊能力"
}}
]
}}
</output>

<constraints>
【必须遵守】
✅ 职业数量和类型根据世界观自行决定
✅ 不同职业的max_stage必须不同
✅ 主职业阶段数建议：5-15个
✅ 副职业阶段数建议：3-10个
✅ stages数组长度必须等于max_stage
✅ 确保职业体系与世界观高度契合

【禁止事项】
❌ 所有职业使用相同的阶段数
❌ 输出markdown标记
❌ 职业设计与世界观脱节
</constraints>"""

    @staticmethod
    def _get_genre_strategy(genre: str) -> str:
        """根据类型获取长篇策略指令"""
        if not genre:
            return ""
            
        # 标准化类型名称
        genre_lower = genre.lower()
        
        # 遍历策略矩阵进行匹配
        for strategy_key, strategy_data in GENRE_STRATEGIES.items():
            # 检查是否匹配关键字
            if any(keyword in genre_lower for keyword in strategy_data["keywords"]):
                return strategy_data["instruction"]
                
        # 默认返回空或通用建议
        return ""

    @staticmethod
    def format_prompt(template: str, **kwargs) -> str:
        """
        格式化提示词模板 - 自动注入类型策略
        
        Args:
            template: 提示词模板
            **kwargs: 模板参数
            
        Returns:
            格式化后的提示词
        """
        try:
            # 自动注入长篇策略 (如果参数中包含 genre)
            if "genre" in kwargs and "genre_strategy" not in kwargs:
                kwargs["genre_strategy"] = PromptService._get_genre_strategy(kwargs["genre"])
            
            # 如果模板中没有 {genre_strategy} 占位符，format 会忽略多余参数
            # 但为了安全起见，我们可以检查一下
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"缺少必需的参数: {e}")
    

    @classmethod
    async def get_chapter_regeneration_prompt(cls, chapter_number: int, title: str, word_count: int, content: str,
                                        modification_instructions: str, project_context: Dict[str, Any],
                                        style_content: str, target_word_count: int,
                                        user_id: str = None, db = None) -> str:
        """
        获取章节重写提示词（支持用户自定义）
        
        Args:
            chapter_number: 章节序号
            title: 章节标题
            word_count: 原始字数
            content: 原始内容
            modification_instructions: 修改指令
            project_context: 项目上下文
            style_content: 写作风格
            target_word_count: 目标字数
            user_id: 用户ID（可选，用于获取自定义模板）
            db: 数据库会话（可选，用于查询自定义模板）
            
        Returns:
            完整的章节重写提示词
        """
        # 获取系统提示词模板（支持用户自定义）
        if user_id and db:
            system_template = await cls.get_template("CHAPTER_REGENERATION_SYSTEM", user_id, db)
        else:
            system_template = cls.CHAPTER_REGENERATION_SYSTEM
        
        prompt_parts = [system_template]
        
        # 原始章节信息
        prompt_parts.append(f"""## 📖 原始章节信息

**章节**：第{chapter_number}章
**标题**：{title}
**字数**：{word_count}字

**原始内容**：
{content}

---
""")
        
        # 修改指令
        prompt_parts.append(modification_instructions)
        prompt_parts.append("\n---\n")
        
        # 项目背景信息
        prompt_parts.append(f"""## 🌍 项目背景信息

**小说标题**：{project_context.get('project_title', '未知')}
**题材**：{project_context.get('genre', '未设定')}
**主题**：{project_context.get('theme', '未设定')}
**叙事视角**：{project_context.get('narrative_perspective', '第三人称')}
**世界观设定**：
- 时代背景：{project_context.get('time_period', '未设定')}
- 地理位置：{project_context.get('location', '未设定')}
- 氛围基调：{project_context.get('atmosphere', '未设定')}

---
""")
        
        # 角色信息
        if project_context.get('characters_info'):
            prompt_parts.append(f"""## 👥 角色信息

{project_context['characters_info']}

---
""")
        
        # 章节大纲
        if project_context.get('chapter_outline'):
            prompt_parts.append(f"""## 📝 本章大纲

{project_context['chapter_outline']}

---
""")
        
        # 前置章节上下文
        if project_context.get('previous_context'):
            prompt_parts.append(f"""## 📚 前置章节上下文

{project_context['previous_context']}

---
""")
        
        # 写作风格要求
        if style_content:
            prompt_parts.append(f"""## 🎨 写作风格要求

{style_content}

请在重新创作时严格遵循上述写作风格。

---
""")
        
        # 创作要求
        prompt_parts.append(f"""## ✨ 创作要求

1. **解决问题**：针对上述修改指令中提到的所有问题进行改进
2. **保持连贯**：确保与前后章节的情节、人物、风格保持一致
3. **提升质量**：在节奏、情感、描写等方面明显优于原版
4. **保留精华**：保持原章节中优秀的部分和关键情节
5. **字数控制**：目标字数约{target_word_count}字（可适当浮动±20%）
{f'6. **风格一致**：严格按照上述写作风格进行创作' if style_content else ''}

---

## 🎬 开始创作

请现在开始创作改进后的新版本章节内容。

**重要提示**：
- 直接输出章节正文内容，从故事内容开始写
- **不要**输出章节标题（如"第X章"、"第X章：XXX"等）
- **不要**输出任何额外的说明、注释或元数据
- 只需要纯粹的故事正文内容

现在开始：
""")
        
        return "\n".join(prompt_parts)

    @classmethod
    async def get_mcp_tool_test_prompts(
        cls,
        plugin_name: str,
        user_id: str = None,
        db = None
    ) -> Dict[str, str]:
        """
        获取MCP工具测试的提示词（支持自定义）
        
        Args:
            plugin_name: 插件名称
            user_id: 用户ID（可选）
            db: 数据库会话（可选）
            
        Returns:
            包含user和system提示词的字典
        """
        # 获取用户自定义或系统默认的user提示词
        if user_id and db:
            user_template = await cls.get_template("MCP_TOOL_TEST", user_id, db)
        else:
            user_template = cls.MCP_TOOL_TEST
        
        # 获取用户自定义或系统默认的system提示词
        if user_id and db:
            system_template = await cls.get_template("MCP_TOOL_TEST_SYSTEM", user_id, db)
        else:
            system_template = cls.MCP_TOOL_TEST_SYSTEM
        
        return {
            "user": cls.format_prompt(user_template, plugin_name=plugin_name),
            "system": system_template
        }

    # ========== 自定义提示词支持 ==========
    
    @classmethod
    async def get_template_with_fallback(cls,
                                        template_key: str,
                                        user_id: str = None,
                                        db = None) -> str:
        """
        获取提示词模板（优先用户自定义，支持降级）
        
        Args:
            template_key: 模板键名
            user_id: 用户ID（可选，如果不提供则直接返回系统默认）
            db: 数据库会话（可选）
            
        Returns:
            提示词模板内容
        """
        # 如果没有提供user_id或db，直接返回系统默认
        if not user_id or not db:
            return getattr(cls, template_key, None)
        
        # 尝试获取用户自定义模板
        return await cls.get_template(template_key, user_id, db)
    
    @classmethod
    async def get_template(cls,
                          template_key: str,
                          user_id: str,
                          db) -> str:
        """
        获取提示词模板（优先用户自定义）
        
        Args:
            template_key: 模板键名
            user_id: 用户ID
            db: 数据库会话
            
        Returns:
            提示词模板内容
        """
        from sqlalchemy import select
        from app.models.prompt_template import PromptTemplate
        from app.logger import get_logger
        
        logger = get_logger(__name__)
        
        # 1. 尝试从数据库获取用户自定义模板
        result = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.user_id == user_id,
                PromptTemplate.template_key == template_key,
                PromptTemplate.is_active == True
            )
        )
        custom_template = result.scalar_one_or_none()
        
        if custom_template:
            logger.info(f"✅ 使用用户自定义提示词: user_id={user_id}, template_key={template_key}, template_name={custom_template.template_name}")
            return custom_template.template_content
        
        # 2. 降级到系统默认模板
        logger.info(f"⚪ 使用系统默认提示词: user_id={user_id}, template_key={template_key} (未找到自定义模板)")
        
        # 直接从类属性获取系统默认模板
        template_content = getattr(cls, template_key, None)
        
        if template_content is None:
            logger.warning(f"⚠️ 未找到系统默认模板: {template_key}")
        
        return template_content
    
    @classmethod
    def get_all_system_templates(cls) -> list:
        """
        获取所有系统默认模板的信息
        
        Returns:
            系统模板列表
        """
        templates = []
        
        # 定义所有模板及其元信息
        template_definitions = {
            "WORLD_BUILDING": {
                "name": "世界构建",
                "category": "世界构建",
                "description": "用于生成小说世界观设定，包括时间背景、地理位置、氛围基调和世界规则",
                "parameters": ["title", "theme", "genre", "description"]
            },
            "CHARACTERS_BATCH_GENERATION": {
                "name": "批量角色生成",
                "category": "角色生成",
                "description": "批量生成多个角色和组织，建立角色关系网络",
                "parameters": ["count", "time_period", "location", "atmosphere", "rules", "theme", "genre", "requirements"]
            },
            "SINGLE_CHARACTER_GENERATION": {
                "name": "单个角色生成",
                "category": "角色生成",
                "description": "生成单个角色的详细设定",
                "parameters": ["project_context", "user_input"]
            },
            "SINGLE_ORGANIZATION_GENERATION": {
                "name": "组织生成",
                "category": "角色生成",
                "description": "生成组织/势力的详细设定",
                "parameters": ["project_context", "user_input"]
            },
            "OUTLINE_CREATE": {
                "name": "初始大纲生成",
                "category": "大纲生成",
                "description": "根据项目信息生成完整的章节大纲",
                "parameters": ["title", "theme", "genre", "chapter_count", "narrative_perspective", "target_words", 
                             "time_period", "location", "atmosphere", "rules", "characters_info", "requirements", "mcp_references"]
            },
            "OUTLINE_CONTINUE": {
                "name": "大纲续写",
                "category": "大纲生成",
                "description": "基于已有章节续写大纲",
                "parameters": ["title", "theme", "genre", "narrative_perspective", "chapter_count", "time_period", 
                             "location", "atmosphere", "rules", "characters_info", "current_chapter_count", 
                             "all_chapters_brief", "recent_plot", "memory_context", "mcp_references", 
                             "plot_stage_instruction", "start_chapter", "end_chapter", "story_direction", "requirements"]
            },
            "CHAPTER_GENERATION_V2": {
                "name": "章节创作V2（首章）",
                "category": "章节创作",
                "description": "根据大纲创作章节内容（用于第1章，无前置章节）",
                "parameters": ["project_title", "genre", "chapter_number", "chapter_title", "chapter_outline",
                             "target_word_count", "narrative_perspective", "characters_info"]
            },
            "CHAPTER_GENERATION_V2_WITH_CONTEXT": {
                "name": "章节创作V2（续章）",
                "category": "章节创作",
                "description": "基于前置章节内容创作新章节（用于第2章及以后）",
                "parameters": ["project_title", "genre", "chapter_number", "chapter_title", "chapter_outline",
                             "target_word_count", "narrative_perspective", "characters_info", "continuation_point",
                             "relevant_memories", "story_skeleton"]
            },
            "CHAPTER_REGENERATION_SYSTEM": {
                "name": "章节重写系统提示",
                "category": "章节重写",
                "description": "用于章节重写的系统提示词",
                "parameters": ["chapter_number", "title", "word_count", "content", "modification_instructions", 
                             "project_context", "style_content", "target_word_count"]
            },
            "PLOT_ANALYSIS": {
                "name": "情节分析",
                "category": "情节分析",
                "description": "深度分析章节的剧情、钩子、伏笔等",
                "parameters": ["chapter_number", "title", "content", "word_count"]
            },
            "OUTLINE_EXPAND_SINGLE": {
                "name": "大纲单批次展开",
                "category": "情节展开",
                "description": "将大纲节点展开为详细章节规划（单批次）",
                "parameters": ["project_title", "project_genre", "project_theme", "project_narrative_perspective", 
                             "project_world_time_period", "project_world_location", "project_world_atmosphere", 
                             "characters_info", "outline_order_index", "outline_title", "outline_content", 
                             "context_info", "strategy_instruction", "target_chapter_count", "scene_instruction", "scene_field"]
            },
            "OUTLINE_EXPAND_MULTI": {
                "name": "大纲分批展开",
                "category": "情节展开",
                "description": "将大纲节点展开为详细章节规划（分批）",
                "parameters": ["project_title", "project_genre", "project_theme", "project_narrative_perspective", 
                             "project_world_time_period", "project_world_location", "project_world_atmosphere", 
                             "characters_info", "outline_order_index", "outline_title", "outline_content", 
                             "context_info", "previous_context", "strategy_instruction", "start_index", 
                             "end_index", "target_chapter_count", "scene_instruction", "scene_field"]
            },
            "MCP_TOOL_TEST": {
                "name": "MCP工具测试(用户提示词)",
                "category": "MCP测试",
                "description": "用于测试MCP插件功能的用户提示词",
                "parameters": ["plugin_name"]
            },
            "MCP_TOOL_TEST_SYSTEM": {
                "name": "MCP工具测试(系统提示词)",
                "category": "MCP测试",
                "description": "用于测试MCP插件功能的系统提示词",
                "parameters": []
            },
            "MCP_WORLD_BUILDING_PLANNING": {
                "name": "MCP世界观规划",
                "category": "MCP增强",
                "description": "使用MCP工具搜索资料辅助世界观设计",
                "parameters": ["title", "genre", "theme", "description"]
            },
            "MCP_CHARACTER_PLANNING": {
                "name": "MCP角色规划",
                "category": "MCP增强",
                "description": "使用MCP工具搜索资料辅助角色设计",
                "parameters": ["title", "genre", "theme", "time_period", "location"]
            },
            "AUTO_CHARACTER_ANALYSIS": {
                "name": "自动角色分析",
                "category": "自动角色引入",
                "description": "分析新生成的大纲，判断是否需要引入新角色",
                "parameters": ["title", "genre", "theme", "time_period", "location", "atmosphere",
                             "existing_characters", "new_outlines", "start_chapter", "end_chapter"]
            },
            "AUTO_CHARACTER_GENERATION": {
                "name": "自动角色生成",
                "category": "自动角色引入",
                "description": "根据剧情需求自动生成新角色的完整设定",
                "parameters": ["title", "genre", "theme", "time_period", "location", "atmosphere", "rules",
                             "existing_characters", "plot_context", "character_specification", "mcp_references"]
            },
            "AUTO_ORGANIZATION_ANALYSIS": {
                "name": "自动组织分析",
                "category": "自动组织引入",
                "description": "分析新生成的大纲，判断是否需要引入新组织",
                "parameters": ["title", "genre", "theme", "time_period", "location", "atmosphere",
                             "existing_organizations", "existing_characters", "all_chapters_brief", "start_chapter", "chapter_count", "plot_stage", "story_direction"]
            },
            "AUTO_ORGANIZATION_GENERATION": {
                "name": "自动组织生成",
                "category": "自动组织引入",
                "description": "根据剧情需求自动生成新组织的完整设定",
                "parameters": ["title", "genre", "theme", "time_period", "location", "atmosphere", "rules",
                             "existing_organizations", "existing_characters", "plot_context", "organization_specification", "mcp_references"]
            },
            "CAREER_SYSTEM_GENERATION": {
                "name": "职业体系生成",
                "category": "世界构建",
                "description": "根据世界观自动生成完整的职业体系，包括主职业和副职业",
                "parameters": ["title", "genre", "theme", "time_period", "location", "atmosphere", "rules"]
            },
            "INSPIRATION_TITLE_SYSTEM": {
                "name": "灵感模式-书名生成(系统提示词)",
                "category": "灵感模式",
                "description": "根据用户的原始想法生成6个书名建议的系统提示词",
                "parameters": ["initial_idea"]
            },
            "INSPIRATION_TITLE_USER": {
                "name": "灵感模式-书名生成(用户提示词)",
                "category": "灵感模式",
                "description": "根据用户的原始想法生成6个书名建议的用户提示词",
                "parameters": ["initial_idea"]
            },
            "INSPIRATION_DESCRIPTION_SYSTEM": {
                "name": "灵感模式-简介生成(系统提示词)",
                "category": "灵感模式",
                "description": "根据用户想法和书名生成6个简介选项的系统提示词",
                "parameters": ["initial_idea", "title"]
            },
            "INSPIRATION_DESCRIPTION_USER": {
                "name": "灵感模式-简介生成(用户提示词)",
                "category": "灵感模式",
                "description": "根据用户想法和书名生成6个简介选项的用户提示词",
                "parameters": ["initial_idea", "title"]
            },
            "INSPIRATION_THEME_SYSTEM": {
                "name": "灵感模式-主题生成(系统提示词)",
                "category": "灵感模式",
                "description": "根据书名和简介生成6个深刻的主题选项的系统提示词",
                "parameters": ["initial_idea", "title", "description"]
            },
            "INSPIRATION_THEME_USER": {
                "name": "灵感模式-主题生成(用户提示词)",
                "category": "灵感模式",
                "description": "根据书名和简介生成6个深刻的主题选项的用户提示词",
                "parameters": ["initial_idea", "title", "description"]
            },
            "INSPIRATION_GENRE_SYSTEM": {
                "name": "灵感模式-类型生成(系统提示词)",
                "category": "灵感模式",
                "description": "根据小说信息生成6个合适的类型标签的系统提示词",
                "parameters": ["initial_idea", "title", "description", "theme"]
            },
            "INSPIRATION_GENRE_USER": {
                "name": "灵感模式-类型生成(用户提示词)",
                "category": "灵感模式",
                "description": "根据小说信息生成6个合适的类型标签的用户提示词",
                "parameters": ["initial_idea", "title", "description", "theme"]
            },
            "INSPIRATION_QUICK_COMPLETE": {
                "name": "灵感模式-智能补全",
                "category": "灵感模式",
                "description": "根据用户提供的部分信息智能补全完整的小说方案",
                "parameters": ["existing"]
            }
        }
        
        for key, info in template_definitions.items():
            template_content = getattr(cls, key, None)
            if template_content:
                templates.append({
                    "template_key": key,
                    "template_name": info["name"],
                    "category": info["category"],
                    "description": info["description"],
                    "parameters": info["parameters"],
                    "content": template_content
                })
        
        return templates
    
    @classmethod
    def get_system_template_info(cls, template_key: str) -> dict:
        """
        获取指定系统模板的信息
        
        Args:
            template_key: 模板键名
            
        Returns:
            模板信息字典
        """
        all_templates = cls.get_all_system_templates()
        for template in all_templates:
            if template["template_key"] == template_key:
                return template
        return None

# ========== 全局实例 ==========
prompt_service = PromptService()