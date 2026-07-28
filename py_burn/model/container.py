from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


ContainerType = Literal["docker", "jenkins", "kubernetes"]


@dataclass
class ContainerBuildResult:
    success: bool
    image_name: str = ""
    errors: list[str] = field(default_factory=list)
    output: str = ""


@dataclass
class ContainerBuilder:
    build_dir: Path = Path("assets/dependencies/containers")

    def __post_init__(self) -> None:
        self.build_dir.mkdir(parents=True, exist_ok=True)

    def build_docker(self, dockerfile_content: str, tag: str = "py_burn-builder:latest") -> ContainerBuildResult:
        dockerfile_path = self.build_dir / "Dockerfile"
        dockerfile_path.write_text(dockerfile_content)

        try:
            result = subprocess.run(
                ["docker", "build", "-t", tag, str(self.build_dir)],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                return ContainerBuildResult(success=True, image_name=tag, output=result.stdout)
            return ContainerBuildResult(
                success=False, image_name=tag,
                errors=[result.stderr], output=result.stdout,
            )
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError) as e:
            return ContainerBuildResult(success=False, errors=[str(e)])

    def build_jenkins(self, pipeline_script: str, job_name: str = "py_burn-pipeline") -> ContainerBuildResult:
        pipeline_path = self.build_dir / "Jenkinsfile"
        pipeline_path.write_text(pipeline_script)

        config = {
            "job_name": job_name,
            "pipeline_file": str(pipeline_path),
            "description": "py_burn automated build pipeline",
        }
        config_path = self.build_dir / "jenkins_config.json"
        config_path.write_text(json.dumps(config, indent=2))

        return ContainerBuildResult(
            success=True,
            image_name=job_name,
            output=f"Jenkins pipeline config written to {config_path}",
        )

    def build_kubernetes(self, manifest: dict, name: str = "py_burn-deployment") -> ContainerBuildResult:
        manifest_path = self.build_dir / f"{name}.yaml"
        yaml_content = self._dict_to_yaml(manifest)
        manifest_path.write_text(yaml_content)

        try:
            result = subprocess.run(
                ["kubectl", "apply", "-f", str(manifest_path)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                return ContainerBuildResult(success=True, image_name=name, output=result.stdout)
            return ContainerBuildResult(
                success=False, image_name=name,
                errors=[result.stderr], output=result.stdout,
            )
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError) as e:
            return ContainerBuildResult(success=False, errors=[str(e)])

    def build(self, container_type: ContainerType, config: str | dict, name: str = "") -> ContainerBuildResult:
        builders = {
            "docker": lambda: self.build_docker(config, name or "py_burn-builder:latest"),
            "jenkins": lambda: self.build_jenkins(config, name or "py_burn-pipeline"),
            "kubernetes": lambda: self.build_kubernetes(config, name or "py_burn-deployment"),
        }
        builder = builders.get(container_type)
        if builder is None:
            return ContainerBuildResult(success=False, errors=[f"Unknown container type: {container_type}"])
        return builder()

    @staticmethod
    def _dict_to_yaml(data: dict, indent: int = 0) -> str:
        lines: list[str] = []
        prefix = "  " * indent
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(ContainerBuilder._dict_to_yaml(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{prefix}-")
                        lines.append(ContainerBuilder._dict_to_yaml(item, indent + 2))
                    else:
                        lines.append(f"{prefix}  - {item}")
            else:
                lines.append(f"{prefix}{key}: {value}")
        return "\n".join(lines)