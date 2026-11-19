"""The knowledge graph and every question the tools can ask of it.

One in-memory Oxigraph store holds:
  * the Livestock Health Ontology (LHO V1.5), in its own named graph
  * one named graph per laboratory, with synthetic diagnostic test records

The language model never writes IRIs or SPARQL. It passes plain words
("BRSV", "kweek", "bacteria", "lab 3"); this module resolves them to ontology
terms through labels and synonyms, builds the SPARQL from fixed templates,
and returns small JSON results. That keeps answers correct and queries safe.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pyoxigraph import NamedNode, RdfFormat, Store

from . import config as cfg

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
PREFIXES = (
    f"PREFIX lho: <{cfg.LHO}>\n"
    f"PREFIX rdfs: <{RDFS}>\n"
    f"PREFIX owl: <{OWL}>\n"
    f"PREFIX skos: <{SKOS}>\n"
)
TIME_GROUPS = {
    "year": 'SUBSTR(?date, 1, 4)',
    "year_month": 'SUBSTR(?date, 1, 7)',
    "month_of_year": 'SUBSTR(?date, 6, 2)',
}
MAX_ROWS = 40
MONTH_NAMES = {name: f"{i:02d}" for i, names in enumerate([
    ("january", "jan", "januari"), ("february", "feb", "februari"), ("march", "mar", "maart"),
    ("april", "apr"), ("may", "mei"), ("june", "jun", "juni"), ("july", "jul", "juli"),
    ("august", "aug", "augustus"), ("september", "sep", "sept"), ("october", "oct", "oktober", "okt"),
    ("november", "nov"), ("december", "dec")], start=1) for name in names}
DATA_ONLY = f"FILTER(?g != <{cfg.GRAPH_NS}ontology>)"


class TermNotFound(ValueError):
    """Raised with a message the model can act on (it lists the valid values)."""


@dataclass
class Term:
    iri: str
    kind: str                      # "class" or "individual"
    label: str
    names: set[str] = field(default_factory=set)
    definition: str = ""
    types: list[str] = field(default_factory=list)      # for individuals
    parents: list[str] = field(default_factory=list)    # for classes

    @property
    def local(self) -> str:
        return re.split(r"[#/]", self.iri)[-1]


def normalise(text: str) -> str:
    """Lower-case, drop accents, keep only letters and digits (any script)."""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.lower() if ch.isalnum())


def prettify(label: str) -> str:
    """'BovineCoronaVirus' -> 'Bovine Corona Virus'. Abbreviations stay as they are."""
    if " " in label:
        return label
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", label)


class KnowledgeGraph:
    def __init__(self, ontology_file: Path = cfg.ONTOLOGY_FILE, data_dir: Path = cfg.DATA_DIR):
        self.store = Store()
        self.store.load(path=str(ontology_file), format=RdfFormat.RDF_XML,
                        to_graph=NamedNode(cfg.GRAPH_NS + "ontology"))
        self.lab_files = sorted(data_dir.glob("lab*.ttl"))
        if not self.lab_files:
            raise FileNotFoundError(
                f"No laboratory files in {data_dir}. Run: python -m lho_demo.generate_data")
        for path in self.lab_files:
            self.store.load(path=str(path), format=RdfFormat.TURTLE,
                            to_graph=NamedNode(cfg.GRAPH_NS + path.stem))
        self.terms: dict[str, Term] = {}
        self._build_term_index()
        self.dimension_values: dict[str, list[str]] = {}
        self.dimension_lookup: dict[str, dict[str, str]] = {}
        self.species_class: dict[str, str] = {}      # species individual -> class of its samples
        self._build_dimensions()

    # ------------------------------------------------------------------ SPARQL
    def select(self, query: str) -> list[dict[str, str]]:
        """Run a SELECT over the union of all graphs and return plain strings."""
        result = self.store.query(PREFIXES + query, use_default_graph_as_union=True)
        names = [v.value for v in result.variables]
        return [{n: (row[n].value if row[n] is not None else None) for n in names} for row in result]

    # -------------------------------------------------------------- term index
    def _build_term_index(self) -> None:
        for row in self.select(
            "SELECT DISTINCT ?e ?kind WHERE { VALUES (?t ?kind) { (owl:Class 'class') "
            "(owl:NamedIndividual 'individual') } ?e a ?t . FILTER(isIRI(?e)) }"
        ):
            term = self.terms.setdefault(row["e"], Term(iri=row["e"], kind=row["kind"], label=""))
            if row["kind"] == "individual":
                term.kind = "individual"     # an IRI used as both is treated as a value
        literals = self.select(
            "SELECT ?e ?p ?o (LANG(?o) AS ?lang) WHERE { ?e ?p ?o . FILTER(isLiteral(?o)) "
            "FILTER(?p IN (rdfs:label, skos:prefLabel, skos:altLabel, rdfs:comment) "
            "|| STRENDS(STR(?p), 'hasExactSynonym')) }"
        )
        labels: dict[str, list[tuple[str, str]]] = {}
        synonyms: dict[str, list[tuple[str, str]]] = {}
        for row in literals:
            term = self.terms.get(row["e"])
            if term is None:
                continue
            predicate, value, lang = row["p"], row["o"].strip(), row["lang"] or ""
            if predicate.endswith("comment"):
                if lang in ("", "en") and (not term.definition or len(value) > len(term.definition)):
                    term.definition = " ".join(value.split())
                continue
            term.names.add(value)
            if predicate.endswith("#label") or predicate.endswith("prefLabel"):
                labels.setdefault(term.iri, []).append((lang, value))
            elif predicate.endswith("hasExactSynonym"):
                synonyms.setdefault(term.iri, []).append((lang, value))
        for term in self.terms.values():
            english = [v for lang, v in labels.get(term.iri, []) if lang in ("", "en")]
            term.label = prettify(english[0]) if english else prettify(term.local)
            term.names.update({term.local, term.label})
        for row in self.select("SELECT ?i ?c WHERE { ?i a ?c . ?i a owl:NamedIndividual . "
                               "FILTER(?c != owl:NamedIndividual && ?c != owl:Class && isIRI(?c)) }"):
            if row["i"] in self.terms:
                self.terms[row["i"]].types.append(row["c"])
        children: dict[str, int] = {}
        for row in self.select("SELECT ?c ?p WHERE { ?c rdfs:subClassOf ?p . FILTER(isIRI(?c) && isIRI(?p)) }"):
            if row["c"] in self.terms:
                self.terms[row["c"]].parents.append(row["p"])
            children[row["p"]] = children.get(row["p"], 0) + 1
        # An individual that is the only member of a leaf class shares that
        # class's names: lho:BRSV is the single instance of the AGROVOC class
        # "bovine respiratory syncytial virus", which carries the synonyms.
        members: dict[str, list[str]] = {}
        for term in self.terms.values():
            for cls in term.types:
                members.setdefault(cls, []).append(term.iri)
        self.full_name: dict[str, str] = {}
        for cls, iris in members.items():
            if len(iris) == 1 and children.get(cls, 0) == 0 and cls in self.terms:
                individual, klass = self.terms[iris[0]], self.terms[cls]
                individual.names.update(klass.names)
                if not individual.definition:
                    individual.definition = klass.definition
                if len(klass.label) > len(individual.label):
                    self.full_name[individual.iri] = klass.label
        for term in self.terms.values():
            english = [v for lang, v in synonyms.get(term.iri, []) if lang in ("", "en")]
            longest = re.sub(r"\s*\([^)]*\)\s*$", "", max(english, key=len, default=""))
            if len(longest) > len(term.label):
                self.full_name[term.iri] = longest

    def display(self, iri: str, dimension: str | None = None) -> str:
        term = self.terms.get(iri)
        label = term.label if term else re.split(r"[#/]", iri)[-1]
        if dimension == "lab":
            return f"Lab {label}"
        # Only pathogens get their full name added: "PM (Pasteurella multocida)".
        is_pathogen = dimension == "pathogen" or (
            dimension is None and term is not None
            and any(c.endswith("#Pathogen") for c in self._ancestors(term.types)))
        full = self.full_name.get(iri) if is_pathogen else None
        return f"{label} ({full})" if full else label

    # -------------------------------------------------------------- dimensions
    def _build_dimensions(self) -> None:
        for dimension, prop in cfg.DIMENSIONS.items():
            rows = self.select(f"SELECT DISTINCT ?v WHERE {{ GRAPH ?g {{ ?s lho:{prop} ?v }} {DATA_ONLY} }}")
            values = sorted((r["v"] for r in rows), key=lambda iri: self.display(iri, dimension))
            self.dimension_values[dimension] = values
            lookup: dict[str, str] = {}
            candidates = list(values)
            if dimension == "pathogen":          # also allow classes: "bacteria", "virus"
                for iri in values:
                    for cls in self._ancestors(self.terms[iri].types):
                        if cls not in candidates and not cls.endswith("#Pathogen"):
                            candidates.append(cls)
            for iri in candidates:
                term = self.terms.get(iri)
                names = set(term.names) if term else {re.split(r"[#/]", iri)[-1]}
                names.add(self.display(iri, dimension))
                for name in names:
                    lookup.setdefault(normalise(name), iri)
            for alias, local in cfg.EXTRA_ALIASES.get(dimension, {}).items():
                lookup[normalise(alias)] = cfg.LHO + local
            self.dimension_lookup[dimension] = lookup

        # Species: which sample classes occur in the data, and the names of each species.
        present = {r["k"] for r in self.select(
            f"SELECT DISTINCT ?k WHERE {{ GRAPH ?g {{ ?s a ?k ; lho:{cfg.RESULT_PROPERTY} ?r }} {DATA_ONLY} }}")}
        lookup = {}
        values = []
        for species, sample_class in cfg.SPECIES.items():
            if cfg.LHO + sample_class not in present:
                continue
            iri = cfg.LHO + species
            self.species_class[iri] = cfg.LHO + sample_class
            values.append(iri)
            for name in (self.terms[iri].names if iri in self.terms else {species}):
                lookup.setdefault(normalise(name), iri)
        for alias, local in cfg.EXTRA_ALIASES.get("species", {}).items():
            lookup[normalise(alias)] = cfg.LHO + local
        self.dimension_values["species"] = values
        self.dimension_lookup["species"] = lookup

    def _ancestors(self, classes: list[str]) -> list[str]:
        seen: list[str] = []
        stack = list(classes)
        while stack:
            cls = stack.pop()
            if cls in seen or cls not in self.terms:
                continue
            seen.append(cls)
            stack.extend(self.terms[cls].parents)
        return seen

    def resolve(self, dimension: str, text: str) -> str:
        """Turn a word from the user into the IRI of a value of this dimension."""
        if dimension not in self.dimension_lookup:
            raise TermNotFound(f"Unknown dimension '{dimension}'. Use one of: {', '.join(self.dimension_lookup)}.")
        lookup = self.dimension_lookup[dimension]
        key = normalise(text)
        if dimension == "lab":
            digits = re.sub(r"\D", "", str(text))
            key = normalise(f"Lab {digits}") if digits else key
        if key in lookup:
            return lookup[key]
        close = difflib.get_close_matches(key, list(lookup), n=1, cutoff=0.86)
        if close:
            return lookup[close[0]]
        valid = ", ".join(self.display(iri, dimension) for iri in self.dimension_values[dimension])
        raise TermNotFound(f"'{text}' is not a known {dimension} in this graph. Valid values: {valid}.")

    # ------------------------------------------------------------------- tools
    def list_values(self, dimension: str) -> dict:
        if dimension not in self.dimension_lookup:
            raise TermNotFound(f"Unknown dimension '{dimension}'. Use one of: {', '.join(self.dimension_lookup)}.")
        result = self.statistics(group_by=dimension)
        return {"dimension": dimension,
                "values": [{"value": r[dimension], "tested": r["tested"]} for r in result["rows"]]}

    def search_terms(self, text: str, limit: int = 6) -> dict:
        key = normalise(text)
        if not key:
            return {"query": text, "matches": []}
        words = {normalise(w) for w in re.split(r"[\s,;/]+", str(text)) if len(normalise(w)) >= 3}
        scored: list[tuple[float, Term]] = []
        for term in self.terms.values():
            best = 0.0
            for name in term.names:
                n = normalise(name)
                if not n:
                    continue
                if n == key:
                    score = 1.0
                elif n in words:                         # one word of the phrase is the term
                    score = 0.9
                elif key in n or n in key:
                    score = 0.6 + 0.3 * min(len(key), len(n)) / max(len(key), len(n))
                else:
                    score = difflib.SequenceMatcher(None, key, n).ratio() * 0.8
                best = max(best, score)
            if best >= 0.62:
                scored.append((best, term))
        scored.sort(key=lambda pair: (-pair[0], pair[1].kind != "individual", pair[1].label))
        return {"query": text, "matches": [self._summary(t) for _, t in scored[:limit]],
                "hint": "Call describe_term with a match to get its definition and relations."}

    def _summary(self, term: Term) -> dict:
        categories = [self.terms[c].label for c in (term.types or term.parents) if c in self.terms]
        return {"term": self.display(term.iri), "kind": term.kind,
                "category": ", ".join(sorted(set(categories))),
                "definition": term.definition[:240]}

    def describe_term(self, text: str) -> dict:
        matches = self.search_terms(text, limit=5)["matches"]
        key = normalise(text)
        exact = [t for t in self.terms.values() if key in {normalise(n) for n in t.names}]
        if not exact:
            if not matches:
                raise TermNotFound(f"No ontology term matches '{text}'.")
            raise TermNotFound(f"No exact ontology term for '{text}'. Closest: "
                               + ", ".join(m["term"] for m in matches) + ".")
        exact.sort(key=lambda t: (t.kind != "individual", t.label))
        term = exact[0]
        relations: dict[str, list[str]] = {}
        for row in self.select(f"SELECT ?p ?o WHERE {{ <{term.iri}> ?p ?o . FILTER(isIRI(?o)) "
                               f"FILTER(STRSTARTS(STR(?p), '{cfg.LHO}')) }}"):
            name = self.terms[row["p"]].label if row["p"] in self.terms else re.split(r"[#/]", row["p"])[-1]
            relations.setdefault(name, []).append(self.display(row["o"]))
        english = sorted({n for n in term.names if n.isascii() and n != term.local
                          and not re.search(r"_\w*\d|^[A-Z]{1,4}\d+$", n)        # codes such as c_33359
                          and not (prettify(n) != n and prettify(n) in term.names | {term.label})})
        other = sorted({n for n in term.names if not n.isascii()})
        return {
            "term": self.display(term.iri),
            "kind": term.kind,
            "iri": term.iri,
            "is_a": [self.terms[c].label for c in self._ancestors(term.types or term.parents)],
            "definition": term.definition[:600],
            "also_called": english[:12],
            "names_in_other_languages": other[:8],
            "relations": {k: sorted(set(v)) for k, v in relations.items()},
        }

    def statistics(self, group_by: str | None = None, pathogen: str | None = None,
                   country: str | None = None, lab: str | None = None, breed: str | None = None,
                   sample_type: str | None = None, diagnostic_test: str | None = None,
                   species: str | None = None, production_stage: str | None = None,
                   year: int | str | None = None, month: int | str | None = None,
                   date_from: str | None = None, date_to: str | None = None) -> dict:
        """Count tested and positive records, optionally filtered and grouped."""
        given = {"species": species, "pathogen": pathogen, "country": country, "lab": lab, "breed": breed,
                 "sample_type": sample_type, "diagnostic_test": diagnostic_test,
                 "production_stage": production_stage}
        kinds = " ".join(f"<{cls}>" for cls in self.species_class.values())
        # GRAPH ?g keeps the example individuals inside the ontology out of the counts.
        patterns = [f"GRAPH ?g {{ ?s a ?kind ; lho:{cfg.RESULT_PROPERTY} ?result ; "
                    f"lho:{cfg.DATE_PROPERTY} ?date . }} {DATA_ONLY} VALUES ?kind {{ {kinds} }}"]
        applied: dict[str, str] = {}
        notes: list[str] = []
        for dimension, value in given.items():
            if value in (None, "", "all", "any"):
                continue
            # Two mistakes small models make, repaired here instead of failing:
            # a placeholder as value (breed="Breed"), and a filter on the very
            # dimension they group by, which would leave only one group to compare.
            placeholder = normalise(str(value)) in {normalise(dimension), normalise(dimension) + "s"}
            if placeholder or dimension == group_by:
                if not placeholder:
                    notes.append(f"The {dimension} filter was ignored because the result is grouped "
                                 f"by {dimension}; all values are compared.")
                continue
            try:
                iri = self.resolve(dimension, str(value))
            except TermNotFound:
                # Several values in one filter: "Belgium, France" or "PCR and culture".
                parts = [p.strip() for p in re.split(r",|;|/|\band\b|\bor\b|\ben\b", str(value)) if p.strip()]
                if len(parts) < 2:
                    raise
                iris = [self.resolve(dimension, part) for part in parts]
                if set(iris) == set(self.dimension_values[dimension]):
                    continue                            # every value was listed: no filter at all
                applied[dimension] = ", ".join(self.display(i, dimension) for i in iris)
                listed = " ".join(f"<{self.species_class[i] if dimension == 'species' else i}>" for i in iris)
                if dimension == "species":
                    patterns.append(f"FILTER(?kind IN ({listed.replace('> <', '>, <')}))")
                else:
                    patterns.append(f"?s lho:{cfg.DIMENSIONS[dimension]} ?{dimension}_m . "
                                    f"VALUES ?{dimension}_m {{ {listed} }}")
                continue
            applied[dimension] = self.display(iri, dimension)
            if dimension == "species":                  # a species is the class of the sample
                patterns.append(f"FILTER(?kind = <{self.species_class[iri]}>)")
                continue
            prop = cfg.DIMENSIONS[dimension]
            is_value = iri in self.dimension_values[dimension]     # some LHO values are classes (Feces)
            if not is_value and self.terms.get(iri) and self.terms[iri].kind == "class":
                # A class such as "bacteria": every pathogen that belongs to it.
                patterns.append(f"?s lho:{prop} ?{dimension}_f . "
                                f"?{dimension}_f a/rdfs:subClassOf* <{iri}> .")
            else:
                patterns.append(f"?s lho:{prop} <{iri}> .")
        filters = []
        if year not in (None, "", 0, "0"):
            if not re.fullmatch(r"\d{4}", str(year)):
                raise TermNotFound(f"year must be four digits, for example 2024 (got '{year}').")
            filters.append(f'SUBSTR(?date, 1, 4) = "{year}"')
            applied["year"] = str(year)
        if month not in (None, "", 0, "0"):
            text = str(month).strip().lower()
            found = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
            if found:                                    # "2022-01": one month of one year
                filters.append(f'SUBSTR(?date, 1, 7) = "{found.group(1)}-{int(found.group(2)):02d}"')
            else:                                        # "1", "01" or "January": that month in every year
                number = MONTH_NAMES.get(text) or (f"{int(text):02d}" if text.isdigit() else None)
                if number is None or not 1 <= int(number) <= 12:
                    raise TermNotFound(f"month must be 1 to 12, a month name, or like 2022-01 (got '{month}').")
                filters.append(f'SUBSTR(?date, 6, 2) = "{number}"')
            applied["month"] = str(month)
        for name, bound, operator, pad in (("date_from", date_from, ">=", "-01-01"),
                                           ("date_to", date_to, "<=", "-12-31")):
            if bound in (None, ""):
                continue
            if not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", str(bound)):
                raise TermNotFound(f"{name} must look like 2024, 2024-03 or 2024-03-15 (got '{bound}').")
            full = str(bound) + pad[len(str(bound)) - 4:] if len(str(bound)) < 10 else str(bound)
            if name == "date_to" and len(str(bound)) == 7:
                full = str(bound) + "-31"
            filters.append(f'?date {operator} "{full}"')
            applied[name] = str(bound)
        group_var = ""
        if group_by not in (None, "", "none"):
            if group_by == "species":
                patterns.append("BIND(?kind AS ?group)")
            elif group_by in cfg.DIMENSIONS:
                patterns.append(f"?s lho:{cfg.DIMENSIONS[group_by]} ?group .")
            elif group_by in TIME_GROUPS:
                patterns.append(f"BIND({TIME_GROUPS[group_by]} AS ?group)")
            else:
                options = ", ".join(list(self.dimension_lookup) + list(TIME_GROUPS))
                raise TermNotFound(f"Cannot group by '{group_by}'. Use one of: {options}.")
            group_var = "?group "
        where = "\n  ".join(patterns + [f"FILTER({f})" for f in filters])
        query = (f"SELECT {group_var}(COUNT(?s) AS ?tested) "
                 f"(SUM(IF(?result = lho:{cfg.POSITIVE}, 1, 0)) AS ?positive)\n"
                 f"WHERE {{\n  {where}\n}}" + (f"\nGROUP BY {group_var.strip()}" if group_var else ""))
        rows = self.select(query)

        def numbers(row: dict) -> dict:
            tested, positive = int(row["tested"] or 0), int(float(row["positive"] or 0))
            return {"tested": tested, "positive": positive, "negative": tested - positive,
                    "positivity_percent": round(100 * positive / tested, 1) if tested else None}

        result: dict = {"filters": applied or "none (all records)"}
        if "species" not in applied and len(self.species_class) > 1:
            result["species_included"] = [self.display(i, "species") for i in self.species_class]
        if not group_var:
            result.update(numbers(rows[0]) if rows else numbers({"tested": 0, "positive": 0}))
            if result["tested"] == 0:
                result["note"] = "No records match these filters. Do not guess a number."
        else:
            table = []
            for row in rows:
                if row["group"] is None:
                    continue
                if group_by == "species":
                    name = next(self.display(sp, "species") for sp, cls in self.species_class.items()
                                if cls == row["group"])
                elif group_by in cfg.DIMENSIONS:
                    name = self.display(row["group"], group_by)
                else:
                    name = row["group"]
                table.append({group_by: name, **numbers(row)})
            if group_by in TIME_GROUPS:
                table.sort(key=lambda r: r[group_by])
            else:
                table.sort(key=lambda r: -r["tested"])
            result["group_by"] = group_by
            if not table:
                result["rows"] = []
                result["note"] = "No records match these filters. Do not guess a number."
            else:
                # The figures for the whole selection come first, so a model that grouped
                # without needing to still has the overall rate and does not average the rows.
                overall_tested = sum(r["tested"] for r in table)
                overall_positive = sum(r["positive"] for r in table)
                result["overall"] = {
                    "tested": overall_tested, "positive": overall_positive,
                    "negative": overall_tested - overall_positive,
                    "positivity_percent": round(100 * overall_positive / overall_tested, 1)}
                rated =[r for r in table if r["positivity_percent"] is not None]
                result["highest_positivity"] = max(rated, key=lambda r: r["positivity_percent"])[group_by]
                result["lowest_positivity"] = min(rated, key=lambda r: r["positivity_percent"])[group_by]
                result["most_tested"] = max(table, key=lambda r: r["tested"])[group_by]
                result["most_positive"] = max(table, key=lambda r: r["positive"])[group_by]
                if len(table) > MAX_ROWS:
                    result["note"] = f"Showing the first {MAX_ROWS} of {len(table)} groups."
                result["rows"] = table[:MAX_ROWS]
        if notes:
            result["note"] = " ".join(notes + ([result["note"]] if "note" in result else []))
        result["_sparql"] = PREFIXES + query
        return result

    def run_sparql(self, query: str) -> dict:
        """Read-only SPARQL for experts: SELECT only, capped at 50 rows."""
        stripped = re.sub(r"#[^\n]*", "", query).strip()
        body = re.sub(r"(?is)^(\s*prefix\s+\w*:\s*<[^>]*>\s*)*", "", stripped)
        if not re.match(r"(?is)^select\b", body):
            raise TermNotFound("Only SELECT queries are allowed.")
        if re.search(r"(?i)\b(insert|delete|load|clear|drop|create|copy|move|add|service)\b", body):
            raise TermNotFound("This query uses a keyword that is not allowed (updates and SERVICE are blocked).")
        try:
            rows = self.select(stripped)
        except Exception as error:           # syntax errors go back to the model
            raise TermNotFound(f"SPARQL error: {error}") from error
        shown = [{k: (self.display(v) if isinstance(v, str) and v.startswith(cfg.LHO) else v)
                  for k, v in row.items()} for row in rows[:50]]
        return {"row_count": len(rows), "rows": shown, "_sparql": stripped}

    def overview(self) -> dict:
        total = self.statistics()
        dates = self.select(f"SELECT (MIN(?d) AS ?first) (MAX(?d) AS ?last) "
                            f"WHERE {{ GRAPH ?g {{ ?s lho:{cfg.DATE_PROPERTY} ?d }} {DATA_ONLY} }}")[0]
        return {
            "description": "Synthetic diagnostic test records for respiratory and enteric pathogens: "
                           "cattle from six laboratories (labs 1 to 6) and pigs from two laboratories "
                           "(labs 7 and 8, Spain), described with the Livestock Health Ontology (LHO V1.5). "
                           "One record is one sample tested for one pathogen.",
            "records": total["tested"], "positive": total["positive"],
            "first_date": dates["first"], "last_date": dates["last"],
            "dimensions": {d: [self.display(i, d) for i in v] for d, v in self.dimension_values.items()},
            "ontology_terms": len(self.terms),
        }
