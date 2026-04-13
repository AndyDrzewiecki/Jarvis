from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class DecisionGrader:
    """Grades decisions using LLM analysis of outcomes.

    Short-term grading: Was this decision immediately useful?
    Signals: outcome field, adapter success, response quality.
    """

    def grade_short_term(self, decision: dict) -> dict:
        """Grade a single decision. Returns dict with grade/score/reason."""
        outcome = decision.get("outcome", "unknown")
        capability = decision.get("capability", "")
        decision_text = decision.get("decision", "")
        reasoning = decision.get("reasoning", "")

        prompt = (
            "You are grading an AI agent decision for quality.\n\n"
            f"Decision: {decision_text[:300]}\n"
            f"Outcome: {outcome}\n"
            f"Capability: {capability}\n"
            f"Reasoning: {reasoning[:300]}\n\n"
            "Grade this decision:\n"
            "- 'good' (score 0.8-1.0): successful, useful, well-reasoned\n"
            "- 'neutral' (score 0.4-0.7): partial success or unclear outcome\n"
            "- 'poor' (score 0.0-0.3): failed, unhelpful, or harmful\n\n"
            "Respond in this exact format:\n"
            "GRADE: good|neutral|poor\n"
            "SCORE: 0.0-1.0\n"
            "REASON: one sentence\n"
        )

        try:
            from jarvis.core import _ask_ollama, FALLBACK_MODEL
            raw = _ask_ollama(prompt, model=FALLBACK_MODEL)
            return self._parse_grade_response(raw, decision.get("id", ""))
        except Exception as exc:
            logger.warning("grade_short_term LLM call failed: %s", exc)
            # Fallback: use outcome field directly
            if outcome == "success":
                return {"grade": "good", "score": 0.7, "reason": "Outcome was success (fallback grade)"}
            elif outcome == "failure":
                return {"grade": "poor", "score": 0.2, "reason": "Outcome was failure (fallback grade)"}
            return {"grade": "neutral", "score": 0.5, "reason": "Unknown outcome (fallback grade)"}

    def _parse_grade_response(self, raw: str, decision_id: str) -> dict:
        """Parse LLM grade response into structured dict."""
        grade = "neutral"
        score = 0.5
        reason = "No reason provided"

        for line in raw.strip().splitlines():
            line = line.strip()
            if line.startswith("GRADE:"):
                val = line[6:].strip().lower()
                if val in ("good", "neutral", "poor"):
                    grade = val
            elif line.startswith("SCORE:"):
                try:
                    score = float(line[6:].strip())
                    score = max(0.0, min(1.0, score))
                except ValueError:
                    pass
            elif line.startswith("REASON:"):
                reason = line[7:].strip()

        return {"grade": grade, "score": score, "reason": reason}

    def grade_long_term(self, decision: dict, grade: dict) -> dict:
        """Re-grade a decision 7-30 days later with hindsight.

        LLM prompt includes original decision, original short-term grade, elapsed time.
        Returns {"grade": "good"|"neutral"|"poor", "score": float, "reason": str}.
        Falls back to {"grade": "neutral", "score": 0.5, "reason": "LLM unavailable"} on error.
        """
        decision_text = decision.get("decision", "")
        capability = decision.get("capability", "")
        outcome = decision.get("outcome", "unknown")
        reasoning = decision.get("reasoning", "")
        st_grade = grade.get("short_term_grade", "unknown")
        st_score = grade.get("short_term_score", 0.5)
        st_reason = grade.get("short_term_reason", "")
        timestamp = decision.get("timestamp", "")

        prompt = (
            "You are re-evaluating an AI agent decision with the benefit of hindsight.\n\n"
            f"Original decision: {decision_text[:300]}\n"
            f"Capability: {capability}\n"
            f"Outcome: {outcome}\n"
            f"Reasoning: {reasoning[:300]}\n"
            f"Decision made at: {timestamp}\n\n"
            f"Short-term grade (given shortly after): {st_grade} (score={st_score})\n"
            f"Short-term reason: {st_reason}\n\n"
            "Now re-grade this decision with hindsight (7-30 days later):\n"
            "- 'good' (score 0.8-1.0): held up well over time\n"
            "- 'neutral' (score 0.4-0.7): mixed results over time\n"
            "- 'poor' (score 0.0-0.3): did not age well or caused problems\n\n"
            "Respond in this exact format:\n"
            "GRADE: good|neutral|poor\n"
            "SCORE: 0.0-1.0\n"
            "REASON: one sentence\n"
        )

        try:
            from jarvis.core import _ask_ollama, FALLBACK_MODEL
            raw = _ask_ollama(prompt, model=FALLBACK_MODEL)
            return self._parse_grade_response(raw, decision.get("id", ""))
        except Exception as exc:
            logger.warning("grade_long_term LLM call failed: %s", exc)
            return {"grade": "neutral", "score": 0.5, "reason": "LLM unavailable"}

    def run_long_term_batch(self) -> int:
        """Re-grade decisions from 7-30 days ago. Returns count graded."""
        from jarvis.agent_memory import get_decisions_for_long_term_grading, update_long_term_grade
        pairs = get_decisions_for_long_term_grading()
        count = 0
        for decision, grade in pairs:
            try:
                result = self.grade_long_term(decision, grade)
                update_long_term_grade(
                    decision["id"],
                    result["grade"],
                    result["score"],
                    result["reason"],
                    model=result.get("model", ""),
                )
                count += 1
            except Exception as exc:
                logger.warning("Long-term grading failed for %s: %s", decision.get("id"), exc)
        return count

    def run_short_term_batch(self) -> int:
        """Grade all ungraded decisions from the last 24h. Returns count graded."""
        import jarvis.agent_memory as am
        decisions = am.get_ungraded_decisions(since_hours=24)
        graded = 0
        for decision in decisions:
            try:
                result = self.grade_short_term(decision)
                from jarvis import config
                am.save_grade(
                    decision_id=decision["id"],
                    short_term_grade=result["grade"],
                    short_term_score=result["score"],
                    short_term_reason=result["reason"],
                    model=config.FALLBACK_MODEL,
                )
                graded += 1
            except Exception as exc:
                logger.warning("Failed to grade decision %s: %s", decision.get("id"), exc)
        logger.info("Short-term grading batch: graded %d/%d decisions", graded, len(decisions))
        return graded
