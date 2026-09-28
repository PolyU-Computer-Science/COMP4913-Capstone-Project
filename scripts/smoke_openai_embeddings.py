#!/usr/bin/env python
"""Manual smoke test for OpenRouter embeddings (NOT run in CI).

Reads OPENROUTER_API_KEY from ``.env`` and performs a few real embedding calls
to verify the runtime path works. Never prints the API key and never writes
results to a committed file.

Usage:
    uv run python scripts/smoke_openai_embeddings.py
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(override=False)


def _banner(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> None:
    from email_assistant.core.embeddings import cosine_similarity
    from email_assistant.core.openai_embeddings import (
        OpenAICompatibleEmbeddingClient,
        build_openai_compatible_embedding_client,
    )

    _banner("Config")
    try:
        client = build_openai_compatible_embedding_client()
    except Exception as error:  # noqa: BLE001
        print(f"FAILED to build client: {error}")
        return

    print(f"model   : {client.model}")
    print(f"base_url: {client._base_url}")
    print("api_key : <set>" if client._api_key else "api_key : <missing>")

    _banner("Single embedding")
    try:
        vec = client.embed_query("refund policy")
        print(f"ok, dim={len(vec)}, first 3 = {[round(v, 4) for v in vec[:3]]}")
    except Exception as error:  # noqa: BLE001
        print(f"FAILED: {error}")
        return

    _banner("Batch embedding")
    try:
        vectors = client.embed_documents(["refund policy", "password reset"])
        dims = {len(v) for v in vectors}
        print(f"ok, count={len(vectors)}, dims={dims}")
    except Exception as error:  # noqa: BLE001
        print(f"FAILED: {error}")
        return

    _banner("Semantic similarity sanity check")
    try:
        refund = client.embed_query("How long is the refund period?")
        train = client.embed_query("When is the next train to Admiralty?")
        sim_same = cosine_similarity(
            refund, client.embed_query("Can I get a refund for my order?")
        )
        sim_diff = cosine_similarity(refund, train)
        print(f"refund<->refund similarity : {round(sim_same, 4)}")
        print(f"refund<->train   similarity : {round(sim_diff, 4)}")
        print("PASS" if sim_same > sim_diff else "WARN: related texts not more similar")
    except Exception as error:  # noqa: BLE001
        print(f"FAILED: {error}")

    _banner("Done")
    print("Embedding runtime smoke test complete.")


if __name__ == "__main__":
    main()
