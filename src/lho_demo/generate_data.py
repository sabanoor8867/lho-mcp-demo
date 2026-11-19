"""Generate synthetic diagnostic test records: six cattle and two pig laboratories.

Every value is invented. The records only follow the *structure* of the
Livestock Health Ontology (LHO): the same classes and properties that real
laboratory data would use. No real laboratory data were used or copied.

Output:
  data/synthetic/lab1.ttl ... lab8.ttl   one RDF file per laboratory (1-6 cattle, 7-8 pigs)
  data/synthetic/records.csv             the same records as a plain table,
                                         used to compute the expected answers
                                         of the evaluation independently of SPARQL

Run:  python -m lho_demo.generate_data
"""
from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta

from .config import DATA_DIR, DATA_NS, LHO

SEED = 42
START, END = date(2019, 1, 1), date(2025, 12, 31)

# key -> (LHO local name, readable label). The keys are what the CSV stores.
PATHOGENS = {
    "BRSV": ("BRSV", "Bovine respiratory syncytial virus"),
    "BCV": ("BCV", "Bovine coronavirus"),
    "PI3": ("PI3", "Parainfluenza-3 virus"),
    "PM": ("PM", "Pasteurella multocida"),
    "MH": ("MH", "Mannheimia haemolytica"),
    "HS": ("HS", "Histophilus somni"),
    "MB": ("MB", "Mycoplasma bovis"),
}
VIRUSES = {"BRSV", "BCV", "PI3"}
BREEDS = {"Beef": "CS06", "Dairy": "Dairy", "Suckler": "CS02", "Veal": "CS08", "Mixed": "CS76", "Unknown": "CS09"}
SAMPLE_TYPES = {"Autopsy": "Autopsy", "BAL": "BAL", "Swab": "Swab", "TTA": "CS39", "Unknown": "CS90", "Missing": "CS46"}
TESTS = {"PCR": "CS07", "Culture": "Culture", "NPS": "CS19"}
COUNTRIES = {"Belgium": "Belgium", "France": "France", "Ireland": "Ireland", "The Netherlands": "TheNetherlands"}
LABS = {1: "1", 2: "2", 3: "CS51", 4: "CS55", 5: "CS61", 6: "CS64"}

# Invented laboratory profiles: size, country and the mix of what they test.
LAB_PROFILES = {
    1: dict(country="Belgium", n=3000, lab_factor=1.00,
            tests={"PCR": 0.60, "Culture": 0.25, "NPS": 0.15},
            breeds={"Beef": 0.35, "Dairy": 0.30, "Veal": 0.20, "Mixed": 0.10, "Unknown": 0.05},
            types={"BAL": 0.40, "Swab": 0.30, "Autopsy": 0.20, "TTA": 0.05, "Unknown": 0.05}),
    2: dict(country="The Netherlands", n=2600, lab_factor=0.90,
            tests={"PCR": 0.75, "Culture": 0.25},
            breeds={"Dairy": 0.45, "Veal": 0.35, "Beef": 0.10, "Mixed": 0.05, "Unknown": 0.05},
            types={"Swab": 0.45, "BAL": 0.25, "Autopsy": 0.25, "Missing": 0.05}),
    3: dict(country="France", n=2200, lab_factor=1.10,
            tests={"PCR": 0.55, "Culture": 0.45},
            breeds={"Beef": 0.40, "Suckler": 0.35, "Dairy": 0.20, "Unknown": 0.05},
            types={"Autopsy": 0.40, "Swab": 0.35, "TTA": 0.15, "BAL": 0.10}),
    4: dict(country="Ireland", n=1800, lab_factor=1.15,
            tests={"PCR": 0.70, "Culture": 0.30},
            breeds={"Suckler": 0.40, "Dairy": 0.35, "Beef": 0.20, "Unknown": 0.05},
            types={"Autopsy": 0.55, "Swab": 0.35, "Unknown": 0.10}),
    5: dict(country="Belgium", n=1400, lab_factor=0.85,
            tests={"NPS": 0.55, "PCR": 0.45},
            breeds={"Veal": 0.50, "Dairy": 0.25, "Beef": 0.15, "Mixed": 0.10},
            types={"BAL": 0.60, "TTA": 0.25, "Swab": 0.15}),
    6: dict(country="France", n=1000, lab_factor=0.95,
            tests={"Culture": 0.60, "PCR": 0.40},
            breeds={"Suckler": 0.45, "Beef": 0.35, "Dairy": 0.15, "Unknown": 0.05},
            types={"Autopsy": 0.50, "Swab": 0.30, "Missing": 0.20}),
}

