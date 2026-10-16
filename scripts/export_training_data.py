"""Export anonymised chats from users who opted in to training.

Run this yourself, locally, and never inside the web app. It needs Supabase's *secret*
key (service role), which bypasses Row Level Security, so keep it in your shell only:

    export SUPABASE_URL=https://YOUR-PROJECT.supabase.co
    export SUPABASE_SECRET_KEY=sb_secret_...
    pip install -r requirements-export.txt
    python -m spacy download en_core_web_lg
    python scripts/export_training_data.py --out training.jsonl

Only users whose consent record has training_opt_in = true are exported. Users are
never identified in the output: each conversation just gets a number.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CHUNK = 50


def build_dataset(consents, conversations, messages, anonymise):
    """Pure function (no network) so it can be tested: returns a list of conversation dicts.

    Only conversations belonging to users with training_opt_in are used, even if the
    caller passes in more.
    """
    opted_in = {c["user_id"] for c in consents if c.get("training_opt_in")}
    by_conversation = defaultdict(list)
    for message in sorted(messages, key=lambda m: m["id"]):
        by_conversation[message["conversation_id"]].append(message)

    dataset = []
    for conversation in conversations:
        if conversation["user_id"] not in opted_in:
            continue
        turns = by_conversation.get(conversation["id"], [])
        if not any(t["role"] == "assistant" for t in turns):
            continue
        dataset.append(
            {
                "conversation": len(dataset) + 1,
                "messages": [
                    {
                        "role": t["role"],
                        "content": anonymise(t["content"]),
                        **({"feedback": t["feedback"]} if t.get("feedback") else {}),
                    }
                    for t in turns
                ],
            }
        )
    return dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="training.jsonl")
    parser.add_argument("--spacy-model", default="en_core_web_lg")
    args = parser.parse_args()

    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SECRET_KEY in your shell first.")

    from supabase import create_client

    from compass.anonymise import Anonymiser

    client = create_client(url, key)
    consents = client.table("consents").select("user_id, training_opt_in").eq("training_opt_in", True).execute().data
    if not consents:
        sys.exit("No users have opted in to training yet. Nothing to export.")
    ids = [c["user_id"] for c in consents]
    # Fetch only the opted-in users' rows; other users' chats never leave the database.
    conversations = (
        client.table("conversations").select("id, user_id").in_("user_id", ids).order("created_at").execute().data
    )
    messages = []
    conversation_ids = [c["id"] for c in conversations]
    for i in range(0, len(conversation_ids), CHUNK):
        chunk = conversation_ids[i : i + CHUNK]
        messages += (
            client.table("messages")
            .select("id, conversation_id, role, content, feedback")
            .in_("conversation_id", chunk)
            .order("id")
            .execute()
            .data
        )

    anonymiser = Anonymiser(args.spacy_model)
    dataset = build_dataset(consents, conversations, messages, anonymiser.anonymise)
    with open(args.out, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Wrote {len(dataset)} anonymised conversations to {args.out}. Spot-check it before using it.")


if __name__ == "__main__":
    main()
