# Agent Service (Autonomous FR AutoFix Agent)

`agentService` is a **LangGraph + Flask** multi-agent system that:

1. Generates a Java service class and JUnit tests,
2. Builds and tests them with Maven,
3. Detects runtime/corner-case failures via tests,
4. Raises a **Jira ticket** (via the sibling Java Jira API) pinpointing **what** failed and **where**,
5. Runs a **fix agent** that repairs the code with minimal changes,
6. Closes the ticket and tracks the whole run for a live frontend dashboard.

The LLM provider is **Groq** (`llama-3.3-70b-versatile`) via `langchain-groq`, with an automatic
fallback model and a deterministic fallback so the loop never stalls on rate limits.

---

## Architecture

```text
agentService/
├── main.py                     # Entry point -> starts the Flask app
├── flask_app.py                # Flask app, REST API, async run execution, dashboard
├── agent_runtime.py            # Single source of runtime config (reads application.yaml + env)
├── application.yaml            # All configurable values via ${ENV_VAR:default}
├── workflow_run_store.py       # Async run tracking + thread-bound progress reporter
├── requirements.txt
├── test_agent.py               # Pytest suite (initial state, /health, /config/active)
├── state/
│   └── agent_state.py          # Typed workflow state (AgentState TypedDict)
├── agents/
│   ├── project_generator_agent.py   # Picks project/domain, loads OpenAPI summary
│   ├── llm_code_generator_agent.py  # Generates Java service (injects a bug on the sad path)
│   ├── llm_test_generator_agent.py  # Generates JUnit baseline tests
│   ├── llm_file_writer_agent.py     # Writes pom.xml, wrapper, source/test to disk
│   ├── build_agent.py               # Maven compile + test; adds the corner-case test
│   ├── llm_fix_agent.py             # Repairs code (source-only, escalates to source+test)
│   ├── jira_agent.py                # Create / close tickets, comments, status, attachments
│   ├── git_ci_agent.py              # Git commit + Jenkins check
│   ├── spring_smoke_agent.py        # Smoke checks against the running service
│   └── ticket_poller_agent.py       # Background poller for open Jira tickets
├── workflows/
│   └── langgraph_workflow_llm.py    # LangGraph graph + routing + progress tracking
├── templates/
│   └── dashboard.html               # Frontend dashboard
└── static/
    ├── app.js                       # Dashboard logic (launch runs, poll progress)
    └── styles.css
```

---

## Runtime and toolchain

The project is **portable**: it can run on a machine with no pre-installed Java, Maven, or
Python. All three runtimes live inside the `Hackathon` folder and `start.ps1` prefers them,
falling back to whatever is on the system PATH if they are missing.

| Tool   | Bundled location        | Discovered by                                  |
| ------ | ----------------------- | ---------------------------------------------- |
| JDK    | `../java`               | `start.ps1` + `agent_runtime._resolve_java_home`  |
| Maven  | `../maven`              | `start.ps1` + `agent_runtime._resolve_maven_home` |
| Python | `../Python`             | `start.ps1` + `agent_runtime._resolve_python_executable` |
| Py deps| `../wheelhouse` (wheels)| installed into `agentService/.venv` on first run |
| Java deps| `../.m2-repo`         | `MAVEN_ARGS=-Dmaven.repo.local=...`            |

- The sibling **Java Spring service** provides the Jira/Git APIs and is expected on `http://localhost:8080`.
- The OpenAPI schema is read from `../service/service/openapi-schema.yaml` (used only as prompt context).

---

## Making a shareable portable bundle

On a machine **with internet**, from the `Hackathon` root, run once:

```powershell
.\setup-portable.ps1            # downloads JDK + Maven + Python, builds wheelhouse, warms .m2-repo
.\setup-portable.ps1 -Force     # re-download/replace everything
```

This populates `java\`, `maven\`, `Python\`, `wheelhouse\`, and `.m2-repo\`. Then **zip the whole
`Hackathon` folder** and share it. Do **not** include `agentService/.venv` in the zip — it is
machine-specific and is (re)created automatically on the target machine.

The recipient needs nothing installed. They unzip and run `.\start.ps1`, which:

1. points `JAVA_HOME` / `PATH` at the bundled JDK and Maven,
2. creates `agentService/.venv` from the bundled Python and installs deps offline from `wheelhouse\`,
3. uses `.m2-repo\` for offline Java builds,
4. launches both services.

---

## How to run

From the `Hackathon` root:

```powershell
.\start.ps1                              # Java on :8080, Flask on :5000
.\start.ps1 -JavaPort 8081 -PythonPort 5001
```

`start.ps1` reads `GROQ_API_KEY` from `agentService/.env` (or the environment), wires
`JIRA_BASE_URL` to the Java port, resolves the portable toolchain, ensures `.venv`, and launches
the Flask app via `.venv\Scripts\python.exe main.py`.

Run only the agent service directly (after `.venv` exists):

```powershell
cd agentService
.\.venv\Scripts\python.exe main.py       # http://localhost:5000
```

Open `http://localhost:5000/` for the dashboard. `GET /runtime` reports which bundled tools were
detected (`local_java_home`, `local_maven_home`, `local_maven_repo`, `local_python_root`).