# ---- Pigs. Categories follow the structure of a pig diagnostic dataset (PCR
# only, one country, production stages); every record and number is invented.
PIG_PATHOGENS = {
    "SIV": ("SwineInfluenzaVirus", "Swine influenza virus"),
    "MHYO": ("Mycoplasmahyopneumoniae", "Mycoplasma hyopneumoniae"),
    "LAWS": ("CS50", "Lawsonia intracellularis"),
    "PRRS": ("CS03", "Porcine reproductive and respiratory syndrome virus"),
}
PIG_VIRUSES = {"SIV", "PRRS"}
PIG_SAMPLE_TYPES = {"Tissue": "Tissue", "Swab": "Swab", "BAL": "BAL", "Feces": "Feces", "Fluid": "Fluid",
                    "Missing": "CS46"}
PIG_STAGES = {"Suckling": "Suckling", "Nursery": "Nursery", "Weaning": "Weaning", "Finishing": "Finishing",
              "Breeding": "Breeding"}
PIG_LAB_PROFILES = {
    7: dict(n=1600, lab_factor=1.05,
            stages={"Nursery": 0.30, "Finishing": 0.30, "Weaning": 0.20, "Breeding": 0.12, "Suckling": 0.08}),
    8: dict(n=1200, lab_factor=0.90,
            stages={"Finishing": 0.40, "Nursery": 0.25, "Breeding": 0.20, "Weaning": 0.10, "Suckling": 0.05}),
}
PIG_BASE_POSITIVE = {"SIV": 0.21, "MHYO": 0.27, "LAWS": 0.33, "PRRS": 0.38}
PIG_STAGE_FACTOR = {
    "SIV": {"Suckling": 0.6, "Nursery": 1.3, "Weaning": 1.2, "Finishing": 0.9, "Breeding": 0.7},
    "MHYO": {"Suckling": 0.3, "Nursery": 0.7, "Weaning": 0.8, "Finishing": 1.5, "Breeding": 0.9},
    "LAWS": {"Suckling": 0.3, "Nursery": 0.8, "Weaning": 1.0, "Finishing": 1.4, "Breeding": 0.8},
    "PRRS": {"Suckling": 0.8, "Nursery": 1.35, "Weaning": 1.2, "Finishing": 0.8, "Breeding": 0.7},
}
PIG_SAMPLE_BY_PATHOGEN = {
    "SIV": {"Swab": 0.45, "BAL": 0.25, "Tissue": 0.25, "Missing": 0.05},
    "MHYO": {"Tissue": 0.45, "BAL": 0.30, "Swab": 0.20, "Missing": 0.05},
    "LAWS": {"Feces": 0.70, "Tissue": 0.25, "Missing": 0.05},
    "PRRS": {"Fluid": 0.45, "Tissue": 0.35, "Swab": 0.15, "Missing": 0.05},
}

# Invented base probability of a positive result per pathogen.
BASE_POSITIVE = {"BRSV": 0.16, "BCV": 0.22, "PI3": 0.07, "PM": 0.34, "MH": 0.24, "HS": 0.18, "MB": 0.20}
TEST_FACTOR = {"PCR": 1.15, "Culture": 0.75, "NPS": 1.25}
BREED_FACTOR = {"Veal": 1.25, "Beef": 1.05, "Suckler": 1.00, "Dairy": 0.85, "Mixed": 1.00, "Unknown": 0.95}


