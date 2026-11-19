"""Build the 40 evaluation questions and their expected answers.

The expected answers are computed with pandas from data/synthetic/records.csv.
They do not pass through SPARQL, the MCP server or the model, so the test is
an independent check of the whole chain.

Run:  python eval/make_questions.py     (writes eval/questions.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_csv(ROOT / "data" / "synthetic" / "records.csv", keep_default_na=False)
df["year"] = df["date"].str[:4].astype(int)
df["month"] = df["date"].str[5:7].astype(int)

BACTERIA = ["PM", "MH", "HS", "MB", "MHYO", "LAWS"]      # cattle and pig pathogens
VIRUSES = ["BRSV", "BCV", "PI3", "SIV", "PRRS"]
pigs = df[df.species == "Pig"]
PATHOGEN_NAMES = {
    "BRSV": ["BRSV", "respiratory syncytial"], "BCV": ["BCV", "coronavirus", "corona virus"],
    "PI3": ["PI3", "parainfluenza"], "PM": ["PM", "Pasteurella multocida"],
    "MH": ["MH", "Mannheimia haemolytica"], "HS": ["HS", "Histophilus"],
    "MB": ["MB", "Mycoplasma bovis"],
    "SIV": ["swine influenza"], "MHYO": ["hyopneumoniae"], "LAWS": ["Lawsonia"],
    "PRRS": ["PRRS", "Porcine reproductive"],
}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def tested(d: pd.DataFrame) -> int:
    return int(len(d))


def positive(d: pd.DataFrame) -> int:
    return int(d["result"].sum())


def rate(d: pd.DataFrame) -> float:
    return round(100 * d["result"].sum() / len(d), 1)


def top(d: pd.DataFrame, column: str, how: str = "rate", lowest: bool = False):
    """Return the winning group and the margin to the runner-up."""
    grouped = d.groupby(column)["result"]
    values = (100 * grouped.mean()) if how == "rate" else grouped.count()
    ordered = values.sort_values(ascending=lowest)
    return ordered.index[0], abs(float(ordered.iloc[0] - ordered.iloc[1]))


questions: list[dict] = []
margins: list[tuple[int, float]] = []


def add(category: str, question: str, *, numbers=None, any_text=None, all_text=None, refusal=False,
        compare="", rivals=None):
    questions.append({"id": len(questions) + 1, "category": category, "question": question,
                      "expect": {"numbers": numbers or [], "any_text": any_text or [],
                                 "all_text": all_text or [], "refusal": refusal,
                                 # the groups the agent must really compare (no lucky guesses)
                                 "compare": compare,
                                 # the other groups: the answer must name the winner first
                                 "rivals": rivals or []}})


def add_ranking(category: str, question: str, frame: pd.DataFrame, column: str, how="rate",
                lowest=False, names=None):
    winner, margin = top(frame, column, how, lowest)
    margins.append((len(questions) + 1, margin))
    rivals = [name for value in frame[column].unique() if value != winner
              for name in (names(value) if names else [str(value)])]
    add(category, question, any_text=names(winner) if names else [str(winner)], compare=column,
        rivals=rivals)


# --- A. Counts -------------------------------------------------------------------
add("count", "How many test records are in the graph in total?", numbers=[tested(df)])
add("count", "How many tests were positive for BRSV in 2024?",
    numbers=[positive(df[(df.pathogen == "BRSV") & (df.year == 2024)])])
add("count", "How many samples were tested for Mycoplasma bovis in Ireland?",
    numbers=[tested(df[(df.pathogen == "MB") & (df.country == "Ireland")])])
add("count", "How many PCR tests did lab 2 perform?",
    numbers=[tested(df[(df.diagnostic_test == "PCR") & (df.lab == 2)])])
add("count", "How many tests on veal calves were positive for Pasteurella multocida?",
    numbers=[positive(df[(df.breed == "Veal") & (df.pathogen == "PM")])])
add("pigs", "How many pig samples were tested for PRRS in Spain?",
    numbers=[tested(pigs[pigs.pathogen == "PRRS"])])
add("count", "How many tests were done in France from 2020 to 2022?",
    numbers=[tested(df[(df.country == "France") & df.year.between(2020, 2022)])])
add("count", "How many positive Mannheimia haemolytica results came from autopsy samples in lab 4?",
    numbers=[positive(df[(df.pathogen == "MH") & (df.sample_type == "Autopsy") & (df.lab == 4)])])

# --- B. Positivity ---------------------------------------------------------------
add("positivity", "What is the positivity rate of bovine coronavirus across all laboratories?",
    numbers=[rate(df[df.pathogen == "BCV"])])
add("positivity", "What percentage of PI3 tests were positive in Belgium?",
    numbers=[rate(df[(df.pathogen == "PI3") & (df.country == "Belgium")])])
add("positivity", "What is the positivity percentage for Histophilus somni when tested by culture?",
    numbers=[rate(df[(df.pathogen == "HS") & (df.diagnostic_test == "Culture")])])
add("positivity", "What was the BRSV positivity rate in January 2022?",
    numbers=[rate(df[(df.pathogen == "BRSV") & (df.year == 2022) & (df.month == 1)])])
add("pigs", "What is the positivity rate of swine influenza virus in pigs?",
    numbers=[rate(pigs[pigs.pathogen == "SIV"])])
add("positivity", "What is the positivity rate for bovine coronavirus in dairy cattle tested with PCR?",
    numbers=[rate(df[(df.pathogen == "BCV") & (df.breed == "Dairy") & (df.diagnostic_test == "PCR")])])

# --- C. Comparisons --------------------------------------------------------------
add_ranking("comparison", "Which pathogen has the highest positivity rate overall?", df, "pathogen",
            names=lambda w: PATHOGEN_NAMES[w])
add_ranking("comparison", "Which pathogen has the lowest positivity rate overall?", df, "pathogen",
            lowest=True, names=lambda w: PATHOGEN_NAMES[w])
add_ranking("comparison", "Which laboratory tested the most samples?", df, "lab", how="count",
            names=lambda w: [f"lab {w}", f"laboratory {w}"])
add_ranking("comparison", "Which country has the highest positivity rate for BRSV?",
            df[df.pathogen == "BRSV"], "country")
add_ranking("comparison", "Which breed has the highest positivity rate for Mycoplasma bovis?",
            df[df.pathogen == "MB"], "breed")
add_ranking("comparison", "Which diagnostic test gives the highest positivity rate for Pasteurella multocida?",
            df[df.pathogen == "PM"], "diagnostic_test")
add_ranking("comparison", "For Mannheimia haemolytica, which gives a higher positivity rate: PCR or culture?",
            df[(df.pathogen == "MH") & df.diagnostic_test.isin(["PCR", "Culture"])], "diagnostic_test")
add_ranking("pigs", "Which pig pathogen has the highest positivity rate?", pigs, "pathogen",
            names=lambda w: PATHOGEN_NAMES[w])

# --- D. Time ---------------------------------------------------------------------
add_ranking("time", "In which year was the BRSV positivity rate highest?", df[df.pathogen == "BRSV"], "year")
winner, margin = top(df[df.pathogen == "BRSV"], "month")
margins.append((len(questions) + 1, margin))
add("time", "In which month of the year is BRSV positivity highest?",
    any_text=[MONTHS[winner - 1], f"month {winner:02d}", f"month {winner}", f"({winner:02d})"],
    compare="month_of_year", rivals=[m for i, m in enumerate(MONTHS, start=1) if i != winner])
add_ranking("pigs", "In pigs, which production stage has the highest positivity rate for Mycoplasma hyopneumoniae?",
            pigs[pigs.pathogen == "MHYO"], "production_stage")

# --- E. Ontology reasoning: a class instead of a single pathogen ----------------
add("ontology reasoning", "How many tests were positive for bacterial pathogens?",
    numbers=[positive(df[df.pathogen.isin(BACTERIA)])])
add("ontology reasoning", "What is the positivity rate of viral pathogens in the Netherlands?",
    numbers=[rate(df[df.pathogen.isin(VIRUSES) & (df.country == "The Netherlands")])])
add("ontology reasoning", "How many tests for viruses were done with NPS?",
    numbers=[tested(df[df.pathogen.isin(VIRUSES) & (df.diagnostic_test == "NPS")])])
add("ontology reasoning", "What is the positivity rate of bacterial pathogens in beef cattle?",
    numbers=[rate(df[df.pathogen.isin(BACTERIA) & (df.breed == "Beef")])])

# --- F. Ontology knowledge -------------------------------------------------------
add("ontology knowledge", "What is BRSV?", any_text=["respiratory syncytial"])
add("ontology knowledge", "Is PI3 a virus or a bacterium?", any_text=["virus"])
add("ontology knowledge", "What does TTA stand for?",
    any_text=["trans-tracheal aspirate", "transtracheal aspirate", "trans tracheal aspirate"])
add("ontology knowledge", "According to the ontology, which type of disease does Pasteurella multocida cause?",
    any_text=["bacterial disease"])
add("ontology knowledge", "According to the ontology, which countries are geographic neighbours of Belgium?",
    all_text=["France", "Netherlands"])

# --- G. Synonyms and other languages --------------------------------------------
add("multilingual", "Hoeveel testen met kweek waren positief?",
    numbers=[positive(df[df.diagnostic_test == "Culture"])])
add("multilingual", "Hoeveel testen zijn er uitgevoerd in België?",
    numbers=[tested(df[df.country == "Belgium"])])
add("multilingual", "How many tests were positive for Bovine orthopneumovirus?",
    numbers=[positive(df[df.pathogen == "BRSV"])])

# --- H. No data: the correct answer is that the graph cannot answer --------------
add("no data", "How many tests were positive for Salmonella?", refusal=True)
add("no data", "How many poultry samples were positive for infectious bronchitis?", refusal=True)
add("no data", "How many BRSV tests were positive in 2030?", refusal=True)

if __name__ == "__main__":
    out = ROOT / "eval" / "questions.json"
    out.write_text(json.dumps(questions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(questions)} questions to {out}")
    close = [(i, round(m, 2)) for i, m in margins if m < 1.0]
    if close:
        print("Rankings with a margin below 1.0 (consider rewording):", close, file=sys.stderr)
