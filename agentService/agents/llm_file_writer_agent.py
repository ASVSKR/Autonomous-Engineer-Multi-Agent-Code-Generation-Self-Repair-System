import os
import re
from pathlib import Path

from agent_runtime import load_runtime_config, create_local_wrapper


def _extract_java_class_name(code: str) -> str:
    match = re.search(r"class\s+([A-Za-z_][A-Za-z0-9_]*)", code)
    if not match:
        return "GeneratedService"
    return match.group(1)


def _strip_markdown_fences(code: str) -> str:
    text = (code or "").strip()
    block_match = re.search(r"```(?:java)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if block_match:
        return block_match.group(1).strip()

    package_idx = text.find("package ")
    if package_idx >= 0:
        return text[package_idx:].strip()

    import_idx = text.find("import ")
    if import_idx >= 0:
        return text[import_idx:].strip()

    class_idx = text.find("class ")
    if class_idx >= 0:
        return text[class_idx:].strip()

    return text.strip()


def _write_base_pom(project_path: Path, project_name: str) -> None:
    pom_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>com.demo</groupId>
    <artifactId>{project_name}</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
            <version>6.1.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.12</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter-api</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter-engine</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <version>5.12.0</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-junit-jupiter</artifactId>
            <version>5.12.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.11.0</version>
                <configuration>
                    <source>17</source>
                    <target>17</target>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
        </plugins>
    </build>

</project>
"""
    (project_path / "pom.xml").write_text(pom_content, encoding="utf-8")


def llm_file_writer(state):
    config = load_runtime_config()
    
    # Resolve project path - use config's generated_projects_dir if java_project_path is empty
    java_project_path = state.get("java_project_path", "").strip()
    if not java_project_path:
        project_name = state.get("project_name", "default-project")
        java_project_path = str(config.generated_projects_dir / project_name)
        state["java_project_path"] = java_project_path
    
    project_path = Path(java_project_path)
    
    # Create directory structure
    source_path = project_path / "src" / "main" / "java" / "com" / "demo"
    test_path = project_path / "src" / "test" / "java" / "com" / "demo"
    os.makedirs(source_path, exist_ok=True)
    os.makedirs(test_path, exist_ok=True)

    # Always write a base pom and wrapper to avoid stale/broken project setup.
    project_name = state.get("project_name", "generated-project")
    _write_base_pom(project_path, project_name)
    create_local_wrapper(project_path, config)

    for stale_file in source_path.glob("*.java"):
        stale_file.unlink()
    for stale_file in test_path.glob("*.java"):
        stale_file.unlink()

    generated_code = _strip_markdown_fences(state.get("generated_code", ""))
    generated_test = _strip_markdown_fences(state.get("generated_test", ""))

    service_class = _extract_java_class_name(generated_code)
    test_class = _extract_java_class_name(generated_test)

    (source_path / f"{service_class}.java").write_text(generated_code, encoding="utf-8")
    if generated_test.strip():
        (test_path / f"{test_class}.java").write_text(generated_test, encoding="utf-8")

    print(f"LLM File Writer Executed - Project: {java_project_path}")

    return state
