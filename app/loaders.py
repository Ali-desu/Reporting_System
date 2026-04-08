"""
Data loading helpers — DB engine, cached loaders, name-matching utilities.
"""
import datetime as _dt
import difflib as _dl
import re as _re

import pandas as pd
import streamlit as st
from sqlalchemy import inspect

from etl import build_engine, get_engine


# ── Engine ────────────────────────────────────────────────────────────────────

@st.cache_resource
def _engine():
    try:
        s = st.secrets["database"]
        return build_engine(s["host"], int(s["port"]), s["name"], s["user"], s["password"])
    except KeyError:
        return get_engine()


def _table_exists(engine) -> bool:
    return inspect(engine).has_table("issues")


def _rl_table_exists(engine) -> bool:
    return inspect(engine).has_table("r25_scope")


# ── Cached loaders ────────────────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner="Loading data…")
def load_data() -> pd.DataFrame:
    engine = _engine()
    if not _table_exists(engine):
        return pd.DataFrame()
    df = pd.read_sql("SELECT * FROM issues", con=engine)
    for col in ["created", "resolved", "closure_date", "sending_date",
                "qualification_date", "last_comment_datetime",
                "start_date_time", "due_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in ["resolution_days", "occurrences", "story_points",
                "nombre_uo", "count_ready_acceptance", "count_ready_staging"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_r25_scope() -> pd.DataFrame:
    """Load scope from DB (r25_scope table), fall back to local Excel."""
    try:
        eng = _engine()
        if _rl_table_exists(eng):
            return pd.read_sql("SELECT * FROM r25_scope", con=eng)
    except Exception:
        pass

    _raw = pd.read_excel("data/Release_lifecycle_R25.xlsx", sheet_name="Scope UPDATE", header=0)
    _raw.columns = [str(c).strip() for c in _raw.columns]
    scope = _raw[["Key", "expected sprint", "Story point", "statut",
                  "expected sprint Jira", "Committed (Yes/No)"]].copy()
    scope.columns = ["key", "scope_sprint", "scope_points",
                     "scope_status", "jira_sprint", "committed"]
    scope["key"] = scope["key"].astype(str).str.strip()
    scope = scope[
        scope["key"].notna() & (scope["key"] != "nan") & (scope["key"] != "")
    ].reset_index(drop=True)

    null_idx = scope[scope["scope_sprint"].isna()].index.tolist()
    if null_idx:
        try:
            _ext = pd.read_excel("data/extract_new.xlsx", sheet_name=0)
            _ext.columns = [str(c).strip() for c in _ext.columns]
            null_keys = scope.loc[null_idx, "key"].tolist()
            ext_map = (
                _ext[_ext["Key"].isin(null_keys)]
                .set_index("Key")["Expected Sprint"]
                .to_dict()
            )
            for idx in null_idx:
                k = scope.at[idx, "key"]
                ext_val = ext_map.get(k)
                jira_val = str(scope.at[idx, "jira_sprint"]).strip()
                if pd.notna(ext_val) and str(ext_val).strip() not in ("", "nan"):
                    scope.at[idx, "scope_sprint"] = ext_val
                elif jira_val not in ("0", "", "nan"):
                    scope.at[idx, "scope_sprint"] = jira_val
        except Exception:
            pass
    return scope


@st.cache_data(ttl=3600, show_spinner=False)
def load_r25_assignee_squad() -> pd.DataFrame:
    """Load the authoritative assignee→squad mapping from r25_assignee_squad table."""
    try:
        eng = _engine()
        if inspect(eng).has_table("r25_assignee_squad"):
            return pd.read_sql("SELECT assignee_name, squad FROM r25_assignee_squad", con=eng)
    except Exception:
        pass
    return pd.DataFrame(columns=["assignee_name", "squad"])


@st.cache_data(ttl=3600, show_spinner=False)
def load_team_availability():
    """Load team availability + sprint metadata from DB, fall back to local Excel."""
    try:
        eng = _engine()
        if inspect(eng).has_table("r25_team_avail") and inspect(eng).has_table("r25_sprint_meta"):
            team = pd.read_sql("SELECT squad, name, cap_prod, transverse FROM r25_team_avail", con=eng)
            meta = pd.read_sql("SELECT * FROM r25_sprint_meta WHERE sprint_name='R25'", con=eng)
            if not meta.empty:
                row = meta.iloc[0]
                sprint_info = {
                    "duration_days":  float(row["duration_days"]) if pd.notna(row["duration_days"]) else 15.0,
                    "start":          pd.Timestamp(row["sprint_start"]).date() if pd.notna(row["sprint_start"]) else None,
                    "end":            pd.Timestamp(row["sprint_end"]).date()   if pd.notna(row["sprint_end"])   else None,
                    "cap_planifiee":  float(row["cap_planifiee"])  if pd.notna(row["cap_planifiee"])  else None,
                    "velocite_reele": float(row["velocite_reele"]) if pd.notna(row["velocite_reele"]) else None,
                    "sp_vs_jh":       float(row["sp_vs_jh"])       if pd.notna(row["sp_vs_jh"])       else None,
                }
                return team, sprint_info
    except Exception:
        pass

    raw = pd.read_excel(
        "data/Release_lifecycle_R25.xlsx",
        sheet_name="Team availibility", header=None,
    )
    sprint_duration = float(raw.iloc[0, 13]) if pd.notna(raw.iloc[0, 13]) else 15.0
    cap_planifiee   = float(raw.iloc[0, 19]) if pd.notna(raw.iloc[0, 19]) else None
    velocite_reele  = float(raw.iloc[1, 19]) if pd.notna(raw.iloc[1, 19]) else None
    sp_vs_jh        = float(raw.iloc[23, 13]) if pd.notna(raw.iloc[23, 13]) else None

    try:
        start_dt = pd.to_datetime(raw.iloc[0, 16])
        end_dt   = pd.to_datetime(str(raw.iloc[1, 16]), dayfirst=True)
        if start_dt > end_dt:
            start_dt = pd.Timestamp(start_dt.year, start_dt.day, start_dt.month)
        sprint_start = start_dt.date()
        sprint_end   = end_dt.date()
    except Exception:
        sprint_start = _dt.date(2026, 3, 8)
        sprint_end   = _dt.date(2026, 4, 4)

    team = raw.iloc[1:22, [0, 1, 6, 7]].copy()
    team.columns = ["squad", "name", "contingence", "cap_prod"]
    team = team[team["name"].notna() & (team["name"].astype(str).str.strip() != "nan")].copy()
    team["name"]     = team["name"].astype(str).str.strip()
    team["squad"]    = team["squad"].astype(str).str.strip().replace({"nan": "—"})
    team["cap_prod"] = pd.to_numeric(team["cap_prod"], errors="coerce").fillna(0)
    team = team[["squad", "name", "cap_prod"]].reset_index(drop=True)

    sprint_info = {
        "duration_days":  sprint_duration,
        "start":          sprint_start,
        "end":            sprint_end,
        "cap_planifiee":  cap_planifiee,
        "velocite_reele": velocite_reele,
        "sp_vs_jh":       sp_vs_jh,
    }
    return team, sprint_info


# ── Name-matching utilities ───────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Normalize a person name for fuzzy matching."""
    s = str(s).lower()
    if "@" in s:
        s = s.split("@")[0]
    s = _re.sub(r"\(.*?\)", "", s)
    s = _re.sub(r"[,\.\-_@]", " ", s)
    s = _re.sub(r"\s+", " ", s).strip()
    tokens = sorted(t for t in s.split() if len(t) > 1)
    return " ".join(tokens)


def _name_score(a: str, b: str) -> float:
    """Per-token matching: for each token in the shorter name, find its best
    matching token in the longer name. Exact hits score 1.0; near-identical
    tokens (≥ 0.85 similarity) score 0.8."""
    na, nb = _norm(a), _norm(b)
    ta = list(set(na.split()))
    tb = list(set(nb.split()))
    if not ta or not tb:
        return 0.0
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    matched = 0.0
    for t in shorter:
        if t in set(longer):
            matched += 1.0
        else:
            best = max(_dl.SequenceMatcher(None, t, u).ratio() for u in longer)
            if best >= 0.85:
                matched += 0.8
    return matched / len(shorter)


def _match_names(avail_name: str, jira_names) -> tuple[str | None, float]:
    """Return (best_jira_name, score) for an availability sheet name."""
    best, best_s = None, 0.0
    for jn in jira_names:
        s = _name_score(avail_name, jn)
        if s > best_s:
            best, best_s = jn, s
    return (best if best_s >= 0.65 else None), best_s


# ── Filter helper ─────────────────────────────────────────────────────────────

def apply_filters(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    if "created" in df.columns and f.get("date_range") and len(f["date_range"]) == 2:
        s, e = f["date_range"]
        df = df[df["created"].between(pd.Timestamp(s), pd.Timestamp(e))]
    for col, key in [("organizations", "orgs"), ("issue_type", "types"),
                     ("environment_type", "envs"), ("priority", "priorities"),
                     ("project", "projects")]:
        if col in df.columns and f.get(key):
            df = df[df[col].isin(f[key])]
    return df
