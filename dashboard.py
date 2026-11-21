"""Presentation and response-contract validation for GEO Pulse AI."""

from collections import Counter
from html import escape
from math import isfinite

import plotly.graph_objects as go
import streamlit as st

TEAL = "#0f9886"
INK = "#142638"
MUTED = "#53667c"
SOURCE_LABELS = {
    "bundled": ("Synthetic demo", "Bundled AcmeFlow example · simulated responses"),
    "backend_demo": ("Synthetic demo", "Backend demo mode · simulated responses"),
    "live": ("Live results", "Provider responses from your latest live scan"),
}

STYLES = """
<style>
[data-testid="stAppViewContainer"], [data-testid="stHeader"] { background: #eff4f8; }
[data-testid="stMainBlockContainer"] { max-width: 88rem; padding: 4rem 3.1rem 3rem; }
[data-testid="stAppDeployButton"] { display: none; }
[data-testid="stSidebar"] { background: #101e30; min-width: 282px; }
[data-testid="stSidebarContent"] { color: #dce8f5; }
[data-testid="stSidebarUserContent"] { padding: .4rem 1.15rem 1.3rem; }
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] { gap: .7rem; }
[data-testid="stSidebar"] p, [data-testid="stSidebar"] summary,
[data-testid="stSidebar"] summary span { color: #dce8f5; }
[data-testid="stSidebar"] [data-testid="stTextInputRootElement"],
[data-testid="stSidebar"] [data-testid="stTextAreaRootElement"] {
    background: #182b40; border-color: #30465e; border-radius: 8px;
}
[data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea { color: #f0f7ff; }
[data-testid="stSidebar"] input::placeholder { color: #a4b5ca; }
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { font-size: .875rem; }
[data-testid="stSidebar"] [data-testid="stExpander"] details { border-color: #32465e; }
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover { background: #192e44; }
[data-testid="stSidebar"] hr { border-color: #34485f; margin: .25rem 0; }
[data-testid="stSidebar"] button[kind="primary"] {
    background: #5bedc8; border-color: #5bedc8; border-radius: 9px;
    min-height: 2.75rem; color: #0b2a2b; font-weight: 750;
}
[data-testid="stSidebar"] button[kind="primary"]:hover {
    background: #8ef5da; border-color: #8ef5da;
}
[data-testid="stSidebar"] button[kind="primary"] p { color: #0b2a2b; font-weight: 750; }
[data-testid="stSidebar"] button[kind="tertiary"] p { color: #a9c2da; font-size: .875rem; }
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button {
    background: #182b40; color: #dce8f5; border-color: #30465e;
}
[data-testid="stSidebar"] [data-testid="stButtonGroup"] button[aria-checked="true"] {
    background: #21534f; color: #d1fff1; border-color: #56c4ac;
}
[data-testid="stSidebarCollapseButton"] button span { color: #dce8f5; }
[data-testid="stSidebarCollapseButton"] button:hover { background: #213c52; }
.st-key-navigation [role="radiogroup"] { gap: .2rem; }
.st-key-navigation label {
    padding: .45rem .65rem; margin: 0; border-radius: 7px; background: transparent;
}
.st-key-navigation label:has(input:checked) { background: #213c52; }
.st-key-navigation label:has(input:checked) p { color: #92f5dc; font-weight: 650; }
.st-key-navigation label:focus-within { outline: 2px solid #69e4ca; outline-offset: 1px; }
.product { display: flex; align-items: center; gap: .7rem; margin: .05rem 0 .7rem; }
.product-mark {
    display: grid; place-items: center; width: 2.45rem; height: 2.45rem; border-radius: 10px;
    background: #5bedc8; color: #0e3135; font-size: 1.4rem; font-weight: 800;
}
.product strong, .product small { display: block; line-height: 1.25; }
.product strong { color: #f1f8ff; font-size: 1.16rem; letter-spacing: -.025em; }
.product small { color: #a5b9cf; font-size: .82rem; margin-top: .18rem; }
.sidebar-label { color: #9fb5ce; font-size: .75rem; font-weight: 750; letter-spacing: .12em;
    text-transform: uppercase; }
.workspace-path { color: #50657a; font-size: .875rem; font-weight: 650; margin-bottom: .1rem; }
.workspace-path span { padding: 0 .5rem; color: #73869a; }
.signal-hero {
    position: relative; overflow: hidden; isolation: isolate; padding: 1.65rem 2rem 1.85rem;
    border-radius: 18px; border: 1px solid #234761; color: #f4f9ff;
    background: linear-gradient(111deg, #112437 0%, #122d42 59%, #154a50 100%);
}
.signal-hero > :not(.signal-grid) { position: relative; z-index: 1; }
.signal-grid {
    position: absolute; z-index: -1; inset: 0 0 0 56%; pointer-events: none;
    background: repeating-radial-gradient(circle at 72% 57%, transparent 0 23px,
                 #69e4ca40 24px 25px, transparent 26px 45px),
                conic-gradient(from 235deg at 72% 57%, transparent 0 67%, #65ebc63b 97%,
                #a0ffe57a 100%);
    mask-image: linear-gradient(to right, transparent, #000 35%);
}
.signal-grid::after {
    position: absolute; content: ""; top: 57%; left: 72%; transform: translate(-50%, -50%);
    width: .55rem; height: .55rem; border-radius: 50%; background: #b0ffe6;
    box-shadow: 0 0 14px #5bedc8, -43px 36px 0 -1px #73dec8, 57px -53px 0 -1px #82eed9;
}
.signal-hero h1 {
    font-size: clamp(2.15rem, 5vw, 3.35rem); line-height: 1.05; margin: .65rem 0 .5rem;
    padding: 0; font-weight: 760; color: #f5faff; letter-spacing: -.055em; overflow-wrap: anywhere;
}
.signal-hero p { margin: 0; color: #c7dbe9; font-size: .98rem; }
.hero-label { color: #9beed9; font-size: .76rem; font-weight: 740; letter-spacing: .12em;
    text-transform: uppercase; }
.source-tag {
    display: inline-flex; align-items: center; gap: .42rem; background: #183e48;
    border: 1px solid #4c8a8c; color: #b9ffeb; border-radius: 100px; padding: .25rem .65rem;
    margin-top: .85rem; font-size: .79rem; font-weight: 700;
}
.source-tag::before { content: ""; width: .4rem; height: .4rem; background: currentColor;
    border-radius: 50%; }
.source-tag.demo { background: #3a352d; border-color: #85714e; color: #ffe0a2; }
.source-tag.idle { background: #283a51; border-color: #607389; color: #dae8f5; }
.source-detail { color: #d1e0ed; margin-left: .65rem; font-size: .85rem; }
.kpi-grid {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .85rem;
}
.kpi {
    position: relative; background: #fff; border: 1px solid #dbe6ed; border-radius: 13px;
    padding: .9rem 1rem .85rem; box-shadow: 0 3px 12px #17395107;
}
.kpi:first-child { border-top: 3px solid #159d8a; padding-top: calc(.9rem - 2px); }
.kpi-label { color: #40566b; font-size: .875rem; font-weight: 700; }
.kpi-value { color: #13293c; font-size: 2.05rem; font-weight: 760; line-height: 1.25;
    letter-spacing: -.05em; font-variant-numeric: tabular-nums; margin: .2rem 0 .15rem; }
.kpi-value span { color: #53667c; font-size: .95rem; letter-spacing: 0; margin-left: .2rem; }
.kpi-detail { color: #53667c; font-size: .84rem; }
[data-testid="stMain"] [data-testid="stVerticalBlock"][data-test-scroll-behavior="normal"] {
    background: #fff; border-color: #dbe6ed; border-radius: 13px;
    box-shadow: 0 3px 12px #17395107;
}
[data-testid="stMain"] .stPlotlyChart { overflow: hidden; }
.panel-heading { color: #142638; font-size: 1.12rem; font-weight: 750; margin: 0; letter-spacing: -.02em; }
.panel-detail { color: #53667c; font-size: .875rem; margin: .3rem 0 0; line-height: 1.4; }
.issue {
    color: #142638; padding: .75rem .8rem; border: 1px solid #dbe6ed;
    border-left: 3px solid #0f9886; border-radius: 8px; background: #fff;
}
.issue.truth { border-left-color: #ca8622; }
.issue p { margin: .35rem 0 0; color: #284056; font-size: .95rem; overflow-wrap: anywhere; }
.severity {
    display: inline-block; background: #edf2f7; color: #354c64; font-size: .77rem;
    font-weight: 750; padding: .15rem .55rem; border-radius: 99px; text-transform: capitalize;
}
.severity.high { background: #fce8e5; color: #9a302a; }
.severity.medium { background: #fff1d9; color: #7b4c07; }
.severity.low { background: #e4f7ee; color: #246447; }
.issue-type { color: #53667c; font-size: .83rem; margin-left: .5rem; }
.evidence-answer { color: #183248; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.6; }
.evidence-query { color: #142638; font-weight: 700; margin-bottom: .3rem; overflow-wrap: anywhere; }
.evidence-provider { color: #53667c; font-size: .84rem; }
.evidence-meta { color: #4c6578; font-size: .85rem; overflow-wrap: anywhere; margin-top: .6rem; }
.action-card p { color: #284056; margin: .45rem 0 0; overflow-wrap: anywhere; }
@media (max-width: 1100px) {
    [data-testid="stMainBlockContainer"] { padding-left: 1.65rem; padding-right: 1.65rem; }
    .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 860px) {
    [data-testid="stMain"] [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
    [data-testid="stMain"] [data-testid="stColumn"] { min-width: min(100%, 21rem); }
}
@media (max-width: 640px) {
    [data-testid="stMainBlockContainer"] { padding: 4rem .9rem 1.7rem; }
    .signal-hero { padding: 1.2rem 1.15rem; }
    .source-detail { display: block; margin: .45rem 0 0; }
    .kpi-grid { gap: .55rem; }
    .kpi { padding-left: .72rem; padding-right: .72rem; }
}
</style>
"""

