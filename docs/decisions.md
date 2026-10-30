# Design decisions

## Why this project over the alternative that was considered

Two project ideas were weighed against this JD before building anything:

1. **AudienceIQ** — an audience-segmentation/targeting tool, closer to the
   JD's literal "marketing solutions" framing, with an LLM-based
   copy/insight layer bolted on to cover the GenAI requirement.
2. **Identity Resolution & Deduplication Engine** (this project) — matching
   and deduplicating customer records across source systems, which is
   TruAudience's actual product domain.

The JD lists Spark, embeddings/vector databases, and RAG under "preferred,"
not "required," skills. That phrasing reads less like "nice to have, ignore
if inconvenient" and more like a signal that the team wants candidates who
reach past the entry-level floor toward what the team's product actually
does. AudienceIQ's AI layer would have been decorative — addressable by any
marketing-tool project, not specific to identity resolution — whereas in
this project, Spark's distributed blocking join and FAISS's vector search
are structurally necessary to the core problem (matching records across
sources at scale), not features added to satisfy a skills checklist.

The trade-off: AudienceIQ would have been more immediately legible to a
reviewer skimming resumes ("audience segmentation" maps directly onto
"marketing solutions"), and carries less risk of reading as over-scoped for
an entry-level role. Identity resolution asks a reviewer to make one extra
inferential leap to see why it's relevant to TruAudience specifically. That
trade was accepted because the JD's own "preferred" skills are the stronger
signal here, and because the project is deliberately scoped to what an
entry-level engineer would realistically own — not a full production
identity-graph system — rather than overclaiming seniority. See the
"Known gaps" section of the main [README](../README.md) for exactly where
that scoping shows up (synchronous union-find rather than a distributed
one, a template explainer rather than a hosted LLM call, etc.).

## Why blocking uses Spark but the classifier doesn't

Blocking — the self-join of every record against every other record sharing
a `(soundex(last_name), zip_prefix)` key — is the step that is genuinely
`O(n²)` without it, and it's the one place a distributed join earns its
keep: it's the mechanism that makes candidate-pair generation tractable at
scale. Once blocking (plus a FAISS nearest-neighbor pass) has cut the
`n²` record pairs down to a few thousand *candidate* pairs, training a
logistic regression classifier on that set runs in well under a second as
plain scikit-learn on the Spark driver. Wrapping that training step in
distributed Spark MLlib code would add complexity without adding real
scale — the same reasoning this portfolio's AML-triage project (Vigil) used
for its own driver-side model training.

## Why TF-IDF character n-grams + FAISS instead of a pretrained embedding model

`huggingface.co` returns a 403 at this sandbox's egress proxy (confirmed
directly with `curl`, not inferred from a timeout), so no pretrained
sentence/text embedding model could be downloaded here. TF-IDF character
n-gram vectors (`char_wb`, n=2..4) over normalized name+address strings,
indexed with FAISS's `IndexFlatIP` after L2 normalization (making inner
product equivalent to cosine similarity), is a substitution for the
*specific unavailable model*, not for the technique category: character
n-gram TF-IDF is itself a real, still-used method for fuzzy string matching,
and the FAISS/cosine-similarity plumbing around it is exactly what a
pretrained neural embedding would plug into if substituted in later — the
`faiss_cosine_sim` feature and the `_build_faiss_candidates` function don't
care what produced the vectors.

## Why candidate_pairs.jsonl exists, not just candidate_pairs.csv

The Python pipeline already computes each pair's natural-language match
explanation and its per-feature contribution breakdown
(`matching/explain.py`). JSONL carries that pre-computed narrative text
(which contains commas and would need CSV-quoting handling) and a nested
list of contribution objects naturally, and — more importantly — means the
Java backend *loads* the explanation rather than re-implementing
`explain.py`'s logic in a second language. One source of truth for "why did
this pair match," not two implementations that can quietly drift apart.

## Why the union-find clustering is deliberately simple

`record_cluster.cluster_root` uses `LEAST`/`GREATEST` root merging, kept
flat (every row always points directly at the current root, never a chain)
so a lookup is always a single row read. This is correct and simple at this
project's scale — thousands of records, a handful of merges per review
session — not a scalable union-find with path compression and union-by-rank
for a production system handling millions of records and thousands of
concurrent merges. Scaling that further is a real, known follow-up, named
here rather than silently left as a hidden limitation.

## Why the explanation layer is a template, not a hosted LLM call

This sandbox has no LLM API credentials to give an application built inside
it — the environment's own Claude access is Claude Code's, not something to
borrow or embed into a project being built *in* that environment. The
default `TemplateExplainer` is a deterministic, grounded natural-language
generator over the model's own exact feature contributions (for a linear
model, contribution = coefficient × value — the literal decomposition of
the decision function, not an approximation). The `Explainer` abstract base
class exists specifically so a real LLM-backed implementation could later
satisfy the same interface — `explain_match(features, probability,
coefficients, explainer=SomeLLMExplainer())` — without changing anything
else in the pipeline or the backend that consumes its output.

## Why Maven Central and Docker Hub being blocked was surfaced, not worked around

Both `repo.maven.apache.org` and `registry-1.docker.io` return a 403 at
this sandbox's egress proxy. Rather than silently abandoning the Java
requirement (e.g., quietly rewriting the backend in a language this
sandbox's allowlist already permits) or pretending local verification had
happened when it hadn't, this was raised directly, with the actual proxy
error and the setting that controls it (Settings → Capabilities), so the
decision belonged to the project owner rather than being made invisibly.
The Spring Boot backend and all Docker/Kubernetes pieces are real,
complete, and get their actual verification in CI (`.github/workflows/ci.yml`),
which runs on GitHub's hosted runners with full internet access — the same
pattern this portfolio's prior Kubernetes project (OpsPilot) already used
for its own Docker/kind verification.
