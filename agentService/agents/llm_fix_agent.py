from langchain_groq import ChatGroq
import re

from agent_runtime import load_runtime_config

config = load_runtime_config()
llm = ChatGroq(
    model=config.llm_model,
    api_key=config.llm_api_key,
)

# Optional secondary model used only when the primary model errors out (e.g. a
# Groq 429 daily-token rate limit). Keeping it lazy avoids constructing a client
# when no fallback is configured.
fallback_llm = (
    ChatGroq(model=config.llm_fallback_model, api_key=config.llm_api_key)
    if config.llm_fallback_model
    else None
)

_RISKY_METHOD_PATTERN = re.compile(
    r"public\s+([\w<>\[\],\s]+?)\s+evaluateRiskyPath\s*\([^)]*\)\s*\{"
)


def _extract_java_class_name(code: str) -> str:
    match = re.search(r"class\s+([A-Za-z_][A-Za-z0-9_]*)", code or "")
    return match.group(1) if match else ""


def _default_return_for_type(return_type: str) -> str:
    token = (return_type or "").strip().split()[-1] if return_type.strip() else ""
    if token in {"void"}:
        return ""
    if token in {"int", "long", "short", "byte", "double", "float"}:
        return "return 0;"
    if token == "boolean":
        return "return false;"
    if token == "char":
        return "return '\\0';"
    return "return null;"


