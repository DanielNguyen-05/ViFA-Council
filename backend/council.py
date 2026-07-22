from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

from .config import (
    CHAIRMAN_ID,
    COUNCIL_MEMBERS_STAGE1,
    COUNCIL_MEMBERS_STAGE2,
)
from .llm_client import query_model, query_models_parallel
from .prompt import build_chairman_prompt, build_stage1_prompt, build_stage2_prompt
from .schemas import canonical_json, normalize_task_type, validate_candidate
from .synthesis import build_synthesis_plan


class StructuredCouncil:
    """Paper-aligned Council for one structured visual-generation task."""

    def __init__(
        self,
        task_type: str,
        *,
        stage1_models: list[str] | None = None,
        stage2_models: list[str] | None = None,
        chairman_model: str = CHAIRMAN_ID,
    ) -> None:
        self.task_type = normalize_task_type(task_type)
        self.stage1_models = list(stage1_models or COUNCIL_MEMBERS_STAGE1)
        self.stage2_models = list(stage2_models or COUNCIL_MEMBERS_STAGE2)
        self.chairman_model = chairman_model

    async def run_task(
        self,
        user_query: str,
        image_url: Optional[str] = None,
        image_data: Optional[bytes] = None,
        image_mime_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        stage1_results = await self._stage1_collect_responses(
            user_query, image_url, image_data, image_mime_type
        )
        if not stage1_results:
            return {
                "error": "All models failed to respond in Stage 1.",
                "task_type": self.task_type,
                "stage1_results": [],
                "stage2_results": [],
                "final_result": None,
            }

        stage2_results = await self._stage2_complete_responses(
            user_query,
            stage1_results,
            image_url,
            image_data,
            image_mime_type,
        )
        final_result = await self._stage3_evaluate_and_select(
            user_query,
            stage2_results,
            image_url,
            image_data,
            image_mime_type,
            stage1_results=stage1_results,
        )
        return {
            "task_type": self.task_type,
            "stage1_results": stage1_results,
            "stage2_results": stage2_results,
            "final_result": final_result,
        }

    async def _stage1_collect_responses(
        self,
        user_query: str,
        image_url: Optional[str],
        image_data: Optional[bytes],
        image_mime_type: str,
    ) -> list[dict[str, Any]]:
        prompt = build_stage1_prompt(self.task_type, user_query)
        responses = await query_models_parallel(
            self.stage1_models,
            [{"role": "user", "content": prompt}],
            image_data=image_data,
            image_mime_type=image_mime_type,
            image_url=image_url,
        )

        results: list[dict[str, Any]] = []
        for model_id in self.stage1_models:
            response = responses.get(model_id)
            if response is None:
                continue
            raw = str(response.get("content", ""))
            validation = validate_candidate(self.task_type, raw)
            results.append(
                {
                    "model": model_id,
                    "model_used": response.get("model_used"),
                    "provider": response.get("provider"),
                    "attempts": response.get("attempts", 1),
                    "response": raw,
                    "task_type": self.task_type,
                    **validation,
                }
            )
        return results

    async def _stage2_complete_responses(
        self,
        user_query: str,
        stage1_results: list[dict[str, Any]],
        image_url: Optional[str],
        image_data: Optional[bytes],
        image_mime_type: str,
    ) -> list[dict[str, Any]]:
        """Refine every Stage-1 draft with every Stage-2 reviewer in parallel."""

        tasks = []
        provenance: list[dict[str, Any]] = []
        for draft_index, stage1_result in enumerate(stage1_results):
            original_response = stage1_result["response"]
            for reviewer_model in self.stage2_models:
                prompt = build_stage2_prompt(
                    self.task_type, user_query, original_response
                )
                tasks.append(
                    query_model(
                        reviewer_model,
                        [{"role": "user", "content": prompt}],
                        image_url=image_url,
                        image_data=image_data,
                        image_mime_type=image_mime_type,
                    )
                )
                provenance.append(
                    {
                        "source_draft_index": draft_index,
                        "original_model": stage1_result["model"],
                        "stage2_model": reviewer_model,
                        "original_response": original_response,
                    }
                )

        responses = await asyncio.gather(*tasks) if tasks else []
        results: list[dict[str, Any]] = []
        for response, source in zip(responses, provenance):
            attempted_response = (
                str(response.get("content", "")) if response is not None else None
            )
            attempted_validation = (
                validate_candidate(self.task_type, attempted_response)
                if attempted_response is not None
                else None
            )

            fallback_used = response is None or not attempted_validation["schema_valid"]
            if fallback_used:
                perfected_response = source["original_response"]
                validation = validate_candidate(self.task_type, perfected_response)
                error = (
                    "Stage 2 provider call failed; original draft retained."
                    if response is None
                    else "Stage 2 returned schema-invalid JSON; original draft retained."
                )
            else:
                perfected_response = attempted_response
                validation = attempted_validation
                error = None

            result = {
                **source,
                "perfected_response": perfected_response,
                "attempted_response": attempted_response,
                "fallback_used": fallback_used,
                "model_used": response.get("model_used") if response else None,
                "provider": response.get("provider") if response else None,
                "attempts": response.get("attempts") if response else None,
                "task_type": self.task_type,
                **validation,
            }
            if attempted_validation and fallback_used:
                result["attempt_validation_errors"] = attempted_validation[
                    "validation_errors"
                ]
            if error:
                result["error"] = error
            results.append(result)
        return results

    async def _stage3_evaluate_and_select(
        self,
        user_query: str,
        stage2_results: list[dict[str, Any]],
        image_url: Optional[str],
        image_data: Optional[bytes],
        image_mime_type: str,
        *,
        stage1_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        stage1_results = stage1_results or self._recover_stage1(stage2_results)
        candidates = self._build_candidates(stage1_results, stage2_results)
        if not candidates:
            return {
                "error": "No candidates are available for Chairman evaluation.",
                "task_type": self.task_type,
                "candidate_count": 0,
            }

        packet = self._format_candidate_packet(candidates)
        prompt = build_chairman_prompt(self.task_type, user_query, packet)
        response = await query_model(
            self.chairman_model,
            [{"role": "user", "content": prompt}],
            image_url=image_url,
            image_data=image_data,
            image_mime_type=image_mime_type,
        )

        evaluation_text = (
            str(response.get("content", ""))
            if response is not None
            else "Chairman call failed."
        )
        requested_label = self._parse_best_response_selection(evaluation_text)
        selected = next(
            (
                candidate
                for candidate in candidates
                if candidate["label"] == requested_label
            ),
            None,
        )

        fallback_reason: str | None = None
        valid_candidates = [item for item in candidates if item["schema_valid"]]
        if selected is None:
            fallback_reason = "Chairman selection was missing or could not be parsed."
            selected = self._deterministic_fallback(candidates)
        elif not selected["schema_valid"] and valid_candidates:
            fallback_reason = "Chairman selected invalid JSON while valid candidates existed."
            selected = self._deterministic_fallback(candidates)

        selected_config = selected["parsed_response"] if selected["schema_valid"] else None
        selected_response = (
            canonical_json(selected_config) if selected_config else selected["response_text"]
        )
        result = {
            "selected_response": selected_response,
            "selected_config": selected_config,
            "selected_model": selected["source_model"],
            "selected_stage": selected["stage"],
            "selected_label": selected["label"],
            "schema_valid": selected["schema_valid"],
            "validation_errors": selected["validation_errors"],
            "evaluation": evaluation_text,
            "chairman_model": self.chairman_model,
            "chairman_attempts": response.get("attempts") if response else None,
            "candidate_count": len(candidates),
            "task_type": self.task_type,
        }
        if selected_config:
            result["synthesis_plan"] = build_synthesis_plan(
                self.task_type, selected_config
            )
        if fallback_reason:
            result["selection_fallback"] = fallback_reason
        return result

    def _recover_stage1(
        self, stage2_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        recovered: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in stage2_results:
            key = (item["original_model"], item["original_response"])
            if key in seen:
                continue
            seen.add(key)
            validation = validate_candidate(self.task_type, item["original_response"])
            recovered.append(
                {
                    "model": item["original_model"],
                    "response": item["original_response"],
                    **validation,
                }
            )
        return recovered

    def _build_candidates(
        self,
        stage1_results: list[dict[str, Any]],
        stage2_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for draft_index, result in enumerate(stage1_results):
            candidates.append(
                {
                    "stage": "Stage 1 (Draft)",
                    "source_draft_index": draft_index,
                    "source_model": result["model"],
                    "response_text": result["response"],
                    "parsed_response": result.get("parsed_response"),
                    "schema_valid": result.get("schema_valid", False),
                    "validation_errors": result.get("validation_errors", []),
                }
            )
        for result in stage2_results:
            candidates.append(
                {
                    "stage": "Stage 2 (Cross-refined)",
                    "source_draft_index": result["source_draft_index"],
                    "source_model": result["stage2_model"],
                    "response_text": result["perfected_response"],
                    "parsed_response": result.get("parsed_response"),
                    "schema_valid": result.get("schema_valid", False),
                    "validation_errors": result.get("validation_errors", []),
                    "fallback_used": result.get("fallback_used", False),
                }
            )

        for index, candidate in enumerate(candidates):
            candidate["label"] = self._label_for_index(index)
        return candidates

    @staticmethod
    def _format_candidate_packet(candidates: list[dict[str, Any]]) -> str:
        sections = []
        for candidate in candidates:
            if candidate["schema_valid"]:
                validity = "VALIDATED AGAINST TASK SCHEMA"
            else:
                errors = "; ".join(candidate["validation_errors"][:4])
                validity = f"SCHEMA INVALID: {errors}"
            source_note = (
                f"anonymous refinement of Draft {candidate['source_draft_index'] + 1}"
                if candidate["stage"].startswith("Stage 2")
                else f"anonymous Draft {candidate['source_draft_index'] + 1}"
            )
            sections.append(
                f"Response {candidate['label']} [{candidate['stage']}; "
                f"{source_note}; {validity}]\n{candidate['response_text']}"
            )
        return "\n\n" + ("\n\n" + "=" * 24 + "\n\n").join(sections)

    @staticmethod
    def _deterministic_fallback(
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        preference_groups = (
            [
                item
                for item in candidates
                if item["stage"].startswith("Stage 2") and item["schema_valid"]
            ],
            [item for item in candidates if item["schema_valid"]],
            [item for item in candidates if item["stage"].startswith("Stage 2")],
            candidates,
        )
        return next(group[0] for group in preference_groups if group)

    @staticmethod
    def _label_for_index(index: int) -> str:
        if index < 0:
            raise ValueError("Candidate index must be non-negative.")
        label = ""
        value = index + 1
        while value:
            value, remainder = divmod(value - 1, 26)
            label = chr(ord("A") + remainder) + label
        return label

    @staticmethod
    def _parse_best_response_selection(evaluation_text: str) -> str | None:
        match = re.search(
            r"BEST\s+RESPONSE\s*:\s*(?:Response\s+)?([A-Z]+)\b",
            evaluation_text,
            re.IGNORECASE,
        )
        return match.group(1).upper() if match else None
