import subprocess
from pathlib import Path
import re

from agent_runtime import load_runtime_config, run_command


_EXCEPTION_PATTERN = re.compile(r"\b([A-Za-z0-9_.]*(?:Exception|Error))\b")
_ROOT_CAUSE_PATTERN = re.compile(r"Unexpected exception thrown:\s+([A-Za-z0-9_.]*(?:Exception|Error))")
_CLASS_PATTERN = re.compile(r"class\s+([A-Za-z_][A-Za-z0-9_]*)")
_FAILING_TEST_PATTERN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*):(\d+)")
_PUBLIC_METHOD_PATTERN = re.compile(r"public\s+[\w<>\[\],\s]+?\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _extract_service_class_name(code: str) -> str:
    match = _CLASS_PATTERN.search(code or "")
    if match:
        return match.group(1)
    return "GeneratedService"


def _extract_public_method(code: str) -> str:
    match = _PUBLIC_METHOD_PATTERN.search(code or "")
    return match.group(1) if match else ""


def _extract_failing_test(output: str) -> tuple[str, str, str]:
    if not output:
        return "", "", ""
    priority_lines = [
        line for line in output.splitlines()
        if "Unexpected exception thrown" in line or "expected:" in line or "<<< FAILURE" in line or "<<< ERROR" in line
    ]
    for line in priority_lines:
        match = _FAILING_TEST_PATTERN.search(line)
        if match:
            return match.group(1), match.group(2), match.group(3)
    match = _FAILING_TEST_PATTERN.search(output)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return "", "", ""


def _write_edge_case_test(project_path: Path, service_class: str, exception_type: str) -> Path:
    test_path = project_path / "src" / "test" / "java" / "com" / "demo"
    test_path.mkdir(parents=True, exist_ok=True)
    file_path = test_path / f"{service_class}EdgeCaseGeneratedTest.java"
    test_code = (
        "package com.demo;\n\n"
        "import org.junit.jupiter.api.Test;\n"
        "import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;\n\n"
        f"class {service_class}EdgeCaseGeneratedTest {{\n"
        "    @Test\n"
        "    void shouldHandleInjectedEdgeCaseWithoutException() {\n"
        f"        {service_class} service = new {service_class}();\n"
        f"        // Corner case discovered by test agent: {exception_type} must not surface to callers.\n"
        "        assertDoesNotThrow(service::evaluateRiskyPath);\n"
        "    }\n"
        "}\n"
    )
    file_path.write_text(test_code, encoding="utf-8")
    return file_path


def _extract_exception_details(output: str) -> tuple[str, str]:
    if not output:
        return "", ""
    root_match = _ROOT_CAUSE_PATTERN.search(output)
    if root_match:
        exception_type = root_match.group(1).split(".")[-1]
        output_lines = output.splitlines()
        detail_line = next((line.strip() for line in output_lines if "Unexpected exception thrown:" in line), "")
        return exception_type, detail_line

    match = _EXCEPTION_PATTERN.search(output)
    if not match:
        return "", ""
    exception_type = match.group(1).split(".")[-1]
    output_lines = output.splitlines()
    detail_line = next((line.strip() for line in output_lines if exception_type in line), "")
    return exception_type, detail_line

def build_agent(state):

    print("Build Agent Executed")
    config = load_runtime_config()
    if config.local_java_home is not None:
        print("JAVA_HOME =", str(config.local_java_home))
    project_path = state["java_project_path"]

    try:
        mvn_wrapper = Path(project_path) / "mvnw.cmd"
        compile_command = ["mvn.cmd", "clean", "test-compile"]
        test_command = ["mvn.cmd", "test"]
        if mvn_wrapper.exists():
            compile_command = [str(mvn_wrapper), "clean", "test-compile"]
            test_command = [str(mvn_wrapper), "test"]

        compile_result = run_command(
            command=compile_command,
            cwd=Path(project_path),
            config=config,
        )

        compile_stdout = compile_result.stdout or ""
        compile_stderr = compile_result.stderr or ""

        if compile_result.returncode != 0:
            print("===== STDOUT =====")
            print(compile_stdout)

            print("===== STDERR =====")
            print(compile_stderr)

            print("Return Code:", compile_result.returncode)

            state["compile_status"] = "FAILED"
            state["test_status"] = "NOT_RUN"
            state["build_status"] = "FAILED"
            state["build_stdout"] = compile_stdout
            state["build_stderr"] = compile_stderr
            state["detected_exception_type"] = ""
            state["detected_exception_message"] = ""
            return state

        test_result = run_command(
            command=test_command,
            cwd=Path(project_path),
            config=config,
        )

        combined_stdout = (compile_stdout + "\n" + (test_result.stdout or "")).strip()
        combined_stderr = (compile_stderr + "\n" + (test_result.stderr or "")).strip()
        exception_type, exception_message = _extract_exception_details(
            (test_result.stdout or "") + "\n" + (test_result.stderr or "")
        )

        print("===== STDOUT =====")
        print(combined_stdout)

        print("===== STDERR =====")
        print(combined_stderr)

        print("Return Code:", test_result.returncode)

        state["compile_status"] = "SUCCESS"
        state["build_status"] = "SUCCESS"
        state["build_stdout"] = combined_stdout
        state["build_stderr"] = combined_stderr
        state["detected_exception_type"] = exception_type
        state["detected_exception_message"] = exception_message
        state["baseline_test_status"] = "PASSED" if test_result.returncode == 0 else "FAILED"
        state["edge_case_test_status"] = "NOT_RUN"

        service_class = _extract_service_class_name(state.get("generated_code", ""))
        state["source_class"] = service_class
        state["source_method"] = _extract_public_method(state.get("generated_code", ""))
        state["source_file_path"] = f"src/main/java/com/demo/{service_class}.java"

        if test_result.returncode == 0:
            state["test_status"] = "PASSED"

            if state.get("trigger_bug_generation"):
                exception_label = state.get("injected_exception_type", "RuntimeException")
                edge_test_file = _write_edge_case_test(Path(project_path), service_class, exception_label)

                edge_test_result = run_command(
                    command=test_command,
                    cwd=Path(project_path),
                    config=config,
                )

                edge_stdout = edge_test_result.stdout or ""
                edge_stderr = edge_test_result.stderr or ""
                edge_exception_type, edge_exception_message = _extract_exception_details(edge_stdout + "\n" + edge_stderr)

                state["build_stdout"] = (
                    state["build_stdout"]
                    + "\n\n===== EDGE TEST PHASE =====\n"
                    + edge_stdout
                ).strip()
                state["build_stderr"] = (
                    (state["build_stderr"] + "\n\n" if state["build_stderr"] else "")
                    + edge_stderr
                ).strip()

                if edge_test_result.returncode == 0:
                    state["edge_case_test_status"] = "PASSED"
                    state["test_status"] = "PASSED"
                else:
                    state["edge_case_test_status"] = "FAILED"
                    state["test_status"] = "FAILED"
                    state["detected_exception_type"] = edge_exception_type or state["detected_exception_type"]
                    state["detected_exception_message"] = edge_exception_message or state["detected_exception_message"]
                    fail_class, fail_method, fail_line = _extract_failing_test(edge_stdout + "\n" + edge_stderr)
                    state["failing_test_class"] = fail_class or f"{service_class}EdgeCaseGeneratedTest"
                    state["failing_test_method"] = fail_method or "shouldHandleInjectedEdgeCaseWithoutException"
                    state["failing_test_line"] = fail_line
                    state["failing_test_file_path"] = (
                        f"src/test/java/com/demo/{service_class}EdgeCaseGeneratedTest.java"
                    )

                print("Edge-case test generated:", edge_test_file)
        else:
            state["test_status"] = "FAILED"
            state["baseline_test_status"] = "FAILED"
            fail_class, fail_method, fail_line = _extract_failing_test(combined_stdout + "\n" + combined_stderr)
            state["failing_test_class"] = fail_class
            state["failing_test_method"] = fail_method
            state["failing_test_line"] = fail_line

    except Exception as e:

        print("Build Error:", e)

        state["build_status"] = "FAILED"
        state["compile_status"] = "FAILED"
        state["test_status"] = "NOT_RUN"
        state["baseline_test_status"] = "NOT_RUN"
        state["edge_case_test_status"] = "NOT_RUN"
        state["build_stdout"] = ""
        state["build_stderr"] = str(e)
        state["detected_exception_type"] = ""
        state["detected_exception_message"] = ""

    return state