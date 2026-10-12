"""
[INPUT]
- PresentationGenerateRequest, SlideData from app.api.presentation.models
- python-pptx (Presentation, Inches, Pt, RGBColor, MSO_SHAPE)

[OUTPUT]
- generate_presentation_structure(request) -> List[SlideData]
- render_pptx_binary(slides, template_style, topic) -> bytes

[POS]
Core PowerPoint generator engine for EnterprisePresentationSlideGeneratorAndVisualConceptIllustrator.
Single file < 300 lines. Strictly typed.
"""

import io
from typing import Dict, List, Tuple

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.api.presentation.models import (
    PresentationGenerateRequest,
    SlideData,
    SlideElement,
)

# 16:9 Widescreen dimensions
SLIDE_WIDTH_INCHES = 13.333
SLIDE_HEIGHT_INCHES = 7.5

# Theme color palettes: (bg_color, primary_accent, card_bg, text_color, subtext_color)
PALETTES: Dict[str, Tuple[RGBColor, RGBColor, RGBColor, RGBColor, RGBColor]] = {
    "enterprise_blue": (
        RGBColor(245, 247, 250),
        RGBColor(14, 116, 144),   # Cyan 700
        RGBColor(255, 255, 255),
        RGBColor(15, 23, 42),     # Slate 900
        RGBColor(100, 116, 139),  # Slate 500
    ),
    "minimal_dark": (
        RGBColor(15, 23, 42),     # Slate 900
        RGBColor(56, 189, 248),   # Sky 400
        RGBColor(30, 41, 59),     # Slate 800
        RGBColor(248, 250, 252),  # Slate 50
        RGBColor(148, 163, 184),  # Slate 400
    ),
    "creative_gradient": (
        RGBColor(250, 245, 255),  # Purple 50
        RGBColor(147, 51, 234),   # Purple 600
        RGBColor(255, 255, 255),
        RGBColor(24, 24, 27),     # Zinc 900
        RGBColor(113, 113, 122),  # Zinc 500
    ),
    "tech_emerald": (
        RGBColor(240, 253, 244),  # Emerald 50
        RGBColor(5, 150, 105),    # Emerald 600
        RGBColor(255, 255, 255),
        RGBColor(6, 78, 59),      # Emerald 900
        RGBColor(16, 185, 129),   # Emerald 500
    ),
}


