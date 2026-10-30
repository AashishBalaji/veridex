# Veridex — Identity Resolution & Deduplication Engine

Built for the **TransUnion / TruAudience Marketing Solutions — Entry-Level Full
Stack Engineer** JD (Java/Spring Boot, React/TypeScript, Apache Spark, SQL,
GenAI/RAG concepts, Docker/Kubernetes, CI/CD).

Given a pile of customer records scattered across multiple source systems —
same person entered three different ways in a CRM, a billing system, and a
legacy mainframe export — Veridex finds the records that are the same real
person, scores how confident it is, explains *why* in plain language, and
gives a human reviewer a queue to confirm or reject each proposed match.

This is the deduplication problem underneath "identity resolution," which is
what TruAudience's actual product does at a much larger scale. The project is
scoped down to something one entry-level engineer can build and explain end
to end, not a toy that ignores the hard parts.

## Why this project, not something flashier

The JD lists Spark, embeddings/vector databases, and RAG as **preferred**
skills, not required ones — a signal that TruAudience wants candidates who
reach toward what the team's product actually does, scaled to an entry-level
scope, rather than bolting on an unrelated AI feature to check a box. Identity
resolution is TruAudience's actual domain (deterministic + probabilistic
matching across data sources), so every piece here — including where Spark
and vector similarity search are used — is load-bearing, not decorative. See
[`docs/decisions.md`](docs/decisions.md) for the fuller reasoning, including
where this design was changed to avoid overclaiming things an entry-level
candidate wouldn't actually own in a real team.

## Architecture

```
matching/  Python + PySpark pipeline: generates synthetic multi-source
           records, blocks candidate pairs (soundex + ZIP prefix) to
           avoid O(n²) comparison, adds a FAISS nearest-neighbor pass
           over TF-IDF character n-gram vectors, trains a logistic
           regression classifier, and explains every match with the
           model's own exact linear feature-contribution decomposition.
           Writes records.csv / candidate_pairs.jsonl / metrics.json.

backend/   Spring Boot REST API. Loads the pipeline's artifacts into
           Postgres once at startup, serves the review queue, and
           applies reviewer decisions with an atomic concurrency guard.
           Plain JdbcTemplate DAOs, not Spring Data JPA -- the SQL stays
           visible and explicit.

dashboard/ React + TypeScript + Vite review-queue UI: see pending pairs
           side by side, read the match explanation, merge or reject,
           and look up which records ended up in the same cluster.

k8s/       Namespace, Postgres StatefulSet, a one-shot Job that runs
           the pipeline into a shared volume, and Deployments/Services
           for the backend and dashboard.

.github/workflows/ci.yml
           Runs the Python test suite, the Java test suite against a
           real Postgres service container, builds the dashboard, then
           builds all three Docker images, spins up a real kind
           cluster, applies the k8s manifests, and runs an HTTP smoke
           test against the actually-running backend.
```

## Why Spark, and why not a pretrained embedding model

The blocking step — a self-join of every record against every other record
in the same (soundex(last_name), ZIP-prefix) bucket — is the step that would
be `O(n²)` without blocking, and it's the one place in this pipeline where
Spark's distributed join genuinely earns its keep. The classifier itself
trains on the much smaller set of *candidate* pairs (thousands, not
millions), so it runs as plain scikit-learn on the driver — training a
model on a few thousand rows inside a distributed job would be
architectural theater, not a real use of Spark.

The "vector search / embeddings" layer uses TF-IDF character n-gram vectors
indexed with FAISS (`IndexFlatIP`), not a pretrained neural embedding model.
That's an honest substitution, not a shortcut dressed up: `huggingface.co`
is blocked by this sandbox's egress allowlist (confirmed directly — a 403 at
the proxy, not a timeout), so no pretrained embedding model could be
downloaded here. TF-IDF character n-grams are themselves a real, still
widely-used technique for fuzzy name/address matching — not an invented
stand-in — and the FAISS/cosine-similarity machinery around them is exactly
what a neural embedding model would plug into if one were swapped in later.

## Honest metrics, not one flattering number

An early run of this pipeline came back with a 0.9999 AUC — the same red
flag as a prior project in this portfolio's near-perfect results on
synthetic data. Rather than reporting that, the dataset generator was pushed
to be harder (heavier field corruption on a "noisy legacy source" subset,
and deliberately confusable negative pairs — people who share a surname,
ZIP, date of birth, or household phone number but are not the same person),
and the pipeline now reports metrics on an **easy** and a **hard** subset
separately instead of one blended number:

| | n | ROC-AUC | Average precision |
|---|---|---|---|
| Easy subset (distinct, unrelated people) | 1,070 | 0.9999 | 0.9998 |
| Hard subset (twins/siblings, noisy legacy records) | 974 | 0.9808 | 0.8831 |

The hard subset's numbers are meaningfully lower — that's the honest story:
distinguishing two different people who share a surname, ZIP and birthday is
a genuinely harder problem than matching records that are obviously the same
or obviously different, and the model is worse at it. At a decision threshold
tuned to 95% recall, the model would still cut the manual review queue by
**81%** (`review_queue_reduction_at_95pct_recall: 0.8097`) relative to
reviewing every candidate pair by hand.

Full numbers: [`matching/artifacts/metrics.json`](matching/artifacts/metrics.json)
(regenerate with `python generate_data.py && python pipeline.py`).

## A real, fixed explainability bug

An early version of the explanation layer could show "working against it:
address overlap is 1.00" for a pair with a *perfect* address match, because
that feature's trained coefficient happened to land near zero (model noise,
not signal), and a perfect value times a tiny coefficient still outranked
several exactly-zero features when sorted by magnitude. The sentence read as
self-contradictory. Fixed by filtering out any contribution below a minimum
magnitude before deciding what counts as "supporting" or "opposing" — see
`matching/explain.py`'s `_MIN_CONTRIBUTION` and `tests/test_explain.py`'s
regression test for it.

## Known gaps (stated, not hidden)

- **Maven Central and Docker Hub are both blocked** by the sandbox this
  project was built in (`repo.maven.apache.org` and `registry-1.docker.io`
  both return a 403 at the egress proxy, confirmed directly with curl). The
  Spring Boot backend has therefore never compiled or run **locally** in
  this environment, and none of the Docker/Kubernetes pieces have been
  tested locally either. `.github/workflows/ci.yml` is where all of that
  gets its real verification, on GitHub's hosted runners, which have full
  internet access — mirroring how this portfolio's prior Kubernetes-based
  project (OpsPilot) was also only ever verified in CI, never locally.
- The union-find clustering (`record_cluster` table, `LEAST`/`GREATEST`
  root merging) is correct and simple at this project's scale — thousands of
  records — not a scalable union-find with path compression for millions.
- The match-explanation text is a deterministic template, not an LLM call
  (see `matching/explain.py`'s docstring for why, and the pluggable
  `Explainer` interface that a real LLM-backed implementation would satisfy
  without changing anything else).

## Running it locally

```bash
# 1. Generate data and run the matching pipeline
cd matching
pip install -r requirements.txt
python generate_data.py
python pipeline.py

# 2. Start Postgres, point the backend at it, run the backend
#    (needs Maven Central reachable -- see "Known gaps" above)
cd ../backend
export VERIDEX_DB_URL=jdbc:postgresql://localhost:5432/veridex
mvn spring-boot:run

# 3. Start the dashboard
cd ../dashboard
npm install
npm run dev
```

Or, once Docker Hub is reachable: `docker compose up --build` from the repo
root.
