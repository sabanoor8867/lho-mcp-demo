"""Paths, namespaces and settings shared by every module."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_FILE = ROOT / "ontology" / "LivestockHealthOntology_V1.5.owl"
DATA_DIR = ROOT / "data" / "synthetic"
RECORDS_CSV = DATA_DIR / "records.csv"

LHO = "http://www.purl.org/decide/LiveStockHealthOnto/LHO#"
DATA_NS = "https://example.org/lho-demo/"
GRAPH_NS = DATA_NS + "graph/"

# Model settings. Change them with environment variables, not in the code.
PROVIDER = os.environ.get("LHO_PROVIDER", "ollama")
MODEL = os.environ.get("LHO_MODEL", "qwen2.5:7b")
MAX_TOOL_ROUNDS = int(os.environ.get("LHO_MAX_TOOL_ROUNDS", "6"))

# Each analysis dimension maps to one LHO object property on a sample.
DIMENSIONS = {
    "pathogen": "hasPathogen",
    "country": "hasCountry",
    "lab": "hasLabReference",
    "breed": "hasBreed",
    "sample_type": "hasSampleType",
    "diagnostic_test": "hasDiagnosticTest",
    "production_stage": "hasProductionStages",   # pigs only
}
# A species is not a property of a sample in LHO: it follows from the sample's
# class. Species individual -> the class of its samples.
SPECIES = {"Cattle": "CattleSample", "Pig": "PigSample"}
DATE_PROPERTY = "CS17"          # lho:CS17, label "date", stored as "YYYY-MM-DD"
SAMPLE_NUMBER_PROPERTY = "CS18"  # lho:CS18, label "hasSampleNumber"
RESULT_PROPERTY = "hasSampleResult"
POSITIVE = "CS05"                # lho:CS05, label "1"
NEGATIVE = "CS04"                # lho:CS04, label "0"

# Everyday words that LHO V1.5 has no label for. They are candidates to add to
# the ontology as skos:altLabel; until then the server maps them here.
EXTRA_ALIASES = {
    "pathogen": {
        "bacteria": "PathogenicBacterium",
        "bacterium": "PathogenicBacterium",
        "bacterial": "PathogenicBacterium",
        "bacterial pathogens": "PathogenicBacterium",
        "virus": "PathogenicVirus",
        "viruses": "PathogenicVirus",
        "viral": "PathogenicVirus",
        "viral pathogens": "PathogenicVirus",
    },
    "country": {"netherlands": "TheNetherlands", "holland": "TheNetherlands", "nederland": "TheNetherlands"},
    "species": {"pigs": "Pig", "swine": "Pig", "porcine": "Pig", "piglets": "Pig", "varken": "Pig",
                "varkens": "Pig", "cow": "Cattle", "cows": "Cattle", "bovine": "Cattle", "calves": "Cattle",
                "rundvee": "Cattle", "runderen": "Cattle"},
    "production_stage": {"sows": "Breeding", "sow": "Breeding", "gilts": "Breeding", "boars": "Breeding",
                         "fattening pigs": "Finishing", "finishers": "Finishing", "weaners": "Weaning"},
}
