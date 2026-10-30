"""
Synthetic multi-source customer records for identity resolution.

There is no legitimate way to use real customer PII for a portfolio
project -- same data-honesty discipline used elsewhere in this
portfolio (see Vigil's generate_data.py). This generator instead
builds its own "true" population of entities and deliberately
scatters each one across 1-4 source-system records with realistic
variation (nicknames, typos, address-format differences, a changed
phone number, an occasional missing field) -- and, just as
importantly, also plants a set of "confusable negatives": genuinely
different people who happen to share a surname and address (e.g. a
parent and adult child still on the same mailing address), so the
matching problem is not trivially separable by surname+zip alone.
The ground-truth entity id is written to a separate file and is used
only for offline evaluation (precision/recall of the matcher) -- the
matching pipeline itself never sees it.
"""

from __future__ import annotations

import csv
import json
import os
import random
from dataclasses import dataclass, field

OUT_DIR = os.path.join(os.path.dirname(__file__), "artifacts")

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Arjun", "Priya", "Rahul", "Ananya",
    "Vikram", "Meera", "Rohan", "Sneha", "Aditya", "Divya",
]
NICKNAME_MAP = {
    "Robert": "Rob", "Elizabeth": "Liz", "William": "Bill", "Richard": "Rick",
    "Joseph": "Joe", "Thomas": "Tom", "Charles": "Chuck", "Jennifer": "Jen",
    "Patricia": "Pat", "Michael": "Mike", "David": "Dave", "James": "Jim",
    "Susan": "Sue", "Barbara": "Barb", "Jessica": "Jess", "Sarah": "Sara",
}
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee", "Iyer", "Nair", "Rao", "Menon",
    "Krishnan", "Pillai",
]
STREET_SUFFIXES = ["St", "Ave", "Blvd", "Dr", "Ln", "Rd", "Ct", "Way"]
STREET_SUFFIX_FULL = {
    "St": "Street", "Ave": "Avenue", "Blvd": "Boulevard", "Dr": "Drive",
    "Ln": "Lane", "Rd": "Road", "Ct": "Court", "Way": "Way",
}
CITIES_STATES = [
    ("Austin", "TX"), ("Chicago", "IL"), ("Columbus", "OH"), ("Denver", "CO"),
    ("Phoenix", "AZ"), ("Seattle", "WA"), ("Atlanta", "GA"), ("Boston", "MA"),
    ("Dallas", "TX"), ("Charlotte", "NC"),
]
SOURCE_SYSTEMS = ["crm", "billing", "marketing_signup"]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "icloud.com"]


@dataclass
class Entity:
    entity_id: int
    first_name: str
    last_name: str
    street_num: int
    street_name: str
    street_suffix: str
    city: str
    state: str
    zip5: str
    phone: str
    email: str
    dob: str  # YYYY-MM-DD


@dataclass
class Record:
    record_id: str
    entity_id: int  # ground truth only -- never fed to the matcher
    source_system: str
    first_name: str
    last_name: str
    address_line1: str
    city: str
    state: str
    zip: str
    phone: str
    email: str
    dob: str


def _typo(s: str, rng: random.Random) -> str:
    if len(s) < 4:
        return s
    i = rng.randrange(1, len(s) - 1)
    op = rng.choice(["swap", "drop", "dup"])
    if op == "swap" and i + 1 < len(s):
        chars = list(s)
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
        return "".join(chars)
    if op == "drop":
        return s[:i] + s[i + 1 :]
    return s[:i] + s[i] + s[i:]


def _make_entity(entity_id: int, rng: random.Random) -> Entity:
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    city, state = rng.choice(CITIES_STATES)
    suffix = rng.choice(STREET_SUFFIXES)
    return Entity(
        entity_id=entity_id,
        first_name=first,
        last_name=last,
        street_num=rng.randint(100, 9999),
        street_name=rng.choice(LAST_NAMES) + " " if False else rng.choice(
            ["Maple", "Oak", "Elm", "Cedar", "Pine", "Sunset", "Lincoln", "Willow", "Birch", "Riverside"]
        ),
        street_suffix=suffix,
        city=city,
        state=state,
        zip5=f"{rng.randint(10000, 99999)}",
        phone=f"{rng.randint(200, 999)}-{rng.randint(200, 999)}-{rng.randint(1000, 9999)}",
        email=f"{first.lower()}.{last.lower()}{rng.randint(1, 99)}@{rng.choice(EMAIL_DOMAINS)}",
        dob=f"19{rng.randint(50, 99)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
    )


