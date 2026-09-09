"""
Generates a technical Word document (.docx) for the agentService self-healing
Java code pipeline, including an architecture diagram and a workflow flowchart.

Run:
    python docs/generate_tech_doc.py
Output:
    docs/agentService_Technical_Design.docx
"""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
ARCH_IMG = os.path.join(HERE, "_arch_diagram.png")
FLOW_IMG = os.path.join(HERE, "_flow_diagram.png")
OUT_DOCX = os.path.join(HERE, "agentService_Technical_Design.docx")

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
C_AI = "#6C5CE7"        # AI / LLM nodes (purple)
C_DET = "#0984E3"       # deterministic nodes (blue)
C_INTEG = "#00B894"     # integration / external (green)
C_ROUTER = "#E17055"    # routers / decisions (orange)
C_STATE = "#2D3436"     # state / infra (dark)
C_BG = "#F5F6FA"


# ---------------------------------------------------------------------------
# 1. Architecture diagram
# ---------------------------------------------------------------------------
def _box(ax, x, y, w, h, text, color, fontsize=9, text_color="white"):
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.2, edgecolor="white", facecolor=color, zorder=2,
    )
    ax.add_patch(box)
    ax.text(
        x + w / 2, y + h / 2, text, ha="center", va="center",
        fontsize=fontsize, color=text_color, weight="bold", zorder=3,
        wrap=True,
    )


def _arrow(ax, p1, p2, color="#636e72", style="-|>", lw=1.4, ls="-"):
    ax.add_patch(FancyArrowPatch(
        p1, p2, arrowstyle=style, mutation_scale=12,
        color=color, linewidth=lw, linestyle=ls, zorder=1,
        connectionstyle="arc3,rad=0.0",
    ))


