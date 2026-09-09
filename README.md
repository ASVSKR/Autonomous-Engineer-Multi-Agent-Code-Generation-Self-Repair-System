# Autonomous Engineer: Multi-Agent Code Generation & Self-Repair System

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Java](https://img.shields.io/badge/Java-17%20%7C%2021-orange.svg)](https://openjdk.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph%20StateGraph-purple.svg)](https://github.com/langchain-ai/langgraph)
[![LLM](https://img.shields.io/badge/LLM-Groq%20LLaMA--3.3--70B%20%7C%20GPT--4o-green.svg)](#)
[![Enterprise](https://img.shields.io/badge/Integrations-JIRA%20%7C%20Maven%20%7C%20Git%20%7C%20Jenkins-red.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)

An enterprise-grade, autonomous **Multi-Agent Software Engineering loop** powered by **LangGraph**, **Python**, and **LLMs (Groq LLaMA-3.3-70B / OpenAI GPT-4o)**. The system autonomously generates Java 17 service classes and JUnit 5 test suites from functional requirements, executes compiler/test cycles with Maven, performs automated Root Cause Analysis (RCA) on failures, files and tracks issues in JIRA, iteratively patches code with a self-repair agent, and commits validated changes to Git/CI.

---

## 📌 Table of Contents
- [System Architecture](#-system-architecture)
- [The Autonomous Self-Repair Loop](#-the-autonomous-self-repair-loop)
- [Specialized Multi-Agent Roster](#-specialized-multi-agent-roster)
- [Enterprise Toolchain & Integrations](#-enterprise-toolchain--integrations)
- [Resilience & LLM Fallback Strategy](#-resilience--llm-fallback-strategy)
- [Repository Structure](#-repository-structure)
- [Zero-Dependency Portable / Offline Mode](#-zero-dependency-portable--offline-mode)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Standard Setup](#standard-setup)
  - [Portable / Offline Setup](#portable--offline-setup)
- [Live Monitoring Dashboard](#-live-monitoring-dashboard)
- [Author & Acknowledgments](#-author--acknowledgments)

---

## 🏛 System Architecture

The core orchestration is modeled as a **StateGraph** in **LangGraph**, passing a typed `AgentState` between specialized autonomous agents with conditional routing, retry limits, and human-in-the-loop escalation.

```
                  +-----------------------------+
                  |    User Prompt / OpenAPI    |
                  +-----------------------------+
                                 │
                                 ▼
                  +-----------------------------+
                  |  Project Generator Agent    |
                  +-----------------------------+
                                 │
                                 ▼
                  +-----------------------------+
                  |  LLM Code Generator Agent   |
                  +-----------------------------+
                                 │
                                 ▼
                  +-----------------------------+
                  |  LLM Test Generator Agent   |
                  +-----------------------------+
                                 │
                                 ▼
                  +-----------------------------+
                  |    LLM File Writer Agent    |
                  +-----------------------------+
                                 │
                                 ▼
                  +-----------------------------+
                  |         Build Agent         |
                  |     (Maven Clean Test)      |
                  +-----------------------------+
                                 │
                     ┌───────────┴───────────┐
                     │                       │
               [Build Passed]          [Build Failed]
                     │                       │
                     │                       ▼
                     │        +-----------------------------+
                     │        |         JIRA Agent          |
                     │        | (Create Ticket + RCA Logs)  |
                     │        +-----------------------------+
                     │                       │
                     │                       ▼
                     │        +-----------------------------+
                     │        |        LLM Fix Agent        |
                     │        | (Contextual Source Patching)|
                     │        +-----------------------------+
                     │                       │
                     │        [Iterate Bounded Retries] ──> (Escalate to Human if max exceeded)
                     │                       │
                     │                       ▼
                     │        [Re-Run Build Agent]
                     │                       │
                     └───────────┬───────────┘
                                 │
                                 ▼
                  +-----------------------------+
                  |        Git & CI Agent       |
                  | (Commit + Jenkins Trigger)  |
                  +-----------------------------+
                                 │
                                 ▼
                  +-----------------------------+
                  |     JIRA Resolution Agent   |
                  |    (Close Ticket as Fixed)  |
                  +-----------------------------+
```

---

## 🔄 The Autonomous Self-Repair Loop

1. **Generation:** Generates production-ready Java 17 service classes with Maven build configurations (`pom.xml`) from natural language functional requirements or OpenAPI specs.
2. **Verification & Stress Testing:** Generates baseline JUnit 5 suites and injects edge/corner cases to test failure thresholds.
3. **Automated Diagnostics (RCA):** If compilation fails or assertions break, the `Build Agent` captures the standard error, Maven logs, and stack traces.
4. **Issue Tracking:** The `JIRA Agent` automatically creates an `ai-fix` labeled ticket with structured root cause analysis and log attachments.
5. **Contextual Patching:** The `LLM Fix Agent` inspects the failing source code, error logs, and unit tests, formulating minimal, regression-free surgical patches.
6. **Delivery:** Once the test suite turns green, the system auto-commits changes to Git, triggers CI builds via Jenkins, and marks the JIRA ticket resolved.

---

## 🤖 Specialized Multi-Agent Roster

| Agent Name | Script | Role & Core Responsibilities |
| :--- | :--- | :--- |
| **Project Generator** | `project_generator_agent.py` | Scaffolds domain architecture, selects target schemas, and initializes project context. |
| **Code Generator** | `llm_code_generator_agent.py` | Generates robust Java 17 business logic, REST controllers, and Spring service beans. |
| **Test Generator** | `llm_test_generator_agent.py` | Synthesizes comprehensive JUnit 5 assertions, mock environments, and edge cases. |
| **File Writer** | `llm_file_writer_agent.py` | Formats and atomically writes Java source files, Maven wrappers, and project manifests. |
| **Build Agent** | `build_agent.py` | Manages Maven execution, parses test outcomes, and extracts structured failure diagnostics. |
| **JIRA Agent** | `jira_agent.py` | Integrates with JIRA REST API: logs bugs, formats markdown RCA reports, updates workflows. |
| **LLM Fix Agent** | `llm_fix_agent.py` | Implements targeted code refactoring and iterative self-repair with a bounded retry budget. |
| **Git & CI Agent** | `git_ci_agent.py` | Manages version control operations: staging, atomic git commits, and Jenkins pipeline dispatch. |
| **Spring Smoke Agent** | `spring_smoke_agent.py` | Performs live health-check probes (`/actuator/health`) against the running application. |
| **Ticket Poller** | `ticket_poller_agent.py` | Background agent continuously polling JIRA backlogs for incoming `ai-fix` issues. |

---

## 🔌 Enterprise Toolchain & Integrations

* **LangGraph (v1.2+):** Cyclic graph orchestration with state snapshotting, checkpointing, and conditional edge branching.
* **Atlassian JIRA:** RESTful integration handling ticket lifecycles, issue assignment, severity classification, and automated transitions.
* **Apache Maven:** Bundled headless execution (`mvn clean test compile`) with automated log extraction.
* **Git & Jenkins CI:** Automated branch management, atomic commits with traceable issue IDs, and webhook-driven build triggers.
* **Flask & Jinja2:** Real-time web dashboard displaying live agent logs, active workflows, and system health metrics.

---

## ⚡ Resilience & LLM Fallback Strategy

To guarantee continuous execution without rate-limit or outage interruptions, the system implements a **multi-tiered fallback architecture**:

1. **Primary Model:** Groq `llama-3.3-70b-versatile` (ultra-low latency code generation).
2. **Secondary Fallback:** Groq `llama-3.1-8b-instant` or OpenAI `gpt-4o`.
3. **Deterministic Heuristic Fallback:** If API quotas are exhausted, a rule-based engine handles known compilation errors to prevent pipeline deadlock.

---

## 📂 Repository Structure

```plaintext
.
├── agentService/
│   ├── agents/                     # Multi-agent implementations (Code, Fix, Build, JIRA, etc.)
│   ├── state/
│   │   └── agent_state.py          # Typed workflow state definition (TypedDict)
│   ├── workflows/
│   │   └── langgraph_workflow_llm.py # LangGraph circular state machine
│   ├── templates/
│   │   └── dashboard.html          # Real-time web monitoring UI
│   ├── static/                     # Dashboard styles and scripts
│   ├── agent_runtime.py            # Centralized environment & configuration parser
│   ├── application.yaml            # Configurable runtime parameters
│   ├── flask_app.py                # REST API and workflow dispatch endpoints
│   ├── main.py                     # Entry point
│   ├── test_agent.py               # Pytest test suite for agent validation
│   └── requirements.txt            # Python dependencies
├── docs/                           # Architecture blueprints, technical design documents, & slides
├── wheelhouse/                     # Offline pre-compiled Python wheels
├── setup-portable.ps1              # One-click portable environment bootstrap
├── start.ps1                       # One-click startup script (API + Agents + Dashboard)
└── README.md
```

---

## 📦 Zero-Dependency Portable / Offline Mode

The repository is built for hackathons, isolated enterprise networks, and air-gapped systems:
* **`wheelhouse/`:** Contains pre-compiled offline Python wheels for all dependencies (LangChain, LangGraph, Flask, Pydantic).
* **`.m2-repo/`:** Pre-cached Maven dependencies for Java 17 and Spring Boot projects.
* **`setup-portable.ps1`:** Provisions embedded Python, OpenJDK 21, and Maven 3.9 without requiring administrative privileges or external internet access.

---

## 🚀 Getting Started

### Prerequisites
* Python 3.11+
* OpenJDK 17 or 21
* Apache Maven 3.9+
* JIRA instance credentials (optional: mock service available)
* Groq API Key or OpenAI API Key

### Standard Setup

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/ASVSKR/Autonomous-Engineer-Multi-Agent-Code-Generation-Self-Repair-System.git
   cd Autonomous-Engineer-Multi-Agent-Code-Generation-Self-Repair-System
   ```

2. **Configure Environment:**
   Create an `.env` file in `agentService/`:
   ```ini
   GROQ_API_KEY=gsk_your_groq_api_key
   OPENAI_API_KEY=sk-your_openai_api_key  # Optional fallback
   JIRA_BASE_URL=https://your-domain.atlassian.net
   JIRA_EMAIL=your-email@domain.com
   JIRA_API_TOKEN=your_api_token
   JIRA_PROJECT_KEY=PROJ
   ```

3. **Install Dependencies & Launch:**
   ```bash
   cd agentService
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   python main.py
   ```

4. **Access the Web Dashboard:**
   Open [http://localhost:5000](http://localhost:5000) in your browser.

---

### Portable / Offline Setup (Windows)

For air-gapped or quick demonstration environments:
```powershell
# Run one-time bootstrap (installs bundled runtimes and caches)
.\setup-portable.ps1

# Launch the entire agent ecosystem
.\start.ps1
```

---

## 📊 Live Monitoring Dashboard

The built-in Flask UI provides real-time observability into the multi-agent graph:
* **Active Node Tracking:** Visualizes current step execution (`Code Generation` &rarr; `Maven Test` &rarr; `Fix Agent`).
* **JIRA Sync Feed:** Real-time updates on created, updated, and closed tickets.
* **Diff Viewer:** Live side-by-side comparison of original vs. repaired code.
* **Console Logs:** Real-time execution logs with timing metrics and token usage.

---

## 👤 Author
* **A S V S Krishna Rajesh** and others
* **LinkedIn:** [linkedin.com/in/asvskr](https://linkedin.com/in/asvskr)
* **GitHub:** [github.com/ASVSKR](https://github.com/ASVSKR)
