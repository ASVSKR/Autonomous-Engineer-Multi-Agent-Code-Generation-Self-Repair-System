const state = {
  activeRunId: null,
  pollTimer: null,
  pollerTimer: null,
};

const elements = {
  connectionBadge: document.getElementById("connection-badge"),
  happyPathButton: document.getElementById("happy-path-button"),
  sadPathButton: document.getElementById("sad-path-button"),
  scanNowButton: document.getElementById("scan-now-button"),
  currentRunId: document.getElementById("current-run-id"),
  currentRunStatus: document.getElementById("current-run-status"),
  buildStatus: document.getElementById("build-status"),
  retryStatus: document.getElementById("retry-status"),
  jenkinsStatus: document.getElementById("jenkins-status"),
  jenkinsUrl: document.getElementById("jenkins-url"),
  jiraStatus: document.getElementById("jira-status"),
  jiraIdSmall: document.getElementById("jira-id-small"),
  sourceStatus: document.getElementById("source-status"),
  runStep: document.getElementById("run-step"),
  fixStrategy: document.getElementById("fix-strategy"),
  diagExceptionType: document.getElementById("diag-exception-type"),
  diagExceptionMessage: document.getElementById("diag-exception-message"),
  diagSourceClass: document.getElementById("diag-source-class"),
  diagSourceMethod: document.getElementById("diag-source-method"),
  diagSourceFile: document.getElementById("diag-source-file"),
  diagFailingTest: document.getElementById("diag-failing-test"),
  diagTestFile: document.getElementById("diag-test-file"),
  diagTestStatuses: document.getElementById("diag-test-statuses"),
  diagTestModified: document.getElementById("diag-test-modified"),
  diagHandoff: document.getElementById("diag-handoff"),
  jiraTicketId: document.getElementById("jira-ticket-id"),
  jiraSummary: document.getElementById("jira-summary"),
  jiraDescription: document.getElementById("jira-description"),
  timeline: document.getElementById("timeline"),
  resultJson: document.getElementById("result-json"),
  recentRuns: document.getElementById("recent-runs"),
  pollerEnabled: document.getElementById("poller-enabled"),
  pollerInterval: document.getElementById("poller-interval"),
  pollerInProgress: document.getElementById("poller-in-progress"),
  pollerProcessed: document.getElementById("poller-processed"),
  pollerLastRun: document.getElementById("poller-last-run"),
};

function formPayload(triggerBugGeneration) {
  const parsedRetries = Number.parseInt(document.getElementById("max-retries").value, 10) || 0;
  return {
    project_name: document.getElementById("project-name").value.trim(),
    domain: document.getElementById("domain").value.trim(),
    max_retries: parsedRetries,
    git_commit_message: document.getElementById("git-commit-message").value.trim(),
    trigger_bug_generation: triggerBugGeneration,
  };
}

function setConnection(text, className) {
  elements.connectionBadge.textContent = text;
  elements.connectionBadge.className = `status-badge ${className}`;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || data.message || `${response.status} ${response.statusText}`);
  }
  return data;
}

function renderTimeline(events = []) {
  elements.timeline.innerHTML = "";
  if (!events.length) {
    const item = document.createElement("li");
    item.className = "timeline-empty";
    item.textContent = "No workflow events yet.";
    elements.timeline.appendChild(item);
    return;
  }

  events.forEach((event) => {
    const item = document.createElement("li");
    item.className = `timeline-item ${String(event.status || "").toLowerCase()}`;
    const when = event.timestamp ? new Date(event.timestamp * 1000).toLocaleTimeString() : "";
    item.innerHTML = `<strong>${event.node}</strong><span>${event.status}</span><small>${when}</small>`;
    elements.timeline.appendChild(item);
  });
}

function renderRun(run) {
  state.activeRunId = run?.run_id || null;
  const result = run?.result || {};

  elements.currentRunId.textContent = run?.run_id || "None";
  elements.currentRunStatus.textContent = run?.status || "Idle";
  elements.buildStatus.textContent = result.build_status || "Waiting";
  elements.retryStatus.textContent = `Retries: ${result.retry_count || 0}/${result.max_retries || 0}`;
  elements.jenkinsStatus.textContent = result.jenkins_status || "Waiting";
  elements.jiraStatus.textContent = result.jira_ticket_status || "Waiting";
  elements.jiraIdSmall.textContent = `Ticket: ${result.jira_ticket_id || "none"}`;
  elements.sourceStatus.textContent = result.source_ticket_status_update || "No source ticket";
  elements.runStep.textContent = run?.current_step || "No run selected";
  renderDiagnosis(result);
  elements.resultJson.textContent = JSON.stringify(run || {}, null, 2);
  renderTimeline(run?.events || []);

  if (result.jenkins_build_url) {
    elements.jenkinsUrl.href = result.jenkins_build_url;
    elements.jenkinsUrl.textContent = result.jenkins_build_url;
  } else {
    elements.jenkinsUrl.href = "#";
    elements.jenkinsUrl.textContent = "No build URL yet";
  }
}

