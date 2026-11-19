"""LangSmith eval for EventRanker: does the ranker score events the way I would?

Run from backend/:
    python3 -m evals.eval_ranker                 # full eval against the golden dataset
    python3 -m evals.eval_ranker --smoke         # 3 examples, quick wiring check

Design notes (the parts interviewers ask about):
  * Target reuses the REAL production path (EventRanker._rank_batch) — same system
    prompt, model, and JSON plumbing. Never eval a copy of the prompt.
  * References are score BANDS, not exact scores (see golden_dataset.py).
  * Two deterministic evaluators (free, instant) + one LLM-as-judge for the fuzzy
    part. The judge runs on a DIFFERENT, stronger model than the ranker
    (gemini-3.1-pro-preview vs gemini-3-flash-preview) to reduce self-preference bias.
    Same vendor, so some bias remains — override with GEMINI_JUDGE_MODEL.
  * gemini_json_chat retries any 429/5xx with exponential backoff.
"""

import argparse
import json
import os

from langsmith import Client, evaluate

from app.config import settings
from app.llm import gemini_json_chat, get_client
from app.models import Event
from app.ranking.event_ranker import EventRanker
from evals.golden_dataset import GOLDEN_EXAMPLES

DATASET_NAME = "event-ranker-golden"
# Judge on a different model than the ranker (see settings.gemini_model)
# to reduce self-preference bias.
JUDGE_MODEL = os.environ.get("GEMINI_JUDGE_MODEL", "gemini-3.1-pro-preview")


# ── Target: dataset row → real ranker → gradeable dict ───────────────────────

def make_event(title: str, description: str = "", organizer: str = "") -> Event:
    """In-memory Event object (never touches the DB) shaped like production rows."""
    return Event(
        external_id="eval-1",
        source="eval",
        title=title,
        short_description=description,
        organizer_name=organizer,
    )


def target(inputs: dict) -> dict:
    event = make_event(**inputs)
    results = EventRanker()._rank_batch([event])
    if not results:
        return {"score": None, "justification": "", "error": "ranker returned no result"}
    return {
        "score": float(results[0]["score"]),
        "justification": str(results[0].get("justification", "")),
    }


# ── Deterministic evaluators ─────────────────────────────────────────────────

def score_in_band(outputs: dict, reference_outputs: dict) -> dict:
    """Primary metric: did the score land in the hand-labeled band?"""
    score = outputs.get("score")
    if score is None:
        return {"key": "score_in_band", "score": 0}
    ok = reference_outputs["min_score"] <= score <= reference_outputs["max_score"]
    return {"key": "score_in_band", "score": int(ok)}


def band_distance(outputs: dict, reference_outputs: dict) -> dict:
    """Miss magnitude: 0.0 when inside the band, else distance to the nearest edge.
    Separates 'barely missed' from 'wildly wrong' — a mean you can track over time."""
    score = outputs.get("score")
    if score is None:
        return {"key": "band_distance", "score": 10.0}
    lo, hi = reference_outputs["min_score"], reference_outputs["max_score"]
    dist = max(lo - score, 0.0) + max(score - hi, 0.0)
    return {"key": "band_distance", "score": round(dist, 2)}


def justification_format(outputs: dict) -> dict:
    """The prompt demands plain text, max 20 words. Cheap contract check
    (25-word tolerance so we measure drift, not nitpick)."""
    text = outputs.get("justification", "")
    ok = bool(text) and len(text.split()) <= 25 and "```" not in text
    return {"key": "justification_format", "score": int(ok)}


# ── LLM-as-judge evaluator ───────────────────────────────────────────────────

JUDGE_SYSTEM_PROMPT = """You grade the output of an event-relevance ranker.
Given an event (title/description/organizer) and the ranker's score + justification,
answer one question: is the justification GROUNDED — i.e. does it refer to things
actually present in the event text, and is it logically consistent with the score given?

Ungrounded examples: citing speakers/topics the event never mentions, praising
"hands-on agentic content" for a wine-tasting event, or a justification that
contradicts its own score (e.g. "not relevant to AI" with a score of 9).

Return ONLY JSON: {"grounded": true|false, "reason": "<one short sentence>"}"""


def justification_grounded(inputs: dict, outputs: dict) -> dict:
    justification = outputs.get("justification", "")
    if not justification:
        return {"key": "justification_grounded", "score": 0, "comment": "empty justification"}

    client = get_client()
    user_prompt = json.dumps(
        {
            "event": inputs,
            "ranker_score": outputs.get("score"),
            "ranker_justification": justification,
        },
        indent=1,
    )
    try:
        content = gemini_json_chat(
            client,
            model=JUDGE_MODEL,
            system=JUDGE_SYSTEM_PROMPT,
            user=user_prompt,
        )
        verdict = json.loads(content)
        return {
            "key": "justification_grounded",
            "score": int(bool(verdict.get("grounded"))),
            "comment": str(verdict.get("reason", ""))[:200],
        }
    except Exception as exc:  # judge failure shouldn't sink the experiment
        return {"key": "justification_grounded", "score": None, "comment": f"judge error: {exc}"}


# ── Dataset bootstrap + runner ───────────────────────────────────────────────

def ensure_dataset(client: Client) -> None:
    """Create the dataset and upload examples once; later runs reuse it so
    experiments stay comparable against the exact same examples."""
    if client.has_dataset(dataset_name=DATASET_NAME):
        return
    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Hand-labeled score bands for the event relevance ranker "
                    "(13 real events from events.db + 8 adversarial cases).",
    )
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[ex["inputs"] for ex in GOLDEN_EXAMPLES],
        outputs=[ex["outputs"] for ex in GOLDEN_EXAMPLES],
    )
    print(f"Created dataset '{DATASET_NAME}' with {len(GOLDEN_EXAMPLES)} examples")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="run on only 3 examples")
    args = parser.parse_args()

    client = Client()
    ensure_dataset(client)

    data = DATASET_NAME
    if args.smoke:
        examples = list(client.list_examples(dataset_name=DATASET_NAME, limit=3))
        data = examples
    # print(data)

    model_slug = settings.gemini_model.split("/")[-1]
    result = evaluate(
        target,
        data=data,
        evaluators=[score_in_band, band_distance, justification_format, justification_grounded],
        experiment_prefix=f"ranker-{model_slug}",
        max_concurrency=4,
        metadata={"ranker_model": settings.gemini_model, "judge_model": JUDGE_MODEL},
    )
    print(f"\nExperiment: {result.experiment_name}")


if __name__ == "__main__":
    main()
