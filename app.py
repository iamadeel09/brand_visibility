"""Streamlit entry point for GEO Visibility."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from dashboard import STYLES, render_dashboard, render_header, validate_result

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)
APP_NAME = "GEO Visibility"


@dataclass(frozen=True)
class Scan:
    brand: str
    competitors: list[str]
    queries: list[str]
    verified_facts: list[str]

    def __post_init__(self) -> None:
        if not self.brand:
            raise ValueError("Enter a brand name.")
        names = [name.casefold() for name in [self.brand, *self.competitors]]
        if len(set(names)) != len(names):
            raise ValueError("Use a different name for each competitor and your brand.")
        if not self.queries:
            raise ValueError("Enter at least one buyer-intent question.")


@dataclass(frozen=True)
class Snapshot:
    scan: Scan
    result: dict
    source: str


class ScanUnavailable(Exception):
    """The selected scan needs an installed backend."""


def load_example() -> Snapshot:
    example = json.loads((ROOT / "demo_data" / "sample.json").read_text(encoding="utf-8"))
    return Snapshot(Scan(**example["scan"]), validate_result(example["result"]), "bundled")


def run_scan(scan: Scan, demo_mode: bool, example: Snapshot) -> Snapshot:
    try:
        from backend.agent import run_analysis
    except ModuleNotFoundError as error:
        if error.name not in {"backend", "backend.agent"}:
            raise
        if demo_mode and scan == example.scan:
            return example
        if demo_mode:
            raise ScanUnavailable(
                "Custom demo scans require the backend. Restore the bundled example "
                "to replay it offline."
            ) from error
        raise ScanUnavailable(
            "Live scans require backend.agent. Add the teammate's backend and install "
            "its dependencies before running a Live scan."
        ) from error

    result = run_analysis(
        brand=scan.brand,
        competitors=scan.competitors.copy(),
        queries=scan.queries.copy(),
        verified_facts=scan.verified_facts.copy(),
        demo_mode=demo_mode,
    )
    result = validate_result(result)
    if not demo_mode and not result["responses"]:
        raise ScanUnavailable(
            "No provider returned a usable response. Check provider settings, API credentials, "
            "and network access, then retry."
        )
    return Snapshot(scan, result, "backend_demo" if demo_mode else "live")


def restore_example(example: Snapshot) -> None:
    scan = example.scan
    st.session_state.brand = scan.brand
    for index in range(3):
        st.session_state[f"competitor_{index}"] = (
            scan.competitors[index] if index < len(scan.competitors) else ""
        )
    for index, query in enumerate(scan.queries):
        st.session_state[f"query_{index}"] = query
    st.session_state.facts = "\n".join(scan.verified_facts)
    st.session_state.snapshots["Demo"] = example
    st.session_state.scan_revision += 1


def sidebar(example: Snapshot) -> tuple[str, str, bool]:
    with st.sidebar:
        st.html(
            '<div class="product"><div class="product-mark" aria-hidden="true">◉</div>'
            f'<div><strong>{APP_NAME}</strong><small>Brand Intelligence for AI Answers</small></div></div>'
        )
        st.html('<div class="sidebar-label">Workspace</div>')
        with st.container(key="navigation"):
            page = st.radio(
                "Workspace navigation",
                ["Overview", "Response evidence", "Findings & actions"],
                label_visibility="collapsed",
            )
        st.divider()
        st.html('<div class="sidebar-label">Scan settings</div>')
        mode = st.segmented_control(
            "Scan mode",
            ["Demo", "Live"],
            default="Demo",
            required=True,
            width="stretch",
        )
        with st.form("scan_settings", border=False, enter_to_submit=False):
            st.text_input("Brand name", key="brand", max_chars=100)
            for index in range(3):
                st.text_input(
                    f"Competitor {index + 1}",
                    key=f"competitor_{index}",
                    max_chars=100,
                    placeholder="Optional",
                )
            with st.expander("Buyer-intent questions", icon=":material/quiz:"):
                for index in range(5):
                    st.text_area(f"Question {index + 1}", key=f"query_{index}", max_chars=500)
            with st.expander("Verified company facts", icon=":material/fact_check:"):
                st.text_area("One fact per line", key="facts", height=125, max_chars=6000)
            submitted = st.form_submit_button(
                "Run scan", icon=":material/radar:", type="primary", width="stretch"
            )
        if mode == "Demo":
            st.button(
                "Restore bundled example",
                on_click=restore_example,
                args=(example,),
                type="tertiary",
                width="stretch",
            )
    return page, mode, submitted


def scan_from_inputs() -> Scan:
    return Scan(
        brand=st.session_state.brand.strip(),
        competitors=[
            name
            for index in range(3)
            if (name := st.session_state[f"competitor_{index}"].strip())
        ],
        queries=[
            query
            for index in range(5)
            if (query := st.session_state[f"query_{index}"].strip())
        ],
        verified_facts=[
            fact.strip() for fact in st.session_state.facts.splitlines() if fact.strip()
        ],
    )


def submit_scan(mode: str, example: Snapshot) -> None:
    st.session_state.snapshots.pop(mode, None)
    try:
        scan = scan_from_inputs()
    except ValueError as error:
        st.error(str(error))
        return

    status = st.status(f"Running {mode.lower()} scan for {scan.brand}…", expanded=True)
    try:
        status.write("Loading the scan results and response evidence.")
        snapshot = run_scan(scan, mode == "Demo", example)
    except ScanUnavailable as error:
        status.update(label="Scan unavailable", state="error", expanded=False)
        st.error(str(error))
    except Exception as error:
        # Keep exception messages out of the UI and logs because they can include
        # provider credentials, request data, or a raw model answer.
        LOGGER.error("%s scan failed (%s)", mode, type(error).__name__)
        status.update(label="Scan failed", state="error", expanded=False)
        st.error(
            "The scan failed. Check backend configuration, provider credentials, "
            "and the response contract, then retry."
        )
    else:
        st.session_state.snapshots[mode] = snapshot
        st.session_state.scan_revision += 1
        status.update(label="Scan complete", state="complete", expanded=False)


def main() -> None:
    st.set_page_config(
        page_title=APP_NAME,
        page_icon="◉",
        layout="wide",
        initial_sidebar_state="auto",
    )
    load_dotenv(ROOT / ".env")
    st.html(STYLES)

    example = load_example()
    if "snapshots" not in st.session_state:
        st.session_state.snapshots = {}
        st.session_state.scan_revision = 0
        restore_example(example)

    page, mode, submitted = sidebar(example)
    snapshot = st.session_state.snapshots.get(mode)
    if submitted:
        submit_scan(mode, example)
        snapshot = st.session_state.snapshots.get(mode)
    render_header(
        page, mode, snapshot.result["brand"] if snapshot else None,
        snapshot.source if snapshot else None,
    )
    if snapshot:
        render_dashboard(
            page,
            snapshot.result,
            len(snapshot.scan.verified_facts),
            f"{mode}-{st.session_state.scan_revision}",
        )
    elif not submitted:
        st.info(f"Configure your scan in the sidebar and select Run scan to see {mode} results.")


if __name__ == "__main__":
    main()
