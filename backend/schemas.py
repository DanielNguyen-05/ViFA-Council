from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


NonEmptyString = Annotated[str, Field(min_length=1)]


class ViFABaseModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)


class InputImageAnalysis(ViFABaseModel):
    original_style: NonEmptyString
    painting_school: NonEmptyString
    dominant_colors: Annotated[list[NonEmptyString], Field(min_length=1)]
    subject_elements: Annotated[list[NonEmptyString], Field(min_length=1)]
    cultural_symbols: list[NonEmptyString]
    composition: NonEmptyString


class ExpansionSettings(ViFABaseModel):
    direction: NonEmptyString
    pixel_amount: Annotated[int, Field(gt=0)]
    mask_blur: Annotated[int, Field(ge=0)]
    preserve_original: bool = True


class SeamlessBlending(ViFABaseModel):
    style_constraints: Annotated[list[NonEmptyString], Field(min_length=1)]
    texture_constraints: Annotated[list[NonEmptyString], Field(min_length=1)]
    color_constraints: Annotated[list[NonEmptyString], Field(min_length=1)]
    pattern_continuity: Annotated[list[NonEmptyString], Field(min_length=1)]
    forbidden_elements: Annotated[list[NonEmptyString], Field(min_length=1)]


class OutpaintingScenario(ViFABaseModel):
    scenario_id: NonEmptyString
    description: NonEmptyString
    prompt: NonEmptyString
    negative_prompt: NonEmptyString


class OutpaintingConfig(ViFABaseModel):
    task_type: Literal["outpainting"]
    input_image_analysis: InputImageAnalysis
    expansion_settings: ExpansionSettings
    seamless_blending: SeamlessBlending
    outpainting_scenarios: Annotated[
        list[OutpaintingScenario], Field(min_length=2)
    ]

    @model_validator(mode="after")
    def unique_scenario_ids(self):
        scenario_ids = [item.scenario_id for item in self.outpainting_scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("outpainting_scenarios must use unique scenario_id values")
        return self


class SourceMaterial(ViFABaseModel):
    painting_title: NonEmptyString
    painting_school: NonEmptyString
    painting_era: NonEmptyString
    cultural_context: NonEmptyString
    symbolic_elements: Annotated[list[NonEmptyString], Field(min_length=1)]


class ArtStylePreservation(ViFABaseModel):
    character_constraints: Annotated[list[NonEmptyString], Field(min_length=1)]
    color_palette: Annotated[list[NonEmptyString], Field(min_length=1)]
    line_quality: NonEmptyString
    perspective: NonEmptyString
    paper_texture: NonEmptyString
    forbidden_elements: Annotated[list[NonEmptyString], Field(min_length=1)]


class StoryCharacter(ViFABaseModel):
    character_id: NonEmptyString
    name: NonEmptyString
    role: NonEmptyString
    appearance: NonEmptyString
    traditional_costume: NonEmptyString
    color_scheme: Annotated[list[NonEmptyString], Field(min_length=1)]
    cultural_significance: NonEmptyString


class DialogueLine(ViFABaseModel):
    character_id: NonEmptyString
    text: NonEmptyString


class StoryPanel(ViFABaseModel):
    panel_number: Annotated[int, Field(gt=0)]
    layout: NonEmptyString
    scene_description: NonEmptyString
    characters_present: list[NonEmptyString]
    dialogue: list[DialogueLine]
    narration: NonEmptyString
    traditional_motifs: list[NonEmptyString]
    transition_to_next: NonEmptyString
    image_generation_prompt: NonEmptyString


class GlossaryEntry(ViFABaseModel):
    term: NonEmptyString
    definition: NonEmptyString
    cultural_context: NonEmptyString


class EducationalContent(ViFABaseModel):
    learning_objectives: Annotated[list[NonEmptyString], Field(min_length=1)]
    cultural_explanations: Annotated[list[NonEmptyString], Field(min_length=1)]
    glossary: list[GlossaryEntry]


class StoryGenerationConfig(ViFABaseModel):
    task_type: Literal["story_generation"]
    source_material: SourceMaterial
    art_style_preservation: ArtStylePreservation
    characters: Annotated[list[StoryCharacter], Field(min_length=1)]
    story_panels: Annotated[list[StoryPanel], Field(min_length=4, max_length=6)]
    educational_content: EducationalContent

    @model_validator(mode="after")
    def validate_story_continuity(self):
        character_ids = [item.character_id for item in self.characters]
        if len(character_ids) != len(set(character_ids)):
            raise ValueError("characters must use unique character_id values")

        panel_numbers = [panel.panel_number for panel in self.story_panels]
        if panel_numbers != list(range(1, len(panel_numbers) + 1)):
            raise ValueError("story_panels must be ordered and numbered consecutively from 1")

        known_ids = set(character_ids)
        for panel in self.story_panels:
            unknown_present = set(panel.characters_present) - known_ids
            unknown_dialogue = {
                line.character_id for line in panel.dialogue
            } - known_ids - {"narrator"}
            unknown = unknown_present | unknown_dialogue
            if unknown:
                raise ValueError(
                    "story_panels reference unknown character IDs: "
                    + ", ".join(sorted(unknown))
                )
        return self


TASK_MODELS: dict[str, type[ViFABaseModel]] = {
    "outpainting": OutpaintingConfig,
    "story_generation": StoryGenerationConfig,
}

TASK_ALIASES = {
    "outpainting": "outpainting",
    "outpaint": "outpainting",
    "story": "story_generation",
    "story_generation": "story_generation",
    "storygeneration": "story_generation",
    "comic": "story_generation",
}


class CandidateJSONError(ValueError):
    """Raised when a provider response contains no decodable JSON object."""


def normalize_task_type(task_type: str) -> str:
    normalized = re.sub(r"[\s-]+", "_", task_type.strip().lower())
    try:
        return TASK_ALIASES[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(TASK_MODELS))
        raise ValueError(
            f"Unsupported task type '{task_type}'. Expected one of: {supported}."
        ) from exc


def extract_json_object(raw_response: str | Mapping[str, Any]) -> dict[str, Any]:
    """Extract the first valid JSON object from a provider response."""

    if isinstance(raw_response, Mapping):
        return dict(raw_response)
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise CandidateJSONError("Response is empty or is not text.")

    text = raw_response.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.I)
    if fenced:
        text = fenced.group(1).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            parsed, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise CandidateJSONError("Response does not contain a valid JSON object.")