def build_architecture_diagram():
    fig, ax = plt.subplots(figsize=(13, 8.2))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 11)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    ax.text(8, 10.6, "agentService — System Architecture",
            ha="center", fontsize=16, weight="bold", color=C_STATE)

    # --- Clients / triggers layer ---
    _box(ax, 0.4, 9.0, 3.2, 0.9, "Web Dashboard\n(Flask UI / REST)", C_STATE, 9)
    _box(ax, 4.0, 9.0, 3.4, 0.9, "Ticket Poller (daemon)\npolls JIRA every 30s", C_INTEG, 9)
    _box(ax, 7.8, 9.0, 3.4, 0.9, "Manual / API trigger\nPOST /workflow/run", C_STATE, 9)

    # --- Flask application boundary ---
    boundary = FancyBboxPatch(
        (0.3, 1.4), 11.3, 7.1,
        boxstyle="round,pad=0.05,rounding_size=0.1",
        linewidth=1.6, edgecolor="#b2bec3", facecolor=C_BG, zorder=0,
    )
    ax.add_patch(boundary)
    ax.text(0.55, 8.25, "Flask App (flask_app.py)  •  agent_runtime config  •  WorkflowRunStore",
            fontsize=9.5, color="#2d3436", weight="bold")

    # --- LangGraph engine ---
    lg = FancyBboxPatch(
        (0.7, 1.8), 10.5, 6.0,
        boxstyle="round,pad=0.04,rounding_size=0.08",
        linewidth=1.3, edgecolor="#dfe6e9", facecolor="white", zorder=0,
    )
    ax.add_patch(lg)
    ax.text(5.95, 7.45, "LangGraph StateGraph  —  AgentState (TypedDict, 50+ fields)",
            ha="center", fontsize=10, color=C_STATE, weight="bold")

    # AI nodes
    _box(ax, 1.0, 6.2, 2.7, 0.85, "llm_code_generator\n(AI)", C_AI, 8.5)
    _box(ax, 4.0, 6.2, 2.7, 0.85, "llm_test_generator\n(AI)", C_AI, 8.5)
    _box(ax, 7.0, 6.2, 2.7, 0.85, "llm_fix_agent\n(AI · 2-stage)", C_AI, 8.5)

    # Deterministic core
    _box(ax, 1.0, 5.0, 2.7, 0.85, "project_generator", C_DET, 8.5)
    _box(ax, 4.0, 5.0, 2.7, 0.85, "llm_file_writer\n(file I/O)", C_DET, 8.5)
    _box(ax, 7.0, 5.0, 2.7, 0.85, "build_agent\n(Maven)", C_DET, 8.5)

    # Integration nodes
    _box(ax, 1.0, 3.8, 2.7, 0.85, "jira_agent /\nfailure_capture", C_INTEG, 8)
    _box(ax, 4.0, 3.8, 2.7, 0.85, "git_commit_agent", C_INTEG, 8.5)
    _box(ax, 7.0, 3.8, 2.7, 0.85, "jenkins_check_agent", C_INTEG, 8.5)

    _box(ax, 1.0, 2.6, 2.7, 0.85, "spring_smoke_agent", C_INTEG, 8.5)
    _box(ax, 4.0, 2.6, 2.7, 0.85, "source_ticket_*\nagents", C_INTEG, 8)
    _box(ax, 7.0, 2.6, 2.7, 0.85, "jira_close_agent", C_INTEG, 8.5)

    # Routers strip
    _box(ax, 9.95, 2.6, 1.05, 4.45,
         "Routers\n\nbuild\n\nretry\n\nsmoke\n\njenkins", C_ROUTER, 8)

    # --- External systems (right column) ---
    _box(ax, 12.0, 6.6, 3.6, 0.9, "Groq LLM API\nllama-3.3-70b-versatile\n(fallback 3.1-8b-instant)", C_AI, 8.5)
    _box(ax, 12.0, 5.3, 3.6, 0.9, "Maven + JDK 17\n(bundled runtimes)", C_DET, 9)
    _box(ax, 12.0, 4.0, 3.6, 0.9, "JIRA REST API\n(tickets, labels, files)", C_INTEG, 9)
    _box(ax, 12.0, 2.7, 3.6, 0.9, "Jenkins CI\n+ Git repo", C_INTEG, 9)
    _box(ax, 12.0, 1.4, 3.6, 0.9, "Sibling Spring service\n(health endpoints)", C_INTEG, 8.5)

    # connectors clients -> flask
    _arrow(ax, (2.0, 9.0), (3.0, 8.5))
    _arrow(ax, (5.7, 9.0), (5.5, 8.5))
    _arrow(ax, (9.5, 9.0), (8.0, 8.5))

    # engine -> externals
    _arrow(ax, (9.7, 6.6), (12.0, 7.0), C_AI, ls="--")
    _arrow(ax, (9.7, 5.4), (12.0, 5.7), C_DET, ls="--")
    _arrow(ax, (3.7, 4.2), (12.0, 4.4), C_INTEG, ls="--")
    _arrow(ax, (9.7, 4.2), (12.0, 3.1), C_INTEG, ls="--")
    _arrow(ax, (2.35, 2.6), (12.0, 1.85), C_INTEG, ls="--")

    # legend
    handles = [
        mpatches.Patch(color=C_AI, label="AI / LLM-backed"),
        mpatches.Patch(color=C_DET, label="Deterministic core"),
        mpatches.Patch(color=C_INTEG, label="Integration / external"),
        mpatches.Patch(color=C_ROUTER, label="Conditional routers"),
    ]
    ax.legend(handles=handles, loc="lower center", ncol=4,
              bbox_to_anchor=(0.5, -0.04), frameon=False, fontsize=9)

    plt.tight_layout()
    fig.savefig(ARCH_IMG, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 2. Workflow flowchart
# ---------------------------------------------------------------------------
def _fbox(ax, cx, cy, w, h, text, color, fontsize=8.5, tc="white"):
    box = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        linewidth=1.1, edgecolor="white", facecolor=color, zorder=2,
    )
    ax.add_patch(box)
    ax.text(cx, cy, text, ha="center", va="center",
            fontsize=fontsize, color=tc, weight="bold", zorder=3)