def generate_presentation_structure(request: PresentationGenerateRequest) -> List[SlideData]:
    """Build structured slide layout and outline data based on topic and count."""
    topic = request.topic
    slides: List[SlideData] = []

    # 1. Title Hero Slide
    slides.append(
        SlideData(
            slide_number=1,
            title=topic,
            subtitle="企业级全景战略规划与核心业务方案 · Myrm High-Fidelity Presentation",
            layout="title_hero",
            elements=[
                SlideElement(
                    element_type="text",
                    title="核心主旨",
                    body=f"全面解析与拆解 {topic} 的关键路径、架构演进与落地执行策略。",
                )
            ],
            speaker_notes=f"本次演示围绕 {topic} 展开，主要聚焦业务价值和实施路线。",
        )
    )

    # 2. Two Column Comparison Slide
    slides.append(
        SlideData(
            slide_number=2,
            title="行业现状痛点与优化突破路径",
            subtitle="传统粗放模式 VS 现代智能化自动化新范式",
            layout="two_column_comparison",
            elements=[
                SlideElement(
                    element_type="comparison_column",
                    title="传统常规方案 (Legacy)",
                    bullet_points=[
                        "流程冗长繁复，各环节存在信息孤岛与割裂",
                        "手工介入比例高达 70%，容易产生人为失误",
                        "响应周期以天为单位，缺乏端到端可观测性",
                    ],
                ),
                SlideElement(
                    element_type="comparison_column",
                    title="新一代自主 Agent 范式 (Next-Gen)",
                    bullet_points=[
                        "全流程秒级闭环，端到端意图理解与即时响应",
                        "具备自进化与自我修正能力，自动化率达 95%+",
                        "全方位遥测大盘，毫秒级状态与产物双向溯源",
                    ],
                ),
            ],
            speaker_notes="对比传统方案与新方案，重点展示效率提升倍率与可靠性指标。",
        )
    )

    # 3. Three Card Flow Slide
    slides.append(
        SlideData(
            slide_number=3,
            title="核心架构与三大阶段演进里程碑",
            subtitle="从基础底座到集群规模化的标准化落地三步法",
            layout="three_card_flow",
            elements=[
                SlideElement(
                    element_type="card",
                    title="阶段一：底座筑基",
                    body="梳理业务标准资产，完成沙箱环境构建与工具协议标准化接入。",
                    metric_value="Phase 01",
                    metric_label="基础设施",
                ),
                SlideElement(
                    element_type="card",
                    title="阶段二：场景深化",
                    body="在研发协作、办公提效等核心高频场景全面落地多 Agent 矩阵协同。",
                    metric_value="Phase 02",
                    metric_label="核心矩阵",
                ),
                SlideElement(
                    element_type="card",
                    title="阶段三：全局自治",
                    body="形成数据与经验飞轮，实现策略自主迭代与组织级工程效能跃升。",
                    metric_value="Phase 03",
                    metric_label="自主演进",
                ),
            ],
            speaker_notes="强调三阶段渐进式落地，风险可控且每个阶段都有可度量的业务收益。",
        )
    )

    # 4. Concept Illustration Focus (if illustrations enabled)
    if request.enable_illustrations and request.slides_count >= 4:
        slides.append(
            SlideData(
                slide_number=4,
                title="全景生态连接与多模态图解透视",
                subtitle="无缝打通知识库、代码沙箱与外部 MCP 服务网络",
                layout="concept_illustration_focus",
                elements=[
                    SlideElement(
                        element_type="concept_illustration",
                        title="概念架构全景图解",
                        body="以多智能体编排中枢为核心，实时聚合多维办公表格、云端容器与即时通信终端。",
                        illustration_prompt=f"A modern minimalist 3D isometric diagram illustrating intelligent agent workflows for {topic}, hyper-detailed enterprise palette",
                        illustration_url="https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1200&q=80",
                    )
                ],
                speaker_notes="图解页帮助听众建立直观的系统架构心智模型，突出高集成度优势。",
            )
        )

    # 5. Summary & Action Items Slide
    slides.append(
        SlideData(
            slide_number=len(slides) + 1,
            title="总结与后续行动建议",
            subtitle="明确关键行动路线，加速业务价值全面转化",
            layout="summary_action",
            elements=[
                SlideElement(
                    element_type="vector_metrics",
                    title="关键产出预期",
                    bullet_points=[
                        "研发协同周期缩短 60%，沟通对齐摩擦大幅消除",
                        "核心产物具备 100% 格式无损双向追溯与导出能力",
                        "标准资产开箱即用，团队复用率提升 4 倍以上",
                    ],
                )
            ],
            speaker_notes="收尾呼应主旨，给出明确的跟进事项与分工排期。",
        )
    )

    return slides[: request.slides_count]