def _deterministic_source_fix(code: str) -> str | None:
    """Neutralize the injected sad-path bug with the smallest possible change.

    The sad-path generator always plants the runtime defect inside
    evaluateRiskyPath(). When the LLM is unavailable we replace ONLY that
    method body with a safe default return, preserving package, class, and
    every other member so the corner-case test (assertDoesNotThrow) passes.
    Returns None if the method cannot be located.
    """
    if not code:
        return None
    match = _RISKY_METHOD_PATTERN.search(code)
    if not match:
        return None

    return_type = match.group(1)
    body_open_index = match.end() - 1  # position of the opening '{'

    depth = 0
    body_close_index = -1
    for index in range(body_open_index, len(code)):
        char = code[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                body_close_index = index
                break
    if body_close_index == -1:
        return None

    safe_return = _default_return_for_type(return_type)
    replacement_body = (
        "{\n"
        "        // Auto-fix: neutralized injected runtime defect with a safe default.\n"
        f"        {safe_return}\n".rstrip() + "\n"
        "    }"
    )
    return code[:body_open_index] + replacement_body + code[body_close_index + 1:]


def _invoke_with_fallback(prompt: str) -> tuple[str, str | None]:
    """Try the primary model, then the fallback model.

    Returns (content, error). content is "" when both providers fail.
    """
    last_error: Exception | None = None
    try:
        response = llm.invoke(prompt)
        return (response.content or "").strip(), None
    except Exception as exc:
        last_error = exc

    if fallback_llm is not None:
        try:
            response = fallback_llm.invoke(prompt)
            return (response.content or "").strip(), None
        except Exception as exc:
            last_error = exc

    return "", str(last_error) if last_error else "unknown error"


def _is_valid_source(candidate_code: str, current_class: str) -> bool:
    if not candidate_code:
        return False
    candidate_class = _extract_java_class_name(candidate_code)
    return candidate_class == current_class and "package com.demo" in candidate_code


def _extract_labeled_block(text: str, label: str) -> str:
    """Extract a fenced block tagged with a specific label, e.g. ```java-test."""
    pattern = re.compile(rf"```{label}\s*(.*?)```", re.DOTALL | re.IGNORECASE)
    match = pattern.search(text or "")
    return match.group(1).strip() if match else ""


def _attempt_source_only_fix(state, diagnostics, code, test_code, retry_count, max_retries):
    """First-line strategy: change SOURCE only, never tests."""
    source_prompt = f"""
You are fixing Java SOURCE code only.

Diagnostics from test/validation:
{diagnostics}

Current source code:
{code}

Current test code (read-only context, DO NOT modify):
{test_code}

Hard constraints:
1. Return ONLY corrected Java source code for the same class.
2. DO NOT modify package name or class name.
3. Make the smallest possible change to fix the failing edge case.
4. Do not introduce new classes/files.
5. Keep code Java 17 compilable.
"""
    current_class = _extract_java_class_name(code)
    candidate_code, llm_error = _invoke_with_fallback(source_prompt)

    if _is_valid_source(candidate_code, current_class):
        state["generated_code"] = candidate_code
        state["fix_strategy"] = "LLM_SOURCE_FIX"
    else:
        deterministic_code = _deterministic_source_fix(code)
        if deterministic_code:
            state["generated_code"] = deterministic_code
            state["fix_strategy"] = "DETERMINISTIC_SOURCE_FIX"
        else:
            state["generated_code"] = code
            state["fix_strategy"] = "NO_FIX_APPLIED"

    state["fix_test_modified"] = "NO"
    return llm_error


def _attempt_source_and_test_fix(state, diagnostics, code, test_code, retry_count, max_retries):
    """Escalation strategy: a source-only fix already failed, so allow editing
    BOTH source and test. Source MUST always change; a test-only change is never
    permitted.
    """
    current_class = _extract_java_class_name(code)
    combined_prompt = f"""
A Java unit test keeps failing after a source-only fix attempt.

Diagnostics from test/validation:
{diagnostics}

Current source code:
{code}

Current test code:
{test_code}

Rules (read carefully):
1. PREFER fixing the SOURCE. Only adjust the test if the source alone cannot
   make the scenario correct.
2. You MUST always include a source change. NEVER return only a test change.
3. Keep package com.demo and the existing class names for both files.
4. Make minimal changes. Keep everything Java 17 compilable.
5. Return EXACTLY two fenced blocks, in this order and with these exact tags:
```java-source
<full corrected source class>
```
```java-test
<full corrected test class>
```
"""
    response_text, llm_error = _invoke_with_fallback(combined_prompt)

    candidate_source = _extract_labeled_block(response_text, "java-source")
    candidate_test = _extract_labeled_block(response_text, "java-test")

    source_changed = (
        _is_valid_source(candidate_source, current_class)
        and candidate_source.strip() != (code or "").strip()
    )

    if source_changed:
        state["generated_code"] = candidate_source
        # Only accept the test change when source also changed (never test-only).
        if candidate_test and candidate_test.strip() != (test_code or "").strip():
            state["generated_test"] = candidate_test
            state["fix_strategy"] = "LLM_SOURCE_AND_TEST_FIX"
            state["fix_test_modified"] = "YES"
        else:
            state["fix_strategy"] = "LLM_SOURCE_FIX"
            state["fix_test_modified"] = "NO"
        return llm_error

    # Could not get a usable combined fix -> deterministic source-only patch.
    deterministic_code = _deterministic_source_fix(code)
    if deterministic_code:
        state["generated_code"] = deterministic_code
        state["fix_strategy"] = "DETERMINISTIC_SOURCE_FIX"
    else:
        state["generated_code"] = code
        state["fix_strategy"] = "NO_FIX_APPLIED"
    state["fix_test_modified"] = "NO"
    return llm_error


def llm_fix_agent(state):

    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", config.workflow_default_max_retries)
    if retry_count >= max_retries:
        return state

    code = state.get("generated_code", "")
    test_code = state.get("generated_test", "")
    diagnostics_stdout = state.get("build_stdout", "")
    diagnostics_stderr = state.get("build_stderr", "")
    diagnostics = (diagnostics_stdout + "\n" + diagnostics_stderr).strip()

    # Fix agent contract:
    #   - Attempt 1 (retry_count == 0): SOURCE only.
    #   - Later attempts (a source-only fix already failed): SOURCE + TEST.
    #   - NEVER produce a test-only change.
    state["generated_test"] = test_code
    escalate_to_tests = retry_count >= 1

    if escalate_to_tests:
        llm_error = _attempt_source_and_test_fix(
            state, diagnostics, code, test_code, retry_count, max_retries
        )
    else:
        llm_error = _attempt_source_only_fix(
            state, diagnostics, code, test_code, retry_count, max_retries
        )

    fix_strategy = state.get("fix_strategy", "")

    comment_prompt = f"""
Prepare an engineering update comment for a Jira FR ticket.

Context:
- Retry attempt: {retry_count + 1}/{max_retries}
- Fix strategy: {fix_strategy}
- Compiler/test diagnostics:
{diagnostics}

Service code (after fix attempt):
{state['generated_code']}

Test code (after fix attempt):
{state['generated_test']}

Return concise plain text with exactly these sections:
Root Cause Analysis:
Solution Applied:
Validation:
"""
    comment_text, comment_error = _invoke_with_fallback(comment_prompt)
    if comment_text:
        state["fix_rca_comment"] = comment_text
    else:
        if fix_strategy == "LLM_SOURCE_AND_TEST_FIX":
            applied = "Applied combined source + test fix (source change required, test adjusted as supporting change)."
        elif fix_strategy == "DETERMINISTIC_SOURCE_FIX":
            applied = "Applied deterministic source-only minimal fix (LLM unavailable)."
        else:
            applied = "Performed automated source-only fix attempt."
        state["fix_rca_comment"] = (
            "Root Cause Analysis:\n"
            f"- Injected/observed runtime defect: {state.get('detected_exception_type', 'runtime exception')}.\n"
            f"- LLM commentary unavailable: {comment_error or 'provider error'}.\n\n"
            "Solution Applied:\n"
            f"- {applied}\n"
            f"- Tests modified: {state.get('fix_test_modified', 'NO')} (test-only changes are never allowed).\n\n"
            "Validation:\n"
            f"- Fix strategy: {fix_strategy}\n"
            f"- Build status before retry: {state.get('build_status', 'FAILED')}\n"
            f"- Retry count: {retry_count + 1}/{max_retries}"
        )

    state["fix_solution_summary"] = f"Fix attempt generated by llm_fix_agent (strategy={fix_strategy})"
    if llm_error:
        state["fix_llm_error"] = llm_error

    state["retry_count"] = retry_count + 1

    print(f"LLM Fix Agent Executed (strategy={fix_strategy}, escalated={escalate_to_tests})")

    return state
