import random

from agent_runtime import load_api_schema, summarize_api_schema

def project_generator(state):

    projects = [
        ("employee-management-system", "employee"),
        ("library-management-system", "library"),
        ("inventory-management-system", "inventory"),
        ("ticket-booking-system", "booking")
    ]

    project_name = state.get("project_name")
    domain = state.get("domain")
    if not project_name or not domain:
        project_name, domain = random.choice(projects)

    schema = load_api_schema()
    state["api_schema_summary"] = summarize_api_schema(schema)

    state["project_name"] = project_name
    state["domain"] = domain

    print(f"Generated Project: {project_name}")

    return state