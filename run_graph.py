from __future__ import annotations

"""
LangGraph workflow: routes checks to either an email-domain tool or a monthly-aggregation tool,
then writes results back to checks.xlsx and a summary report.xlsx.
"""

from pathlib import Path
import os
import re
import math
import calendar
from datetime import date
from typing import TypedDict, Literal

import pandas as pd
from dotenv import load_dotenv
from langchain_core.tools import tool
from langgraph.graph import START, END, StateGraph

# ---------------------- Config & Paths ----------------------
# Reads .env (or ENV_FILE) to resolve file locations and provider settings.
# All relative paths are resolved against BASE_DIR.
SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = os.getenv("ENV_FILE")
load_dotenv(ENV_FILE or (SCRIPT_DIR / ".env"))

BASE = Path(os.getenv("BASE_DIR", str(SCRIPT_DIR)))

def _resolve_file(env_key: str, default_name: str) -> Path:
    """Resolve a file path from env; fall back to default_name. Relative -> BASE_DIR."""
    p = Path(os.getenv(env_key, default_name))
    return p if p.is_absolute() else (BASE / p)

CONTACTS_PATH = _resolve_file("CONTACTS_FILE", "contacts.xlsx")
CHECKS_PATH = _resolve_file("CHECKS_FILE", "checks.xlsx")
REPORT_PATH = _resolve_file("REPORT_FILE", "report.xlsx")
METRICS_PATH = _resolve_file("METRICS_FILE", "metrics.xlsx")