ROW_SCHEMAS = {
    "competitors": {"name": str, "score": float},
    "responses": {"provider": str, "query": str, "answer": str, "mentions": list},
    "issues": {"type": str, "severity": str, "description": str},
    "recommendations": {"title": str, "reason": str, "action": str},
}


def valid_score(value: object) -> bool:
    return type(value) in (int, float) and 0 <= value <= 100 and isfinite(value)


def validate_result(result: object) -> dict:
    if not isinstance(result, dict) or not isinstance(result.get("brand"), str):
        raise ValueError("Expected a result with a string brand.")
    for key in ("visibility_score", "mention_rate"):
        if not valid_score(result.get(key)):
            raise ValueError(f"Expected a finite percentage for {key}.")
    for key, schema in ROW_SCHEMAS.items():
        rows = result.get(key)
        if not isinstance(rows, list):
            raise ValueError(f"Expected {key} to be a list.")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"Expected an object in {key}.")
            for field, expected in schema.items():
                value = row.get(field)
                valid = valid_score(value) if expected is float else isinstance(value, expected)
                if not valid:
                    raise ValueError(f"Invalid field {key}.{field}.")
            if key == "responses" and any(not isinstance(name, str) for name in row["mentions"]):
                raise ValueError("Expected brand names as strings in responses.mentions.")
    return result


