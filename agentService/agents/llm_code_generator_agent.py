from langchain_groq import ChatGroq
import re
import random

from agent_runtime import load_runtime_config

config = load_runtime_config()
llm = ChatGroq(
    model=config.llm_model,
    api_key=config.llm_api_key
)


def _service_class_name(domain: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", domain or "")
    parts = [part for part in cleaned.split() if part]
    base = "".join(part[:1].upper() + part[1:] for part in parts) or "Generated"
    return f"{base}Service"


_SAD_EXCEPTION_SCENARIOS = [
    ("NullPointerException", "String value = null; return value.length();"),
    ("ArrayIndexOutOfBoundsException", "int[] values = {1, 2, 3}; return values[10];"),
    ("ClassCastException", "Object value = \"text\"; return ((Integer) value).intValue();"),
    ("ArithmeticException", "int divisor = 0; return 100 / divisor;"),
    ("NumberFormatException", "return Integer.parseInt(\"not-a-number\");"),
    (
        "ConcurrentModificationException",
        "java.util.List<Integer> values = new java.util.ArrayList<>(); values.add(1); for (Integer item : values) { values.add(item + 1); } return values.size();",
    ),
    ("StringIndexOutOfBoundsException", "String value = \"abc\"; return value.charAt(10);"),
    ("IllegalArgumentException", "throw new IllegalArgumentException(\"Invalid input supplied\");"),
    ("OutOfMemoryError", "throw new OutOfMemoryError(\"Simulated bounded OOM for test scenario\");"),
]


def llm_code_generator(state):

    domain = state["domain"]
    trigger_bug = state.get("trigger_bug_generation", False)
    bug_instruction = "Intentionally add one logical bug in the business method." if trigger_bug else "Do not introduce bugs."

    if trigger_bug:
        service_class = _service_class_name(domain)
        exception_type, buggy_statement = random.choice(_SAD_EXCEPTION_SCENARIOS)
        state["generated_code"] = (
            "package com.demo;\n\n"
            f"public class {service_class} {{\n"
            "    public int evaluateRiskyPath() {\n"
            f"        // Intentional sad-path runtime bug: {exception_type}.\n"
            f"        {buggy_statement}\n"
            "    }\n"
            "}\n"
        )
        state["injected_exception_type"] = exception_type
        state["injected_exception_scenario"] = "runtime_exception_injected"
        print("LLM Code Generator Executed")
        return state

    service_class = _service_class_name(domain)
    prompt = f"""
Generate a single, SELF-CONTAINED Java 17 class for the '{domain}' domain.

Strict requirements (all mandatory):
1. Package must be com.demo
2. Class name must end with Service (for example: {service_class})
3. Exactly ONE public business method with simple, deterministic logic
   (basic arithmetic, String, or java.util collection processing on its parameters).
4. NO external or third-party types. Do NOT use Spring, Lombok, @Autowired, or any
   annotation. Do NOT reference any class you do not define yourself.
5. Only java.* imports are allowed (prefer no imports at all).
6. The class MUST have a usable public no-argument constructor (the default is fine);
   do NOT require any injected dependencies.
7. The class MUST compile standalone with javac and MUST NOT throw on a normal call.
8. {bug_instruction}
9. Return ONLY raw Java code, no markdown fences, no prose.
"""

    try:
        response = llm.invoke(prompt)
        state["generated_code"] = (response.content or "").strip()
    except Exception as exc:
        service_class = _service_class_name(domain)
        state["generated_code"] = (
            "package com.demo;\n\n"
            f"public class {service_class} {{\n"
            "    public String process(String input) {\n"
            "        return input == null ? \"\" : input;\n"
            "    }\n"
            "}\n"
        )
        state["build_stderr"] = (
            (state.get("build_stderr", "") + "\n" if state.get("build_stderr") else "")
            + f"LLM_CODE_GENERATOR_ERROR: {exc}"
        )

    print("LLM Code Generator Executed")

    return state