def _pick(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def _season_factor(day: date, pathogen: str) -> float:
    """Winter peak (January), stronger for viruses."""
    amplitude = 0.55 if pathogen in VIRUSES else 0.25
    return 1.0 + amplitude * math.cos(2 * math.pi * (day.timetuple().tm_yday - 15) / 365.25)


def _random_day(rng: random.Random) -> date:
    """More submissions in the cold months."""
    span = (END - START).days
    while True:
        day = START + timedelta(days=rng.randint(0, span))
        accept = 0.55 + 0.45 * math.cos(2 * math.pi * (day.timetuple().tm_yday - 15) / 365.25)
        if rng.random() < max(accept, 0.25):
            return day


def generate() -> list[dict]:
    rng = random.Random(SEED)
    records: list[dict] = []
    for lab, profile in LAB_PROFILES.items():
        for i in range(1, profile["n"] + 1):
            test = _pick(rng, profile["tests"])
            # Culture only detects bacteria.
            pool = [p for p in PATHOGENS if not (test == "Culture" and p in VIRUSES)]
            pathogen = rng.choice(pool)
            breed = _pick(rng, profile["breeds"])
            day = _random_day(rng)
            p = (BASE_POSITIVE[pathogen] * TEST_FACTOR[test] * BREED_FACTOR[breed]
                 * profile["lab_factor"] * _season_factor(day, pathogen))
            records.append({
                "sample_number": f"L{lab}-{i:06d}",
                "species": "Cattle",
                "lab": lab,
                "country": profile["country"],
                "date": day.isoformat(),
                "breed": breed,
                "production_stage": "",
                "sample_type": _pick(rng, profile["types"]),
                "diagnostic_test": test,
                "pathogen": pathogen,
                "result": 1 if rng.random() < min(p, 0.95) else 0,
            })
    # Pigs come after the cattle, so the cattle records stay the same as before.
    for lab, profile in PIG_LAB_PROFILES.items():
        for i in range(1, profile["n"] + 1):
            pathogen = rng.choice(list(PIG_PATHOGENS))
            stage = _pick(rng, profile["stages"])
            day = _random_day(rng)
            season = 1.0 + (0.35 if pathogen in PIG_VIRUSES else 0.10) * math.cos(
                2 * math.pi * (day.timetuple().tm_yday - 15) / 365.25)
            p = PIG_BASE_POSITIVE[pathogen] * PIG_STAGE_FACTOR[pathogen][stage] * profile["lab_factor"] * season
            records.append({
                "sample_number": f"L{lab}-{i:06d}",
                "species": "Pig",
                "lab": lab,
                "country": "Spain",
                "date": day.isoformat(),
                "breed": "Meat",
                "production_stage": stage,
                "sample_type": _pick(rng, PIG_SAMPLE_BY_PATHOGEN[pathogen]),
                "diagnostic_test": "PCR",
                "pathogen": pathogen,
                "result": 1 if rng.random() < min(p, 0.95) else 0,
            })
    return records


def write_csv(records: list[dict]) -> None:
    with open(DATA_DIR / "records.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def write_turtle(records: list[dict]) -> None:
    header = (
        "# SYNTHETIC DATA. Every record is invented; no real laboratory data.\n"
        f"@prefix lho: <{LHO}> .\n\n"
    )
    for lab in LAB_PROFILES:
        lines = [header]
        for r in (x for x in records if x["lab"] == lab):
            iri = f"<{DATA_NS}lab{lab}/sample/{r['sample_number']}>"
            lines.append(
                f"{iri} a lho:CattleSample ;\n"
                f"    lho:CS18 \"{r['sample_number']}\" ;\n"
                f"    lho:CS17 \"{r['date']}\" ;\n"
                f"    lho:hasLabReference <{LHO}{LABS[lab]}> ;\n"
                f"    lho:hasCountry lho:{COUNTRIES[r['country']]} ;\n"
                f"    lho:hasBreed lho:{BREEDS[r['breed']]} ;\n"
                f"    lho:hasSampleType lho:{SAMPLE_TYPES[r['sample_type']]} ;\n"
                f"    lho:hasDiagnosticTest lho:{TESTS[r['diagnostic_test']]} ;\n"
                f"    lho:hasPathogen lho:{PATHOGENS[r['pathogen']][0]} ;\n"
                f"    lho:hasSampleResult lho:{'CS05' if r['result'] else 'CS04'} .\n"
            )
        (DATA_DIR / f"lab{lab}.ttl").write_text("\n".join(lines), encoding="utf-8")
    for lab in PIG_LAB_PROFILES:
        lab_iri = f"<{DATA_NS}lab/{lab}>"
        lines = [header.replace("\n\n", "\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n\n"),
                 # LHO V1.5 lists laboratory references 1 to 6; the pig laboratories are declared here.
                 f"{lab_iri} a lho:LabReference ; rdfs:label \"{lab}\" .\n"]
        for r in (x for x in records if x["lab"] == lab):
            iri = f"<{DATA_NS}lab{lab}/sample/{r['sample_number']}>"
            lines.append(
                f"{iri} a lho:PigSample ;\n"
                f"    lho:CS18 \"{r['sample_number']}\" ;\n"
                f"    lho:CS17 \"{r['date']}\" ;\n"
                f"    lho:hasLabReference {lab_iri} ;\n"
                f"    lho:hasCountry lho:Spain ;\n"
                f"    lho:hasBreed lho:Meat ;\n"
                f"    lho:hasProductionStages lho:{PIG_STAGES[r['production_stage']]} ;\n"
                f"    lho:hasSampleType lho:{PIG_SAMPLE_TYPES[r['sample_type']]} ;\n"
                f"    lho:hasDiagnosticTest lho:CS07 ;\n"
                f"    lho:hasPathogen lho:{PIG_PATHOGENS[r['pathogen']][0]} ;\n"
                f"    lho:hasSampleResult lho:{'CS05' if r['result'] else 'CS04'} .\n"
            )
        (DATA_DIR / f"lab{lab}.ttl").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records = generate()
    write_csv(records)
    write_turtle(records)
    positives = sum(r["result"] for r in records)
    print(f"Wrote {len(records)} synthetic records for {len(LAB_PROFILES) + len(PIG_LAB_PROFILES)} laboratories "
          f"({positives} positive) to {DATA_DIR}")


if __name__ == "__main__":
    main()