def render_header(page: str, mode: str, brand: str | None, source: str | None) -> None:
    label, detail = SOURCE_LABELS.get(source, (f"{mode} mode", "Awaiting scan"))
    tag_class = {"bundled": "demo", "backend_demo": "demo", "live": "live"}.get(source, "idle")
    st.html(
        f'<div class="workspace-path">Workspace<span aria-hidden="true">/</span>{escape(page)}</div>'
        '<div class="signal-hero"><div class="signal-grid" aria-hidden="true"></div>'
        '<div class="hero-label">Brand visibility &amp; truth intelligence</div>'
        f'<h1>{escape(brand or "Brand visibility")}</h1>'
        '<p>See where AI recommends your brand and which claims need a closer look.</p>'
        f'<div class="source-tag {tag_class}">{escape(label)}</div>'
        f'<span class="source-detail">{escape(detail)}</span></div>'
    )


def contains_brand(response: dict, brand: str) -> bool:
    return any(name.strip().casefold() == brand.strip().casefold() for name in response["mentions"])


def render_kpis(result: dict) -> None:
    responses = result["responses"]
    providers = len({response["provider"] for response in responses})
    questions = len({response["query"] for response in responses})
    issue_count = len(result["issues"])
    cards = [
        ("Visibility score", f'{result["visibility_score"]:g}<span>/ 100</span>',
         "Overall brand visibility"),
        ("Brand mention rate", f'{result["mention_rate"]:g}%', "Across scanned responses"),
        ("Responses reviewed", str(len(responses)), f"{providers} providers · {questions} questions"),
        ("Findings", str(issue_count), f'{len(result["recommendations"])} suggested actions'),
    ]
    st.html(
        '<div class="kpi-grid">'
        + "".join(
            f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}</div><div class="kpi-detail">{detail}</div></div>'
            for label, value, detail in cards
        )
        + "</div>"
    )