def _diamond(ax, cx, cy, w, h, text, color=C_ROUTER, fontsize=8):
    pts = [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)]
    ax.add_patch(plt.Polygon(pts, closed=True, facecolor=color,
                             edgecolor="white", linewidth=1.1, zorder=2))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fontsize,
            color="white", weight="bold", zorder=3)


def _farrow(ax, p1, p2, color="#636e72", label="", lw=1.4, rad=0.0):
    ax.add_patch(FancyArrowPatch(
        p1, p2, arrowstyle="-|>", mutation_scale=12, color=color,
        linewidth=lw, zorder=1, connectionstyle=f"arc3,rad={rad}"))
    if label:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(mx, my, label, fontsize=7.5, color=color,
                ha="center", va="center", weight="bold",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))


def build_flowchart():
    fig, ax = plt.subplots(figsize=(12.5, 9.5))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 15)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.text(6, 14.6, "agentService — Self-Healing Workflow (LangGraph)",
            ha="center", fontsize=15, weight="bold", color=C_STATE)

    W, H = 3.0, 0.75
    # vertical chain
    _fbox(ax, 6, 13.6, W, H, "project_generator", C_DET)
    _fbox(ax, 6, 12.6, W, H, "source_ticket_in_progress_agent", C_INTEG, 7.8)
    _fbox(ax, 6, 11.6, W, H, "llm_code_generator (AI)", C_AI)
    _fbox(ax, 6, 10.6, W, H, "llm_test_generator (AI)", C_AI)
    _fbox(ax, 6, 9.6, W, H, "llm_file_writer", C_DET)
    _fbox(ax, 6, 8.6, W, H, "build_agent (Maven)", C_DET)
    _diamond(ax, 6, 7.45, 2.4, 1.0, "build_router\nbuild & test\npassed?")

    for y1, y2 in [(13.225, 12.975), (12.225, 12.975), (12.225, 11.975),
                   (11.225, 10.975), (10.225, 9.975), (9.225, 8.975),
                   (8.225, 7.95)]:
        _farrow(ax, (6, y1), (6, y2))

    # FAILED branch (left)
    _fbox(ax, 2.4, 7.45, W, H, "jira_failure_capture_agent", C_INTEG, 7.8)
    _fbox(ax, 2.4, 6.3, W, H, "llm_fix_agent (AI · 2-stage)", C_AI, 8)
    _diamond(ax, 2.4, 5.0, 2.4, 1.0, "retry_router\nretry_count\n< max?")
    _farrow(ax, (4.5, 7.45), (3.9, 7.45), C_ROUTER, "FAILED")
    _farrow(ax, (2.4, 7.075), (2.4, 6.675))
    _farrow(ax, (2.4, 5.925), (2.4, 5.5))
    # retry loop back to file_writer
    _farrow(ax, (2.4, 4.5), (2.4, 9.6), C_ROUTER, "RETRY", rad=-0.45)
    _farrow(ax, (2.4, 9.6), (4.5, 9.6), C_ROUTER, rad=0.0)

    # SUCCESS branch (down) -> spring smoke
    _fbox(ax, 6, 6.0, W, H, "spring_smoke_agent", C_INTEG)
    _farrow(ax, (6, 6.95), (6, 6.375), C_ROUTER, "SUCCESS")
    # no_retry merges into spring smoke
    _farrow(ax, (3.6, 4.85), (4.6, 6.0), C_ROUTER, "NO_RETRY", rad=-0.2)

    _diamond(ax, 6, 4.85, 2.4, 0.95, "smoke_router")
    _farrow(ax, (6, 5.625), (6, 5.325))

    _fbox(ax, 6, 3.75, W, H, "git_commit_agent", C_INTEG)
    _farrow(ax, (6, 4.375), (6, 4.125), C_ROUTER, "after_success")

    _fbox(ax, 6, 2.75, W, H, "jenkins_check_agent", C_INTEG)
    _farrow(ax, (6, 3.375), (6, 3.125))
    _diamond(ax, 6, 1.75, 2.4, 0.95, "jenkins_router")
    _farrow(ax, (6, 2.375), (6, 2.225))

    # jira branches
    _fbox(ax, 9.6, 3.75, W, H, "jira_agent\n(create/update)", C_INTEG, 8)
    _farrow(ax, (7.5, 4.85), (8.4, 3.95), C_ROUTER, "after_failure", rad=0.1)
    _fbox(ax, 9.6, 1.75, W, H, "jira_close_agent", C_INTEG)
    _farrow(ax, (7.2, 1.75), (8.1, 1.75), C_ROUTER, "OK")
    _farrow(ax, (6, 1.275), (3.6, 1.0), C_ROUTER, "FAILED", rad=0.0)

    _fbox(ax, 2.4, 0.85, W, H, "source_ticket_finalize_agent\n(RCA · close / handoff)", C_INTEG, 7.2)
    _farrow(ax, (9.6, 1.375), (3.9, 0.95), "#636e72", rad=0.1)
    _farrow(ax, (9.6, 3.375), (9.6, 2.125))  # jira_agent -> jenkins area (fail path note)

    _fbox(ax, 0.9, 0.85, 1.0, 0.55, "END", C_STATE, 9)
    _farrow(ax, (0.9, 1.225), (0.9, 1.0))
    _farrow(ax, (1.55, 0.85), (0.9, 0.85))

    handles = [
        mpatches.Patch(color=C_AI, label="AI / LLM"),
        mpatches.Patch(color=C_DET, label="Deterministic"),
        mpatches.Patch(color=C_INTEG, label="Integration"),
        mpatches.Patch(color=C_ROUTER, label="Router / decision"),
    ]
    ax.legend(handles=handles, loc="lower center", ncol=4,
              bbox_to_anchor=(0.5, -0.02), frameon=False, fontsize=9)

    plt.tight_layout()
    fig.savefig(FLOW_IMG, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 3. Word document
# ---------------------------------------------------------------------------
def _set_cell_bg(cell, hex_color):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = tcpr.makeelement(qn("w:shd"), {
        qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): hex_color})
    tcpr.append(shd)


