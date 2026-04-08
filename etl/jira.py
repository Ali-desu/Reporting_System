"""
Jira REST API v3 fetcher — pulls issues into the `issues` DB table.
"""
import pandas as pd
from sqlalchemy import inspect as _inspect

from etl.clean import DATE_COLS, KPI_COLS, initial_load, upsert

# ── Jira field ID → DB column name ───────────────────────────────────────────
_JIRA_FIELD_MAP = {
    "issuetype":          "issue_type",
    "summary":            "summary",
    "assignee":           "assignee",
    "reporter":           "reporter",
    "priority":           "priority",
    "status":             "status",
    "created":            "created",
    "resolutiondate":     "resolved",
    "duedate":            "due_date",
    "fixVersions":        "fix_versions",
    "project":            "project",
    "customfield_10002":  "organizations",
    "customfield_10127":  "customer_reference_id",
    "customfield_10187":  "environment_type",
    "customfield_10238":  "environment",
    "customfield_10171":  "component",
    "customfield_10173":  "current_tier",
    "customfield_10242":  "reproductibility",
    "customfield_10301":  "resolutions",
    "customfield_10310":  "root_cause_description",
    "customfield_10312":  "impact_description",
    "customfield_10311":  "resolution_description",
    "customfield_10248":  "last_comment_datetime",
    "customfield_10303":  "client_priority",
    "customfield_10179":  "target_release",
    "customfield_10297":  "closure_date",
    "customfield_10492":  "qualification_date",
    "customfield_10327":  "count_ready_acceptance",
    "customfield_10321":  "count_ready_staging",
    "customfield_10317":  "start_date_time",
    "customfield_10229":  "product_line",
    "customfield_10049":  "story_points",
    "customfield_10520":  "story_points_option",
    "customfield_10369":  "sending_date",
    "customfield_10381":  "occurrences",
    "customfield_10429":  "sla_justified",
    "customfield_10446":  "out_of_sla_reason",
    "customfield_10452":  "root_cause_origin",
    "customfield_10447":  "nombre_uo",
    "customfield_10165":  "service_request_types",
    "customfield_10382":  "enhancement_request_type",
    "customfield_11038":  "resolution_owner",
    "customfield_10315":  "expected_sprint",
    "customfield_10642":  "original_expected_sprint",
    "customfield_10305":  "baseline_standard_issue",
    "customfield_10553":  "project_cf",
}


