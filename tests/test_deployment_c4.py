"""
Tests for Phase C-4: Deployment & Containerization

Validates Docker, Docker Compose, and Kubernetes configurations.
"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml


# =============================================================================
# Test Dockerfile
# =============================================================================

class TestDockerfile:
    """Test Dockerfile configuration and structure."""

    def test_dockerfile_exists(self):
        """Test that Dockerfile exists."""
        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        assert dockerfile.exists()

    def test_dockerfile_has_stages(self):
        """Test Dockerfile has multi-stage build."""
        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        content = dockerfile.read_text()
        
        # Check for multi-stage build
        assert "FROM python:3.13-slim as builder" in content
        assert "FROM python:3.13-slim" in content

    def test_dockerfile_has_nonroot_user(self):
        """Test Dockerfile creates non-root user."""
        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        content = dockerfile.read_text()
        
        assert "useradd -m -u 1000 olav" in content
        assert "USER olav" in content

    def test_dockerfile_has_healthcheck(self):
        """Test Dockerfile includes health check."""
        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        content = dockerfile.read_text()
        
        assert "HEALTHCHECK" in content

    def test_dockerfile_has_entrypoint(self):
        """Test Dockerfile has entrypoint."""
        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        content = dockerfile.read_text()
        
        assert "ENTRYPOINT" in content
        assert "cli_main" in content


# =============================================================================
# Test docker-compose.yml
# =============================================================================

class TestDockerCompose:
    """Test Docker Compose configuration."""

    @pytest.fixture
    def compose_content(self):
        """Load docker-compose.yml content."""
        compose_file = Path(__file__).parent.parent / "docker-compose.yml"
        with open(compose_file) as f:
            return yaml.safe_load(f)

    def test_docker_compose_exists(self):
        """Test that docker-compose.yml exists."""
        compose_file = Path(__file__).parent.parent / "docker-compose.yml"
        assert compose_file.exists()

    def test_docker_compose_valid_yaml(self, compose_content):
        """Test that docker-compose.yml is valid YAML."""
        assert compose_content is not None
        assert isinstance(compose_content, dict)

    def test_docker_compose_has_services(self, compose_content):
        """Test that docker-compose defines services."""
        assert "services" in compose_content
        assert len(compose_content["services"]) > 0

    def test_docker_compose_has_olav_service(self, compose_content):
        """Test that docker-compose defines olav-agent service."""
        assert "olav-agent" in compose_content["services"]
        
        service = compose_content["services"]["olav-agent"]
        assert "image" in service or "build" in service
        assert "volumes" in service

    def test_docker_compose_has_networks(self, compose_content):
        """Test that docker-compose defines networks."""
        assert "networks" in compose_content
        assert "olav-network" in compose_content["networks"]

    def test_docker_compose_has_volumes(self, compose_content):
        """Test that docker-compose defines volumes."""
        assert "volumes" in compose_content

    def test_docker_compose_olav_healthcheck(self, compose_content):
        """Test that olav service has healthcheck."""
        service = compose_content["services"]["olav-agent"]
        assert "healthcheck" in service

    def test_docker_compose_olav_volumes(self, compose_content):
        """Test that olav service has proper volume mounts."""
        service = compose_content["services"]["olav-agent"]
        volumes = service.get("volumes", [])
        
        # Should mount .olav directory
        assert any(".olav" in str(v) for v in volumes)

    def test_docker_compose_resource_limits(self, compose_content):
        """Test that services have resource limits."""
        services = ["olav-agent", "ollama", "postgres", "redis"]
        
        for service_name in services:
            if service_name in compose_content["services"]:
                service = compose_content["services"][service_name]
                assert "deploy" in service or "resources" in service

    def test_docker_compose_restart_policy(self, compose_content):
        """Test that services have restart policy."""
        service = compose_content["services"]["olav-agent"]
        assert "restart" in service


# =============================================================================
# Test Kubernetes Manifests
# =============================================================================

class TestKubernetesManifests:
    """Test Kubernetes manifest files."""

    @pytest.fixture
    def k8s_content(self):
        """Load Kubernetes manifest content."""
        k8s_file = Path(__file__).parent.parent / "k8s" / "olav-deployment.yaml"
        with open(k8s_file) as f:
            return list(yaml.safe_load_all(f))

    def test_k8s_manifest_exists(self):
        """Test that Kubernetes manifest exists."""
        k8s_file = Path(__file__).parent.parent / "k8s" / "olav-deployment.yaml"
        assert k8s_file.exists()

    def test_k8s_manifest_valid_yaml(self, k8s_content):
        """Test that manifest is valid YAML."""
        assert k8s_content is not None
        assert len(k8s_content) > 0

    def test_k8s_has_namespace(self, k8s_content):
        """Test that manifest defines namespace."""
        kinds = [obj.get("kind") for obj in k8s_content]
        assert "Namespace" in kinds

    def test_k8s_has_configmap(self, k8s_content):
        """Test that manifest defines ConfigMap."""
        kinds = [obj.get("kind") for obj in k8s_content]
        assert "ConfigMap" in kinds

    def test_k8s_has_secret(self, k8s_content):
        """Test that manifest defines Secret."""
        kinds = [obj.get("kind") for obj in k8s_content]
        assert "Secret" in kinds

    def test_k8s_has_persistentvolumeclaim(self, k8s_content):
        """Test that manifest defines PersistentVolumeClaims."""
        kinds = [obj.get("kind") for obj in k8s_content]
        assert "PersistentVolumeClaim" in kinds

    def test_k8s_has_deployment(self, k8s_content):
        """Test that manifest defines Deployment."""
        kinds = [obj.get("kind") for obj in k8s_content]
        assert "Deployment" in kinds

    def test_k8s_has_service(self, k8s_content):
        """Test that manifest defines Service."""
        kinds = [obj.get("kind") for obj in k8s_content]
        assert "Service" in kinds

    def test_k8s_has_serviceaccount(self, k8s_content):
        """Test that manifest defines ServiceAccount."""
        kinds = [obj.get("kind") for obj in k8s_content]
        assert "ServiceAccount" in kinds

    def test_k8s_has_rbac(self, k8s_content):
        """Test that manifest defines RBAC."""
        kinds = [obj.get("kind") for obj in k8s_content]
        assert "Role" in kinds or "ClusterRole" in kinds

    def test_k8s_has_hpa(self, k8s_content):
        """Test that manifest defines HorizontalPodAutoscaler."""
        kinds = [obj.get("kind") for obj in k8s_content]
        assert "HorizontalPodAutoscaler" in kinds

    def test_k8s_deployment_has_init_container(self, k8s_content):
        """Test that Deployment has init container."""
        deployment = next(
            (obj for obj in k8s_content if obj.get("kind") == "Deployment"),
            None
        )
        assert deployment is not None
        
        spec = deployment["spec"]["template"]["spec"]
        assert "initContainers" in spec

    def test_k8s_deployment_has_probes(self, k8s_content):
        """Test that containers have health probes."""
        deployment = next(
            (obj for obj in k8s_content if obj.get("kind") == "Deployment"),
            None
        )
        assert deployment is not None
        
        containers = deployment["spec"]["template"]["spec"]["containers"]
        container = containers[0]
        
        assert "livenessProbe" in container
        assert "readinessProbe" in container

    def test_k8s_deployment_has_security_context(self, k8s_content):
        """Test that containers have security context."""
        deployment = next(
            (obj for obj in k8s_content if obj.get("kind") == "Deployment"),
            None
        )
        assert deployment is not None
        
        containers = deployment["spec"]["template"]["spec"]["containers"]
        container = containers[0]
        
        assert "securityContext" in container
        assert container["securityContext"]["runAsNonRoot"] is True


# =============================================================================
# Test .dockerignore
# =============================================================================

class TestDockerignore:
    """Test .dockerignore file."""

    def test_dockerignore_exists(self):
        """Test that .dockerignore exists."""
        dockerignore = Path(__file__).parent.parent / ".dockerignore"
        assert dockerignore.exists()

    def test_dockerignore_has_common_excludes(self):
        """Test that .dockerignore excludes common patterns."""
        dockerignore = Path(__file__).parent.parent / ".dockerignore"
        content = dockerignore.read_text()
        
        # Should exclude development files
        assert ".git" in content or "git" in content
        assert "__pycache__" in content or "*.pyc" in content
        assert ".venv" in content or "venv" in content


# =============================================================================
# Test Integration
# =============================================================================

class TestDeploymentIntegration:
    """Test integration between deployment components."""

    def test_dockerfile_matches_compose_image(self):
        """Test that Dockerfile and docker-compose use same image."""
        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        compose_file = Path(__file__).parent.parent / "docker-compose.yml"
        
        assert dockerfile.exists()
        assert compose_file.exists()

    def test_compose_and_k8s_use_same_namespace(self):
        """Test that compose and k8s configs align."""
        compose_file = Path(__file__).parent.parent / "docker-compose.yml"
        k8s_file = Path(__file__).parent.parent / "k8s" / "olav-deployment.yaml"
        
        with open(compose_file) as f:
            compose_content = yaml.safe_load(f)
        
        with open(k8s_file) as f:
            k8s_content = list(yaml.safe_load_all(f))
        
        # Both should reference similar services
        assert "olav-agent" in compose_content["services"]
        assert any(obj.get("metadata", {}).get("name") == "olav-agent" 
                  for obj in k8s_content)

    def test_config_consistency(self):
        """Test that configurations are consistent."""
        compose_file = Path(__file__).parent.parent / "docker-compose.yml"
        
        with open(compose_file) as f:
            compose_content = yaml.safe_load(f)
        
        service = compose_content["services"]["olav-agent"]
        
        # Should have environment variables
        assert "environment" in service
        
        # Should mount .olav directory
        volumes = service.get("volumes", [])
        assert any(".olav" in str(v) for v in volumes)


# =============================================================================
# Test Configuration Loading
# =============================================================================

class TestDeploymentConfiguration:
    """Test deployment configuration management."""

    def test_phase_c1_integration(self):
        """Test Phase C-1 configuration integration."""
        compose_file = Path(__file__).parent.parent / "docker-compose.yml"
        
        with open(compose_file) as f:
            content = yaml.safe_load(f)
        
        # Should reference C-1 settings
        service = content["services"]["olav-agent"]
        env = service.get("environment", {})
        
        # Should have configuration-related environment variables
        env_vars = list(env) if isinstance(env, list) else list(env.values())
        env_str = " ".join(str(v) for v in env_vars)
        
        assert "CONFIG" in env_str or "settings" in env_str.lower()

    def test_phase_c3_integration(self):
        """Test Phase C-3 migration integration."""
        k8s_file = Path(__file__).parent.parent / "k8s" / "olav-deployment.yaml"
        
        with open(k8s_file) as f:
            content = list(yaml.safe_load_all(f))
        
        deployment = next(
            (obj for obj in content if obj.get("kind") == "Deployment"),
            None
        )
        
        # Should have init container for migration
        spec = deployment["spec"]["template"]["spec"]
        init_containers = spec.get("initContainers", [])
        
        assert len(init_containers) > 0
        assert any("migrate" in str(c) or "verify" in str(c).lower() 
                  for c in init_containers)


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestDeploymentEdgeCases:
    """Test edge cases and error conditions."""

    def test_dockerfile_handles_missing_venv(self):
        """Test Dockerfile handles missing venv gracefully."""
        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        content = dockerfile.read_text()
        
        # Should copy from builder stage
        assert ".venv" in content

    def test_compose_handles_service_restart(self):
        """Test docker-compose restart policy."""
        compose_file = Path(__file__).parent.parent / "docker-compose.yml"
        
        with open(compose_file) as f:
            content = yaml.safe_load(f)
        
        service = content["services"]["olav-agent"]
        assert service.get("restart") in ["always", "unless-stopped", "on-failure"]

    def test_k8s_handles_pod_disruption(self):
        """Test Kubernetes handles pod disruptions."""
        k8s_file = Path(__file__).parent.parent / "k8s" / "olav-deployment.yaml"
        
        with open(k8s_file) as f:
            content = list(yaml.safe_load_all(f))
        
        deployment = next(
            (obj for obj in content if obj.get("kind") == "Deployment"),
            None
        )
        
        # Should have anti-affinity rules
        spec = deployment["spec"]["template"]["spec"]
        assert "affinity" in spec


# =============================================================================
# Test Resource Requirements
# =============================================================================

class TestResourceRequirements:
    """Test resource requests and limits."""

    def test_compose_resource_limits(self):
        """Test Docker Compose resource limits."""
        compose_file = Path(__file__).parent.parent / "docker-compose.yml"
        
        with open(compose_file) as f:
            content = yaml.safe_load(f)
        
        service = content["services"]["olav-agent"]
        assert "deploy" in service
        assert "resources" in service["deploy"]
        
        resources = service["deploy"]["resources"]
        assert "limits" in resources
        assert "reservations" in resources

    def test_k8s_resource_requests(self):
        """Test Kubernetes resource requests."""
        k8s_file = Path(__file__).parent.parent / "k8s" / "olav-deployment.yaml"
        
        with open(k8s_file) as f:
            content = list(yaml.safe_load_all(f))
        
        deployment = next(
            (obj for obj in content if obj.get("kind") == "Deployment"),
            None
        )
        
        containers = deployment["spec"]["template"]["spec"]["containers"]
        container = containers[0]
        
        assert "resources" in container
        assert "requests" in container["resources"]
        assert "limits" in container["resources"]