def _heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    return h


def _table(doc, headers, rows, widths=None, header_bg="2D3436"):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, htext in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        run = p.add_run(htext)
        run.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.size = Pt(9.5)
        _set_cell_bg(hdr[i], header_bg)
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            run = p.add_run(str(val))
            run.font.size = Pt(9)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Inches(w)
    return t


def build_docx():
    doc = Document()

    # base styles
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)

    # ---- Title page ----
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("agentService")
    r.bold = True
    r.font.size = Pt(30)
    r.font.color.rgb = RGBColor(0x6C, 0x5C, 0xE7)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run("Autonomous Self-Healing Java Code Pipeline")
    r.font.size = Pt(16)
    r.font.color.rgb = RGBColor(0x2D, 0x34, 0x36)

    sub2 = doc.add_paragraph()
    sub2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub2.add_run("Technical Design Document")
    r.italic = True
    r.font.size = Pt(13)

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.add_run("Built on LangGraph · Groq LLM · Flask · Maven · JIRA · Jenkins\n"
                 "Date: 2026-06-12  ·  Version 1.0").font.size = Pt(10)

    doc.add_page_break()

    # ---- TOC-ish overview ----
    _heading(doc, "1. Executive Summary", 1)
    doc.add_paragraph(
        "agentService is an autonomous, agent-based pipeline that generates a "
        "Java 17 service together with its JUnit 5 tests, builds and tests it with "
        "Maven, and — when failures occur — automatically diagnoses the root cause, "
        "repairs the code with an LLM, and re-runs the build. The pipeline integrates "
        "with JIRA (ticketing), Git and Jenkins (CI), and a sibling Spring service "
        "(health checks). It is orchestrated as a LangGraph StateGraph in which 14 "
        "specialized nodes (referred to as ~15 nodes including the terminal END "
        "state) exchange a single typed AgentState dictionary, enabling granular "
        "context propagation and deterministic, router-driven decisioning."
    )

    _heading(doc, "2. Agent Catalogue (AI vs Non-AI)", 1)
    doc.add_paragraph(
        "The system distinguishes AI agents (which call the Groq LLM) from non-AI "
        "agents (deterministic, rule-based, or integration components). All LLM "
        "agents use Groq llama-3.3-70b-versatile with llama-3.1-8b-instant as a "
        "fallback model."
    )

    _heading(doc, "2.1 AI Agents (LLM-backed via Groq)", 2)
    _table(
        doc,
        ["Agent", "File", "Purpose"],
        [
            ["llm_code_generator", "agents/llm_code_generator_agent.py",
             "Generates a self-contained Java 17 service class with one public method. "
             "Can intentionally inject runtime bugs (NullPointer, ArrayIndexOutOfBounds, "
             "ClassCast, etc.) when trigger_bug_generation=True."],
            ["llm_test_generator", "agents/llm_test_generator_agent.py",
             "Generates the JUnit 5 test class for the service. Reflection-based "
             "fallback if the LLM call fails."],
            ["llm_fix_agent", "agents/llm_fix_agent.py",
             "Two-stage repair: Stage 1 (retry 0) source-only minimal fix; Stage 2 "
             "(retry 1+) source + test escalation. Generates the RCA comment. Falls "
             "back to a deterministic patch if the LLM fails."],
        ],
        widths=[1.6, 2.4, 3.5],
    )

    _heading(doc, "2.2 Non-AI Agents (deterministic / integration)", 2)
    _table(
        doc,
        ["Agent", "File", "Purpose"],
        [
            ["project_generator", "agents/project_generator_agent.py",
             "Picks project name/domain and loads the OpenAPI schema summary. Workflow entry point."],
            ["llm_file_writer", "agents/llm_file_writer_agent.py",
             "Writes pom.xml, Maven wrapper, and Java source/test files to disk (pure file I/O — no LLM)."],
            ["build_agent", "agents/build_agent.py",
             "Runs mvn clean test-compile + mvn test; regex-parses output for exception "
             "type and failing test class/method/line."],
            ["source_ticket_in_progress_agent", "agents/jira_agent.py",
             "Marks the external JIRA source ticket 'In Progress'."],
            ["jira_failure_capture_agent", "workflows/langgraph_workflow_llm.py",
             "Wrapper node that creates/updates a JIRA failure ticket on build failure."],
            ["jira_agent", "agents/jira_agent.py",
             "Creates failure ticket (label ai-fix), attaches source/test files, writes "
             "WHAT/WHERE/HOW-TO-REPRODUCE description."],
            ["git_commit_agent", "agents/git_ci_agent.py",
             "git add + commit of repaired code."],
            ["jenkins_check_agent", "agents/git_ci_agent.py",
             "Triggers and polls a Jenkins CI job (SKIPPED_NO_CONFIG if not configured)."],
            ["spring_smoke_agent", "agents/spring_smoke_agent.py",
             "Non-destructive GET health checks against the sibling Spring service."],
            ["jira_close_agent", "agents/jira_agent.py",
             "Marks the JIRA ticket 'Done' after successful build + CI."],
            ["source_ticket_finalize_agent", "agents/jira_agent.py",
             "Posts RCA, closes or keeps In Progress, and on exhausted retries hands off "
             "to a human (ai-fix -> developer-fix label)."],
            ["ticket_poller_agent", "agents/ticket_poller_agent.py",
             "Background daemon (not a graph node) polling JIRA every 30s for open ai-fix "
             "tickets and auto-launching workflows."],
        ],
        widths=[1.9, 2.3, 3.3],
    )

    # ---- Architecture ----
    _heading(doc, "3. System Architecture", 1)
    doc.add_paragraph(
        "The Flask application hosts the LangGraph engine, the runtime configuration "
        "(agent_runtime), and a WorkflowRunStore for live run tracking. Workflows are "
        "triggered manually (REST), by the background ticket poller, or via the web "
        "dashboard. The engine communicates with external systems — the Groq LLM API, "
        "Maven/JDK, JIRA, Git/Jenkins, and a sibling Spring service."
    )
    doc.add_picture(ARCH_IMG, width=Inches(6.5))
    cap = doc.paragraphs[-1]
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    c = doc.add_paragraph()
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rc = c.add_run("Figure 1 — agentService system architecture")
    rc.italic = True
    rc.font.size = Pt(9)

    # ---- Workflow ----
    doc.add_page_break()
    _heading(doc, "4. Workflow & Control Flow", 1)
    doc.add_paragraph(
        "The pipeline is a LangGraph StateGraph. Each node is wrapped with a _tracked() "
        "helper that emits RUNNING/COMPLETED events to workflow_events via a "
        "contextvars-bound progress callback, which the dashboard polls for live status."
    )
    doc.add_picture(FLOW_IMG, width=Inches(6.2))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    c = doc.add_paragraph()
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rc = c.add_run("Figure 2 — Self-healing workflow flowchart")
    rc.italic = True
    rc.font.size = Pt(9)

    _heading(doc, "4.1 Node Sequence (14 nodes + END)", 2)
    _table(
        doc,
        ["#", "Node", "Type", "Responsibility"],
        [
            ["1", "project_generator", "Deterministic", "Entry; choose project, load schema"],
            ["2", "source_ticket_in_progress_agent", "Integration", "Mark source ticket In Progress"],
            ["3", "llm_code_generator", "AI", "Generate Java service"],
            ["4", "llm_test_generator", "AI", "Generate JUnit tests"],
            ["5", "llm_file_writer", "Deterministic", "Write files (retry-loop target)"],
            ["6", "build_agent", "Deterministic", "Maven compile + test, parse failures"],
            ["7", "jira_failure_capture_agent", "Integration", "Create failure ticket (failure branch)"],
            ["8", "llm_fix_agent", "AI", "Repair code (2-stage)"],
            ["9", "spring_smoke_agent", "Integration", "Service health checks"],
            ["10", "git_commit_agent", "Integration", "Commit repaired code"],
            ["11", "jenkins_check_agent", "Integration", "Trigger/poll CI"],
            ["12", "jira_agent", "Integration", "Create/update ticket on CI/smoke failure"],
            ["13", "jira_close_agent", "Integration", "Close ticket on success"],
            ["14", "source_ticket_finalize_agent", "Integration", "RCA + close or developer handoff -> END"],
        ],
        widths=[0.4, 2.5, 1.3, 3.0],
    )

    _heading(doc, "4.2 Routers (conditional decisioning)", 2)
    _table(
        doc,
        ["Router", "Decision", "Routes"],
        [
            ["build_router", "build_status==SUCCESS and test_status==PASSED",
             "success -> spring_smoke_agent | failed -> jira_failure_capture_agent"],
            ["retry_router", "retry_count < max_retries",
             "retry -> llm_file_writer (loop) | no_retry -> spring_smoke_agent"],
            ["smoke_router", "build & test passed",
             "after_success -> git_commit_agent | after_failure -> jira_agent"],
            ["jenkins_router", "jenkins_status in (SUCCESS, SKIPPED_NO_CONFIG)",
             "ok -> jira_close_agent | failed -> jira_agent"],
        ],
        widths=[1.3, 3.0, 3.0],
    )

    # ---- AgentState ----
    doc.add_page_break()
    _heading(doc, "5. State Model — AgentState (TypedDict)", 1)
    doc.add_paragraph(
        "LangGraph passes one typed AgentState dictionary between every node. Each node "
        "reads what it needs via .get() and writes its results back, enabling granular "
        "context propagation. Routers make deterministic decisions purely by reading "
        "these fields (e.g., build_status, retry_count, jenkins_status), so the same "
        "typed contract that propagates context also drives the branching logic. "
        "Defined in state/agent_state.py."
    )
    _table(
        doc,
        ["Group", "Fields"],
        [
            ["Input / control",
             "project_name, domain, trigger_bug_generation, source_ticket_id, "
             "source_ticket_details, max_retries, retry_count"],
            ["Code generation",
             "generated_code, generated_test, java_project_path"],
            ["Build / test",
             "build_status, test_status, compile_status, baseline_test_status, "
             "edge_case_test_status, build_stdout, build_stderr, "
             "detected_exception_type, detected_exception_message"],
            ["Failure diagnostics",
             "source_class, source_method, source_file_path, failing_test_class, "
             "failing_test_method, failing_test_line, failing_test_file_path"],
            ["Fix / repair",
             "fix_strategy (LLM_SOURCE_FIX / DETERMINISTIC_SOURCE_FIX / "
             "LLM_SOURCE_AND_TEST_FIX), fix_rca_comment, fix_solution_summary, "
             "fix_test_modified, fix_llm_error"],
            ["JIRA",
             "jira_ticket_id, jira_ticket_status, jira_summary, jira_description, "
             "jira_attachment_status, developer_handoff_status, "
             "source_ticket_comment_status, source_ticket_status_update"],
            ["External / CI",
             "jenkins_status, jenkins_build_url, git_commit_message, git_commit_result, "
             "spring_smoke_status, spring_smoke_results, api_schema_summary, "
             "injected_exception_type, injected_exception_scenario"],
            ["Tracking",
             "workflow_run_id, workflow_status, workflow_current_step, workflow_events"],
        ],
        widths=[1.6, 5.3],
    )

    # ---- Tech stack ----
    _heading(doc, "6. Technology Stack & External Integrations", 1)
    _table(
        doc,
        ["Component", "Technology", "Used by"],
        [
            ["LLM", "Groq llama-3.3-70b-versatile (fallback llama-3.1-8b-instant) via langchain-groq",
             "llm_code_generator, llm_test_generator, llm_fix_agent"],
            ["Orchestration", "LangGraph StateGraph", "Entire workflow"],
            ["API / UI", "Flask (flask_app.py) + dashboard", "Triggering & live tracking"],
            ["Build", "Maven 3.9.x + JDK 17 (bundled)", "build_agent"],
            ["Ticketing", "JIRA REST API", "jira_agent and source_ticket_* agents"],
            ["CI / VCS", "Jenkins + Git", "git_commit_agent, jenkins_check_agent"],
            ["Service health", "Sibling Spring service", "spring_smoke_agent"],
            ["Run store", "WorkflowRunStore (max 20 runs, FIFO, thread-safe)", "Dashboard polling"],
        ],
        widths=[1.5, 3.2, 2.2],
    )

    # ---- Run instructions ----
    _heading(doc, "7. Build & Run", 1)
    doc.add_paragraph(
        "One-time setup (with internet): ./setup-portable.ps1 downloads JDK, Maven, "
        "Python, builds the offline wheelhouse, and warms the local Maven repo.")
    doc.add_paragraph(
        "Start (any machine): ./start.ps1 prefers bundled runtimes, creates "
        "agentService/.venv, installs deps offline from wheelhouse/, and launches the "
        "Java service (:8080) and the Flask agent (:5000).")
    doc.add_paragraph(
        "Tests: pytest test_agent.py -v covers initial state defaults/overrides, "
        "/health, and /config/active.")

    doc.save(OUT_DOCX)


def main():
    build_architecture_diagram()
    build_flowchart()
    build_docx()
    # cleanup temp images
    for f in (ARCH_IMG, FLOW_IMG):
        try:
            os.remove(f)
        except OSError:
            pass
    print("Generated:", OUT_DOCX)


if __name__ == "__main__":
    main()
