from __future__ import annotations

from typing import Any, Mapping

from .config import IMAGE_MODEL
from .prompt import generate_outpainting, generate_story
from .schemas import normalize_task_type, validate_candidate


class InvalidSynthesisConfig(ValueError):
    pass


def build_synthesis_plan(
    task_type: str,
    config: Mapping[str, Any],
    *,
    scenario_id: str | None = None,
) -> dict[str, Any]:
    """Translate validated Council JSON into deterministic image-generation steps."""

    task_type = normalize_task_type(task_type)
    validation = validate_candidate(task_type, config)
    if not validation["schema_valid"]:
        errors = "; ".join(validation["validation_errors"])
        raise InvalidSynthesisConfig(f"Synthesis configuration is invalid: {errors}")
    normalized = validation["parsed_response"]

    if task_type == "outpainting":
        return _build_outpainting_plan(normalized, scenario_id=scenario_id)
    return _build_story_plan(normalized)


def _build_outpainting_plan(
    config: dict[str, Any], *, scenario_id: str | None
) -> dict[str, Any]:
    scenarios = config["outpainting_scenarios"]
    selected = next(
        (
            scenario
            for scenario in scenarios
            if scenario_id and scenario["scenario_id"] == scenario_id
        ),
        scenarios[0],
    )
    blending = config["seamless_blending"]
    constraint_text = "; ".join(
        blending["style_constraints"]
        + blending["texture_constraints"]
        + blending["color_constraints"]
        + blending["pattern_continuity"]
    )
    negative_text = "; ".join(
        blending["forbidden_elements"] + [selected["negative_prompt"]]
    )
    return {
        "task_type": "outpainting",
        "backend_model": IMAGE_MODEL,
        "source_image_required": True,
        "execution": "single_image_edit",
        "selected_scenario_id": selected["scenario_id"],
        "expansion_settings": config["expansion_settings"],
        "steps": [
            {
                "step": 1,
                "prompt": (
                    f"{generate_outpainting()}\n\nScenario: {selected['prompt']}\n\n"
                    f"Continuity constraints: {constraint_text}"
                ),
                "negative_prompt": negative_text,
            }
        ],
    }


def _build_story_plan(config: dict[str, Any]) -> dict[str, Any]:
    preservation = config["art_style_preservation"]
    characters = config["characters"]
    shared_context = {
        "art_style_preservation": preservation,
        "characters": characters,
        "source_material": config["source_material"],
    }
    steps = []
    for panel in sorted(config["story_panels"], key=lambda item: item["panel_number"]):
        steps.append(
            {
                "step": panel["panel_number"],
                "execution": "sequential_image_generation",
                "prompt": (
                    f"{generate_story()}\n\nPanel scene: {panel['image_generation_prompt']}\n"
                    f"Narration: {panel['narration']}"
                ),
                "panel": panel,
                "shared_identity_context": shared_context,
                "condition_on_previous_panel": panel["panel_number"] > 1,
            }
        )
    return {
        "task_type": "story_generation",
        "backend_model": IMAGE_MODEL,
        "source_image_required": True,
        "execution": "sequential_panels",
        "steps": steps,
        "educational_content": config["educational_content"],
    }