def _variant_record(
    entity: Entity, source: str, rng: random.Random, record_counter: list[int], noisy: bool = False
) -> Record:
    """
    One "appearance" of an entity in a source system, with realistic,
    independently-rolled variation per field -- never all fields
    drifting together, which is what would make this trivially easy.

    `noisy` marks a record as coming from a particularly messy legacy
    source (roughly 15% of entities get one) -- much higher corruption
    on every field at once, including collapsing the first name to a
    bare initial. Without this, every field's corruption is small and
    independent, which is exactly the setup that produced an
    unrealistic, trivially-separable 0.9999 test AUC on the first run
    of this pipeline -- the same failure mode Vigil's label-noise fix
    addressed, here solved by making a meaningful fraction of true
    duplicates genuinely hard to recognize, not just a little fuzzy.
    """
    typo_rate = 0.4 if noisy else 0.08
    missing_rate = 0.55 if noisy else 0.15

    first = entity.first_name
    if rng.random() < 0.25 and first in NICKNAME_MAP:
        first = NICKNAME_MAP[first]
    if noisy and rng.random() < 0.3:
        first = first[0]  # collapsed to a bare initial, as some legacy systems do
    elif rng.random() < typo_rate:
        first = _typo(first, rng)

    last = entity.last_name
    if rng.random() < (0.2 if noisy else 0.06):
        last = _typo(last, rng)

    suffix = entity.street_suffix
    if rng.random() < 0.5:
        suffix = STREET_SUFFIX_FULL[suffix]
    address = f"{entity.street_num} {entity.street_name} {suffix}"
    if rng.random() < typo_rate:
        address = _typo(address, rng)
    if noisy and rng.random() < 0.3:
        # Abbreviated beyond recognition by the simple normalizer --
        # e.g. a legacy system that only stored "123 Maple" with the
        # suffix dropped entirely.
        address = f"{entity.street_num} {entity.street_name}"

    zip_code = entity.zip5
    if rng.random() < 0.1:
        zip_code = f"{zip_code}-{rng.randint(1000, 9999)}"  # ZIP+4 format difference, not a typo
    if noisy and rng.random() < 0.2:
        zip_code = _typo(zip_code, rng)  # a genuinely mistyped ZIP, not just a format difference

    phone = entity.phone
    if rng.random() < (0.3 if noisy else 0.12):
        # A genuinely changed phone number -- a true duplicate that
        # this field will NOT help identify. Realistic, and it's
        # exactly the kind of case other fields have to carry.
        phone = f"{rng.randint(200, 999)}-{rng.randint(200, 999)}-{rng.randint(1000, 9999)}"
    if rng.random() < missing_rate:
        phone = ""  # missing

    email = entity.email
    if rng.random() < missing_rate:
        email = ""  # not every source system collects email
    elif rng.random() < 0.1:
        email = f"{first.lower()}.{last.lower()}{rng.randint(1, 999)}@{rng.choice(EMAIL_DOMAINS)}"

    dob = entity.dob
    if rng.random() < (0.25 if noisy else 0.05):
        dob = ""  # missing
    elif rng.random() < (0.1 if noisy else 0.03):
        # a genuine data-entry error: month/day swapped
        parts = dob.split("-")
        if int(parts[1]) <= 12 and int(parts[2]) <= 12:
            dob = f"{parts[0]}-{parts[2]}-{parts[1]}"

    record_counter[0] += 1
    return Record(
        record_id=f"R{record_counter[0]:06d}",
        entity_id=entity.entity_id,
        source_system=source,
        first_name=first,
        last_name=last,
        address_line1=address,
        city=entity.city,
        state=entity.state,
        zip=zip_code,
        phone=phone,
        email=email,
        dob=dob,
    )


