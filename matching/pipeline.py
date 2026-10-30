"""
The core matching pipeline: blocking + vector-search candidate
generation (Spark + FAISS), pairwise feature engineering (Spark),
and a trained, interpretable classifier that scores each candidate
pair (scikit-learn, on the driver, over the much smaller candidate
set blocking+FAISS produced).

Why Spark for blocking/features but plain sklearn for the
classifier: comparing every record against every other record is
O(n^2) and is exactly the problem blocking exists to avoid, so that
all-pairs explosion is the one place genuine distributed computation
earns its keep here. Once blocking + FAISS have cut 2,361 records
down to a few thousand *candidate pairs*, training a model on that
candidate set is a small, driver-local problem -- forcing it through
Spark MLlib at this scale would be the kind of "because we have a
hammer" pattern this portfolio deliberately avoids (see Vigil's
model/train.py, which makes the same choice for the same reason).

Why TF-IDF character n-grams + FAISS instead of a pretrained neural
embedding model: this sandbox's network proxy blocks
huggingface.co (confirmed directly, not assumed), so no pretrained
embedding model can be downloaded. Character n-gram TF-IDF vectors,
built entirely from this project's own data, are a real and still
widely-used technique for fuzzy name/address matching -- the
"embeddings" and "vector search" here are genuine (a real vector
space, a real FAISS nearest-neighbor index), just not neural. The
honest comparison is: this is what entity-resolution systems used for
years before contextual embeddings existed, not a dressed-up
workaround.
"""

from __future__ import annotations

import json
import os
import re
import time

import faiss
import jellyfish
import joblib
import numpy as np
import pandas as pd

from explain import explain_match
from pyspark.sql import SparkSession, functions as F
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
FEATURE_NAMES = [
    "name_jaro_winkler",
    "address_token_jaccard",
    "zip5_match",
    "dob_exact_match",
    "dob_day_month_swapped_match",
    "phone_exact_match",
    "email_exact_match",
    "email_local_part_match",
    "faiss_cosine_sim",
]