function dash(value) {
  const text = value === undefined || value === null ? "" : String(value);
  return text.trim() ? text : "-";
}

function renderDiagnosis(result = {}) {
  elements.fixStrategy.textContent = result.fix_strategy || "No fix yet";
  elements.diagExceptionType.textContent = dash(result.detected_exception_type);
  elements.diagExceptionMessage.textContent = dash(result.detected_exception_message);
  elements.diagSourceClass.textContent = dash(result.source_class);
  elements.diagSourceMethod.textContent = dash(result.source_method);
  elements.diagSourceFile.textContent = dash(result.source_file_path);

  let failingTest = dash(result.failing_test_class);
  if (result.failing_test_class && result.failing_test_method) {
    failingTest = `${result.failing_test_class}.${result.failing_test_method}`;
    if (result.failing_test_line) {
      failingTest += `:${result.failing_test_line}`;
    }
  }
  elements.diagFailingTest.textContent = failingTest;
  elements.diagTestFile.textContent = dash(result.failing_test_file_path);
  elements.diagTestStatuses.textContent =
    `${dash(result.baseline_test_status)} / ${dash(result.edge_case_test_status)} / ${dash(result.test_status)}`;
  elements.diagTestModified.textContent = dash(result.fix_test_modified);
  elements.diagHandoff.textContent = dash(result.developer_handoff_status);

  elements.jiraTicketId.textContent = result.jira_ticket_id || "No ticket";
  elements.jiraSummary.textContent = result.jira_summary || "No summary yet.";
  elements.jiraDescription.textContent = result.jira_description || "No description yet.";
}

function renderRecentRuns(runs = []) {
  elements.recentRuns.innerHTML = "";
  if (!runs.length) {
    const item = document.createElement("li");
    item.textContent = "No workflow runs recorded yet.";
    elements.recentRuns.appendChild(item);
    return;
  }

  runs.forEach((run) => {
    const item = document.createElement("li");
    item.className = "recent-run-item";
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${run.payload?.project_name || "project"} • ${run.status}`;
    button.addEventListener("click", () => pollRun(run.run_id));
    item.appendChild(button);
    elements.recentRuns.appendChild(item);
  });
}

async function refreshRecentRuns() {
  try {
    const data = await fetchJson("/workflow/runs");
    renderRecentRuns(data.runs || []);
  } catch (error) {
    console.error(error);
  }
}

async function refreshPollerStatus() {
  try {
    const status = await fetchJson("/poller/status");
    elements.pollerEnabled.textContent = String(Boolean(status.enabled));
    elements.pollerInterval.textContent = `${status.interval_seconds || 0}s`;
    elements.pollerInProgress.textContent = String((status.in_progress || []).length);
    elements.pollerProcessed.textContent = String((status.processed_tickets || []).length);
    elements.pollerLastRun.textContent = JSON.stringify(status.last_run_result || { status: "IDLE" }, null, 2);
    setConnection("API Ready", "success");
  } catch (error) {
    setConnection("API Offline", "error");
    elements.pollerLastRun.textContent = String(error);
  }
}

async function pollRun(runId) {
  if (!runId) {
    return;
  }
  try {
    const run = await fetchJson(`/workflow/runs/${runId}`);
    renderRun(run);
    await refreshRecentRuns();
    if (run.status === "RUNNING" || run.status === "QUEUED") {
      state.pollTimer = window.setTimeout(() => pollRun(runId), 1500);
    }
  } catch (error) {
    elements.resultJson.textContent = String(error);
  }
}

async function startRun(triggerBugGeneration) {
  window.clearTimeout(state.pollTimer);
  const payload = formPayload(triggerBugGeneration);
  try {
    const data = await fetchJson("/workflow/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderRun({
      run_id: data.run_id,
      status: data.status,
      current_step: "queued",
      events: [],
      result: null,
    });
    pollRun(data.run_id);
  } catch (error) {
    elements.resultJson.textContent = String(error);
  }
}

async function scanNow() {
  try {
    await fetchJson("/poller/scan-now", { method: "POST" });
    await refreshPollerStatus();
  } catch (error) {
    elements.pollerLastRun.textContent = String(error);
  }
}

elements.happyPathButton.addEventListener("click", () => startRun(false));
elements.sadPathButton.addEventListener("click", () => startRun(true));
elements.scanNowButton.addEventListener("click", scanNow);

refreshPollerStatus();
refreshRecentRuns();
state.pollerTimer = window.setInterval(refreshPollerStatus, 4000);