def panel_heading(title: str, detail: str) -> None:
    st.html(
        f'<h2 class="panel-heading">{escape(title)}</h2>'
        f'<p class="panel-detail">{escape(detail)}</p>'
    )


def bars(labels: list[str], scores: list[float], colors: list[str],
         hover_details: list[str], unit: str) -> go.Figure:
    rows = list(range(len(labels)))
    short_labels = [escape(name if len(name) <= 17 else name[:16] + "…") for name in labels]
    figure = go.Figure(
        go.Bar(
            x=scores, y=rows, orientation="h", width=.51,
            marker=dict(color=colors, cornerradius=5),
            text=[f"{score:.1f}".removesuffix(".0") + unit for score in scores],
            textposition="outside", cliponaxis=False, customdata=hover_details,
            hovertemplate="%{customdata}<extra></extra>",
        )
    )
    figure.update_layout(
        height=max(224, 76 + 37 * len(rows)),
        margin=dict(l=4, r=24, t=9, b=28),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui, sans-serif", size=13, color=INK),
        hoverlabel=dict(bgcolor="#112437", font_color="#ffffff"),
        xaxis=dict(
            range=[0, 113], tickvals=[0, 25, 50, 75, 100],
            tickfont=dict(size=11, color=MUTED), ticksuffix=unit,
            gridcolor="#e4edf3", zeroline=False, fixedrange=True,
        ),
        yaxis=dict(
            tickvals=rows, ticktext=short_labels, autorange="reversed",
            automargin=True, fixedrange=True,
        ),
    )
    return figure


def render_charts(result: dict) -> None:
    comparison, provider = st.columns(2)
    with comparison, st.container(border=True):
        panel_heading("Competitive visibility", "Visibility scores on a 100-point scale.")
        ranked = [(result["brand"], result["visibility_score"], TEAL)]
        ranked.extend((item["name"], item["score"], "#91a8bd") for item in result["competitors"])
        ranked.sort(key=lambda item: item[1], reverse=True)
        labels, scores, colors = (list(series) for series in zip(*ranked))
        figure = bars(labels, scores, colors, [
            f"{escape(label)} · {score:g} / 100" for label, score in zip(labels, scores)
        ], "")
        st.plotly_chart(figure, theme=None, config={"displayModeBar": False})
    with provider, st.container(border=True):
        panel_heading("Mentions by provider", "Share of each provider’s responses that mention your brand.")
        totals = Counter(row["provider"] for row in result["responses"])
        hits = Counter(
            row["provider"] for row in result["responses"] if contains_brand(row, result["brand"])
        )
        if totals:
            labels = sorted(totals, key=lambda name: (-hits[name] / totals[name], name))
            figure = bars(
                labels,
                [100 * hits[name] / totals[name] for name in labels],
                [TEAL] * len(labels),
                [f"{escape(name)} · {hits[name]} of {totals[name]} responses" for name in labels],
                "%",
            )
            st.plotly_chart(figure, theme=None, config={"displayModeBar": False})
        else:
            st.info("This scan returned no provider responses.")


def group_issues(issues: list[dict]) -> dict[str, list[dict]]:
    groups = {"visibility": [], "truth": [], "other": []}
    for issue in issues:
        kind = issue["type"].casefold()
        if any(word in kind for word in (
            "misinform", "hallucin", "truth", "fact", "accuracy", "inaccur", "false",
            "contradict", "incorrect", "uncertain_claim",
        )):
            groups["truth"].append(issue)
        elif any(word in kind for word in ("gap", "visib", "mention", "coverage", "recommend")):
            groups["visibility"].append(issue)
        else:
            groups["other"].append(issue)
    return groups


