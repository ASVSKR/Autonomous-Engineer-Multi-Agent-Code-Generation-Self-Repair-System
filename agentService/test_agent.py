from agent_runtime import load_runtime_config
from flask_app import _initial_state, create_app


def test_initial_state_defaults():
	config = load_runtime_config()
	state = _initial_state({}, config)
	assert state["trigger_bug_generation"] is False
	assert state["max_retries"] == config.workflow_default_max_retries
	assert state["git_commit_message"] == config.workflow_default_git_commit_message


def test_initial_state_overrides():
	config = load_runtime_config()
	state = _initial_state(
		{
			"trigger_bug_generation": True,
			"max_retries": 4,
			"git_commit_message": "fix: test",
		},
		config,
	)
	assert state["trigger_bug_generation"] is True
	assert state["max_retries"] == 4
	assert state["git_commit_message"] == "fix: test"


def test_health_endpoint():
	app = create_app()
	client = app.test_client()
	response = client.get("/health")
	assert response.status_code == 200
	payload = response.get_json()
	assert payload["status"] == "ok"


def test_config_endpoint():
	app = create_app()
	client = app.test_client()
	response = client.get("/config/active")
	assert response.status_code == 200
	payload = response.get_json()
	assert "app_port" in payload
	assert "llm_model" in payload
	assert "jira_base_url" in payload