def _normalize_text(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _soundex_block_key(last_name: str, zip_code: str) -> str:
    """
    Classic blocking key: soundex of the surname (survives most typos
    and nickname-adjacent spelling drift) plus the first 3 digits of
    the ZIP (survives ZIP+4 vs ZIP5 formatting differences, and still
    groups records from the same general area even if the full ZIP
    differs slightly). Deliberately coarse -- blocking's whole job is
    to be a cheap, high-recall filter; precision is the scorer's job,
    not the blocking key's.
    """
    try:
        sx = jellyfish.soundex(last_name) if last_name else "0000"
    except Exception:
        sx = "0000"
    zip_prefix = (zip_code or "")[:3] or "000"
    return f"{sx}_{zip_prefix}"


def _dob_day_month_swapped(a: str, b: str) -> bool:
    if not a or not b:
        return False
    pa, pb = a.split("-"), b.split("-")
    if len(pa) != 3 or len(pb) != 3:
        return False
    return pa[0] == pb[0] and pa[1] == pb[2] and pa[2] == pb[1] and pa[1] != pa[2]


def _pair_features(row_a: dict, row_b: dict, faiss_sim: float) -> dict:
    name_a = f"{row_a['first_name']} {row_a['last_name']}"
    name_b = f"{row_b['first_name']} {row_b['last_name']}"
    addr_a_tokens = set(_normalize_text(row_a["address_line1"]).split())
    addr_b_tokens = set(_normalize_text(row_b["address_line1"]).split())
    union = addr_a_tokens | addr_b_tokens
    jaccard = len(addr_a_tokens & addr_b_tokens) / len(union) if union else 0.0

    email_a, email_b = (row_a["email"] or ""), (row_b["email"] or "")
    local_a = email_a.split("@")[0].lower() if email_a else ""
    local_b = email_b.split("@")[0].lower() if email_b else ""

    return {
        "name_jaro_winkler": jellyfish.jaro_winkler_similarity(
            _normalize_text(name_a), _normalize_text(name_b)
        ),
        "address_token_jaccard": jaccard,
        "zip5_match": float(bool(row_a["zip"]) and (row_a["zip"] or "")[:5] == (row_b["zip"] or "")[:5]),
        "dob_exact_match": float(bool(row_a["dob"]) and row_a["dob"] == row_b["dob"]),
        "dob_day_month_swapped_match": float(_dob_day_month_swapped(row_a["dob"], row_b["dob"])),
        "phone_exact_match": float(bool(row_a["phone"]) and row_a["phone"] == row_b["phone"]),
        "email_exact_match": float(bool(email_a) and email_a == email_b),
        "email_local_part_match": float(bool(local_a) and local_a == local_b),
        "faiss_cosine_sim": faiss_sim,
    }


def _build_faiss_candidates(records_pdf: pd.DataFrame, top_k: int = 6) -> dict[tuple[str, str], float]:
    """
    A real FAISS nearest-neighbor index over TF-IDF character-n-gram
    vectors of each record's normalized "identity string" (name +
    address). This is the project's vector-search/semantic-similarity
    layer: it catches true-duplicate pairs that blocking's surname+ZIP
    key can miss entirely -- e.g. a typo severe enough to change the
    soundex code, or a record whose ZIP genuinely differs. Returns a
    dict of (record_id_a, record_id_b) -> cosine similarity for every
    pair found this way, to be unioned with blocking's candidate set.
    """
    identity_strings = (
        records_pdf["first_name"].fillna("") + " " + records_pdf["last_name"].fillna("") + " "
        + records_pdf["address_line1"].fillna("")
    ).map(_normalize_text)

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
    vectors = vectorizer.fit_transform(identity_strings).astype("float32").toarray()
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = vectors / norms  # L2-normalize so inner product == cosine similarity

    index = faiss.IndexFlatIP(normalized.shape[1])
    index.add(normalized)
    similarities, neighbor_idx = index.search(normalized, top_k + 1)  # +1 because a record matches itself

    record_ids = records_pdf["record_id"].tolist()
    candidates: dict[tuple[str, str], float] = {}
    for i, (sims, neighbors) in enumerate(zip(similarities, neighbor_idx)):
        for sim, j in zip(sims, neighbors):
            if i == j:
                continue
            a, b = record_ids[i], record_ids[int(j)]
            key = (a, b) if a < b else (b, a)
            candidates[key] = max(candidates.get(key, 0.0), float(sim))
    return candidates


def run(records_csv: str | None = None, out_dir: str | None = None) -> None:
    records_csv = records_csv or os.path.join(ARTIFACTS_DIR, "records.csv")
    out_dir = out_dir or ARTIFACTS_DIR
    os.makedirs(out_dir, exist_ok=True)
    # ground_truth.csv and entity_meta.csv are generated alongside
    # records.csv by generate_data.py -- read them from records_csv's
    # own directory (not the hardcoded module-level ARTIFACTS_DIR) so a
    # caller pointing records_csv at a test fixture directory doesn't
    # silently fall back to reading the real project dataset's labels.
    input_dir = os.path.dirname(records_csv) or "."

    spark = SparkSession.builder.master("local[*]").appName("veridex-matching").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    df = spark.read.option("header", True).csv(records_csv)
    block_key_udf = F.udf(_soundex_block_key)
    df = df.withColumn("block_key", block_key_udf(F.col("last_name"), F.col("zip"))).cache()
    df.count()  # materialize the cache once, so later actions don't re-run the UDF

    # Blocking candidate pairs: self-join within each block, a < b to
    # avoid duplicate/reversed pairs. This is the step that would be
    # O(n^2) without blocking -- Spark does the join, not a Python loop.
    left = df.alias("a")
    right = df.alias("b")
    blocked_pairs = (
        left.join(right, on="block_key")
        .where(F.col("a.record_id") < F.col("b.record_id"))
        .select(
            F.col("a.record_id").alias("record_id_a"),
            F.col("b.record_id").alias("record_id_b"),
        )
    )
    blocked_pairs_pdf = blocked_pairs.toPandas()
    n_blocks = df.select("block_key").distinct().count()
    print(f"blocking: {n_blocks} blocks, {len(blocked_pairs_pdf)} candidate pairs from blocking")

    t0 = time.time()
    records_pdf = df.drop("block_key").toPandas()
    records_pdf = records_pdf.where(pd.notnull(records_pdf), "")
    print(f"[{time.time()-t0:.1f}s] collected {len(records_pdf)} records to driver")

    faiss_candidates = _build_faiss_candidates(records_pdf)
    print(f"[{time.time()-t0:.1f}s] faiss vector search: {len(faiss_candidates)} candidate pairs from nearest-neighbor search")

    blocked_keys = [
        (a, b) if a < b else (b, a)
        for a, b in zip(blocked_pairs_pdf["record_id_a"].tolist(), blocked_pairs_pdf["record_id_b"].tolist())
    ]
    all_pairs: dict[tuple[str, str], float] = {key: faiss_candidates.get(key, 0.0) for key in blocked_keys}
    for key, sim in faiss_candidates.items():
        if key not in all_pairs:
            all_pairs[key] = sim
    print(f"[{time.time()-t0:.1f}s] total unique candidate pairs after union: {len(all_pairs)}")

    records_by_id = records_pdf.set_index("record_id").to_dict(orient="index")

    rows = []
    for (a, b), faiss_sim in all_pairs.items():
        feats = _pair_features(records_by_id[a], records_by_id[b], faiss_sim)
        feats["record_id_a"] = a
        feats["record_id_b"] = b
        rows.append(feats)
    pairs_df = pd.DataFrame(rows)
    print(f"[{time.time()-t0:.1f}s] computed pairwise features for {len(pairs_df)} candidate pairs")

    gt = pd.read_csv(os.path.join(input_dir, "ground_truth.csv")).set_index("record_id")["entity_id"]
    entity_meta = pd.read_csv(os.path.join(input_dir, "entity_meta.csv")).set_index("entity_id")
    entity_a = gt.reindex(pairs_df["record_id_a"])
    entity_b = gt.reindex(pairs_df["record_id_b"])
    pairs_df["label"] = (entity_a.to_numpy() == entity_b.to_numpy()).astype(int)

    # A pair is a "hard case" if either side's entity is a twin
    # negative or came from a noisy legacy source (see
    # generate_data.py) -- used below to report sliced metrics
    # honestly, rather than one flattering global number.
    noisy_lookup = entity_meta["is_noisy_source"].reindex(pd.concat([entity_a, entity_b]).unique()).fillna(False)
    twin_lookup = entity_meta["is_twin_negative"].reindex(pd.concat([entity_a, entity_b]).unique()).fillna(False)
    pairs_df["is_hard_case"] = (
        entity_a.map(noisy_lookup).to_numpy() | entity_b.map(noisy_lookup).to_numpy()
        | entity_a.map(twin_lookup).to_numpy() | entity_b.map(twin_lookup).to_numpy()
    )

    n_true_duplicate_pairs_total = _count_true_duplicate_pairs(gt)
    n_found = int(pairs_df["label"].sum())
    print(
        f"candidate recall: {n_found}/{n_true_duplicate_pairs_total} true duplicate pairs "
        f"survived blocking+FAISS ({n_found / n_true_duplicate_pairs_total:.1%})"
    )

    X = pairs_df[FEATURE_NAMES].to_numpy()
    y = pairs_df["label"].to_numpy()
    idx = np.arange(len(pairs_df))
    idx_train, idx_rest = train_test_split(idx, test_size=0.4, random_state=42, stratify=y)
    idx_val, idx_test = train_test_split(idx_rest, test_size=0.5, random_state=42, stratify=y[idx_rest])

    model = LogisticRegression(max_iter=1000, class_weight="balanced")
    model.fit(X[idx_train], y[idx_train])

    y_test = y[idx_test]
    test_probs = model.predict_proba(X[idx_test])[:, 1]
    test_auc = roc_auc_score(y_test, test_probs)
    test_ap = average_precision_score(y_test, test_probs)

    threshold, review_reduction = _review_reduction_at_recall(y_test, test_probs, target_recall=0.95)

    # The honest breakdown: how much worse does the model do on the
    # subset of test pairs that are genuinely hard (twins, or involve
    # a noisy legacy-source record) versus the easy majority? If these
    # two numbers were close, the "hard case" design wouldn't have
    # done its job.
    hard_mask_test = pairs_df["is_hard_case"].to_numpy()[idx_test]
    easy_metrics = _safe_auc_ap(y_test[~hard_mask_test], test_probs[~hard_mask_test])
    hard_metrics = _safe_auc_ap(y_test[hard_mask_test], test_probs[hard_mask_test])

    pairs_df["match_probability"] = model.predict_proba(X)[:, 1]
    pairs_df.to_csv(os.path.join(out_dir, "candidate_pairs.csv"), index=False)

    # The backend loads precomputed explanations rather than
    # reimplementing the same logic in Java: the model and its exact
    # linear decomposition only need to exist once, in the language
    # that trained the model. JSONL (one JSON object per line) avoids
    # the CSV-quoting problems a narrative sentence containing commas
    # would otherwise cause.
    coefficients = dict(zip(FEATURE_NAMES, model.coef_[0].tolist()))
    jsonl_path = os.path.join(out_dir, "candidate_pairs.jsonl")
    with open(jsonl_path, "w") as f:
        for _, row in pairs_df.iterrows():
            feats = {name: float(row[name]) for name in FEATURE_NAMES}
            explanation = explain_match(feats, float(row["match_probability"]), coefficients)
            record = {
                "record_id_a": row["record_id_a"],
                "record_id_b": row["record_id_b"],
                "features": feats,
                "match_probability": float(row["match_probability"]),
                "narrative": explanation["narrative"],
                "contributions": explanation["contributions"],
            }
            f.write(json.dumps(record) + "\n")
    print(f"[{time.time()-t0:.1f}s] wrote {len(pairs_df)} explained candidate pairs -> {jsonl_path}")

    joblib.dump(model, os.path.join(out_dir, "model.joblib"))

    metrics = {
        "n_records": len(records_pdf),
        "n_blocks": n_blocks,
        "n_candidate_pairs_from_blocking": len(blocked_pairs_pdf),
        "n_candidate_pairs_from_faiss": len(faiss_candidates),
        "n_candidate_pairs_total": len(all_pairs),
        "n_true_duplicate_pairs_total": n_true_duplicate_pairs_total,
        "candidate_recall": round(n_found / n_true_duplicate_pairs_total, 4),
        "test_roc_auc": round(float(test_auc), 4),
        "test_average_precision": round(float(test_ap), 4),
        "n_hard_case_test_pairs": int(hard_mask_test.sum()),
        "n_easy_test_pairs": int((~hard_mask_test).sum()),
        "easy_subset_metrics": easy_metrics,
        "hard_subset_metrics": hard_metrics,
        "decision_threshold_at_95pct_recall": round(float(threshold), 4),
        "review_queue_reduction_at_95pct_recall": round(float(review_reduction), 4),
        "feature_names": FEATURE_NAMES,
        "model_coefficients": dict(zip(FEATURE_NAMES, model.coef_[0].tolist())),
        "model_intercept": float(model.intercept_[0]),
    }
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    print(json.dumps(metrics, indent=2))
    spark.stop()


def _safe_auc_ap(y_true: np.ndarray, probs: np.ndarray) -> dict:
    if len(y_true) == 0 or len(np.unique(y_true)) < 2:
        return {"n": int(len(y_true)), "roc_auc": None, "average_precision": None}
    return {
        "n": int(len(y_true)),
        "roc_auc": round(float(roc_auc_score(y_true, probs)), 4),
        "average_precision": round(float(average_precision_score(y_true, probs)), 4),
    }


def _count_true_duplicate_pairs(gt: pd.Series) -> int:
    counts = gt.value_counts()
    return int((counts * (counts - 1) // 2).sum())


def _review_reduction_at_recall(y_true: np.ndarray, probs: np.ndarray, target_recall: float) -> tuple[float, float]:
    """
    The operational KPI, mirroring Vigil's "queue-volume reduction at
    a target recall": find the lowest score threshold at which pairs
    scoring BELOW it can be auto-resolved as non-matches without
    losing more than (1 - target_recall) of the true duplicate pairs
    in this test set, and report what fraction of all pairs that
    threshold lets us skip sending to human review.
    """
    order = np.argsort(-probs)
    sorted_probs = probs[order]
    sorted_labels = y_true[order]
    total_positives = sorted_labels.sum()
    if total_positives == 0:
        return 0.5, 0.0
    cum_positives = np.cumsum(sorted_labels)
    recall_at_k = cum_positives / total_positives
    idx = np.searchsorted(recall_at_k, target_recall)
    idx = min(idx, len(sorted_probs) - 1)
    threshold = sorted_probs[idx]
    n_above_threshold = int((probs >= threshold).sum())
    reduction = 1 - (n_above_threshold / len(probs))
    return threshold, reduction


if __name__ == "__main__":
    run()