def render_pptx_binary(slides: List[SlideData], template_style: str, topic: str) -> bytes:
    """Render SlideData list into a compliant, editable binary PowerPoint (.pptx) file."""
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_WIDTH_INCHES)
    prs.slide_height = Inches(SLIDE_HEIGHT_INCHES)

    palette = PALETTES.get(template_style, PALETTES["enterprise_blue"])
    bg_color, primary_accent, card_bg, text_color, subtext_color = palette

    # Use a blank slide layout for precision vector positioning
    blank_layout = prs.slide_layouts[6]

    for slide_data in slides:
        slide = prs.slides.add_slide(blank_layout)

        # 1. Background fill shape
        bg_shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0),
            Inches(0),
            Inches(SLIDE_WIDTH_INCHES),
            Inches(SLIDE_HEIGHT_INCHES),
        )
        bg_shape.fill.solid()
        bg_shape.fill.fore_color.rgb = bg_color
        bg_shape.line.fill.background()

        # 2. Header Title & Subtitle Banner
        title_box = slide.shapes.add_textbox(Inches(1.0), Inches(0.8), Inches(11.333), Inches(1.5))
        tf = title_box.text_frame
        tf.word_wrap = True

        p_title = tf.paragraphs[0]
        p_title.text = slide_data.title
        p_title.font.size = Pt(28)
        p_title.font.bold = True
        p_title.font.color.rgb = text_color

        if slide_data.subtitle:
            p_sub = tf.add_paragraph()
            p_sub.text = slide_data.subtitle
            p_sub.font.size = Pt(14)
            p_sub.font.color.rgb = subtext_color

        # 3. Layout Specific Content Placement
        if slide_data.layout == "title_hero":
            # Center Hero Card
            hero_card = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(1.5),
                Inches(2.8),
                Inches(10.333),
                Inches(3.2),
            )
            hero_card.fill.solid()
            hero_card.fill.fore_color.rgb = card_bg
            hero_card.line.color.rgb = primary_accent
            hero_card.line.width = Pt(1.5)

            ctf = hero_card.text_frame
            ctf.word_wrap = True
            cp1 = ctf.paragraphs[0]
            cp1.text = topic
            cp1.alignment = PP_ALIGN.CENTER
            cp1.font.size = Pt(24)
            cp1.font.bold = True
            cp1.font.color.rgb = primary_accent

            if slide_data.elements:
                cp2 = ctf.add_paragraph()
                cp2.text = slide_data.elements[0].body or ""
                cp2.alignment = PP_ALIGN.CENTER
                cp2.font.size = Pt(14)
                cp2.font.color.rgb = text_color

        elif slide_data.layout == "two_column_comparison":
            col_width = Inches(5.3)
            col_gap = Inches(0.7)
            left_margin = Inches(1.0)
            top_pos = Inches(2.6)
            height = Inches(4.0)

            for idx, elem in enumerate(slide_data.elements[:2]):
                x_pos = left_margin + idx * (col_width + col_gap)
                col_card = slide.shapes.add_shape(
                    MSO_SHAPE.ROUNDED_RECTANGLE,
                    x_pos,
                    top_pos,
                    col_width,
                    height,
                )
                col_card.fill.solid()
                col_card.fill.fore_color.rgb = card_bg
                col_card.line.color.rgb = primary_accent if idx == 1 else subtext_color

                ctf = col_card.text_frame
                ctf.word_wrap = True
                hp = ctf.paragraphs[0]
                hp.text = elem.title or f"Column {idx + 1}"
                hp.font.size = Pt(18)
                hp.font.bold = True
                hp.font.color.rgb = primary_accent if idx == 1 else text_color

                for bullet in elem.bullet_points or []:
                    bp = ctf.add_paragraph()
                    bp.text = f"• {bullet}"
                    bp.font.size = Pt(13)
                    bp.font.color.rgb = text_color

        elif slide_data.layout == "three_card_flow":
            card_width = Inches(3.5)
            card_gap = Inches(0.4)
            left_margin = Inches(1.0)
            top_pos = Inches(2.6)
            height = Inches(4.0)

            for idx, elem in enumerate(slide_data.elements[:3]):
                x_pos = left_margin + idx * (card_width + card_gap)
                f_card = slide.shapes.add_shape(
                    MSO_SHAPE.ROUNDED_RECTANGLE,
                    x_pos,
                    top_pos,
                    card_width,
                    height,
                )
                f_card.fill.solid()
                f_card.fill.fore_color.rgb = card_bg
                f_card.line.color.rgb = primary_accent

                ctf = f_card.text_frame
                ctf.word_wrap = True
                badge_p = ctf.paragraphs[0]
                badge_p.text = elem.metric_value or f"0{idx + 1}"
                badge_p.font.size = Pt(12)
                badge_p.font.bold = True
                badge_p.font.color.rgb = primary_accent

                tp = ctf.add_paragraph()
                tp.text = elem.title or f"Step {idx + 1}"
                tp.font.size = Pt(16)
                tp.font.bold = True
                tp.font.color.rgb = text_color

                bp = ctf.add_paragraph()
                bp.text = elem.body or ""
                bp.font.size = Pt(12)
                bp.font.color.rgb = subtext_color

        else:
            # Default fallback card
            def_card = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(1.0),
                Inches(2.6),
                Inches(11.333),
                Inches(4.0),
            )
            def_card.fill.solid()
            def_card.fill.fore_color.rgb = card_bg
            def_card.line.color.rgb = primary_accent

            ctf = def_card.text_frame
            ctf.word_wrap = True
            for elem in slide_data.elements:
                tp = ctf.add_paragraph()
                tp.text = elem.title or ""
                tp.font.size = Pt(16)
                tp.font.bold = True
                tp.font.color.rgb = primary_accent

                if elem.body:
                    bp = ctf.add_paragraph()
                    bp.text = elem.body
                    bp.font.size = Pt(13)
                    bp.font.color.rgb = text_color

                for bullet in elem.bullet_points or []:
                    blp = ctf.add_paragraph()
                    blp.text = f"• {bullet}"
                    blp.font.size = Pt(12)
                    blp.font.color.rgb = text_color

    # Save to binary in-memory stream
    buffer = io.BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
