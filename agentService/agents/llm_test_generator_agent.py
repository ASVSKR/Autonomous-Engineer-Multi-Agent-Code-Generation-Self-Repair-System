from langchain_groq import ChatGroq
import re

from agent_runtime import load_runtime_config

config = load_runtime_config()
llm = ChatGroq(
    model=config.llm_model,
    api_key=config.llm_api_key
)


def _extract_service_class_name(java_code: str) -> str:
    match = re.search(r"class\s+([A-Za-z_][A-Za-z0-9_]*)", java_code or "")
    if match:
        return match.group(1)
    return "GeneratedService"


def llm_test_generator(state):

    java_code = state["generated_code"]
    trigger_bug = state.get("trigger_bug_generation", False)

    if trigger_bug:
        service_class = _extract_service_class_name(java_code)
        test_class = f"{service_class}Test"
        # Sad-path baseline suite: this MUST pass on the buggy code so the
        # documented semantics hold (baseline PASSED -> the build agent then adds
        # a corner-case test that FAILS on the injected defect). The corner-case
        # test asserts CORRECT behavior (assertDoesNotThrow), so after the fix
        # agent repairs the source, every test passes and the loop can close.
        # We intentionally do NOT assert the buggy behavior here (e.g. with
        # assertThrows), because such a test would start failing once the bug is
        # fixed and would prevent the fix agent from making all tests pass.
        state["generated_test"] = (
            "package com.demo;\n\n"
            "import org.junit.jupiter.api.Test;\n"
            "import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;\n\n"
            f"class {test_class} {{\n"
            "    @Test\n"
            "    void baselineSanityShouldPass() {\n"
            "        // Existing baseline test case: always passes.\n"
            "        assertDoesNotThrow(() -> { int value = 2 + 3; });\n"
            "    }\n"
            "}\n"
        )
        print("LLM Test Generator Executed")
        return state

    prompt = f"""
Generate a JUnit 5 test class for the Java code below. The class under test is
fully self-contained (no external dependencies).

Java Code:
{java_code}

Hard constraints (all mandatory):
1. Return ONLY raw Java code, no markdown fences, no prose.
2. Use package com.demo.
3. Use ONLY imports from org.junit.jupiter.api.* (and its Assertions). Do NOT use
   Mockito, Spring, reflection, or any third-party library.
4. Instantiate the class under test with its public no-argument constructor.
5. Call the public business method with simple literal arguments and assert the
   result. If the exact return value is hard to predict, use assertDoesNotThrow.
6. Keep it to one or two small @Test methods that compile and pass.
"""

    try:
        response = llm.invoke(prompt)
        state["generated_test"] = (response.content or "").strip()
    except Exception as exc:
        service_class = _extract_service_class_name(java_code)
        test_class = f"{service_class}Test"
        state["generated_test"] = (
            "package com.demo;\n\n"
            "import java.lang.reflect.Constructor;\n"
            "import java.lang.reflect.Method;\n"
            "import java.lang.reflect.Modifier;\n"
            "import org.junit.jupiter.api.Test;\n"
            "import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;\n\n"
            f"class {test_class} {{\n"
            "    @Test\n"
            "    void generatedServiceCompilesAndInvokesPublicMethod() {\n"
            "        assertDoesNotThrow(() -> {\n"
            f"            Constructor<?> constructor = {service_class}.class.getDeclaredConstructors()[0];\n"
            "            Object service = constructor.newInstance(buildArgs(constructor.getParameterTypes()));\n"
            f"            Method method = findTargetMethod({service_class}.class);\n"
            "            if (method != null) {\n"
            "                method.invoke(service, buildArgs(method.getParameterTypes()));\n"
            "            }\n"
            "        });\n"
            "    }\n"
            "\n"
            "    private static Method findTargetMethod(Class<?> type) {\n"
            "        for (Method method : type.getDeclaredMethods()) {\n"
            "            if (Modifier.isPublic(method.getModifiers()) && method.getDeclaringClass() != Object.class) {\n"
            "                return method;\n"
            "            }\n"
            "        }\n"
            "        return null;\n"
            "    }\n"
            "\n"
            "    private static Object[] buildArgs(Class<?>[] parameterTypes) {\n"
            "        Object[] args = new Object[parameterTypes.length];\n"
            "        for (int index = 0; index < parameterTypes.length; index++) {\n"
            "            args[index] = defaultValue(parameterTypes[index]);\n"
            "        }\n"
            "        return args;\n"
            "    }\n"
            "\n"
            "    private static Object defaultValue(Class<?> type) {\n"
            "        if (!type.isPrimitive()) {\n"
            "            return null;\n"
            "        }\n"
            "        if (type == boolean.class) {\n"
            "            return false;\n"
            "        }\n"
            "        if (type == byte.class) {\n"
            "            return (byte) 0;\n"
            "        }\n"
            "        if (type == short.class) {\n"
            "            return (short) 0;\n"
            "        }\n"
            "        if (type == int.class) {\n"
            "            return 0;\n"
            "        }\n"
            "        if (type == long.class) {\n"
            "            return 0L;\n"
            "        }\n"
            "        if (type == float.class) {\n"
            "            return 0F;\n"
            "        }\n"
            "        if (type == double.class) {\n"
            "            return 0D;\n"
            "        }\n"
            "        if (type == char.class) {\n"
            "            return '\\0';\n"
            "        }\n"
            "        return null;\n"
            "    }\n"
            "}\n"
        )
        state["build_stderr"] = (
            (state.get("build_stderr", "") + "\n" if state.get("build_stderr") else "")
            + f"LLM_TEST_GENERATOR_ERROR: {exc}"
        )

    print("LLM Test Generator Executed")

    return state
