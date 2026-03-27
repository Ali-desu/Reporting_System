"""
AI Agent — DXC Service Desk Analytics Assistant
Uses Claude API with tool use to answer natural language questions
about the issues table in Aiven MySQL.

Requires:  ANTHROPIC_API_KEY in .env or environment
"""

import os
import re
import pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Tool definitions (sent to Claude)
# ──────────────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "query_data",
        "description": (
            "Execute a read-only SQL SELECT query against the `issues` table "
            "in the service desk database. Returns results as a formatted string. "
            "Use this for specific counts, filters, groupings, or any data lookup. "
            "Only SELECT statements are allowed — never INSERT, UPDATE, DELETE, DROP, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": (
                        "A valid MySQL SELECT query. The table name is `issues`. "
                        "Always include a LIMIT (max 200) to avoid overloading the response."
                    ),
                },
                "explanation": {
                    "type": "string",
                    "description": "One sentence explaining what this query is checking.",
                },
            },
            "required": ["sql", "explanation"],
        },
    },
    {
        "name": "get_summary_stats",
        "description": (
            "Return high-level KPI summary for the entire dataset or a filtered subset: "
            "total issues, resolved, open, SLA compliance %, avg/median resolution days, "
            "critical open count, and total story points. "
            "Use this as a starting point for any overview or status question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "where_clause": {
                    "type": "string",
                    "description": (
                        "Optional SQL WHERE clause (without the word WHERE) to filter results. "
                        "E.g. \"priority = 'Critical'\" or \"YEAR(created) = 2025\". "
                        "Leave empty for full dataset summary."
                    ),
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_trend",
        "description": (
            "Return monthly counts of issues created and resolved over time. "
            "Use this when asked about trends, patterns over months, or whether "
            "things are improving or getting worse."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {
                    "type": "string",
                    "description": (
                        "Additional column to split the trend by. "
                        "E.g. 'priority', 'issue_type', 'assignee'. "
                        "Leave empty for total-only trend."
                    ),
                },
                "months": {
                    "type": "integer",
                    "description": "How many recent months to include. Default 12.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_assignee_stats",
        "description": (
            "Return a performance table for all assignees (or a specific one): "
            "issue count, resolved count, resolution rate %, avg resolution days, "
            "critical issues, story points handled. "
            "Use this for any question about team performance, workload, or individual productivity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "assignee": {
                    "type": "string",
                    "description": "Filter to a specific assignee name. Leave empty for all.",
                },
                "top_n": {
                    "type": "integer",
                    "description": "Limit results to top N by volume. Default 10.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_sla_breakdown",
        "description": (
            "Return SLA compliance breakdown grouped by a dimension. "
            "Use this for questions about SLA performance by priority, type, project, assignee, or over time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {
                    "type": "string",
                    "description": (
                        "Column to group SLA results by. "
                        "Options: 'priority', 'issue_type', 'project', 'assignee', "
                        "'environment_type', 'product_line', 'created_yearmonth'."
                    ),
                }
            },
            "required": ["group_by"],
        },
    },
    {
        "name": "get_sprint_status",
        "description": (
            "Return sprint progress: total story points, completed points, remaining, "
            "completion %, and list of unresolved issues for a given sprint group. "
            "Use this for any question about sprint health, burndown, or delivery."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sprint_name": {
                    "type": "string",
                    "description": (
                        "Sprint group name as stored in expected_sprint column. "
                        "E.g. 'v22 R25'. If unsure, query the distinct values first."
                    ),
                }
            },
            "required": ["sprint_name"],
        },
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are an expert service desk analytics assistant for DXC Technology.
You have direct access to a MySQL database containing Jira service desk issue data.

DATABASE TABLE: `issues`

KEY COLUMNS:
- key                         : unique issue identifier (e.g. "SD-1234")
- issue_type                  : Bug, Incident, Service Request, Enhancement, etc.
- summary                     : issue title/description
- priority                    : Critical, High, Medium, Low
- status                      : current workflow status
- assignee                    : person assigned to the issue
- reporter                    : person who reported it
- organizations               : client/organisation name
- project                     : project name
- component                   : system component affected
- product_line                : product line category
- environment_type            : Production, Non-Production, etc.
- created       (DATETIME)    : when the issue was created
- resolved      (DATETIME)    : when it was resolved (NULL if open)
- closure_date  (DATETIME)    : alternative closure date
- is_resolved   (TINYINT 0/1) : 1 = resolved, 0 = open
- resolution_days (FLOAT)     : days from created to resolved
- sla_justified (Yes/No)      : whether SLA was met
- out_of_sla_reason           : reason if SLA was breached
- story_points  (FLOAT)       : effort estimate
- expected_sprint             : sprint name (normalised, e.g. "v22 R25")
- kpi_time_to_solve_minutes   : minutes from open to solve (negative = breached)
- kpi_time_initial_response_minutes
- kpi_time_to_analyse_minutes
- kpi_time_to_assist_minutes
- kpi_time_to_estimate_minutes
- created_yearmonth           : "YYYY-MM" string for easy grouping
- created_year, created_month, created_week : integer extracts

BEHAVIOUR RULES:
1. Always use a tool to fetch data before giving numbers — never guess or fabricate figures.
2. Be concise and direct. Use tables or bullet points when presenting multiple values.
3. When you spot anomalies (e.g. SLA drop, critical spike), flag them clearly.
4. If a question is ambiguous, state your assumption then answer it.
5. KPI times: negative values mean SLA breach, positive means within SLA.
6. Use get_summary_stats first for any overview question, then drill down with query_data if needed.
7. Format large numbers with commas. Round percentages to 1 decimal place.
"""


# ──────────────────────────────────────────────────────────────────────────────
# Tool execution
# ──────────────────────────────────────────────────────────────────────────────

def _safe_sql(sql: str) -> str | None:
    """Return None if safe, error string if not."""
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return "Only SELECT queries are allowed."
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
                 "CREATE", "TRUNCATE", "EXEC", "EXECUTE", "--", ";"]
    for kw in forbidden:
        if re.search(r'\b' + kw + r'\b', stripped):
            return f"Forbidden keyword detected: {kw}"
    return None


def _execute_tool(name: str, inputs: dict, engine) -> str:
    try:
        if name == "query_data":
            sql = inputs.get("sql", "").strip()
            err = _safe_sql(sql)
            if err:
                return f"Blocked: {err}"
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            if df.empty:
                return "Query returned no results."
            return df.to_string(index=False, max_rows=50)

        if name == "get_summary_stats":
            where = inputs.get("where_clause", "").strip()
            where_sql = f"WHERE {where}" if where else ""
            sql = f"""
                SELECT
                    COUNT(*)                                                        AS total_issues,
                    SUM(is_resolved)                                                AS resolved,
                    COUNT(*) - SUM(is_resolved)                                     AS open_issues,
                    ROUND(SUM(is_resolved) / COUNT(*) * 100, 1)                     AS resolution_rate_pct,
                    ROUND(AVG(resolution_days), 1)                                  AS avg_resolution_days,
                    ROUND(
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_days)
                        OVER (), 1)                                                 AS median_resolution_days,
                    SUM(CASE WHEN priority='Critical' AND is_resolved=0 THEN 1 ELSE 0 END) AS critical_open,
                    ROUND(
                        SUM(CASE WHEN sla_justified='Yes' THEN 1 ELSE 0 END) /
                        NULLIF(SUM(CASE WHEN sla_justified IN ('Yes','No') THEN 1 ELSE 0 END), 0)
                        * 100, 1)                                                   AS sla_compliance_pct,
                    ROUND(SUM(COALESCE(story_points, 0)), 0)                        AS total_story_points
                FROM issues {where_sql}
            """
            # MySQL doesn't support PERCENTILE_CONT, use simpler query
            sql = f"""
                SELECT
                    COUNT(*)                                                              AS total_issues,
                    SUM(is_resolved)                                                      AS resolved,
                    COUNT(*) - SUM(is_resolved)                                           AS open_issues,
                    ROUND(SUM(is_resolved) / COUNT(*) * 100, 1)                           AS resolution_rate_pct,
                    ROUND(AVG(resolution_days), 1)                                        AS avg_resolution_days,
                    SUM(CASE WHEN priority='Critical' AND is_resolved=0 THEN 1 ELSE 0 END) AS critical_open,
                    ROUND(
                        SUM(CASE WHEN sla_justified='Yes' THEN 1 ELSE 0 END) /
                        NULLIF(SUM(CASE WHEN sla_justified IN ('Yes','No') THEN 1 ELSE 0 END), 0)
                        * 100, 1)                                                          AS sla_compliance_pct,
                    ROUND(SUM(COALESCE(story_points, 0)), 0)                               AS total_story_points
                FROM issues {where_sql}
            """
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            return df.to_string(index=False)

        if name == "get_trend":
            group_by = inputs.get("group_by", "").strip()
            months   = int(inputs.get("months", 12))
            if group_by and group_by in ["priority", "issue_type", "assignee",
                                          "project", "environment_type", "product_line"]:
                sql = f"""
                    SELECT created_yearmonth, `{group_by}`, COUNT(*) AS issues_created
                    FROM issues
                    WHERE created >= DATE_SUB(CURDATE(), INTERVAL {months} MONTH)
                    GROUP BY created_yearmonth, `{group_by}`
                    ORDER BY created_yearmonth, issues_created DESC
                    LIMIT 200
                """
            else:
                sql = f"""
                    SELECT
                        created_yearmonth,
                        COUNT(*) AS issues_created,
                        SUM(is_resolved) AS issues_resolved,
                        ROUND(SUM(is_resolved)/COUNT(*)*100,1) AS resolution_rate_pct
                    FROM issues
                    WHERE created >= DATE_SUB(CURDATE(), INTERVAL {months} MONTH)
                    GROUP BY created_yearmonth
                    ORDER BY created_yearmonth
                """
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            return df.to_string(index=False) if not df.empty else "No trend data found."

        if name == "get_assignee_stats":
            assignee = inputs.get("assignee", "").strip()
            top_n    = int(inputs.get("top_n", 10))
            where    = f"AND assignee = '{assignee}'" if assignee else ""
            sql = f"""
                SELECT
                    assignee,
                    COUNT(*)                                                               AS total,
                    SUM(is_resolved)                                                       AS resolved,
                    ROUND(SUM(is_resolved)/COUNT(*)*100,1)                                 AS resolution_rate_pct,
                    ROUND(AVG(resolution_days),1)                                          AS avg_resolution_days,
                    SUM(CASE WHEN priority='Critical' THEN 1 ELSE 0 END)                   AS critical_issues,
                    ROUND(SUM(COALESCE(story_points,0)),0)                                  AS story_points
                FROM issues
                WHERE assignee IS NOT NULL {where}
                GROUP BY assignee
                ORDER BY total DESC
                LIMIT {top_n}
            """
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            return df.to_string(index=False) if not df.empty else "No assignee data found."

        if name == "get_sla_breakdown":
            group_by = inputs.get("group_by", "priority").strip()
            allowed  = ["priority", "issue_type", "project", "assignee",
                        "environment_type", "product_line", "created_yearmonth"]
            if group_by not in allowed:
                return f"group_by must be one of: {', '.join(allowed)}"
            sql = f"""
                SELECT
                    `{group_by}`,
                    SUM(CASE WHEN sla_justified='Yes' THEN 1 ELSE 0 END)  AS sla_met,
                    SUM(CASE WHEN sla_justified='No'  THEN 1 ELSE 0 END)  AS sla_breached,
                    SUM(CASE WHEN sla_justified IN ('Yes','No') THEN 1 ELSE 0 END) AS total_evaluated,
                    ROUND(
                        SUM(CASE WHEN sla_justified='Yes' THEN 1 ELSE 0 END) /
                        NULLIF(SUM(CASE WHEN sla_justified IN ('Yes','No') THEN 1 ELSE 0 END),0)
                        * 100, 1)                                          AS compliance_pct
                FROM issues
                WHERE sla_justified IN ('Yes','No')
                GROUP BY `{group_by}`
                ORDER BY total_evaluated DESC
                LIMIT 30
            """
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            return df.to_string(index=False) if not df.empty else "No SLA data found."

        if name == "get_sprint_status":
            sprint = inputs.get("sprint_name", "").strip()
            if not sprint:
                # Return list of available sprints
                sql = """
                    SELECT DISTINCT expected_sprint, COUNT(*) AS issues
                    FROM issues
                    WHERE expected_sprint IS NOT NULL
                    GROUP BY expected_sprint
                    ORDER BY expected_sprint DESC
                    LIMIT 30
                """
                with engine.connect() as conn:
                    df = pd.read_sql(text(sql), conn)
                return "Available sprints:\n" + df.to_string(index=False)

            sql = f"""
                SELECT
                    COUNT(*)                                                            AS total_issues,
                    SUM(is_resolved)                                                    AS completed_issues,
                    COUNT(*) - SUM(is_resolved)                                         AS remaining_issues,
                    ROUND(SUM(COALESCE(story_points,0)),0)                               AS total_points,
                    ROUND(SUM(CASE WHEN is_resolved=1 THEN COALESCE(story_points,0) ELSE 0 END),0) AS completed_points,
                    ROUND(SUM(CASE WHEN is_resolved=0 THEN COALESCE(story_points,0) ELSE 0 END),0) AS remaining_points,
                    ROUND(
                        SUM(CASE WHEN is_resolved=1 THEN COALESCE(story_points,0) ELSE 0 END) /
                        NULLIF(SUM(COALESCE(story_points,0)),0) * 100, 1)               AS completion_pct,
                    SUM(CASE WHEN is_resolved=0 AND priority='Critical' THEN 1 ELSE 0 END) AS critical_remaining
                FROM issues
                WHERE expected_sprint = '{sprint}'
            """
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            summary = df.to_string(index=False)

            # Also get open issues list
            open_sql = f"""
                SELECT `key`, summary, priority, status,
                       COALESCE(story_points,0) AS points
                FROM issues
                WHERE expected_sprint = '{sprint}' AND is_resolved = 0
                ORDER BY
                    CASE priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
                                  WHEN 'Medium' THEN 3 ELSE 4 END
                LIMIT 20
            """
            with engine.connect() as conn:
                open_df = pd.read_sql(text(open_sql), conn)
            open_str = open_df.to_string(index=False) if not open_df.empty else "No open issues."
            return f"Sprint summary:\n{summary}\n\nOpen issues (top 20 by priority):\n{open_str}"

        return f"Unknown tool: {name}"

    except Exception as e:
        return f"Tool error in {name}: {e}"


# ──────────────────────────────────────────────────────────────────────────────
# Agent entry point
# ──────────────────────────────────────────────────────────────────────────────

def run_agent(user_message: str, engine, history: list | None = None) -> str:
    """
    Run one turn of the agent.

    Parameters
    ----------
    user_message : str
        The user's question.
    engine : SQLAlchemy engine
        Connected to Aiven MySQL.
    history : list, optional
        Prior conversation turns in Claude message format.
        Each item: {"role": "user"|"assistant", "content": str}

    Returns
    -------
    str
        The assistant's final text response.
    """
    try:
        import anthropic
    except ImportError:
        return (
            "The `anthropic` package is not installed. "
            "Run:  pip install anthropic"
        )

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("anthropic", {}).get("api_key", "").strip()
        except Exception:
            pass
    if not api_key:
        return (
            "**API key not configured.**\n\n"
            "To activate the assistant:\n"
            "1. Get a key at console.anthropic.com\n"
            "2. Add it to your `.env` file:  `ANTHROPIC_API_KEY=sk-ant-...`\n"
            "3. On Streamlit Cloud: add it under App Settings → Secrets\n"
            "4. Restart the app"
        )

    client = anthropic.Anthropic(api_key=api_key)

    # Build message list from history + new user message
    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    MAX_TOOL_ROUNDS = 8  # prevent infinite loops

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            # Extract text from response
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "No response generated."

        if response.stop_reason != "tool_use":
            break

        # Collect all tool calls from this response
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = _execute_tool(block.name, block.input, engine)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        # Add assistant turn + tool results to message history
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user",      "content": tool_results})

    return "The agent did not produce a final response. Please try rephrasing your question."


def check_api_key() -> bool:
    """Return True if ANTHROPIC_API_KEY is set (env or st.secrets)."""
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return True
    try:
        import streamlit as st
        return bool(st.secrets.get("anthropic", {}).get("api_key", "").strip())
    except Exception:
        return False
