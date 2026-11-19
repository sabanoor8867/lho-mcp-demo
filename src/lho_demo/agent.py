"""The agent: a language model that answers by calling the MCP tools.

Loop: send the question and the tool list to the model; if the model asks for
a tool, call it on the MCP server and give the result back; repeat until the
model writes its answer. Every tool call is recorded, so each answer can be
traced to the query that produced it.

Ask one question:   python -m lho_demo.agent "How many BRSV tests were positive in 2024?"
Chat:               python -m lho_demo.agent
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time

import ollama
from mcp import Client, StdioServerParameters

from . import config as cfg

SYSTEM_PROMPT = """You are a data assistant for veterinary laboratory data.
You answer questions about a knowledge graph of SYNTHETIC diagnostic test records (2019 to 2025), described with the Livestock Health Ontology (LHO): cattle from six laboratories in Belgium, France, Ireland and the Netherlands, and pigs from two laboratories in Spain.

Rules:
1. Every number in your answer must come from a tool result in this conversation. Never use your own knowledge for numbers.
2. For counts, percentages, comparisons and trends, call test_statistics. For one number or one rate, leave group_by empty and report that number. Only for a "which ... has the highest, lowest or most" question, set group_by to the thing being compared (group_by="lab" for "which laboratory"); the result already names the highest and lowest group, so name that group as the answer. Never guess which group wins and never average rows yourself.
3. For the meaning of a term, call describe_term (or search_terms if you are unsure of the term) and answer from its result.
4. Pass the words of the user as filter values (any language); the tools resolve synonyms.
5. If a tool returns an error, read it, correct the arguments and call the tool again.
6. If the result has 0 records, or the question is outside this graph (species other than cattle and pigs, other topics, the future), say that the graph has no data for it. Do not guess.
7. Answer in one to three sentences, in the language of the user. Give the exact numbers from the tool, and name the filters you used.
8. Never add a filter the user did not ask for. The graph holds two species; when the question names no animal, leave species empty so that both are counted. A follow-up such as "why?", "and for dairy cattle?" or "what about 2023?" refers to the previous question in this conversation: keep its filters and change only what the user changes. To explain a percentage, show the calculation from the previous result (positive divided by tested).
9. If you cannot tell what the user refers to, ask them what they mean. Do not pick a pathogen, laboratory or year yourself."""

NUDGE = ("Reminder: answer only from tool results. If the question is about the test records or "
         "the ontology, call a tool now. If it is outside the scope of this graph, say so briefly.")


def _numbers(text: str) -> set[float]:
    text = re.sub(r"(?<=\d)[,  ](?=\d{3}\b)", "", text)          # 1,234 -> 1234
    return {float(n) for n in re.findall(r"(?<![\w.-])\d+(?:\.\d+)?", text)}


def ungrounded_numbers(answer: str, question: str, steps: list[dict]) -> list[float]:
    """Numbers in the answer that no tool returned and the user did not mention.

    This is the hallucination check: a count or percentage that appears from
    nowhere is caught before the user sees it. Rounded values of tool numbers
    are accepted (20.7 may be written as 21).
    """
    known = _numbers(question)             # with earlier turns, when there are any
    for step in steps:
        known |= _numbers(step["result"])
    known |= {float(round(n)) for n in known} | {round(n, 1) for n in known}
    known.add(100.0)                       # "multiply by 100" when a percentage is explained
    return sorted(n for n in _numbers(answer) if n not in known and n > 12)


class OllamaModel:
    """An open-source model served locally by Ollama."""

    def __init__(self, model: str):
        self.model = model
        self.client = ollama.Client(host=os.environ.get("OLLAMA_HOST"))

    def chat(self, messages: list[dict], tools: list[dict]) -> tuple[str, list[tuple[str, dict]]]:
        response = self.client.chat(
            model=self.model, messages=messages, tools=tools, keep_alive="30m",
            options={"temperature": 0, "num_ctx": 8192, "seed": 1})
        message = response.message
        calls = [(c.function.name, dict(c.function.arguments or {})) for c in (message.tool_calls or [])]
        entry: dict = {"role": "assistant", "content": message.content or ""}
        if calls:
            entry["tool_calls"] = [{"function": {"name": n, "arguments": a}} for n, a in calls]
        messages.append(entry)
        return message.content or "", calls

    @staticmethod
    def tool_message(name: str, content: str) -> dict:
        return {"role": "tool", "tool_name": name, "content": content}


def make_model(provider: str = cfg.PROVIDER, model: str = cfg.MODEL):
    if provider == "ollama":
        return OllamaModel(model)
    raise ValueError(f"Unknown provider '{provider}'. Supported: ollama.")


class Agent:
    def __init__(self, provider: str = cfg.PROVIDER, model: str = cfg.MODEL):
        self.model = make_model(provider, model)
        self.model_name = f"{provider}:{model}"
        env = {**os.environ, "PYTHONPATH": str(cfg.ROOT / "src"), "PYTHONIOENCODING": "utf-8"}
        self._params = StdioServerParameters(command=sys.executable, args=["-m", "lho_demo.server"], env=env)
        self._client: Client | None = None
        self.tools: list[dict] = []
        self._parameters: dict[str, list[str]] = {}

    async def __aenter__(self) -> "Agent":
        self._client = Client(self._params)
        await self._client.__aenter__()
        listed = await self._client.list_tools()
        # The tool list comes from the MCP server; nothing about the tools is hard-coded here.
        self.tools = [{"type": "function", "function": {
            "name": t.name, "description": t.description or "", "parameters": t.input_schema}}
            for t in listed.tools]
        self._parameters = {t.name: list((t.input_schema or {}).get("properties", {})) for t in listed.tools}
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.__aexit__(*exc)

    async def call_tool(self, name: str, arguments: dict) -> tuple[str, str | None]:
        """Call one MCP tool. Returns (text for the model, SPARQL used or None)."""
        arguments = {k: v for k, v in arguments.items() if v is not None}
        # A parameter the tool does not have must never be ignored silently: the
        # model would get a number for a different question than it asked.
        known = self._parameters.get(name)
        unknown = [k for k in arguments if known is not None and k not in known]
        if unknown:
            return json.dumps({"error": f"{name} has no parameter {unknown}. "
                                        f"Valid parameters: {', '.join(known)}."}), None
        try:
            result = await self._client.call_tool(name, arguments)
            text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
        except Exception as error:                      # unknown tool, bad arguments
            return json.dumps({"error": str(error)}), None
        sparql = None
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                sparql = data.pop("_sparql", None)       # shown to the user, not to the model
                text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        except json.JSONDecodeError:
            pass
        return text, sparql

    def _earlier_turns(self, turns: list[dict]) -> list[dict]:
        """Replay earlier turns as real messages: question, tool calls, tool results, answer.

        The model sees its earlier answers together with the tool calls behind them,
        in the same form as a live turn. Describing them in plain text instead taught
        the model to write a made-up tool result into its answer (found in testing).
        """
        messages: list[dict] = []
        for turn in turns[-3:]:
            question, answer = str(turn.get("question", ""))[:500], str(turn.get("answer", ""))[:1200]
            if not question or not answer:
                continue
            messages.append({"role": "user", "content": question})
            steps = [s for s in (turn.get("steps") or [])[:4] if isinstance(s, dict) and s.get("tool")]
            if steps:
                messages.append({"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": s["tool"], "arguments": s.get("arguments") or {}}} for s in steps]})
                for s in steps:
                    messages.append(self.model.tool_message(s["tool"], str(s.get("result", ""))[:1500]))
            messages.append({"role": "assistant", "content": answer})
        return messages

    async def ask(self, question: str, history: list[dict] | None = None) -> dict:
        """history: earlier turns of the conversation, each {"question", "answer", "steps"}."""
        started = time.time()
        earlier = self._earlier_turns(history or [])
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *earlier,
                    {"role": "user", "content": question}]
        # Numbers the answer may repeat: this question and what earlier turns established.
        context = question + " " + " ".join(str(m.get("content", "")) for m in earlier)
        steps: list[dict] = []
        nudged = corrected = False
        answer = ""
        grounded = True
        for _ in range(cfg.MAX_TOOL_ROUNDS):
            text, calls = await asyncio.to_thread(self.model.chat, messages, self.tools)
            if not calls:
                if not steps and not nudged and not earlier:   # answered without looking anything up
                    nudged = True
                    messages.append({"role": "user", "content": NUDGE})
                    continue
                answer = text.strip()
                invented = ungrounded_numbers(answer, context, steps)
                grounded = not invented
                if invented and not corrected:           # one chance to repair the answer
                    corrected = True
                    messages.append({"role": "user", "content": (
                        f"Your answer contains {invented}, which is not in any tool result. "
                        + ("You did not call a tool for this question. Call test_statistics now "
                           "with the filters this question needs. " if not steps else
                           "If the last tool call returned an error, correct the arguments and "
                           "call the tool again. ")
                        + "Use only numbers that a tool returned.")})
                    continue
                break
            for name, arguments in calls:
                output, sparql = await self.call_tool(name, arguments)
                steps.append({"tool": name, "arguments": arguments, "result": output, "sparql": sparql})
                messages.append(self.model.tool_message(name, output))
        else:
            answer = "I could not finish this question within the allowed number of tool calls."
        result = {"question": question, "answer": answer, "steps": steps, "grounded": grounded,
                  "model": self.model_name}
        if not grounded:
            # An answer whose numbers cannot be traced to the data is not shown as an answer.
            result["unverified_answer"] = answer
            result["answer"] = ("I could not verify my answer against the data, so I am not showing it. "
                                "Please ask the question again in other words.")
        result["seconds"] = round(time.time() - started, 1)
        return result


async def _cli() -> None:
    async with Agent() as agent:
        single = " ".join(sys.argv[1:])
        print(f"Model: {agent.model_name}. Tools: {', '.join(t['function']['name'] for t in agent.tools)}")
        while True:
            question = single or input("\nQuestion (empty to stop): ").strip()
            if not question:
                break
            result = await agent.ask(question)
            for step in result["steps"]:
                print(f"  tool: {step['tool']}({json.dumps(step['arguments'], ensure_ascii=False)})")
                print(f"    -> {step['result'][:300]}")
            print(f"\nAnswer ({result['seconds']} s): {result['answer']}")
            if single:
                break


def main() -> None:
    asyncio.run(_cli())


if __name__ == "__main__":
    main()
