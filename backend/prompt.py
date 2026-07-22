from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .schemas import normalize_task_type


OUTPAINTING_TEMPLATE: dict[str, Any] = {
    "task_type": "outpainting",
    "input_image_analysis": {
        "original_style": "",
        "painting_school": "dong_ho|hang_trong|kim_hoang|other",
        "dominant_colors": [],
        "subject_elements": [],
        "cultural_symbols": [],
        "composition": "",
    },
    "expansion_settings": {
        "direction": "",
        "pixel_amount": 512,
        "mask_blur": 16,
        "preserve_original": True,
    },
    "seamless_blending": {
        "style_constraints": [],
        "texture_constraints": [],
        "color_constraints": [],
        "pattern_continuity": [],
        "forbidden_elements": [
            "modern typography or labels",
            "generic Sino-centric imperial motifs",
            "photorealism or 3D rendering",
        ],
    },
    "outpainting_scenarios": [
        {
            "scenario_id": "scenario_01",
            "description": "",
            "prompt": "",
            "negative_prompt": "",
        },
        {
            "scenario_id": "scenario_02",
            "description": "",
            "prompt": "",
            "negative_prompt": "",
        },
    ],
}


def _panel_template(panel_number: int) -> dict[str, Any]:
    return {
        "panel_number": panel_number,
        "layout": "",
        "scene_description": "",
        "characters_present": [],
        "dialogue": [{"character_id": "", "text": ""}],
        "narration": "",
        "traditional_motifs": [],
        "transition_to_next": "",
        "image_generation_prompt": "",
    }


STORY_TEMPLATE: dict[str, Any] = {
    "task_type": "story_generation",
    "source_material": {
        "painting_title": "",
        "painting_school": "dong_ho|hang_trong|kim_hoang|other",
        "painting_era": "",
        "cultural_context": "",
        "symbolic_elements": [],
    },
    "art_style_preservation": {
        "character_constraints": [],
        "color_palette": [],
        "line_quality": "",
        "perspective": "",
        "paper_texture": "",
        "forbidden_elements": [
            "modern infographic layout",
            "rigid typographic headers",
            "manga, anime, photorealism, or 3D rendering",
            "generic Sino-centric imperial motifs",
        ],
    },
    "characters": [
        {
            "character_id": "char_01",
            "name": "",
            "role": "",
            "appearance": "",
            "traditional_costume": "",
            "color_scheme": [],
            "cultural_significance": "",
        }
    ],
    "story_panels": [_panel_template(number) for number in range(1, 5)],
    "educational_content": {
        "learning_objectives": [],
        "cultural_explanations": [],
        "glossary": [
            {"term": "", "definition": "", "cultural_context": ""}
        ],
    },
}

TASK_TEMPLATES = {
    "outpainting": OUTPAINTING_TEMPLATE,
    "story_generation": STORY_TEMPLATE,
}

TASK_NAMES = {
    "outpainting": "Vietnamese folk-painting outpainting",
    "story_generation": "Vietnamese folk-art educational story generation",
}


def task_template(task_type: str) -> dict[str, Any]:
    return deepcopy(TASK_TEMPLATES[normalize_task_type(task_type)])


def build_stage1_prompt(task_type: str, user_query: str) -> str:
    task_type = normalize_task_type(task_type)
    template = json.dumps(task_template(task_type), indent=2, ensure_ascii=False)
    panel_instruction = (
        "Create 4 to 6 sequential panels as requested by the directive."
        if task_type == "story_generation"
        else "Create at least two genuinely different outpainting scenarios."
    )
    return f"""You are an expert curator of traditional Vietnamese folk art.
Analyze the attached source painting and complete a structured configuration for
{TASK_NAMES[task_type]}.

USER DIRECTIVE (obey its direction, size, subject, panel count, and language):
{user_query}

Requirements:
- Ground every claim in visible evidence from the source image; do not invent a
  painting school or historical title when uncertain. State uncertainty plainly.
- Preserve the source painting's silhouettes, flat perspective, line quality,
  traditional palette, motifs, and handmade paper texture.
- Do not inject modern text, modern clothing, photorealism, generic East Asian
  imperial imagery, or a modern infographic layout unless the source contains it.
- {panel_instruction}
- Fill every required field with concrete, synthesis-ready values.
- Return exactly one valid JSON object. Do not use Markdown fences or commentary.

Required shape:
{template}
"""


