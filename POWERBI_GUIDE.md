# Power BI Integration Guide
## DXC Service Desk Analytics — Full Reference

---

## Table of Contents

1. [Connecting Power BI to Aiven MySQL](#1-connecting-power-bi-to-aiven-mysql)
2. [Data Model Setup](#2-data-model-setup)
3. [DAX Measures — Full Library](#3-dax-measures--full-library)
4. [KPI Cards](#4-kpi-cards)
5. [Overview Page](#5-overview-page)
6. [Trends Page](#6-trends-page)
7. [Analysis Page](#7-analysis-page)
8. [SLA & KPIs Page](#8-sla--kpis-page)
9. [Sprint Burndown Page](#9-sprint-burndown-page)
10. [AI Agent Integration](#10-ai-agent-integration)
11. [Report Layout Recommendations](#11-report-layout-recommendations)

---

## 1. Connecting Power BI to Aiven MySQL

### Prerequisites

1. Download and install **MySQL Connector/NET** (version 8.x)
   - Search: `MySQL Connector NET download site:dev.mysql.com`
   - Install it on the same machine as Power BI Desktop

2. Download **Power BI Desktop** (free, from Microsoft Store or powerbi.com)

---

### Step-by-Step Connection

**Step 1 — Open Power BI Desktop**
- Click **Get Data** (Home ribbon) → search **MySQL database** → click **Connect**

**Step 2 — Enter server details**
```
Server:   mysql-6047a7e-uca-0f17.e.aivencloud.com:25768
Database: ReportingSystemDB
```
- Data Connectivity mode: **Import** (recommended for performance)
- Click **OK**

**Step 3 — Authentication**
- Select **Database** tab (not Windows)
- Username: `avnadmin`
- Password: *(from your `.env` file — `DB_PASSWORD`)*
- Click **Connect**

**Step 4 — SSL Certificate (required by Aiven)**

If you get an SSL error:
1. Log into your Aiven console → select your MySQL service
2. Go to **Overview** tab → scroll to **Connection Information**
3. Click **Download CA Certificate** → save as `aiven-ca.crt`
4. In Power BI: **File → Options and Settings → Options → Security**
5. Under **Trusted server certificates**, add the path to `aiven-ca.crt`
6. Retry the connection

**Step 5 — Load the table**
- In the Navigator window, check `ReportingSystemDB` → `issues`
- Click **Transform Data** to open Power Query first (recommended)
- In Power Query, verify column types look correct, then click **Close & Apply**

---

### Scheduled Refresh (Power BI Service)

Once you publish the report to Power BI Service:
1. Go to your dataset → **Settings → Data source credentials**
2. Enter the same MySQL credentials
3. Under **Scheduled refresh**, enable it and set frequency (daily recommended)
4. Aiven MySQL will be queried automatically — no manual refresh needed

---

## 2. Data Model Setup

### Column Types to Set in Power Query

After connecting, open **Transform Data** and set these types explicitly:

| Column | Type |
|---|---|
| `key` | Text |
| `created` | Date/Time |
| `resolved` | Date/Time |
| `closure_date` | Date/Time |
| `last_comment_datetime` | Date/Time |
| `start_date_time` | Date/Time |
| `due_date` | Date/Time |
| `qualification_date` | Date/Time |
| `sending_date` | Date/Time |
| `is_resolved` | True/False |
| `resolution_days` | Decimal Number |
| `story_points` | Decimal Number |
| `occurrences` | Decimal Number |
| `created_year` | Whole Number |
| `created_month` | Whole Number |
| `created_week` | Whole Number |
| `kpi_time_to_solve_minutes` | Decimal Number |
| `kpi_time_initial_response_minutes` | Decimal Number |
| `kpi_time_to_analyse_minutes` | Decimal Number |
| `kpi_time_to_assist_minutes` | Decimal Number |
| `kpi_time_to_estimate_minutes` | Decimal Number |
| All other columns | Text |

### Add a Date Table (Best Practice)

In Power BI Desktop → **Modeling → New Table**:

```dax
DateTable =
ADDCOLUMNS(
    CALENDAR(DATE(2020,1,1), DATE(2030,12,31)),
    "Year",        YEAR([Date]),
    "Month",       MONTH([Date]),
    "MonthName",   FORMAT([Date], "MMMM"),
    "Quarter",     "Q" & QUARTER([Date]),
    "YearMonth",   FORMAT([Date], "YYYY-MM"),
    "WeekNum",     WEEKNUM([Date]),
    "DayOfWeek",   FORMAT([Date], "dddd"),
    "IsWeekend",   IF(WEEKDAY([Date],2) >= 6, TRUE, FALSE)
)
```

Then create a relationship:
- `DateTable[Date]` → `issues[created]` (many-to-one)

---

## 3. DAX Measures — Full Library

Create a dedicated **Measures** table: **Modeling → New Table** → `Measures = {}`

Then add all measures below to that table.

---

### Core Counts

```dax
Total Issues = COUNTROWS(issues)
```

```dax
Resolved Issues =
CALCULATE(COUNTROWS(issues), issues[is_resolved] = TRUE())
```

```dax
Open Issues =
CALCULATE(COUNTROWS(issues), issues[is_resolved] = FALSE())
```

```dax
Critical Issues =
CALCULATE(COUNTROWS(issues), issues[priority] = "Critical")
```

```dax
High Priority Issues =
CALCULATE(COUNTROWS(issues), issues[priority] = "High")
```

```dax
Critical Open =
CALCULATE(
    COUNTROWS(issues),
    issues[priority] = "Critical",
    issues[is_resolved] = FALSE()
)
```

---

### Resolution Metrics

```dax
Resolution Rate % =
DIVIDE([Resolved Issues], [Total Issues], 0) * 100
```

```dax
Avg Resolution Days =
AVERAGEX(
    FILTER(issues, NOT ISBLANK(issues[resolution_days])),
    issues[resolution_days]
)
```

```dax
Median Resolution Days =
MEDIANX(
    FILTER(issues, NOT ISBLANK(issues[resolution_days])),
    issues[resolution_days]
)
```

```dax
Max Resolution Days =
MAXX(issues, issues[resolution_days])
```

```dax
Issues Resolved This Month =
CALCULATE(
    COUNTROWS(issues),
    issues[is_resolved] = TRUE(),
    MONTH(issues[resolved]) = MONTH(TODAY()),
    YEAR(issues[resolved]) = YEAR(TODAY())
)
```

```dax
Issues Created This Month =
CALCULATE(
    COUNTROWS(issues),
    MONTH(issues[created]) = MONTH(TODAY()),
    YEAR(issues[created]) = YEAR(TODAY())
)
```

---

### SLA Measures

```dax
SLA Met =
CALCULATE(COUNTROWS(issues), issues[sla_justified] = "Yes")
```

```dax
SLA Breached =
CALCULATE(COUNTROWS(issues), issues[sla_justified] = "No")
```

```dax
SLA Evaluated =
CALCULATE(
    COUNTROWS(issues),
    issues[sla_justified] IN {"Yes", "No"}
)
```

```dax
SLA Compliance % =
DIVIDE([SLA Met], [SLA Evaluated], 0) * 100
```

```dax
SLA Compliance % (formatted) =
FORMAT([SLA Compliance %], "0.0") & "%"
```

```dax
SLA Breach Rate % =
DIVIDE([SLA Breached], [SLA Evaluated], 0) * 100
```

---

### KPI Time Measures

```dax
KPI Solve On Time =
CALCULATE(
    COUNTROWS(issues),
    issues[kpi_time_to_solve_minutes] >= 0
)
```

```dax
KPI Solve Breached =
CALCULATE(
    COUNTROWS(issues),
    issues[kpi_time_to_solve_minutes] < 0
)
```

```dax
KPI Solve On-Time Rate % =
DIVIDE(
    [KPI Solve On Time],
    [KPI Solve On Time] + [KPI Solve Breached],
    0
) * 100
```

```dax
Avg KPI Time to Solve (h) =
AVERAGEX(
    FILTER(issues, issues[kpi_time_to_solve_minutes] >= 0),
    issues[kpi_time_to_solve_minutes] / 60
)
```

```dax
Avg KPI Initial Response (h) =
AVERAGEX(
    FILTER(issues, issues[kpi_time_initial_response_minutes] >= 0),
    issues[kpi_time_initial_response_minutes] / 60
)
```

```dax
Avg KPI Time to Analyse (h) =
AVERAGEX(
    FILTER(issues, issues[kpi_time_to_analyse_minutes] >= 0),
    issues[kpi_time_to_analyse_minutes] / 60
)
```

```dax
Avg KPI Time to Assist (h) =
AVERAGEX(
    FILTER(issues, issues[kpi_time_to_assist_minutes] >= 0),
    issues[kpi_time_to_assist_minutes] / 60
)
```

```dax
Avg KPI Time to Estimate (h) =
AVERAGEX(
    FILTER(issues, issues[kpi_time_to_estimate_minutes] >= 0),
    issues[kpi_time_to_estimate_minutes] / 60
)
```

---

### Story Points / Sprint

```dax
Total Story Points =
SUM(issues[story_points])
```

```dax
Completed Story Points =
CALCULATE(
    SUM(issues[story_points]),
    issues[is_resolved] = TRUE()
)
```

```dax
Remaining Story Points =
[Total Story Points] - [Completed Story Points]
```

```dax
Sprint Completion % =
DIVIDE([Completed Story Points], [Total Story Points], 0) * 100
```

```dax
Unpointed Issues =
CALCULATE(
    COUNTROWS(issues),
    ISBLANK(issues[story_points])
)
```

---

### Period-over-Period Measures

```dax
Issues Previous Month =
CALCULATE(
    [Total Issues],
    PREVIOUSMONTH(DateTable[Date])
)
```

```dax
Issues MoM Change =
[Total Issues] - [Issues Previous Month]
```

```dax
Issues MoM Change % =
DIVIDE([Issues MoM Change], [Issues Previous Month], 0) * 100
```

```dax
SLA Compliance Previous Month =
CALCULATE(
    [SLA Compliance %],
    PREVIOUSMONTH(DateTable[Date])
)
```

```dax
SLA Compliance MoM Change =
[SLA Compliance %] - [SLA Compliance Previous Month]
```

---

### Assignee Metrics

```dax
Assignee Resolution Rate % =
DIVIDE(
    CALCULATE([Resolved Issues]),
    CALCULATE([Total Issues]),
    0
) * 100
```

```dax
Assignee Avg Resolution Days =
AVERAGEX(
    FILTER(issues, NOT ISBLANK(issues[resolution_days])),
    issues[resolution_days]
)
```

```dax
Assignee Critical Count =
CALCULATE([Total Issues], issues[priority] = "Critical")
```

---

## 4. KPI Cards

Use **Card** visuals for each. Add conditional formatting where noted.

| Card Title | Measure | Conditional Format |
|---|---|---|
| Total Issues | `[Total Issues]` | None |
| Open Issues | `[Open Issues]` | Red if > threshold |
| Resolved Issues | `[Resolved Issues]` | None |
| Resolution Rate | `[Resolution Rate %]` | Green ≥ 80%, Orange < 80% |
| Critical Open | `[Critical Open]` | Red if > 0 |
| SLA Compliance | `[SLA Compliance %]` | Green ≥ 80%, Red < 60% |
| Avg Resolution Days | `[Avg Resolution Days]` | None |
| Median Resolution Days | `[Median Resolution Days]` | None |
| KPI Solve On-Time Rate | `[KPI Solve On-Time Rate %]` | Green ≥ 80%, Red < 60% |
| Total Story Points | `[Total Story Points]` | None |
| Sprint Completion | `[Sprint Completion %]` | Green ≥ 80% |

---

## 5. Overview Page

### Chart 1 — Issues by Type (Donut Chart)
- Visual: **Donut Chart**
- Legend: `issue_type`
- Values: `[Total Issues]`
- Colors: Use DXC palette (#6D2077, #9B26AF, #B04FC0, #6D7278)

### Chart 2 — Issues by Priority (Bar Chart)
- Visual: **Clustered Bar Chart**
- Axis: `priority`
- Values: `[Total Issues]`
- Sort axis: Critical → High → Medium → Low

Custom sort: Create a calculated column:
```dax
Priority Order =
SWITCH(issues[priority],
    "Critical", 1,
    "High",     2,
    "Medium",   3,
    "Low",      4,
    5
)
```
Sort `priority` by `Priority Order`.

Color each bar manually: Critical=#C62828, High=#E65100, Medium=#6D2077, Low=#4A4A4A

### Chart 3 — Top Statuses (Horizontal Bar)
- Visual: **Clustered Bar Chart** (horizontal)
- Axis: `status`
- Values: `[Total Issues]`
- Top N filter: 10
- Sort: Descending by count

### Chart 4 — Issues by Project (Horizontal Bar)
- Visual: **Clustered Bar Chart** (horizontal)
- Axis: `project`
- Values: `[Total Issues]`
- Top N filter: 15
- Sort: Descending by count

### Chart 5 — Issues by Environment Type (Pie)
- Visual: **Pie Chart**
- Legend: `environment_type`
- Values: `[Total Issues]`

---

## 6. Trends Page

### Chart 1 — Monthly Volume Trend (Area Chart)
- Visual: **Area Chart**
- X Axis: `created_yearmonth` (or use `DateTable[YearMonth]`)
- Y Axis: `[Total Issues]`
- Sort X axis ascending

### Chart 2 — Created vs Resolved per Month (Grouped Bar)
- Visual: **Clustered Column Chart**
- X Axis: `created_yearmonth`
- Values:
  - `[Total Issues]` (rename to "Created")
  - A second measure for resolved by resolved date:

```dax
Resolved by Month =
CALCULATE(
    COUNTROWS(issues),
    issues[is_resolved] = TRUE(),
    USERELATIONSHIP(DateTable[Date], issues[resolved])
)
```

### Chart 3 — Issues by Day of Week (Bar Chart)
- Visual: **Clustered Column Chart**
- Add a calculated column first:

```dax
Day of Week = FORMAT(issues[created], "dddd")
```

```dax
Day of Week Order = WEEKDAY(issues[created], 2)
```

Sort `Day of Week` by `Day of Week Order`

- X Axis: `Day of Week`
- Values: `[Total Issues]`

### Chart 4 — Issue Type Mix Over Time (Stacked Area)
- Visual: **Stacked Area Chart**
- X Axis: `created_yearmonth`
- Y Axis: `[Total Issues]`
- Legend: `issue_type`

### Chart 5 — Rolling 3-Month Average
```dax
Rolling 3M Avg Issues =
AVERAGEX(
    DATESINPERIOD(DateTable[Date], LASTDATE(DateTable[Date]), -3, MONTH),
    [Issues Created This Month]
)
```

---

## 7. Analysis Page

### Chart 1 — Top Assignees by Volume (Horizontal Bar)
- Visual: **Clustered Bar Chart** (horizontal)
- Axis: `assignee`
- Values: `[Total Issues]`
- Top N filter: 15
- Add tooltip: `[Resolved Issues]`, `[Assignee Resolution Rate %]`

### Chart 2 — Assignee Performance Table
- Visual: **Table** or **Matrix**
- Rows: `assignee`
- Values:
  - `[Total Issues]`
  - `[Resolved Issues]`
  - `[Assignee Resolution Rate %]`
  - `[Assignee Avg Resolution Days]`
  - `[Assignee Critical Count]`

Add conditional formatting (data bars or color scale) on Resolution Rate % column.

### Chart 3 — Root Cause Origin (Donut)
- Visual: **Donut Chart**
- Legend: `root_cause_origin`
- Values: `[Total Issues]`

### Chart 4 — Product Line Distribution (Pie)
- Visual: **Pie Chart**
- Legend: `product_line`
- Values: `[Total Issues]`

### Chart 5 — Priority × Issue Type Heatmap (Matrix)
- Visual: **Matrix**
- Rows: `priority`
- Columns: `issue_type`
- Values: `[Total Issues]`
- Enable conditional formatting → Background color (white to #6D2077)

### Chart 6 — Component Breakdown (Horizontal Bar)
- Visual: **Clustered Bar Chart** (horizontal)
- Axis: `component`
- Values: `[Total Issues]`
- Top N filter: 10

### Chart 7 — Resolution Owner Split (Column Chart)
- Visual: **Clustered Column Chart**
- Axis: `resolution_owner`
- Values: `[Total Issues]`

---

## 8. SLA & KPIs Page

### Chart 1 — SLA Compliance Gauge
- Visual: **Gauge**
- Value: `[SLA Compliance %]`
- Min: 0, Max: 100
- Target: 80
- Color zones: 0–60 red, 60–80 orange, 80–100 green

### Chart 2 — SLA by Issue Type (Stacked Bar)
- Visual: **Stacked Bar Chart**
- Axis: `issue_type`
- Values:
  - `[SLA Met]` (color: #6D2077)
  - `[SLA Breached]` (color: #A0A4A8)

### Chart 3 — SLA by Priority (Grouped Bar)
- Visual: **Clustered Column Chart**
- Axis: `priority`
- Values:
  - `[SLA Met]`
  - `[SLA Breached]`
- Sort: Critical → High → Medium → Low

### Chart 4 — SLA Compliance Over Time (Line Chart)
- Visual: **Line Chart**
- X Axis: `created_yearmonth`
- Y Axis: `[SLA Compliance %]`
- Add a constant line at 80% (Analytics pane → Constant line)

### Chart 5 — Resolution Time Distribution (Histogram)

Power BI doesn't have a native histogram for continuous data. Use this approach:

Create a calculated column for buckets:
```dax
Resolution Bucket =
SWITCH(TRUE(),
    issues[resolution_days] <= 1,   "0–1 day",
    issues[resolution_days] <= 3,   "1–3 days",
    issues[resolution_days] <= 7,   "3–7 days",
    issues[resolution_days] <= 14,  "7–14 days",
    issues[resolution_days] <= 30,  "14–30 days",
    issues[resolution_days] <= 60,  "30–60 days",
    issues[resolution_days] <= 90,  "60–90 days",
    "90+ days"
)
```

```dax
Resolution Bucket Order =
SWITCH(issues[Resolution Bucket],
    "0–1 day",    1,
    "1–3 days",   2,
    "3–7 days",   3,
    "7–14 days",  4,
    "14–30 days", 5,
    "30–60 days", 6,
    "60–90 days", 7,
    "90+ days",   8
)
```

Sort `Resolution Bucket` by `Resolution Bucket Order`.

- Visual: **Clustered Column Chart**
- Axis: `Resolution Bucket`
- Values: `[Total Issues]`

### Chart 6 — KPI Summary Table
- Visual: **Table**
- Add one row per KPI using a disconnected table approach

Create a new table:
```dax
KPI Summary = DATATABLE(
    "KPI Name", STRING,
    {
        {"Time to Solve"},
        {"Initial Response"},
        {"Time to Analyse"},
        {"Time to Assist"},
        {"Time to Estimate"}
    }
)
```

Then create measures per KPI (example for Time to Solve):
```dax
KPI Solve Total =
COUNTROWS(FILTER(issues, NOT ISBLANK(issues[kpi_time_to_solve_minutes])))
```

```dax
KPI Solve On-Time Count =
CALCULATE(COUNTROWS(issues), issues[kpi_time_to_solve_minutes] >= 0)
```

```dax
KPI Solve Breached Count =
CALCULATE(COUNTROWS(issues), issues[kpi_time_to_solve_minutes] < 0)
```

```dax
KPI Solve Avg Hours =
AVERAGEX(
    FILTER(issues, issues[kpi_time_to_solve_minutes] >= 0),
    issues[kpi_time_to_solve_minutes] / 60
)
```

Repeat the same pattern replacing `kpi_time_to_solve_minutes` with:
- `kpi_time_initial_response_minutes`
- `kpi_time_to_analyse_minutes`
- `kpi_time_to_assist_minutes`
- `kpi_time_to_estimate_minutes`

---

## 9. Sprint Burndown Page

### Setup

Create a **Sprint slicer** first using `expected_sprint` column.

Add a calculated column to normalize sprint names (same logic as the Python `sprint_group()` function):

```dax
Sprint Group =
VAR raw = TRIM(issues[expected_sprint])
VAR isTMA = LEFT(UPPER(raw), 3) = "TMA"
RETURN
IF(
    ISBLANK(raw),
    BLANK(),
    IF(
        isTMA,
        "TMA v" &
            TRIM(MID(raw, FIND(" ", raw) + 1,
                FIND(".", raw, FIND(".", raw, FIND(" ", raw)) + 1) -
                FIND(" ", raw) - 1)) &
            " R" &
            TRIM(MID(raw,
                FIND(".", raw, FIND(".", raw, FIND(" ", raw)) + 1) + 1,
                FIND(".", raw, FIND(".", raw, FIND(".", raw, FIND(" ", raw)) + 1) + 1) -
                FIND(".", raw, FIND(".", raw, FIND(" ", raw)) + 1) - 1)),
        raw
    )
)
```

> Note: For complex sprint name normalization, it is easier to use the `sprint_group` column pre-computed by the Python ETL — it is already stored in the database as `expected_sprint` after processing. Use that column directly.

### Chart 1 — Sprint Burndown (Line Chart)

For a proper burndown, you need a date scaffold. Create this calculated table when a sprint is selected:

```dax
-- First, create measures for sprint context

Sprint Total Points =
CALCULATE(
    SUM(issues[story_points]),
    NOT ISBLANK(issues[expected_sprint])
)
```

```dax
Sprint Completed Points =
CALCULATE(
    SUM(issues[story_points]),
    issues[is_resolved] = TRUE(),
    NOT ISBLANK(issues[expected_sprint])
)
```

```dax
Sprint Remaining Points =
[Sprint Total Points] - [Sprint Completed Points]
```

```dax
Sprint Done % =
DIVIDE([Sprint Completed Points], [Sprint Total Points], 0) * 100
```

For the actual day-by-day burndown line, use the Date Table:
```dax
Remaining on Date =
VAR currentDate = MAX(DateTable[Date])
RETURN
CALCULATE(
    SUM(issues[story_points]),
    issues[is_resolved] = FALSE() ||
    (issues[is_resolved] = TRUE() && issues[resolved] > currentDate),
    NOT ISBLANK(issues[expected_sprint])
)
```

- Visual: **Line Chart**
- X Axis: `DateTable[Date]` (filtered to sprint range via slicer)
- Y Axis: `[Remaining on Date]`
- Add a second line for ideal burndown using an analytics pane constant or a secondary measure

### Chart 2 — Sprint Issues Table
- Visual: **Table**
- Columns: `key`, `summary`, `priority`, `status`, `story_points`, `resolved`
- Filter: current sprint via slicer
- Conditional format: highlight unresolved critical rows in red

### Sprint KPI Cards
Add these 4 cards at the top of the burndown page:
- `[Sprint Total Points]`
- `[Sprint Completed Points]`
- `[Sprint Remaining Points]`
- `[Sprint Done %]`

---

## 10. AI Agent Integration

The AI agent (`agent.py`) runs inside the **Streamlit app** and queries the same Aiven MySQL database using natural language. Power BI and the AI agent are independent presentation layers over the same data.

### What the AI Agent Does

| User asks | Agent does |
|---|---|
| "How many critical issues are open?" | Runs `SELECT COUNT(*) FROM issues WHERE priority='Critical' AND is_resolved=0` |
| "Is SLA getting worse?" | Queries monthly SLA % and describes the trend |
| "Who resolved the most issues this month?" | Groups by assignee, filters by resolved date |
| "Generate a weekly summary" | Pulls all KPIs and writes a management-style paragraph |
| "Is sprint v22 R25 on track?" | Calculates remaining vs ideal burndown |

### Setup Steps

1. Get a Claude API key from console.anthropic.com
2. Add it to your `.env` file:
```
ANTHROPIC_API_KEY=sk-ant-...
```
3. Install the SDK:
```bash
pip install anthropic
```
4. The `agent.py` file (in the project root) handles all conversation logic
5. In `app.py`, a **Chat** tab calls `run_agent(user_message, engine)`

### What the Agent Has Access To

- Full `issues` table via read-only SQL queries
- Pre-computed summary stats (total, resolved, SLA %, avg days)
- All columns: priority, assignee, project, sprint, KPI times, story points, dates

### Security

- The agent is restricted to `SELECT` queries only — it cannot modify the database
- Input validation strips any non-SELECT statements before execution
- Conversation history is stored in `st.session_state` (in-memory, per session only)

---

## 11. Report Layout Recommendations

### Suggested Power BI File Structure

```
report_sys.pbix
├── Page 1: Executive Overview
│   ├── 6 KPI cards (row at top)
│   ├── Issues by Type (donut)
│   ├── Issues by Priority (bar)
│   ├── SLA Compliance (gauge)
│   └── Month-over-month trend (line)
│
├── Page 2: SLA & KPIs
│   ├── SLA compliance by type & priority
│   ├── KPI on-time rates (5 gauges or table)
│   └── Resolution time distribution
│
├── Page 3: Team Performance
│   ├── Assignee volume & resolution rate
│   ├── Priority × assignee matrix
│   └── Resolution owner split
│
├── Page 4: Trends
│   ├── Monthly volume area chart
│   ├── Created vs resolved grouped bar
│   └── Issue type mix over time
│
└── Page 5: Sprint Burndown
    ├── Sprint slicer
    ├── 4 KPI cards
    ├── Burndown line chart
    └── Sprint issues table
```

### DXC Brand Colors (for Power BI theme)

Go to **View → Themes → Customize current theme** and use:

```json
{
  "name": "DXC Technology",
  "dataColors": [
    "#6D2077",
    "#9B26AF",
    "#B04FC0",
    "#4A1557",
    "#6D7278",
    "#A0A4A8",
    "#3D3D3D",
    "#D0D0D0"
  ],
  "background": "#FFFFFF",
  "foreground": "#0D0D0D",
  "tableAccent": "#6D2077"
}
```

Save as a `.json` file and import it via **View → Themes → Browse for themes**.

### Slicers to Add on Every Page

| Slicer | Column | Type |
|---|---|---|
| Date Range | `created` | Between (date range) |
| Issue Type | `issue_type` | Dropdown or list |
| Priority | `priority` | List (checkboxes) |
| Project | `project` | Dropdown |
| Assignee | `assignee` | Dropdown |
| Status | `status` | Dropdown |

Use **Sync Slicers** (View → Sync Slicers) to make Date Range and Priority apply across all pages.

---

## Quick Reference — Measure Cheat Sheet

| What you want | Measure |
|---|---|
| Count all issues | `[Total Issues]` |
| Count open issues | `[Open Issues]` |
| Count resolved | `[Resolved Issues]` |
| Resolution % | `[Resolution Rate %]` |
| SLA pass count | `[SLA Met]` |
| SLA fail count | `[SLA Breached]` |
| SLA compliance % | `[SLA Compliance %]` |
| Avg days to resolve | `[Avg Resolution Days]` |
| Median days to resolve | `[Median Resolution Days]` |
| KPI solve on-time % | `[KPI Solve On-Time Rate %]` |
| Sprint total points | `[Sprint Total Points]` |
| Sprint done % | `[Sprint Done %]` |
| Month-over-month change | `[Issues MoM Change %]` |

---

*Last updated: 2026-03-25*
*Database: Aiven MySQL — ReportingSystemDB*
*ETL: etl.py → Streamlit upload tab*
*AI Agent: agent.py — Claude API (Anthropic)*
