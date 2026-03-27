# Sprint Burndown Chart in Power BI
## Step-by-step guide — data already loaded from MySQL

> **Assumption:** You have the `issues` table loaded in Power BI Desktop (Import mode).
> The guide assumes your table is named `issues` in Power Query.

---

## Table of Contents

1. [Verify Required Columns](#1-verify-required-columns)
2. [Fix Column Types in Power Query](#2-fix-column-types-in-power-query)
3. [Create a Date Table](#3-create-a-date-table)
4. [Create Calculated Columns on `issues`](#4-create-calculated-columns-on-issues)
5. [Create All DAX Measures](#5-create-all-dax-measures)
6. [Build the Burndown Page](#6-build-the-burndown-page)
7. [Sprint Issues Detail Table](#7-sprint-issues-detail-table)
8. [Carried-Over Issues Section](#8-carried-over-issues-section)
9. [KPI Cards at the Top](#9-kpi-cards-at-the-top)
10. [Final Page Layout](#10-final-page-layout)

---

## 1. Verify Required Columns

Before building anything, confirm these columns exist in your `issues` table.
In Power BI Desktop → **Data view** → click the `issues` table and check:

| Column | DB Type | Purpose |
|---|---|---|
| `expected_sprint` | Text | Sprint name (e.g. `TMA v22.25.1 ...`) |
| `original_expected_sprint` | Text | Original sprint before slip/carry-over |
| `story_points` | Decimal | Work weight per issue |
| `is_resolved` | True/False (or 0/1) | Whether the issue is done |
| `resolved` | Date/Time | When the issue was resolved |
| `closure_date` | Date/Time | Fallback resolution date |
| `key` | Text | Issue identifier (e.g. ABC-123) |
| `summary` | Text | Issue title |
| `issue_type` | Text | Bug / Story / Task / etc. |
| `priority` | Text | Critical / High / Medium / Low |
| `status` | Text | Current Jira status |

---

## 2. Fix Column Types in Power Query

**Home → Transform Data** to open Power Query Editor.

Set these types explicitly (right-click column header → **Change Type**):

| Column | Type to set |
|---|---|
| `resolved` | Date/Time |
| `closure_date` | Date/Time |
| `created` | Date/Time |
| `story_points` | Decimal Number |
| `is_resolved` | True/False |

Click **Close & Apply** when done.

---

## 3. Create a Date Table

You need a date table to scaffold the burndown line day by day.

Go to **Modeling → New Table** and paste:

```dax
DateTable =
ADDCOLUMNS(
    CALENDAR(DATE(2024,1,1), DATE(2027,12,31)),
    "Year",      YEAR([Date]),
    "Month",     MONTH([Date]),
    "YearMonth", FORMAT([Date], "YYYY-MM"),
    "WeekNum",   WEEKNUM([Date])
)
```

Then create the relationship:
- **Model view** → drag `DateTable[Date]` onto `issues[created]`
- Relationship: Many-to-one, Single direction

> The relationship to `created` is the default. The burndown measure uses `MAX(DateTable[Date])` inside its own CALCULATE context, so this relationship does not interfere.

---

## 4. Create Calculated Columns on `issues`

These columns are computed once and stored in the model.

Go to **Modeling → New Column** for each one below.

---

### 4a. Effective Resolution Date

The Python ETL uses `resolved` first, falls back to `closure_date`. Replicate that:

```dax
Resolved At =
IF(
    NOT ISBLANK(issues[resolved]),
    issues[resolved],
    issues[closure_date]
)
```

---

### 4b. Sprint Group (normalized name)

The raw `expected_sprint` column contains values like:
- `TMA v22.25.1 Sprint R25`
- `TMA v22.25.2 Sprint R25`
- `v22.25.1 R25 ADDS`

The Streamlit app groups all of these into a single sprint label (e.g. `v22 R25`).

In Power BI, the simplest approach: **use a slicer on `expected_sprint` directly and select all variants manually**, or use this calculated column to normalize them:

```dax
Sprint Group =
VAR raw = TRIM(issues[expected_sprint])
VAR upper = UPPER(raw)
RETURN
IF(
    ISBLANK(raw) || raw = "",
    BLANK(),
    IF(
        LEFT(upper, 3) = "TMA",
        -- Extract major.minor from TMA v{major}.{minor}.{sprint}...
        -- Simplified: return everything up to the 3rd dot segment as "vMajor RMinor"
        "TMA " &
            TRIM(
                MID(raw,
                    SEARCH(" ", raw) + 1,
                    SEARCH(".", raw, SEARCH(".", raw) + 1) - SEARCH(" ", raw) - 1
                )
            ) &
            " R" &
            TRIM(
                MID(raw,
                    SEARCH(".", raw, SEARCH(".", raw) + 1) + 1,
                    SEARCH(".", raw, SEARCH(".", raw, SEARCH(".", raw) + 1) + 1) -
                    SEARCH(".", raw, SEARCH(".", raw) + 1) - 1
                )
            ),
        raw
    )
)
```

> **Simpler alternative:** Skip `Sprint Group` entirely. Instead, use a slicer on the raw `expected_sprint` column with multi-select enabled. Select all rows that belong to the same sprint manually. This avoids complex DAX string parsing.

---

## 5. Create All DAX Measures

Create a dedicated measures table first:
**Modeling → New Table** → enter exactly: `Measures = {}`

Then add every measure below to that table (**Modeling → New Measure**, make sure the table dropdown shows `Measures`).

---

### Sprint Scope Measures

```dax
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

```dax
Sprint Total Tickets =
CALCULATE(
    COUNTROWS(issues),
    NOT ISBLANK(issues[expected_sprint])
)
```

```dax
Sprint Completed Tickets =
CALCULATE(
    COUNTROWS(issues),
    issues[is_resolved] = TRUE(),
    NOT ISBLANK(issues[expected_sprint])
)
```

```dax
Sprint Remaining Tickets =
[Sprint Total Tickets] - [Sprint Completed Tickets]
```

---

### Burndown Line Measure (Story Points mode)

This is the core measure — it computes how many points remain on each day.
It reads the current date from the X-axis of the chart (via `MAX(DateTable[Date])`).

```dax
Remaining Points on Date =
VAR currentDate = MAX(DateTable[Date])
RETURN
CALCULATE(
    SUM(issues[story_points]),
    NOT ISBLANK(issues[expected_sprint]),
    issues[is_resolved] = FALSE()
        || (
            issues[is_resolved] = TRUE()
            && issues[Resolved At] > currentDate
        )
)
```

**How this works:**
- For a given day on the X-axis, it counts points from issues that are either:
  - Still unresolved (`is_resolved = FALSE`), **or**
  - Resolved after that day (so they were still open at end of that day)
- This gives you the correct "remaining" value for each day.

---

### Ideal Burndown Line

The ideal line goes from total to zero linearly. Because Power BI can't compute a dynamic slope in a measure without knowing the sprint endpoints, use the **Analytics pane → Trend Line** as the simplest approach (see section 6).

Alternatively, hardcode the sprint total in a measure for reference:

```dax
Sprint Start Total =
-- Replace 42 with your sprint's actual total story points
-- Or use Sprint Total Points (static reference)
[Sprint Total Points]
```

---

### Ticket Count Burndown (alternative mode)

```dax
Remaining Tickets on Date =
VAR currentDate = MAX(DateTable[Date])
RETURN
CALCULATE(
    COUNTROWS(issues),
    NOT ISBLANK(issues[expected_sprint]),
    issues[is_resolved] = FALSE()
        || (
            issues[is_resolved] = TRUE()
            && issues[Resolved At] > currentDate
        )
)
```

---

### Carried-Over Issues

```dax
Carried Over Count =
CALCULATE(
    COUNTROWS(issues),
    NOT ISBLANK(issues[original_expected_sprint]),
    issues[original_expected_sprint] <> issues[expected_sprint]
)
```

```dax
Carried Over Points =
CALCULATE(
    SUM(issues[story_points]),
    NOT ISBLANK(issues[original_expected_sprint]),
    issues[original_expected_sprint] <> issues[expected_sprint]
)
```

```dax
Carried Over Still Open =
CALCULATE(
    COUNTROWS(issues),
    NOT ISBLANK(issues[original_expected_sprint]),
    issues[original_expected_sprint] <> issues[expected_sprint],
    issues[is_resolved] = FALSE()
)
```

---

## 6. Build the Burndown Page

### Step 1 — Add a Sprint Slicer

- Add a **Slicer** visual
- Field: `issues[expected_sprint]`
- Format → Slicer Settings → Style: **Dropdown** or **List**
- Enable **Multi-select** (so you can pick all variants of the same sprint together, e.g. v22 R25.1 and v22 R25.2)

> If you created the `Sprint Group` calculated column, use that instead for a cleaner single-selection.

---

### Step 2 — Add a Date Range Slicer

- Add a second **Slicer** visual
- Field: `DateTable[Date]`
- Format → Slicer Settings → Style: **Between** (date range picker)
- Set the range to match your sprint dates, e.g. **08 Mar 2026 → 26 Mar 2026**

> This controls what date range the burndown X-axis shows. Without this, the chart would span the entire date table.

---

### Step 3 — Create the Burndown Line Chart

- Add a **Line Chart** visual
- **X Axis:** `DateTable[Date]`
- **Y Axis:** `[Remaining Points on Date]`
- Rename the Y axis label to "Remaining (pts)"

**Add the Ideal line:**
- Click the chart → go to **Analytics pane** (magnifying glass icon on the right panel)
- Expand **Constant Line** → Add a constant line set to your sprint's total points (e.g. 42)
- Then add a **Trend Line** — this gives a rough ideal, but it's not a true linear burndown

**Better ideal line approach — add a second measure as a second Y series:**

```dax
Ideal Remaining =
-- You must hardcode the sprint total and sprint length here
-- Replace 42 = total story points, 19 = number of sprint days
VAR sprintTotal = 42
VAR sprintDays = 19
VAR dayIndex =
    DATEDIFF(
        DATE(2026, 3, 8),   -- sprint start date
        MAX(DateTable[Date]),
        DAY
    )
RETURN
MAX(0, sprintTotal * (1 - dayIndex / (sprintDays - 1)))
```

> Change `42`, `19`, and `DATE(2026, 3, 8)` to match your sprint.
> Add this as a second line series on the same chart.

- Second line: color `#A0A4A8` (grey), dashed style → Format → Lines → Line style: Dashed

**Final chart series:**
| Series | Measure | Color | Style |
|---|---|---|---|
| Actual Remaining | `[Remaining Points on Date]` | `#9B26AF` (DXC purple) | Solid, markers on |
| Ideal | `[Ideal Remaining]` | `#A0A4A8` (grey) | Dashed |

**Chart formatting:**
- Title: `Sprint Burndown — v22 R25`
- X axis: show dates, label every 2–3 days
- Y axis: starts at 0, no negative values
- Turn on **Data labels** for the Actual line

---

### Step 4 — Add Story Points vs Ticket Toggle

Power BI doesn't have a native radio button. Workaround options:

**Option A (simplest):** Create two separate pages — one for Story Points burndown, one for Ticket Count burndown.

**Option B:** Use a **Disconnected parameter table**:

```dax
BurnMode = DATATABLE(
    "Mode", STRING,
    "ModeID", INTEGER,
    {{"Story Points", 1}, {"Ticket Count", 2}}
)
```

Add a **Slicer** on `BurnMode[Mode]`, then use a dynamic measure:

```dax
Remaining Work on Date =
VAR selectedMode = SELECTEDVALUE(BurnMode[ModeID], 1)
VAR currentDate = MAX(DateTable[Date])
RETURN
IF(
    selectedMode = 1,
    -- Story Points mode
    CALCULATE(
        SUM(issues[story_points]),
        NOT ISBLANK(issues[expected_sprint]),
        issues[is_resolved] = FALSE()
            || (issues[is_resolved] = TRUE() && issues[Resolved At] > currentDate)
    ),
    -- Ticket Count mode
    CALCULATE(
        COUNTROWS(issues),
        NOT ISBLANK(issues[expected_sprint]),
        issues[is_resolved] = FALSE()
            || (issues[is_resolved] = TRUE() && issues[Resolved At] > currentDate)
    )
)
```

Use `[Remaining Work on Date]` on the chart instead of the two separate measures.

---

## 7. Sprint Issues Detail Table

Below the burndown chart, add a **Table** visual showing all issues in the selected sprint.

**Columns to add (drag from `issues`):**
1. `key`
2. `summary`
3. `issue_type`
4. `priority`
5. `status`
6. `story_points`
7. `Resolved At` (the calculated column from step 4a)

**Conditional formatting on `priority`:**
- Click the table → Format → Cell elements → `priority` column → Background color
- Rules:
  - `priority` = "Critical" → `#C62828` (red)
  - `priority` = "High" → `#E65100` (orange)

**Conditional formatting on `status`:**
- Unresolved statuses (In Progress, Open, Reopened) → light orange background

---

## 8. Carried-Over Issues Section

Add below the sprint issues table.

**KPI Cards (4 cards in a row):**

| Card | Measure |
|---|---|
| Carried Over (count) | `[Carried Over Count]` |
| % of Sprint | `DIVIDE([Carried Over Count], [Sprint Total Tickets], 0) * 100` |
| Carried Points | `[Carried Over Points]` |
| Still Open | `[Carried Over Still Open]` |

Color the first two cards orange (`#E65100`) and the "Still Open" card red (`#C62828`).

**Carried-over detail table:**

Add a **Table** visual filtered to only show carried-over issues:

- Add a visual-level filter:
  - Field: `issues[original_expected_sprint]`
  - Filter type: **Is not blank**
- Also filter where `original_expected_sprint` ≠ `expected_sprint` — this requires a calculated column:

```dax
Is Carried Over =
IF(
    NOT ISBLANK(issues[original_expected_sprint])
        && issues[original_expected_sprint] <> issues[expected_sprint],
    TRUE(),
    FALSE()
)
```

Add a visual-level filter on `Is Carried Over` = `TRUE`.

Columns for this table: `key`, `summary`, `original_expected_sprint`, `priority`, `status`, `story_points`

---

## 9. KPI Cards at the Top

Add 4 KPI cards in a row at the very top of the Sprint Burndown page:

| Position | Title | Measure | Conditional color |
|---|---|---|---|
| Card 1 | Sprint | *(text slicer or title)* | — |
| Card 2 | Total Work | `[Sprint Total Points]` | None |
| Card 3 | Completed | `[Sprint Completed Points]` | Purple if ≥ 80% done, Orange otherwise |
| Card 4 | Done % | `[Sprint Done %]` | Purple if ≥ 80%, Orange otherwise |

For conditional coloring on Card 3 and 4, use a measure:

```dax
Done Color Flag =
IF([Sprint Done %] >= 80, "#9B26AF", "#E65100")
```

Apply via **Format → Callout value → Font color → Conditional formatting → Field value → Done Color Flag**.

---

## 10. Final Page Layout

```
┌────────────────────────────────────────────────────┐
│  [Sprint Slicer]            [Date Range Slicer]    │
├──────────┬──────────┬──────────┬───────────────────┤
│  Sprint  │ Total Pts│ Completed│     Done %        │
│  v22 R25 │    42    │    36    │     85.7%         │
├──────────┴──────────┴──────────┴───────────────────┤
│                                                    │
│          BURNDOWN LINE CHART                       │
│          (Actual purple solid + Ideal grey dashed) │
│                                                    │
├────────────────────────────────────────────────────┤
│          SPRINT ISSUES TABLE                       │
│  key | summary | type | priority | status | pts   │
├────────────────────────────────────────────────────┤
│  Carried Over: 3   | % of Sprint: 12.5%            │
│  Carried Pts: 8    | Still Open: 2                 │
│          CARRIED-OVER ISSUES TABLE                 │
└────────────────────────────────────────────────────┘
```

**Slicers sync:** Go to **View → Sync Slicers** and sync the Sprint slicer and Date Range slicer across all pages.

---

## Quick Troubleshooting

| Problem | Fix |
|---|---|
| Burndown line is flat (doesn't change by day) | The Date slicer must be set to a range — the measure needs `MAX(DateTable[Date])` to vary by day on the X axis. Make sure the X axis is `DateTable[Date]`, not `issues[created]`. |
| Remaining goes up on some days | Some issues were re-opened or their `resolved` date changed. This is correct behavior — the actual line reflects real data. |
| All values are blank | Check that the sprint slicer selection matches values in `expected_sprint`. The column may have leading/trailing spaces — fix in Power Query with `Text.Trim`. |
| Story points all zero | The `story_points` column type must be **Decimal Number**, not Text. Fix in Power Query. |
| `Resolved At` column is blank | Check that `resolved` and `closure_date` are loaded as Date/Time, not Text. Fix column types in Power Query. |
| Carried over count is wrong | `original_expected_sprint` must be loaded as Text. The `Is Carried Over` column compares raw strings — make sure both sprint columns are trimmed in Power Query. |

---

*Database: Aiven MySQL — ReportingSystemDB — table: `issues`*
*Sprint in use: v22 R25 (08 Mar 2026 → 26 Mar 2026)*
*Created: 2026-03-27*