def generate(n_entities: int = 900, n_confusable_pairs: int = 280, seed: int = 42) -> tuple[list[Record], dict]:
    rng = random.Random(seed)
    counter = [0]
    records: list[Record] = []
    entity_meta: dict[int, dict] = {}

    entities = [_make_entity(i, rng) for i in range(n_entities)]

    for entity in entities:
        n_appearances = rng.choices([1, 2, 3, 4], weights=[0.15, 0.45, 0.3, 0.1])[0]
        sources = rng.sample(SOURCE_SYSTEMS * 2, k=n_appearances)
        # ~30% of entities have at least one appearance from a
        # particularly messy legacy source -- see _variant_record's
        # docstring for why this matters for honest metrics.
        is_noisy_entity = rng.random() < 0.3
        entity_meta[entity.entity_id] = {"is_noisy_source": is_noisy_entity, "is_twin_negative": False}
        for i, source in enumerate(sources):
            noisy = is_noisy_entity and i == 0
            records.append(_variant_record(entity, source, rng, counter, noisy=noisy))

    # Confusable negatives: a different entity sharing the SAME last
    # name and address as an existing entity -- the realistic "two
    # people at one address" case that stops a blocking-key-only
    # matcher from looking trivially perfect. About a third of these
    # are "twins" -- same DOB as well (a genuinely hard case: real
    # twins/siblings sharing a household, a birthday, and a surname
    # are a known, real failure mode for naive deterministic matching
    # rules), and some reuse a first name from the same nickname
    # family as the base entity's, so even name similarity alone
    # doesn't cleanly separate them.
    for _ in range(n_confusable_pairs):
        base = rng.choice(entities)
        is_twin = rng.random() < 0.5
        if is_twin and rng.random() < 0.4 and base.first_name in NICKNAME_MAP:
            # A sibling whose first name happens to share a nickname
            # family with the base entity's (e.g. base is "Robert",
            # sibling is "Rick" off a different root name) would be
            # unrealistic to construct exactly, so instead: reuse a
            # *different* full first name that still starts with the
            # same letter, a real source of false-positive name
            # similarity.
            other_first = rng.choice([n for n in FIRST_NAMES if n[0] == base.first_name[0]] or FIRST_NAMES)
        else:
            other_first = rng.choice(FIRST_NAMES)
        other = Entity(
            entity_id=-1,  # assigned below, must be a new ground-truth id
            first_name=other_first,
            last_name=base.last_name,
            street_num=base.street_num,
            street_name=base.street_name,
            street_suffix=base.street_suffix,
            city=base.city,
            state=base.state,
            zip5=base.zip5,
            # A household landline shared with the base entity is a
            # real source of false-positive phone matches for family
            # members at the same address -- about a third of twins
            # get this, making them harder still to tell apart.
            phone=base.phone if (is_twin and rng.random() < 0.35) else (
                f"{rng.randint(200, 999)}-{rng.randint(200, 999)}-{rng.randint(1000, 9999)}"
            ),
            email=f"other{rng.randint(1,999999)}@{rng.choice(EMAIL_DOMAINS)}",
            dob=base.dob if is_twin else f"19{rng.randint(50, 99)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
        )
        other.entity_id = n_entities + len(entities)
        entities.append(other)
        entity_meta[other.entity_id] = {"is_noisy_source": False, "is_twin_negative": is_twin}
        n_appearances = rng.choices([1, 2], weights=[0.6, 0.4])[0]
        for source in rng.sample(SOURCE_SYSTEMS * 2, k=n_appearances):
            records.append(_variant_record(other, source, rng, counter))

    rng.shuffle(records)
    return records, entity_meta


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    records, entity_meta = generate()

    records_path = os.path.join(OUT_DIR, "records.csv")
    with open(records_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "record_id", "source_system", "first_name", "last_name",
                "address_line1", "city", "state", "zip", "phone", "email", "dob",
            ],
        )
        writer.writeheader()
        for r in records:
            row = r.__dict__.copy()
            row.pop("entity_id")
            writer.writerow(row)

    ground_truth_path = os.path.join(OUT_DIR, "ground_truth.csv")
    with open(ground_truth_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["record_id", "entity_id"])
        writer.writeheader()
        for r in records:
            writer.writerow({"record_id": r.record_id, "entity_id": r.entity_id})

    entity_meta_path = os.path.join(OUT_DIR, "entity_meta.csv")
    with open(entity_meta_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["entity_id", "is_noisy_source", "is_twin_negative"])
        writer.writeheader()
        for entity_id, meta in entity_meta.items():
            writer.writerow({"entity_id": entity_id, **meta})

    n_entities = len({r.entity_id for r in records})
    meta = {
        "n_records": len(records),
        "n_true_entities": n_entities,
        "avg_records_per_entity": round(len(records) / n_entities, 2),
        "note": (
            "Synthetic data. entity_id in ground_truth.csv is for offline "
            "evaluation only -- the matching pipeline (pipeline.py) never "
            "reads ground_truth.csv as an input feature."
        ),
    }
    with open(os.path.join(OUT_DIR, "dataset_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"wrote {len(records)} records across {n_entities} true entities -> {records_path}")


if __name__ == "__main__":
    main()