def _format_validation_error(error: dict[str, Any]) -> str:
    location = ".".join(str(part) for part in error.get("loc", ())) or "root"
    return f"{location}: {error.get('msg', 'invalid value')}"


def validate_candidate(
    task_type: str, raw_response: str | Mapping[str, Any]
) -> dict[str, Any]:
    """Parse and validate a raw LLM candidate without raising to callers."""

    task_type = normalize_task_type(task_type)
    try:
        parsed = extract_json_object(raw_response)
    except CandidateJSONError as exc:
        return {
            "parsed_response": None,
            "schema_valid": False,
            "validation_errors": [str(exc)],
        }

    candidate_task = parsed.get("task_type")
    if isinstance(candidate_task, str):
        try:
            parsed["task_type"] = normalize_task_type(candidate_task)
        except ValueError:
            pass

    model = TASK_MODELS[task_type]
    try:
        validated = model.model_validate(parsed)
    except ValidationError as exc:
        return {
            "parsed_response": parsed,
            "schema_valid": False,
            "validation_errors": [
                _format_validation_error(error) for error in exc.errors()
            ],
        }

    return {
        "parsed_response": validated.model_dump(mode="json"),
        "schema_valid": True,
        "validation_errors": [],
    }


def canonical_json(value: Mapping[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, indent=2, ensure_ascii=False)


def json_schema_for_task(task_type: str) -> dict[str, Any]:
    task_type = normalize_task_type(task_type)
    return TASK_MODELS[task_type].model_json_schema()
