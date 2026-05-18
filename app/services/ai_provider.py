"""Optional AI grading backends with heuristic fallback."""

import json
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class AIProvider:
    """Unified optional LLM/VLM interface."""

    def __init__(self):
        self.settings = get_settings()
        self.backend = self.settings.effective_ai_backend

    @property
    def available(self) -> bool:
        return self.backend != "none"

    async def grade_answer(
        self,
        question: str,
        rubric_text: str,
        student_answer: str,
        max_marks: float,
    ) -> dict[str, Any] | None:
        if not self.available:
            return None
        prompt = (
            f"Grade this exam answer. Return JSON only: "
            f'{{"marks_awarded": number, "justification": string, "confidence": 0-1}}\n'
            f"Question: {question}\nMax marks: {max_marks}\n"
            f"Rubric/solution: {rubric_text[:2000]}\n"
            f"Student answer (OCR): {student_answer[:2000]}"
        )
        try:
            if self.backend == "openai":
                return await self._openai(prompt, max_marks)
            if self.backend == "gemini":
                return await self._gemini(prompt, max_marks)
            if self.backend == "huggingface":
                return await self._huggingface(prompt, max_marks)
        except Exception as exc:
            logger.warning("AI grading failed (%s): %s", self.backend, exc)
        return None

    async def _openai(self, prompt: str, max_marks: float) -> dict[str, Any] | None:
        key = self.settings.openai_api_key
        if not key:
            return None
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=key)
        resp = await client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {"role": "system", "content": "You are an exam grader. Respond with JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        text = resp.choices[0].message.content or ""
        return self._parse_json(text, max_marks)

    async def _gemini(self, prompt: str, max_marks: float) -> dict[str, Any] | None:
        key = self.settings.gemini_api_key
        if not key:
            return None
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_model}:generateContent?key={key}"
        )
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            resp.raise_for_status()
            data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return self._parse_json(text, max_marks)

    async def _huggingface(self, prompt: str, max_marks: float) -> dict[str, Any] | None:
        key = self.settings.huggingface_api_key
        if not key:
            return None
        url = f"https://api-inference.huggingface.co/models/{self.settings.huggingface_model}"
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                json={"inputs": prompt, "parameters": {"max_new_tokens": 400}},
            )
            resp.raise_for_status()
            data = resp.json()
        text = data[0]["generated_text"] if isinstance(data, list) else str(data)
        return self._parse_json(text, max_marks)

    def _parse_json(self, text: str, max_marks: float) -> dict[str, Any] | None:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(text[start:end])
            marks = float(obj.get("marks_awarded", 0))
            obj["marks_awarded"] = max(0, min(marks, max_marks))
            obj["confidence"] = float(obj.get("confidence", 0.7))
            obj["justification"] = str(obj.get("justification", "AI-assisted grade"))
            return obj
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
