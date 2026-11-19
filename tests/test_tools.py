"""Check the knowledge-graph tools against pandas, without any language model."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lho_demo.graph import KnowledgeGraph, TermNotFound  # noqa: E402


@pytest.fixture(scope="module")
def kg():
    return KnowledgeGraph()


@pytest.fixture(scope="module")
def df():
    frame = pd.read_csv(ROOT / "data" / "synthetic" / "records.csv", keep_default_na=False)
    frame["year"] = frame["date"].str[:4].astype(int)
    return frame


def test_total_matches_csv(kg, df):
    result = kg.statistics()
    assert (result["tested"], result["positive"]) == (len(df), int(df.result.sum()))


@pytest.mark.parametrize("pathogen", ["BRSV", "BCV", "PI3", "PM", "MH", "HS", "MB"])
def test_every_pathogen_and_year_matches_csv(kg, df, pathogen):
    rows = kg.statistics(pathogen=pathogen, group_by="year")["rows"]
    for row in rows:
        part = df[(df.pathogen == pathogen) & (df.year == int(row["year"]))]
        assert (row["tested"], row["positive"]) == (len(part), int(part.result.sum()))


def test_combined_filters_match_csv(kg, df):
    part = df[(df.lab == 4) & (df.breed == "Suckler") & (df.diagnostic_test == "PCR")
              & (df.date >= "2021-03-01") & (df.date <= "2023-06-31")]
    result = kg.statistics(lab="lab 4", breed="suckler", diagnostic_test="pcr",
                           date_from="2021-03", date_to="2023-06")
    assert (result["tested"], result["positive"]) == (len(part), int(part.result.sum()))


def test_class_filter_uses_the_ontology_hierarchy(kg, df):
    bacteria = df[df.pathogen.isin(["PM", "MH", "HS", "MB", "MHYO", "LAWS"])]
    assert kg.statistics(pathogen="bacteria")["tested"] == len(bacteria)
    viruses = df[df.pathogen.isin(["BRSV", "BCV", "PI3", "SIV", "PRRS"])]
    assert kg.statistics(pathogen="Pathogenic Virus")["positive"] == int(viruses.result.sum())


@pytest.mark.parametrize("word,expected", [
    ("kweek", "Culture"), ("polymerase chain reaction", "PCR"),
    ("België", "Belgium"), ("Holland", "The Netherlands"),
])
def test_synonyms_and_other_languages_resolve(kg, word, expected):
    dimension = "diagnostic_test" if expected in ("Culture", "PCR") else "country"
    assert kg.display(kg.resolve(dimension, word), dimension) == expected


def test_synonym_of_a_pathogen(kg, df):
    assert kg.statistics(pathogen="Bovine orthopneumovirus")["tested"] == int((df.pathogen == "BRSV").sum())


def test_unknown_value_lists_the_valid_ones(kg):
    with pytest.raises(TermNotFound, match="Valid values"):
        kg.statistics(pathogen="Salmonella")


def test_no_match_returns_zero_with_a_warning(kg):
    result = kg.statistics(pathogen="BRSV", year=2030)
    assert result["tested"] == 0 and "Do not guess" in result["note"]


def test_ontology_examples_are_not_counted_as_data(kg):
    # LHO V1.5 contains example samples from Scotland; they are not data.
    assert "Scotland" not in [kg.display(i) for i in kg.dimension_values["country"]]


@pytest.mark.parametrize("query", [
    "INSERT DATA { <a:a> <a:b> <a:c> }", "DELETE WHERE { ?s ?p ?o }", "DROP ALL",
    "SELECT * WHERE { SERVICE <http://example.org/sparql> { ?s ?p ?o } }",
])
def test_sparql_tool_is_read_only(kg, query):
    with pytest.raises(TermNotFound):
        kg.run_sparql(query)


def test_month_filter_matches_csv(kg, df):
    part = df[(df.pathogen == "BRSV") & df.date.str.startswith("2022-01")]
    result = kg.statistics(pathogen="BRSV", month="2022-01")
    assert (result["tested"], result["positive"]) == (len(part), int(part.result.sum()))
    every_january = df[df.date.str[5:7] == "01"]
    assert kg.statistics(month="January")["tested"] == len(every_january)


def test_search_finds_a_term_inside_a_phrase(kg):
    matches = kg.search_terms("geographic neighbours of Belgium")["matches"]
    assert matches and matches[0]["term"] == "Belgium"


def test_grouped_result_also_gives_the_overall_rate(kg, df):
    part = df[(df.pathogen == "BCV")]
    result = kg.statistics(pathogen="bovine coronavirus", group_by="lab")
    assert result["overall"]["positivity_percent"] == round(100 * part.result.mean(), 1)
    assert result["overall"]["tested"] == len(part)


def test_filter_on_the_grouped_dimension_is_ignored(kg):
    result = kg.statistics(pathogen="MH", diagnostic_test="PCR", group_by="diagnostic_test")
    assert len(result["rows"]) > 1 and "ignored" in result["note"]


def test_placeholder_value_is_ignored(kg, df):
    result = kg.statistics(pathogen="Mycoplasma bovis", breed="Breed", group_by="breed")
    assert result["highest_positivity"] == "Veal"


def test_species_filter_and_grouping_match_csv(kg, df):
    pigs = df[df.species == "Pig"]
    result = kg.statistics(species="pigs")
    assert (result["tested"], result["positive"]) == (len(pigs), int(pigs.result.sum()))
    rows = {r["species"]: r["tested"] for r in kg.statistics(group_by="species")["rows"]}
    assert rows == {"Cattle": int((df.species == "Cattle").sum()), "Pig": len(pigs)}


def test_pig_pathogen_and_production_stage_match_csv(kg, df):
    part = df[(df.pathogen == "PRRS") & (df.production_stage == "Nursery")]
    result = kg.statistics(pathogen="PRRS", production_stage="nursery", country="Spain")
    assert (result["tested"], result["positive"]) == (len(part), int(part.result.sum()))


def test_a_sample_type_that_is_a_class_in_lho_is_matched_as_a_value(kg, df):
    assert kg.statistics(sample_type="faeces")["tested"] == int((df.sample_type == "Feces").sum())


def test_species_word_in_dutch(kg, df):
    assert kg.statistics(species="varkens")["tested"] == int((df.species == "Pig").sum())


def test_several_values_in_one_filter(kg, df):
    part = df[df.country.isin(["Belgium", "France"])]
    result = kg.statistics(country="Belgium, France")
    assert (result["tested"], result["positive"]) == (len(part), int(part.result.sum()))
    part = df[(df.pathogen == "MH") & df.diagnostic_test.isin(["PCR", "Culture"])]
    assert kg.statistics(pathogen="MH", diagnostic_test="PCR and culture")["tested"] == len(part)


def test_listing_every_value_is_the_same_as_no_filter(kg, df):
    assert kg.statistics(species="Cattle, Pig")["tested"] == len(df)


def test_result_says_which_species_were_counted(kg):
    assert kg.statistics()["species_included"] == ["Cattle", "Pig"]
    assert "species_included" not in kg.statistics(species="pigs")
