# SOP_Agent LangGraph Workflow

Overview
- LangGraph workflow routes each check to one of two tools and writes results:
  - mail_tool: validates whether an email?s domain exists among contact domains.
  - monthly_tool: aggregates numeric metrics by month/week and compares against targets.
- Results update `checks.xlsx` (Status/Explanation) and produce `report.xlsx` with rich fields.

Files
- run_graph.py ? the workflow implementation.
- .env.example ? configuration template; copy to `.env` and fill values.
- contacts.xlsx ? contact list with emails (domain source).
- metrics.xlsx ? mock numeric dataset with proper dates and values.
- checks.xlsx ? checks to execute; includes email-based and numeric checks.
- report.xlsx ? generated summary of all checks.

Configuration (.env)
- BASE_DIR ? base folder for relative paths (default: script directory).
- CONTACTS_FILE, CHECKS_FILE, REPORT_FILE, METRICS_FILE ? filenames or absolute paths.
- Provider precedence for optional LLM routing (used for classification only if enabled):
  - If LLMFOUNDRY_TOKEN is set, Azure OpenAI is used and OPENAI_API_KEY is ignored.
  - Else if OPENAI_API_KEY is set, OpenAI via langchain-openai is used.
  - Else, heuristic routing runs (no LLM call).

Tools
- domain_check(email)
  - Loads `contacts.xlsx`, extracts domains from contact emails.
  - Validates the input email?s domain and returns: result, reason, domain.
- monthly_aggregate(metric, period)
  - Loads `metrics.xlsx` with proper datetime `date` column.
  - Period formats: `month:YYYY-MM` or `week:YYYY-WW` (ISO week).
  - Filters by `metric` and `period`, sums `value`, returns: period, value.

Parsing and Routing
- parse_check(text) extracts:
  - kind: mail/monthly/skip based on keywords and comparator presence.
  - metric: detects `csr_supply` or `spend` from text.
  - period: supports month names (e.g., March 2025) and `YYYY-MM`; supports `this week` or `week 12`.
  - comparator: maps natural phrases and symbols to lt/le/gt/ge/eq/ne.
  - target: first numeric value in the check text.
- classify node decides tool:
  - mail_tool if email/domain-only; monthly_tool for numeric/aggregation checks; skip otherwise.
  - Mail has precedence when both are mentioned.

Graph Nodes
- classify: parse check text and set `decision` + stash parsed params.
- run_tool: call `domain_check` with state email; store `tool_output`.
- run_monthly_tool: call `monthly_aggregate` with parsed metric/period; store `monthly_output`.
- finalize: compute `Status`/`Explanation` per decision:
  - mail_tool: Success/Failed with reason.
  - monthly_tool: compare tool_value to target_value using comparator; `No data` if absent; write details.

Outputs
- checks.xlsx: Status and Explanation per row.
- report.xlsx: row, check, tool, email, domain, metric, period, tool_value, target_value, comparator, result, reason.

Run
- Ensure `.env` exists (copy from `.env.example`).
- Populate or generate input files (contacts.xlsx, metrics.xlsx, checks.xlsx).
- Command: `\.venv\Scripts\python.exe .\run_graph.py`.
- Review `report.xlsx` and `checks.xlsx`.

Troubleshooting
- Blank result/reason: ensure Email cells are truly blank (not the literal string `nan`), and you open the `REPORT_FILE` configured in `.env`.
- `No data`: indicates the period/metric combination had no rows in metrics.xlsx.
- Model routing not used: set Azure/OpenAI env keys; otherwise heuristic routing applies.

Extending
- Add more comparator synonyms to `COMPARATORS`.
- Extend `parse_check` to recognize new metrics or phrasing.
- Add new tools and conditional edges to the graph.