---

## Flask endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/` | Dashboard UI |
| `GET`  | `/health` | Health check |
| `GET`  | `/runtime` | Resolved local runtime paths (Java/Python/schema/Jira/Jenkins) |
| `GET`  | `/schema/summary` | Summarized OpenAPI endpoint inventory |
| `POST` | `/workflow/run` | Run a workflow **synchronously**, returns the final state |
| `POST` | `/workflow/start` | Start a workflow **asynchronously**, returns a `run_id` (202) |
| `GET`  | `/workflow/runs` | List recent runs |
| `GET`  | `/workflow/runs/<run_id>` | Get a single run (status, events, result snapshot) |
| `GET`  | `/config/active` | All resolved configuration values |
| `GET`  | `/poller/status` | Ticket poller status |
| `POST` | `/poller/scan-now` | Trigger an immediate poller scan |

Example body for `/workflow/run` or `/workflow/start`:

```json
{
  "project_name": "inventory-management-system",
  "domain": "inventory",
  "trigger_bug_generation": true,
  "max_retries": 2,
  "git_commit_message": "fix: auto repair after ticket"
}
```

- **Happy path**: `trigger_bug_generation: false` — clean code, build/tests pass.
- **Sad path**: `trigger_bug_generation: true` — a single runtime defect is injected so the
  pipeline detects the failure, raises a Jira ticket, fixes the code, and closes the ticket.

---

## The workflow

Defined in `workflows/langgraph_workflow_llm.py`. Every node is wrapped to emit live progress
events for the dashboard.

```text
project_generator
  -> source_ticket_in_progress_agent
  -> llm_code_generator
  -> llm_test_generator
  -> llm_file_writer
  -> build_agent
       | success (build SUCCESS & tests PASSED) -> spring_smoke_agent
       | failed                                 -> jira_failure_capture_agent -> llm_fix_agent
                                                       | retry    -> llm_file_writer (re-build)
                                                       | no_retry -> spring_smoke_agent
spring_smoke_agent
  | after_success -> git_commit_agent -> jenkins_check_agent
  |                                        | ok     -> jira_close_agent -> source_ticket_finalize_agent
  |                                        | failed -> jira_agent       -> source_ticket_finalize_agent
  | after_failure -> jira_agent -> source_ticket_finalize_agent
source_ticket_finalize_agent -> END
```

### Sad-path semantics (deterministic, not LLM-dependent)

- `llm_code_generator` injects **one** runtime bug into `evaluateRiskyPath()` (e.g.
  `ArithmeticException`, `ConcurrentModificationException`, `NullPointerException`, ...). Every
  injected scenario **compiles cleanly** so the build never breaks on compilation.
- `llm_test_generator` writes a **passing baseline** test only (it never asserts the buggy
  behavior, so the suite can go fully green once fixed).
- `build_agent` runs the baseline (PASS), then writes an added corner-case test
  `*EdgeCaseGeneratedTest.java` using `assertDoesNotThrow(service::evaluateRiskyPath)` and re-runs.
  With the bug present this test **fails**, flipping `edge_case_test_status` / `test_status` to `FAILED`.
- The state distinguishes `compile_status`, `baseline_test_status`, `edge_case_test_status`, and `test_status`.

### Jira ticket

On the first detected failure the workflow routes `build failed -> jira_failure_capture_agent`,
which creates a precise ticket (WHAT failed — exception type/message; WHERE — source class/method/file
and failing test class/method/line/file; HOW TO REPRODUCE; pipeline status; and an explicit
instruction for the fix agent). An idempotency guard prevents duplicate tickets across retries.

Tickets are created against the **real Java Jira endpoint** (`POST /jira/create`) by default
(`JIRA_STUB_ENABLED=false`). When stub mode is enabled the agent fabricates a local ticket id and
skips attachment upload.

### Fix agent contract

`llm_fix_agent` repairs with the **smallest** change and preserves package/class:

1. **Attempt 1**: source-only fix (primary model -> fallback model -> deterministic minimal patch).
2. **Later attempts** (a source-only fix already failed): escalate to a combined **source + test** fix.
3. **Never** a test-only change — a test edit is accepted only if the source also changed.