def _adf_to_text(node) -> str:
    """Recursively extract plain text from an Atlassian Document Format node."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        t = node.get("type", "")
        if t == "text":
            return node.get("text", "")
        if t == "hardBreak":
            return "\n"
        children = node.get("content", [])
        sep = "\n" if t in ("paragraph", "bulletList", "orderedList", "listItem", "heading") else ""
        return sep.join(_adf_to_text(c) for c in children)
    if isinstance(node, list):
        return " ".join(_adf_to_text(c) for c in node)
    return str(node)


def _jira_extract(field_id: str, val):
    """Extract a scalar value from a raw Jira field value."""
    if val is None:
        return None

    if field_id == "customfield_10020":
        if isinstance(val, list) and val:
            return val[-1].get("name")
        return None

    if field_id == "fixVersions":
        if isinstance(val, list):
            return ", ".join(v.get("name", "") for v in val if isinstance(v, dict))
        return None

    if field_id == "customfield_10002":
        if isinstance(val, list) and val:
            return val[0].get("name")
        return None

    if field_id == "customfield_10301":
        if isinstance(val, list) and val:
            return val[0].get("value")
        if isinstance(val, dict):
            return val.get("value") or val.get("name")
        return str(val) if val is not None else None

    if field_id in ("customfield_10310", "customfield_10311", "customfield_10312",
                    "customfield_10179"):
        if isinstance(val, dict) and val.get("type") == "doc":
            return _adf_to_text(val).strip() or None
        return str(val) if val else None

    if isinstance(val, dict):
        return (val.get("name") or val.get("displayName") or
                val.get("value") or val.get("key"))

    if isinstance(val, list):
        parts = []
        for item in val:
            if isinstance(item, dict):
                parts.append(str(item.get("name") or item.get("displayName") or item.get("value") or ""))
            else:
                parts.append(str(item))
        return ", ".join(p for p in parts if p) or None

    return val


def fetch_jira_issues(engine, jira_url: str, email: str, api_token: str,
                      project: str = "IRPAUTO", mode: str = "upsert",
                      updated_since: str = None,
                      progress_cb=None) -> dict:
    """
    Fetch issues from Jira REST API v3 and load into `issues` table.

    updated_since : ISO date "YYYY-MM-DD" — incremental sync filter (None = full)
    progress_cb   : callable(fetched, total) for UI progress updates
    mode          : "upsert" | "replace"
    Returns       : {"fetched": N, "loaded": N}
    """
    import requests
    from requests.auth import HTTPBasicAuth

    auth     = HTTPBasicAuth(email, api_token)
    headers  = {"Accept": "application/json", "Content-Type": "application/json"}
    base     = jira_url.rstrip("/")
    endpoint = f"{base}/rest/api/3/search/jql"

    jql = f"project = {project}"
    if updated_since:
        jql += f' AND updated >= "{updated_since}"'
    jql += " ORDER BY updated ASC"

    total_hint = 0
    try:
        _cr = requests.post(
            f"{base}/rest/api/3/search/approximate-count",
            auth=auth, headers=headers, json={"jql": jql}, timeout=15,
        )
        if _cr.ok:
            total_hint = _cr.json().get("count", 0)
    except Exception:
        pass

    requested_fields = list(_JIRA_FIELD_MAP.keys())
    all_rows = []
    next_page_token = None

    while True:
        payload = {"jql": jql, "maxResults": 100, "fields": requested_fields}
        if next_page_token:
            payload["nextPageToken"] = next_page_token

        # Retry up to 3 times on timeout / transient errors
        for _attempt in range(3):
            try:
                resp = requests.post(endpoint, auth=auth, headers=headers,
                                     json=payload, timeout=120)
                resp.raise_for_status()
                break
            except Exception as _exc:
                if _attempt == 2:
                    raise
                import time as _time
                print(f"[ETL] Jira request failed ({_exc}), retrying in 10s…")
                _time.sleep(10)
        data = resp.json()

        for issue in data.get("issues", []):
            row = {"key": issue["key"]}
            fields = issue.get("fields", {})
            for jira_fid, db_col in _JIRA_FIELD_MAP.items():
                if db_col in row:
                    continue
                row[db_col] = _jira_extract(jira_fid, fields.get(jira_fid))
            all_rows.append(row)

        if progress_cb:
            progress_cb(len(all_rows), total_hint or len(all_rows))

        if data.get("isLast", True):
            break
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    if not all_rows:
        return {"fetched": 0, "loaded": 0}

    df = pd.DataFrame(all_rows)

    obj_cols = df.select_dtypes(include="object").columns
    for col in obj_cols:
        df[col] = df[col].astype(str).str.strip().replace({"nan": None, "None": None, "": None})

    def _to_dt(series):
        return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_convert(None)

    for col in DATE_COLS:
        if col in df.columns:
            df[col] = _to_dt(df[col])

    for kpi in KPI_COLS:
        if kpi not in df.columns:
            df[kpi] = None
        df[kpi + "_minutes"] = None
        df.drop(columns=[kpi], inplace=True, errors="ignore")

    for col in ("story_points", "occurrences", "nombre_uo",
                "count_ready_acceptance", "count_ready_staging"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "story_points_option" in df.columns:
        _sp_opt = pd.to_numeric(df["story_points_option"], errors="coerce")
        if "story_points" not in df.columns:
            df["story_points"] = _sp_opt
        else:
            df["story_points"] = df["story_points"].fillna(_sp_opt)
        df.drop(columns=["story_points_option"], inplace=True)

    if "resolved" in df.columns and "closure_date" in df.columns:
        df["is_resolved"] = df["resolved"].notna() | df["closure_date"].notna()
    elif "resolved" in df.columns:
        df["is_resolved"] = df["resolved"].notna()
    else:
        df["is_resolved"] = False

    if "created" in df.columns and "resolved" in df.columns:
        mask = df["resolved"].notna() & df["created"].notna()
        df["resolution_days"] = None
        df.loc[mask, "resolution_days"] = (
            (df.loc[mask, "resolved"] - df.loc[mask, "created"]).dt.total_seconds() / 86400
        )
    else:
        df["resolution_days"] = None

    if "created" in df.columns:
        df["created_yearmonth"] = df["created"].dt.to_period("M").astype(str)
        df["created_year"]      = df["created"].dt.year
        df["created_month"]     = df["created"].dt.month
        df["created_week"]      = df["created"].dt.isocalendar().week.astype(float)

    df.dropna(axis=1, how="all", inplace=True)
    df = df.drop_duplicates(subset=["key"], keep="last")

    if mode == "replace" or not _inspect(engine).has_table("issues"):
        n = initial_load(df, engine)
    else:
        n = upsert(df, engine)

    print(f"[ETL] Jira fetch complete: {len(all_rows)} fetched, {n} loaded.")
    return {"fetched": len(all_rows), "loaded": n}