def build_stage2_prompt(
    task_type: str, user_query: str, original_response: str
) -> str:
    task_type = normalize_task_type(task_type)
    template = json.dumps(task_template(task_type), indent=2, ensure_ascii=False)
    return f"""You are a second, independent Vietnamese folk-art curator.
Review the attached source image and refine the anonymous draft below for
{TASK_NAMES[task_type]}.

USER DIRECTIVE:
{user_query}

ANONYMOUS STAGE-1 DRAFT:
{original_response}

Refinement duties:
1. Correct the draft into strictly valid JSON matching the required shape.
2. Check every setting, panel, character, and prompt against the user directive.
3. Improve cultural fidelity and explicitly preserve source-specific palette,
   outlines, perspective, motifs, and paper texture.
4. Remove modern typography, modern infographic structure, photorealism, and
   generic Sino-centric motifs not supported by the source image.
5. Keep useful details; a longer answer is not automatically a better answer.

Return exactly one improved JSON object in this shape, without Markdown or prose:
{template}
"""


def build_chairman_prompt(
    task_type: str, user_query: str, candidates_text: str
) -> str:
    task_type = normalize_task_type(task_type)
    return f"""You are the isolated Chairman of ViFA-Council. Select exactly one
anonymous candidate for {TASK_NAMES[task_type]} using the attached source image.

USER DIRECTIVE:
{user_query}

ANONYMOUS CANDIDATES:
{candidates_text}

Evaluate each candidate on the four paper-defined criteria:
1. JSON structural validity and schema completeness.
2. Logical coherence of spatial settings or narrative parameters.
3. Fidelity to the visible Vietnamese folk-art style and cultural conventions.
4. Whether a Stage-2 refinement improves its source draft without cultural or
   structural drift.

Reject unsupported modern typography, infographic layouts, photorealism,
flattened traditional texture/palette, and generic Sino-centric imperial motifs.
Never select a schema-invalid candidate when at least one valid candidate exists.
Briefly justify the comparison. End with exactly this line:
BEST RESPONSE: Response X
where X is one candidate label from the packet.
"""


# Compatibility wrappers retained for existing scripts.
def outpainting_prompt_stage1(user_query: str = "Expand the painting") -> str:
    return build_stage1_prompt("outpainting", user_query)


def outpainting_prompt_stage2(
    original_model: str, original_response: str, user_query: str = "Expand the painting"
) -> str:
    del original_model
    return build_stage2_prompt("outpainting", user_query, original_response)


def outpainting_prompt_stage3(
    responses_text: str, user_query: str = "Expand the painting"
) -> str:
    return build_chairman_prompt("outpainting", user_query, responses_text)


def storyGeneration_prompt_stage1(
    user_query: str = "Create a four-panel educational story"
) -> str:
    return build_stage1_prompt("story_generation", user_query)


def storyGeneration_prompt_stage2(
    original_response: str,
    user_query: str = "Create a four-panel educational story",
) -> str:
    return build_stage2_prompt("story_generation", user_query, original_response)


def storyGeneration_prompt_stage3(
    responses_text: str,
    user_query: str = "Create a four-panel educational story",
) -> str:
    return build_chairman_prompt("story_generation", user_query, responses_text)


def generate_outpainting() -> str:
    return """Use the attached source image and validated outpainting JSON. Preserve
the original pixels and seamlessly extend only the requested region. Apply every
style, texture, color, pattern-continuity, and negative constraint."""


def generate_story() -> str:
    return """Use the attached source image and validated story JSON. Render panels
sequentially while holding character identity, folk-art palette, line quality,
flat perspective, motifs, and paper texture constant across the story."""
