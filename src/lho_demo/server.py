"""MCP server: the tools a language model may use on the LHO knowledge graph.

Run (stdio, for local clients such as the agent in this repository):
    python -m lho_demo.server
Run (HTTP, for remote clients):
    python -m lho_demo.server --http

The server is read-only. Tools take plain words, never IRIs or SPARQL, and
answer with small JSON objects. A wrong word gives an error that lists the
valid values, so the model can correct itself.
"""
from __future__ import annotations

import os
import sys

from mcp.server.mcpserver import MCPServer

from .graph import KnowledgeGraph, TermNotFound

INSTRUCTIONS = (
    "Tools for synthetic diagnostic test records of cattle (six laboratories) and pigs (two "
    "laboratories), described with the Livestock Health Ontology (LHO). Use test_statistics for any number. "
    "Use search_terms or describe_term for the meaning of a term. Never invent numbers."
)

server = MCPServer(name="lho-knowledge-graph", instructions=INSTRUCTIONS, version="0.1.0")
_graph: KnowledgeGraph | None = None


def graph() -> KnowledgeGraph:
    global _graph
    if _graph is None:
        _graph = KnowledgeGraph()
    return _graph


def _clean(value: str | int) -> str | None:
    """Models often send '', 'null' or 'all' for a filter they do not want."""
    text = str(value).strip()
    return None if text.lower() in ("", "null", "none", "all", "any", "n/a") else text


def _safe(call):
    try:
        return call()
    except TermNotFound as error:
        return {"error": str(error)}


@server.tool()
def graph_overview() -> dict:
    """What the graph contains: number of records, date range, and the valid values of
    every dimension (species, pathogen, country, lab, breed, sample_type, diagnostic_test,
    production_stage)."""
    return graph().overview()


@server.tool()
def test_statistics(
    group_by: str = "",
    pathogen: str = "",
    country: str = "",
    lab: str | int = "",
    breed: str = "",
    sample_type: str = "",
    diagnostic_test: str = "",
    production_stage: str = "",
    year: str | int = "",
    month: str | int = "",
    date_from: str = "",
    date_to: str = "",
    species: str = "",
) -> dict:
    """Count test records: tested, positive, negative and positivity_percent.

    Use this for every question about numbers, percentages, comparisons or trends.
    Leave a filter empty when the question does not mention it.

    group_by: leave EMPTY for one number or one rate ("how many", "what is the positivity").
        Set it ONLY to compare groups ("which ... highest, lowest, most"): one of species,
        pathogen, country, lab, breed, sample_type, diagnostic_test, production_stage, year,
        year_month, month_of_year.
        The result then has "overall" (the whole selection), one row per group, and
        highest_positivity, lowest_positivity, most_tested, most_positive.
        "Which pathogen has the highest positivity?" -> group_by="pathogen".
        "Which laboratory tested the most samples?" -> group_by="lab".
        "Which breed ... for Mycoplasma bovis?" -> group_by="breed", pathogen="Mycoplasma bovis"
        (do not also fill the breed filter).
    pathogen: cattle: BRSV, BCV, PI3, "Pasteurella multocida", "Mannheimia haemolytica",
        "Histophilus somni", "Mycoplasma bovis". Pigs: PRRS, "Swine influenza virus",
        "Mycoplasma hyopneumoniae", "Lawsonia intracellularis". Or a group: "bacteria", "virus".
    country: Belgium, France, Ireland, The Netherlands (cattle), Spain (pigs).
    lab: 1 to 6 (cattle), 7 and 8 (pigs).
    breed: Beef, Dairy, Suckler, Veal, Mixed, Unknown (cattle), Meat (pigs).
    sample_type: Autopsy, BAL, Swab, TTA, Tissue, Feces, Fluid, Unknown, Missing.
    diagnostic_test: PCR, Culture, NPS.
    production_stage (pigs only): Suckling, Nursery, Weaning, Finishing, Breeding.
    year: four digits, for example 2024.
    month: "2022-01" for one month of one year, or 1 to 12 for that month in every year.
    date_from, date_to: 2024, 2024-03 or 2024-03-15 (both ends included).
    species: leave EMPTY unless the question itself names an animal. Empty means both species,
        which is what "overall", "in total" and "all tests" ask for. Fill "Pig" only for a
        question about pigs, "Cattle" only for a question about cattle.
    Several values for one filter may be given with commas: country="Belgium, France".
    Synonyms and other languages work (for example "kweek" for Culture).
    """
    return _safe(lambda: graph().statistics(
        group_by=_clean(group_by), species=_clean(species), pathogen=_clean(pathogen),
        production_stage=_clean(production_stage), country=_clean(country),
        lab=_clean(lab), breed=_clean(breed), sample_type=_clean(sample_type),
        diagnostic_test=_clean(diagnostic_test), year=_clean(year), month=_clean(month),
        date_from=_clean(date_from), date_to=_clean(date_to)))


@server.tool()
def list_values(dimension: str) -> dict:
    """List the valid values of one dimension with the number of tests for each.
    dimension: species, pathogen, country, lab, breed, sample_type, diagnostic_test
    or production_stage."""
    return _safe(lambda: graph().list_values(dimension.strip()))


@server.tool()
def search_terms(text: str) -> dict:
    """Find ontology terms by name, abbreviation or synonym, in any language.
    Use it when you are not sure which term the user means."""
    return _safe(lambda: graph().search_terms(text))


@server.tool()
def describe_term(term: str) -> dict:
    """Definition of one ontology term: what it is, its parent classes, synonyms,
    names in other languages and its relations (which disease a pathogen causes, which
    species it affects, the neighbours of a country). Pass ONE term, not a sentence.
    Use it for "What is BRSV?", "Is PI3 a virus?", "Which countries border Belgium?" (term: Belgium)."""
    return _safe(lambda: graph().describe_term(term))


if os.environ.get("LHO_ENABLE_SPARQL") == "1":
    @server.tool()
    def run_sparql(query: str) -> dict:
        """Expert tool: run a read-only SPARQL SELECT (prefix lho: is defined). Maximum 50 rows.
        Prefer test_statistics; use this only when no other tool can answer."""
        return _safe(lambda: graph().run_sparql(query))


def main() -> None:
    graph()                                   # load once, fail early if data are missing
    if "--http" in sys.argv:
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
