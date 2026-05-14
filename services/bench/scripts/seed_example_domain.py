"""
Seed an example domain into a running BenchAnything API server.

Usage:
    python scripts/seed_example_domain.py [--api-url http://localhost:8000]
"""

import argparse
import sys

import httpx

API_URL = "http://localhost:8000"

DOMAIN_PAYLOAD = {
    "id": "trivia-challenge-v1",
    "name": "Trivia Challenge",
    "owner_id": "benchanything-team",
    "detail": (
        "A curated multi-category trivia benchmark designed to probe general-knowledge "
        "recall across 12 domains including Science, History, Geography, Arts & Culture, "
        "Sports, and Technology. Episodes present a sequence of questions; agents earn "
        "reward for correct answers and must handle ambiguous phrasings gracefully. "
        "Ideal for evaluating factual grounding, instruction following, and calibration."
    ),
    "pricing": "free",
    "tags": ["NLP", "Knowledge", "Multi-Category", "RLVR", "Tier 1"],
    "has_gold_benchmark": True,
    "version_history": [
        {
            "version": "1.0.0",
            "date": "2026-01-15",
            "changes": "Initial release with 1,000 hand-verified questions across 12 categories.",
        },
        {
            "version": "1.1.0",
            "date": "2026-02-28",
            "changes": "Added 400 STEM questions; corrected 23 ambiguous phrasings flagged in community review.",
        },
        {
            "version": "1.2.0",
            "date": "2026-04-01",
            "changes": (
                "Upgraded scoring to use partial-credit rubric for multi-part answers. "
                "Binding Vow bumped to v1.2.0."
            ),
        },
    ],
    "binding_vow": {
        "id": "trivia-challenge-vow",
        "version": "1.2.0",
        "domain_id": "trivia-challenge-v1",
        "tier": "tier1",
        "description": (
            "Text-in / text-out trivia Q&A. Observation is a question string; "
            "action is a free-text answer. Reward is 1.0 for correct, 0.0 otherwise."
        ),
        "observation_space": {
            "type": "text",
            "description": "A natural-language trivia question.",
        },
        "action_space": {
            "type": "text",
            "description": "The agent's free-text answer.",
        },
        "reward": {
            "type": "binary",
            "range": {"min": 0.0, "max": 1.0},
            "description": "1.0 for a correct answer, 0.0 otherwise.",
        },
        "episode": {
            "max_steps": 20,
            "deterministic_reset": True,
            "supports_seed": True,
            "observability": "full",
        },
        "techniques": [],
        "metadata": {"num_questions": 1400, "categories": 12},
    },
    "endpoint": {
        "mode": "remote",
        "url": "http://localhost:8765",
    },
    "scoring": {
        "primary_metric": "accuracy",
        "higher_is_better": True,
        "metrics": [
            {
                "name": "accuracy",
                "type": "episode_reward",
                "aggregation": "mean",
            }
        ],
    },
}


def seed(api_url: str) -> None:
    base = api_url.rstrip("/")
    domain_id = DOMAIN_PAYLOAD["id"]

    with httpx.Client(base_url=base, timeout=30) as client:
        # 1. Create or update
        r = client.post("/v1/domains", json=DOMAIN_PAYLOAD)
        if r.status_code == 409:
            print(f"Domain '{domain_id}' already exists — checking status…")
            existing = client.get(f"/v1/domains/{domain_id}").json()
            if existing.get("status") == "published":
                print("Already published. Nothing to do.")
                return
            # Patch to update metadata (works only if still draft)
            patch = {
                k: DOMAIN_PAYLOAD[k]
                for k in (
                    "detail",
                    "pricing",
                    "tags",
                    "version_history",
                    "has_gold_benchmark",
                    "image_url",
                    "profile_picture_url",
                )
                if k in DOMAIN_PAYLOAD
            }
            r = client.patch(f"/v1/domains/{domain_id}", json=patch)
            r.raise_for_status()
            print(f"Updated draft domain '{domain_id}'.")
        else:
            r.raise_for_status()
            print(f"Created domain '{domain_id}'.")

        # 2. Publish
        r = client.post(f"/v1/domains/{domain_id}/publish")
        r.raise_for_status()
        result = r.json()
        print(f"Published domain '{domain_id}'  status={result['status']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed example domain into BenchAnything.")
    parser.add_argument("--api-url", default=API_URL, help="BenchAnything API base URL")
    args = parser.parse_args()

    try:
        seed(args.api_url)
    except httpx.ConnectError:
        print(f"ERROR: Cannot connect to API at {args.api_url}")
        print("Make sure the backend is running first (./scripts/dev.sh or uvicorn).")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"ERROR: {e.response.status_code} — {e.response.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