# Provider envs and precedence (optional LLM routing for future use)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2025-01-01-preview")
AZURE_ENDPOINT = os.getenv("base_url")
LLMFOUNDRY_TOKEN = os.getenv("LLMFOUNDRY_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PROVIDER = "azure" if LLMFOUNDRY_TOKEN else ("openai" if OPENAI_API_KEY else "none")

# ---------------------- Utilities ----------------------
# Helpers, constants and regex used by tools and parsers.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MONTH_NAMES = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
COMPARATORS = {
    "<": "lt", "<=": "le", ">": "gt", ">=": "ge", "==": "eq", "!=": "ne",
    "less than": "lt", "at most": "le", "greater than": "gt", "at least": "ge",
    "equals": "eq", "equal": "eq", "not equal": "ne",
}
NUM_RE = re.compile(r"(?<![\w.])([0-9]+(?:\.[0-9]+)?)")

# ---------------------- Tools ----------------------

def extract_domain(email: str) -> str | None:
    """Validate email and return the domain part after '@' in lowercase."""
    if not isinstance(email, str) or not email:
        return None
    email = email.strip()
    if not EMAIL_RE.match(email):
        return None
    return email.split('@', 1)[1].lower()

@tool
def domain_check(email: str) -> dict:
    """Return whether the email domain exists among contacts.xlsx domains.
    - Loads contacts.xlsx and builds a set of domains from contact emails.
    - Extracts the domain from the input email and checks membership.
    Returns: {result, reason, domain}
    """
    df = pd.read_excel(CONTACTS_PATH)
    domains = {extract_domain(e) for e in df.get("email", []) if extract_domain(e)}
    dom = extract_domain(email)
    if not dom:
        return {"result": "Failed", "reason": "Invalid or missing email format", "domain": None}
    ok = dom in domains
    return {
        "result": "Success" if ok else "Failed",
        "reason": "Domain found in contacts" if ok else "Domain not found in contacts",
        "domain": dom,
    }

@tool
def monthly_aggregate(metric: str, period: str) -> dict:
    """Aggregate values from metrics.xlsx for a given metric and period.
    period format:
      - month:YYYY-MM
      - week:YYYY-WW (ISO week)
    Returns: { "period": str, "value": float }
    """
    mdf = pd.read_excel(METRICS_PATH, parse_dates=["date"])  # ensure datetime
    if metric:
        mdf = mdf[mdf["metric"].str.lower() == str(metric).lower()]
    value = float("nan")
    if period.startswith("month:"):
        ym = period.split(":", 1)[1]
        y, m = ym.split("-"); y = int(y); m = int(m)
        sel = (mdf["date"].dt.year == y) & (mdf["date"].dt.month == m)
        value = float(mdf.loc[sel, "value"].sum()) if sel.any() else float("nan")
    elif period.startswith("week:"):
        yw = period.split(":", 1)[1]
        y, w = yw.split("-"); y = int(y); w = int(w)
        iso = mdf["date"].dt.isocalendar()
        sel = (iso.year == y) & (iso.week == w)
        value = float(mdf.loc[sel, "value"].sum()) if sel.any() else float("nan")
    return {"period": period, "value": value}

# ---------------------- Parsing ----------------------

def parse_check(text: str) -> dict:
    """Parse check text into routing + parameters.
    Extracts:
      - kind: one of "mail", "monthly", or "skip"
      - metric: e.g., "csr_supply" or "spend"
      - period: "month:YYYY-MM" or "week:YYYY-WW"
      - comparator: lt/le/gt/ge/eq/ne (from symbols or natural phrases)
      - target: numeric value to compare against
    """
    t = (text or "").lower()
    # Detect intent
    mail_hint = ("email" in t or "domain" in t)
    monthly_hint = ("aggregate" in t or "csr" in t or "supply" in t or "spend" in t or any(k in t for k in COMPARATORS))

    # Comparator phrase
    comp = None
    for k in sorted(COMPARATORS.keys(), key=len, reverse=True):
        if k in t:
            comp = COMPARATORS[k]; break

    # Target number
    m = NUM_RE.search(t)
    target = float(m.group(1)) if m else None

    # Month parsing
    month = None; year = None
    for name, idx in MONTH_NAMES.items():
        if name in t:
            month = idx
            ym = re.search(r"(20\d{2})", t)
            year = int(ym.group(1)) if ym else date.today().year
            break
    if not month:
        ym2 = re.search(r"(20\d{2})-(\d{1,2})", t)
        if ym2:
            year = int(ym2.group(1)); month = int(ym2.group(2))

    # Week parsing
    week = None
    if "week" in t:
        w = re.search(r"week\s*(\d{1,2})", t)
        if w:
            week = int(w.group(1))
            if not year:
                year = date.today().year
        elif "this week" in t:
            iso = date.today().isocalendar()
            week = int(iso.week); year = int(iso.year)

    # Metric
    metric = "csr_supply" if ("csr" in t or "supply" in t) else ("spend" if "spend" in t else None)

    # Period
    period = None
    if month and year:
        period = f"month:{year}-{month:02d}"
    elif week and year:
        period = f"week:{year}-{week:02d}"

    # Decide kind (mail takes precedence when only mail is hinted)
    if mail_hint and not monthly_hint:
        kind = "mail"
    elif monthly_hint:
        kind = "monthly"
    else:
        kind = "skip"

    return {"kind": kind, "metric": metric, "period": period, "comparator": comp, "target": target}

# ---------------------- Graph Nodes ----------------------
class NodeState(TypedDict):
    # Per-check state carried across nodes. Keys are read/written by nodes.
    check_text: str
    email: str
    decision: Literal["mail_tool", "monthly_tool", "skip"]
    tool_output: dict | None
    monthly_output: dict | None
    parsed: dict | None
    status: str
    explanation: str


def classify(state: NodeState) -> NodeState:
    """Parse the check and decide which tool to run (mail/monthly/skip)."""
    # Parse the raw check text into structured params for routing and tools.
    check = (state.get("check_text") or "").strip()
    parsed = parse_check(check)
    if parsed["kind"] == "mail":
        decision = "mail_tool"
    elif parsed["kind"] == "monthly":
        decision = "monthly_tool"
    else:
        decision = "skip"
    state["decision"] = decision
    state["parsed"] = parsed
    return state


def run_tool(state: NodeState) -> NodeState:
    """Invoke email domain tool and store its output in the state."""
    # Extract email from state; default to empty if missing
    email = state.get("email", "")
    # Invoke domain_check and store output for finalize
    state["tool_output"] = domain_check.invoke({"email": email})
    return state


def run_monthly_tool(state: NodeState) -> NodeState:
    """Invoke monthly aggregation tool using parsed metric/period."""
    parsed = state.get("parsed", {}) or {}
    metric = parsed.get("metric") or "csr_supply"
    period = parsed.get("period") or ""
    state["monthly_output"] = monthly_aggregate.invoke({"metric": metric, "period": period})
    return state


def finalize(state: NodeState) -> NodeState:
    """Compute Status/Explanation for mail or monthly checks and return updated state."""
    decision = state.get("decision")
    if decision == "mail_tool" and state.get("tool_output"):
        out = state["tool_output"] or {}
        state["status"] = str(out.get("result", "Failed"))
        state["explanation"] = str(out.get("reason", ""))
    elif decision == "monthly_tool":
        parsed = state.get("parsed", {}) or {}
        mout = state.get("monthly_output", {}) or {}
        tool_val = mout.get("value")
        comp = parsed.get("comparator")
        target = parsed.get("target")
        if tool_val is None or (isinstance(tool_val, float) and math.isnan(tool_val)):
            state["status"] = "Failed"; state["explanation"] = "No data"
        elif comp and target is not None:
            ops = {
                "lt": lambda a,b: a < b,
                "le": lambda a,b: a <= b,
                "gt": lambda a,b: a > b,
                "ge": lambda a,b: a >= b,
                "eq": lambda a,b: abs(a-b) < 1e-9,
                "ne": lambda a,b: abs(a-b) >= 1e-9,
            }
            ok = ops.get(comp, lambda a,b: False)(float(tool_val), float(target))
            state["status"] = "Success" if ok else "Failed"
            state["explanation"] = f"tool_value={tool_val}, target_value={target}, comparator={comp}, period={parsed.get('period')}, metric={parsed.get('metric')}"
        else:
            state["status"] = "Failed"; state["explanation"] = "Comparator/target missing"
    else:
        state["status"] = "Skipped"; state["explanation"] = "No check was done"
    return state

# ---------------------- Graph Wiring ----------------------
workflow = StateGraph(NodeState)
workflow.add_node("classify", classify)
workflow.add_node("run_tool", run_tool)
workflow.add_node("run_monthly_tool", run_monthly_tool)
workflow.add_node("finalize", finalize)
workflow.add_edge(START, "classify")
workflow.add_conditional_edges("classify", lambda s: s.get("decision"), {"mail_tool": "run_tool", "monthly_tool": "run_monthly_tool", "skip": "finalize"})
workflow.add_edge("run_tool", "finalize")
workflow.add_edge("run_monthly_tool", "finalize")
workflow.add_edge("finalize", END)

graph = workflow.compile()

# ---------------------- Runner ----------------------
# Iterates rows in checks.xlsx, runs the graph, updates checks.xlsx, writes report.xlsx.

def main():
    checks_df = pd.read_excel(CHECKS_PATH)
    # Ensure required columns
    for col in ["Check", "Email", "Status", "Explanation"]:
        if col not in checks_df.columns:
            checks_df[col] = ""
    checks_df["Status"] = checks_df["Status"].fillna("").astype(str)
    checks_df["Explanation"] = checks_df["Explanation"].fillna("").astype(str)

    def norm_email(v):
        s = str(v).strip()
        return "" if s.lower() in ("", "nan", "none") else s

    rows = []
    for idx, r in checks_df.iterrows():
        state: NodeState = {
            "check_text": str(r.get("Check", "")),
            "email": norm_email(r.get("Email", "")),
            "decision": "skip",
            "tool_output": None,
            "monthly_output": None,
            "parsed": None,
            "status": "",
            "explanation": "",
        }
        res = graph.invoke(state)
        checks_df.at[idx, "Status"] = res.get("status", "")
        checks_df.at[idx, "Explanation"] = res.get("explanation", "")
        rows.append({
            "row": int(idx) + 1,
            "check": state["check_text"],
            "tool": res.get("decision"),
            "email": state.get("email", ""),
            "domain": (res.get("tool_output") or {}).get("domain") if isinstance(res.get("tool_output"), dict) else None,
            "metric": (res.get("parsed") or {}).get("metric") if isinstance(res.get("parsed"), dict) else (state.get("parsed") or {}).get("metric"),
            "period": (res.get("parsed") or {}).get("period") if isinstance(res.get("parsed"), dict) else (state.get("parsed") or {}).get("period"),
            "tool_value": (res.get("monthly_output") or {}).get("value") if isinstance(res.get("monthly_output"), dict) else None,
            "target_value": (res.get("parsed") or {}).get("target") if isinstance(res.get("parsed"), dict) else (state.get("parsed") or {}).get("target"),
            "comparator": (res.get("parsed") or {}).get("comparator") if isinstance(res.get("parsed"), dict) else (state.get("parsed") or {}).get("comparator"),
            "result": res.get("status"),
            "reason": res.get("explanation"),
        })
    checks_df.to_excel(CHECKS_PATH, index=False)
    pd.DataFrame(rows).to_excel(REPORT_PATH, index=False)
    print("LangGraph run complete. Provider:", PROVIDER, "Report:", REPORT_PATH)

if __name__ == "__main__":
    main()