A deterministic source patch (neutralizing `evaluateRiskyPath()` with a safe default return) is used
when the LLM is unavailable (e.g. a Groq `429` rate limit), so the closed loop always completes.
`fix_strategy` and `fix_test_modified` are recorded in state and surfaced on the dashboard.

### Ticket poller

`ticket_poller_agent` runs in the background (debug-reloader safe), polls `/jira/getOpenTicket`,
and triggers the workflow for new tickets. It deduplicates via `processed_tickets` and skips
auto-generated tickets. It only detects and triggers — it does not close or comment.

---

## Configuration

All values live in `application.yaml` and are overridable via environment variables using
`${ENV_VAR:default}`. `agent_runtime.py` is the single loader.

**App (Flask)**
- `APP_HOST` (`0.0.0.0`), `APP_PORT` (`5000`), `APP_DEBUG` (`true`)

**LLM (Groq)**
- `LLM_MODEL` (`llama-3.3-70b-versatile`)
- `LLM_FALLBACK_MODEL` (`llama-3.1-8b-instant`) — used only when the primary model errors
- `GROQ_API_KEY` — required for LLM calls (set in `agentService/.env` or the environment)

**Workflow**
- `WORKFLOW_DEFAULT_MAX_RETRIES` (`2`)
- `WORKFLOW_DEFAULT_GIT_COMMIT_MESSAGE` (`chore: automated agent commit`)

**HTTP**
- `HTTP_REQUEST_TIMEOUT_SECONDS` (`20`)

**Jira**
- `JIRA_BASE_URL` (`http://localhost:8080`)
- `JIRA_CREATE_PATH` (`/jira/create`), `JIRA_GET_OPEN_TICKET_PATH` (`/jira/getOpenTicket`)
- `JIRA_COMMENT_PATH_TEMPLATE`, `JIRA_ATTACHMENT_PATH_TEMPLATE`, `JIRA_UPDATE_STATUS_PATH_TEMPLATE`
  (use `__ISSUE_ID__` as the placeholder)
- `JIRA_IN_PROGRESS_STATUS_VALUE` (`In Progress`), `JIRA_DONE_STATUS_VALUE` (`Done`)
- `JIRA_STUB_ENABLED` (`false`) — set `true` to run offline without the Java service
- `JIRA_PROJECT_KEY` (`HACK`)
- `TICKET_POLLER_ENABLED` (`true`), `TICKET_POLLER_INTERVAL_SECONDS` (`10`)
- `TICKET_POLLER_DEFAULT_PROJECT_NAME` (`inventory-management-system`), `TICKET_POLLER_DEFAULT_DOMAIN` (`inventory`)

**Jenkins** (optional — skipped when unset)
- `JENKINS_BASE_URL`, `JENKINS_JOB_NAME`, `JENKINS_USER`, `JENKINS_TOKEN`
- `JENKINS_POLL_ATTEMPTS` (`20`), `JENKINS_POLL_INTERVAL_SECONDS` (`3`)

**Maven**
- `MAVEN_WRAPPER_DISTRIBUTION_URL`

**Paths** (auto-detected when unset)
- `WORKSPACE_ROOT`, `GENERATED_PROJECTS_DIR`, `SERVICE_ROOT`, `SCHEMA_PATH`,
  `LOCAL_JAVA_HOME`, `LOCAL_PYTHON_ROOT`

Example overrides (PowerShell):

```powershell
$env:APP_PORT = "8080"
$env:JIRA_STUB_ENABLED = "true"
$env:WORKFLOW_DEFAULT_MAX_RETRIES = "3"
python main.py
```

---

## Generated project layout

Each generated project follows the standard Maven layout under `generated_projects/<project-name>/`:

```text
generated_projects/<project-name>/
├── pom.xml                          # JUnit 5 + Mockito, Java 17
├── mvnw.cmd / mvnw                  # local wrapper
└── src/
    ├── main/java/com/demo/<ServiceClass>.java
    └── test/java/com/demo/
        ├── <ServiceClass>Test.java                 # baseline tests
        └── <ServiceClass>EdgeCaseGeneratedTest.java # corner-case test (sad path)
```

---

## Testing

```powershell
cd agentService
python -m pytest test_agent.py
```

`test_agent.py` covers default/override initial state and the `/health` and `/config/active` endpoints.

---

## Operating notes

- The fix agent must **never** edit tests alone; only minimal source edits, escalating to
  source+test if source-only is insufficient.
- The sad path is **deterministic** (independent of LLM variability).
- Keep deployment-sensitive values in `application.yaml` / environment, not hardcoded.
- Real Jira/Git operations require the sibling Java service running on `JIRA_BASE_URL`.