def render_issue_list(issues: list[dict], group: str) -> None:
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for issue in sorted(issues, key=lambda row: severity_order.get(row["severity"].strip().lower(), 4)):
        severity = issue["severity"].strip().lower()
        style = "high" if severity == "critical" else severity
        if style not in {"high", "medium", "low"}:
            style = ""
        kind = issue["type"].replace("_", " ").replace("-", " ").capitalize()
        st.html(
            f'<article class="issue {group}">'
            f'<span class="severity {style}">{escape(severity or "Unspecified")}</span>'
            f'<span class="issue-type">{escape(kind)}</span>'
            f'<p>{escape(issue["description"])}</p></article>'
        )


def render_findings(result: dict, fact_count: int) -> None:
    groups = group_issues(result["issues"])
    left, right = st.columns(2)
    with left, st.container(border=True):
        panel_heading("Visibility gaps", "Buyer questions where the brand may be missing from shortlists.")
        if groups["visibility"]:
            render_issue_list(groups["visibility"], "visibility")
        else:
            st.caption("This scan reported no visibility gaps.")
    with right, st.container(border=True):
        panel_heading("Potential misinformation", "Flagged claims to review against your verified facts.")
        if not fact_count:
            st.caption("This scan included no verified facts.")
        if groups["truth"]:
            render_issue_list(groups["truth"], "truth")
        else:
            st.caption("This scan reported no potential misinformation.")
    if groups["other"]:
        with st.container(border=True):
            panel_heading("Other findings", "Additional issues reported by the scan.")
            render_issue_list(groups["other"], "other")


def render_recommendations(recommendations: list[dict]) -> None:
    st.subheader("AI agent recommendations")
    if not recommendations:
        st.caption("This scan returned no recommendations.")
    for row in recommendations:
        with st.container(border=True):
            st.html(
                f'<article class="action-card"><h3 class="panel-heading">{escape(row["title"])}</h3>'
                f'<p><strong>Why it matters</strong> · {escape(row["reason"])}</p>'
                f'<p><strong>Next action</strong> · {escape(row["action"])}</p></article>'
            )


def render_evidence(result: dict, scan_key: str) -> None:
    st.subheader("Response evidence")
    responses = result["responses"]
    if not responses:
        st.info("This scan returned no responses to explore.")
        return

    provider_column, query_column = st.columns([1, 2])
    providers = sorted({row["provider"] for row in responses})
    queries = list(dict.fromkeys(row["query"] for row in responses))
    provider = provider_column.selectbox(
        "Provider", [None, *providers],
        format_func=lambda value: "All providers" if value is None else value,
        key=f"provider-{scan_key}",
    )
    query = query_column.selectbox(
        "Buyer-intent question", [None, *queries],
        format_func=lambda value: "All questions" if value is None else value,
        key=f"question-{scan_key}",
    )
    mentions_only = st.checkbox("Only responses that mention the brand", key=f"mentions-{scan_key}")
    filtered = [
        (index, row) for index, row in enumerate(responses, start=1)
        if (provider is None or row["provider"] == provider)
        and (query is None or row["query"] == query)
        and (not mentions_only or contains_brand(row, result["brand"]))
    ]
    st.caption(f"Showing {len(filtered)} of {len(responses)} responses.")
    if not filtered:
        st.info("No responses match these filters.")
    for position, (index, row) in enumerate(filtered):
        mentioned = contains_brand(row, result["brand"])
        names = ", ".join(row["mentions"]) or "None reported"
        with st.expander(
            f"Response {index} · {'Brand mentioned' if mentioned else 'Brand absent'}",
            expanded=position == 0,
        ):
            st.html(
                f'<div class="evidence-query">{escape(row["query"])}</div>'
                f'<div class="evidence-provider">{escape(row["provider"])}</div>'
                f'<p class="evidence-answer">{escape(row["answer"])}</p>'
                f'<div class="evidence-meta"><strong>Brands mentioned</strong> · {escape(names)}</div>'
            )


def render_dashboard(page: str, result: dict, fact_count: int, scan_key: str) -> None:
    if page == "Overview":
        render_kpis(result)
        render_charts(result)
        render_findings(result, fact_count)
        render_recommendations(result["recommendations"])
    elif page == "Response evidence":
        render_evidence(result, scan_key)
    else:
        render_findings(result, fact_count)
        render_recommendations(result["recommendations"])
