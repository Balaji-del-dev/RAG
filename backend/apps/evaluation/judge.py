"""DeepEval with the local Ollama model as judge (same model across compared runs; calibrate against people)."""

import json
import re

from deepeval.models import DeepEvalBaseLLM

from apps.core.clients import llm

JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class LocalJudge(DeepEvalBaseLLM):
    def __init__(self, model_name: str, timeout: int = 240):
        self.model_name = model_name
        self.timeout = timeout
        super().__init__(model=model_name)

    def load_model(self):
        return self.model_name

    def get_model_name(self) -> str:
        return f"local:{self.model_name}"

    def generate(self, prompt: str, schema=None):
        text = llm.complete(
            self.model_name,
            prompt + ("\n\nReply with JSON only." if schema else ""),
            temperature=0.0,
            max_tokens=700,
            timeout=self.timeout,
        )
        if schema is None:
            return text
        match = JSON_OBJECT.search(text)
        data = json.loads(match.group(0) if match else text)
        return schema.model_validate(data)

    async def a_generate(self, prompt: str, schema=None):
        import asyncio

        return await asyncio.to_thread(self.generate, prompt, schema)


def judge_answer(model_name: str, question: str, answer: str, contexts: list[str]) -> dict[str, tuple[float, dict]]:
    """faithfulness and answer_relevancy, each (score, details). A metric that errors is left out."""
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
    from deepeval.test_case import LLMTestCase

    judge = LocalJudge(model_name)
    case = LLMTestCase(input=question, actual_output=answer, retrieval_context=contexts)
    results: dict[str, tuple[float, dict]] = {}
    for name, metric in (
        ("faithfulness", FaithfulnessMetric(model=judge, include_reason=True, async_mode=False)),
        ("answer_relevancy", AnswerRelevancyMetric(model=judge, include_reason=True, async_mode=False)),
    ):
        try:
            metric.measure(case)
            results[name] = (float(metric.score or 0.0), {"reason": metric.reason, "judge": judge.get_model_name()})
        except Exception as exc:  # a noisy small judge can return unusable JSON
            results[f"{name}_error"] = (0.0, {"error": f"{type(exc).__name__}: {exc}"[:500]})
    return results
