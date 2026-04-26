import json
import logging
import re

import anthropic
from dotenv import load_dotenv

load_dotenv()  # loads ANTHROPIC_API_KEY from .env if present

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {"relevante", "potencialmente_relevante", "no_relevante"}


class ClaudeEvaluator:
    """
    Evaluates paper abstracts against a research context using Claude.

    Prompt caching strategy: the system prompt (which embeds the research
    context) is marked cache_control=ephemeral. All papers in the same
    batch share the same context, so after the first call the prefix is
    served from cache (~0.1x cost vs full input price).
    """

    def __init__(self, model: str, max_tokens: int = 400):
        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens
        self._cached_context: str | None = None
        self._system_blocks: list | None = None

    def _build_system(self, context: str) -> list:
        """Build the system-prompt blocks with cache_control so the context prefix is cached across calls."""
        return [
            {
                "type": "text",
                "text": (
                    "You are a scientific literature evaluator for a research project.\n\n"
                    f"Research context:\n{context}\n\n"
                    "Classify each paper as exactly one of:\n"
                    '- "relevante": directly addresses the research context or is closely related\n'
                    '- "potencialmente_relevante": tangentially related or useful as background/methodology\n'
                    '- "no_relevante": not related to the research context\n\n'
                    "Respond ONLY with valid JSON, no additional text:\n"
                    '{"category": "<category>", "reasoning": "<2-3 sentence explanation>"}'
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _ensure_system(self, context: str) -> None:
        """Rebuild system blocks only when the context changes (avoids redundant string construction)."""
        if self._cached_context != context:
            self._cached_context = context
            self._system_blocks = self._build_system(context)

    def _parse_response(self, raw: str) -> dict:
        """
        Parse Claude's JSON response defensively.

        Claude occasionally wraps the JSON in prose or adds a trailing period.
        The regex fallback extracts the first JSON object if strict parsing fails,
        rather than crashing the whole batch.
        """
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*?\}", raw, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group())
                except json.JSONDecodeError:
                    return {"category": "no_relevante", "reasoning": f"Parse error: {raw[:120]}"}
            else:
                return {"category": "no_relevante", "reasoning": f"Parse error: {raw[:120]}"}

        if result.get("category") not in _VALID_CATEGORIES:
            result["category"] = "no_relevante"
        return result

    def evaluate(self, paper: dict, context: str) -> dict:
        """Send one paper to Claude and return the paper dict enriched with an 'evaluation' key."""
        self._ensure_system(context)

        user_msg = (
            f"Title: {paper.get('title') or 'Unknown'}\n"
            f"Year: {paper.get('year', 'Unknown')} | Citations: {paper.get('citationCount', 'Unknown')}\n"
            f"Abstract: {paper.get('abstract') or ''}"
        )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system_blocks,
            messages=[{"role": "user", "content": user_msg}],
        )

        evaluation = self._parse_response(response.content[0].text.strip())
        return {**paper, "evaluation": evaluation}

    def evaluate_batch(self, papers: list[dict], context: str) -> list[dict]:
        results = []
        n = len(papers)
        for i, paper in enumerate(papers, 1):
            title_preview = (paper.get("title") or "")[:55]
            logger.info(f"[{i}/{n}] Evaluating: {title_preview}")
            try:
                results.append(self.evaluate(paper, context))
            except anthropic.RateLimitError:
                logger.warning("Rate limit hit, retrying in 60s...")
                import time; time.sleep(60)
                results.append(self.evaluate(paper, context))
            except Exception as exc:
                logger.error(f"Error evaluating paper: {exc}")
                results.append({**paper, "evaluation": {"category": "error", "reasoning": str(exc)}})
        return results
