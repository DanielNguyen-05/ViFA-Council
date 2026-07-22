from __future__ import annotations


def outpainting_config(tag: str = "base") -> dict:
    return {
        "task_type": "outpainting",
        "input_image_analysis": {
            "original_style": f"Đông Hồ woodblock style {tag}",
            "painting_school": "dong_ho",
            "dominant_colors": ["earth red", "indigo", "paper white"],
            "subject_elements": ["anthropomorphic mice", "procession"],
            "cultural_symbols": ["ceremonial gifts"],
            "composition": "flat, rhythmic horizontal procession",
        },
        "expansion_settings": {
            "direction": "right",
            "pixel_amount": 512,
            "mask_blur": 16,
            "preserve_original": True,
        },
        "seamless_blending": {
            "style_constraints": ["bold woodblock outlines", "flat perspective"],
            "texture_constraints": ["fibrous giấy điệp texture"],
            "color_constraints": ["limited earthy source palette"],
            "pattern_continuity": ["continue the procession baseline"],
            "forbidden_elements": ["modern text", "curved imperial pagodas"],
        },
        "outpainting_scenarios": [
            {
                "scenario_id": "scenario_01",
                "description": "Continue the rural procession to the right.",
                "prompt": "Extend the procession with source-matched mice and foliage.",
                "negative_prompt": "modern text, photorealism, imperial architecture",
            },
            {
                "scenario_id": "scenario_02",
                "description": "Reveal a restrained village path continuation.",
                "prompt": "Extend the path and native plants in the exact print style.",
                "negative_prompt": "modern signs, gradients, 3D lighting",
            },
        ],
    }


def story_config() -> dict:
    panels = []
    for number in range(1, 5):
        panels.append(
            {
                "panel_number": number,
                "layout": "organic rectangular folk-print panel",
                "scene_description": f"Traditional procession scene {number}",
                "characters_present": ["char_01"],
                "dialogue": [
                    {"character_id": "char_01", "text": f"Lời thoại {number}"}
                ],
                "narration": f"Lời dẫn {number}",
                "traditional_motifs": ["village plants"],
                "transition_to_next": "visual match cut",
                "image_generation_prompt": f"Render traditional panel {number}",
            }
        )
    return {
        "task_type": "story_generation",
        "source_material": {
            "painting_title": "Đám cưới chuột",
            "painting_school": "dong_ho",
            "painting_era": "traditional; exact date uncertain",
            "cultural_context": "Satirical rural procession",
            "symbolic_elements": ["mice", "ceremonial procession"],
        },
        "art_style_preservation": {
            "character_constraints": ["retain source silhouettes"],
            "color_palette": ["earth red", "indigo", "paper white"],
            "line_quality": "bold hand-carved woodblock outlines",
            "perspective": "flat",
            "paper_texture": "fibrous giấy điệp",
            "forbidden_elements": ["modern infographic", "anime"],
        },
        "characters": [
            {
                "character_id": "char_01",
                "name": "Chuột dẫn đoàn",
                "role": "protagonist",
                "appearance": "source-matched anthropomorphic mouse",
                "traditional_costume": "costume visible in source painting",
                "color_scheme": ["earth red", "black"],
                "cultural_significance": "member of the satirical procession",
            }
        ],
        "story_panels": panels,
        "educational_content": {
            "learning_objectives": ["recognize Đông Hồ visual conventions"],
            "cultural_explanations": ["explain the procession's satire"],
            "glossary": [
                {
                    "term": "giấy điệp",
                    "definition": "traditional coated paper",
                    "cultural_context": "used in Đông Hồ prints",
                }
            ],
        },
    }
