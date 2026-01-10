# OLAV v0.8 Deployment Guide

**Version**: 0.8.0  
**Last Updated**: 2025-01-10  
**Environments**: Docker, Docker Compose, Kubernetes  

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Docker Local Deployment](#docker-local-deployment)
3. [Docker Compose Stack](#docker-compose-stack)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Configuration Management](#configuration-management)
6. [Health Checks & Monitoring](#health-checks--monitoring)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites
- Docker 20.10+ or Docker Desktop
- Docker Compose 2.0+ (for multi-container setup)
- kubectl 1.24+ (for Kubernetes)
- Git

### Fastest Setup (Docker Compose)
```bash
# Clone the repository
git clone <repo-url>
cd Olav

# Start the full stack
docker-compose up -d

# Verify services are running
docker-compose ps

# Check OLAV agent logs
docker-compose logs -f olav-agent
```

---

## Docker Local Deployment

### Building the Image

```bash
# Build image with default tag
docker build -t olav:0.8 .

# Build with custom tag
docker build -t olav:latest .

# Build for multiple architectures (requires buildx)
docker buildx build --platform linux/amd64,linux/arm64 -t olav:0.8 .
```

### Running Standalone Container

```bash
# Basic run
docker run -it --rm olav:0.8

# With volume mounts
docker run -it --rm \
  -v $(pwd)/.olav:/app/.olav \
  -v $(pwd)/data:/app/data \
  olav:0.8

# With environment variables
docker run -it --rm \
  -e LLM_MODEL_NAME=gpt-4 \
  -e LLM_TEMPERATURE=0.7 \
  -e LOG_LEVEL=DEBUG \
  olav:0.8

# Detached mode with custom name
docker run -d \
  --name olav-agent \
  -v $(pwd)/.olav:/app/.olav \
  olav:0.8 --help
```

### Managing Container Lifecycle

```bash
# Check container status
docker ps -a | grep olav

# View logs
docker logs olav-agent
docker logs -f olav-agent  # Follow logs

# Execute command in running container
docker exec olav-agent python -m olav.cli.cli_main config show

# Stop container
docker stop olav-agent

# Remove container
docker rm olav-agent

# View resource usage
docker stats olav-agent
```

---

## Docker Compose Stack

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                OLAV Docker Compose Stack            │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  OLAV Agent (Main Service)                   │   │
│  │  - Python 3.13 with project dependencies    │   │
│  │  - CLI interface accessible                 │   │
│  │  - Volumes: .olav/, data/, knowledge/       │   │
│  └──────────────┬───────────────────────────────┘   │
│                 │                                   │
│  ┌──────────────┴───────────────────────────────┐   │
│  │  Supporting Services                         │   │
│  ├──────────────────────────────────────────────┤   │
│  │  • Ollama (Local LLM backend)               │   │
│  │  • PostgreSQL (Checkpointer storage)        │   │
│  │  • Redis (Caching layer)                    │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Starting Services

```bash
# Start all services in background
docker-compose up -d

# Start with verbose output
docker-compose up

# Start specific service
docker-compose up -d olav-agent

# Start without building (image must exist)
docker-compose up -d --no-build
```

### Service Management

```bash
# View status of all services
docker-compose ps

# View logs for all services
docker-compose logs

# View logs for specific service
docker-compose logs olav-agent
docker-compose logs -f ollama  # Follow logs

# Execute command in service
docker-compose exec olav-agent python -m olav.cli.cli_main config show

# Scale service (if applicable)
docker-compose up -d --scale olav-agent=2  # Not recommended, single agent
```

### Stopping and Cleanup

```bash
# Stop all services (containers remain)
docker-compose stop

# Stop specific service
docker-compose stop olav-agent

# Remove stopped containers
docker-compose rm -f

# Stop, remove containers, and clean volumes
docker-compose down -v

# Remove dangling images
docker image prune
```

### Configuration Management

Configuration is managed through three layers (Phase C-1):

**Layer 1: Environment Variables** (docker-compose.yml)
```yaml
environment:
  - LLM_MODEL_NAME=gpt-4
  - LLM_TEMPERATURE=0.7
  - ROUTING_CONFIDENCE_THRESHOLD=0.7
```

**Layer 2: settings.json** (.olav/settings.json)
Mount as volume and override at runtime:
```bash
docker-compose up -d -v .olav/settings.json:/app/.olav/settings.json
```

**Layer 3: Code Defaults**
Automatically applied if higher layers are missing

---

## Kubernetes Deployment

### Prerequisites

```bash
# Verify kubectl access
kubectl cluster-info

# Verify namespace capabilities
kubectl api-resources | grep namespace

# Check PersistentVolume support
kubectl get storageclass
```

### Deploying to Kubernetes

```bash
# Create namespace and deploy
kubectl apply -f k8s/olav-deployment.yaml

# Verify deployment
kubectl get pods -n olav
kubectl get services -n olav
kubectl get pvc -n olav

# Check rollout status
kubectl rollout status deployment/olav-agent -n olav

# View pod details
kubectl describe pod <pod-name> -n olav
```

### Configuration Management

**ConfigMap** contains agent configuration:
```bash
# View current config
kubectl get configmap olav-config -n olav -o yaml

# Update config
kubectl apply -f k8s/olav-deployment.yaml

# Edit inline
kubectl edit configmap olav-config -n olav
```

**Secret** contains sensitive data:
```bash
# Create/update secret
kubectl create secret generic olav-secrets \
  --from-literal=OPENAI_API_KEY=<api-key> \
  --from-literal=POSTGRES_PASSWORD=<password> \
  --from-literal=REDIS_PASSWORD=<password> \
  -n olav --dry-run=client -o yaml | kubectl apply -f -

# View secret (base64 encoded)
kubectl get secret olav-secrets -n olav -o yaml
```

### Scaling

```bash
# View current replicas
kubectl get deployment olav-agent -n olav

# Scale to N replicas
kubectl scale deployment olav-agent --replicas=3 -n olav

# Set autoscaling (1-3 replicas based on CPU)
kubectl apply -f k8s/olav-deployment.yaml  # Includes HPA
kubectl get hpa -n olav
```

### Monitoring

```bash
# View pod logs
kubectl logs <pod-name> -n olav
kubectl logs -f <pod-name> -n olav  # Follow

# View events
kubectl describe pod <pod-name> -n olav
kubectl get events -n olav

# Check pod status
kubectl get pod <pod-name> -n olav -o wide

# View resource usage (requires metrics-server)
kubectl top pod -n olav
kubectl top node
```

### Updating Deployment

```bash
# Update image (rolling update)
kubectl set image deployment/olav-agent \
  olav-agent=olav:0.8.1 -n olav

# Check rollout status
kubectl rollout status deployment/olav-agent -n olav

# Rollback if needed
kubectl rollout undo deployment/olav-agent -n olav
```

---

## Configuration Management

### Phase C-1 Integration

All deployment methods integrate with OLAV's three-layer configuration:

**Docker**: Environment variables in docker-compose.yml
```yaml
environment:
  - LLM_TEMPERATURE=0.7
  - ROUTING_CONFIDENCE_THRESHOLD=0.7
```

**Kubernetes**: ConfigMap + Secrets
```bash
kubectl get configmap olav-config -n olav
kubectl get secret olav-secrets -n olav
```

### Runtime Configuration Updates

**Docker Compose**:
```bash
# Update settings.json and restart
docker-compose restart olav-agent

# Or scale to new version
docker-compose up -d --force-recreate
```

**Kubernetes**:
```bash
# Update ConfigMap
kubectl edit configmap olav-config -n olav

# Rollout restart to apply changes
kubectl rollout restart deployment/olav-agent -n olav
```

### Configuration Validation

All deployment methods run Phase C-3 validation:

**Docker**: In container entrypoint
**Kubernetes**: In init container (`migrate-config`)

```bash
# Verify validation
docker logs olav-agent | grep "validation"
kubectl logs <pod-name> -n olav | grep "migration"
```

---

## Health Checks & Monitoring

### Health Check Endpoints

**Docker Container**:
```bash
# Check health status
docker inspect --format='{{json .State.Health}}' olav-agent | jq

# Expected output
{"Status":"healthy","FailingStreak":0,"Successes":2,"Failures":0,...}
```

**Kubernetes Pod**:
```bash
# Check liveness probe
kubectl describe pod <pod-name> -n olav | grep -A 5 "Liveness"

# Expected: Container is running and responsive
```

### Logging

**Docker Compose**:
```bash
# View centralized logs
docker-compose logs olav-agent

# Filter by level
docker-compose logs --follow olav-agent | grep ERROR
```

**Kubernetes**:
```bash
# View pod logs
kubectl logs <pod-name> -n olav

# Stream logs
kubectl logs -f <pod-name> -n olav

# View previous pod logs (if crashed)
kubectl logs <pod-name> -n olav --previous
```

### Metrics

**Docker**:
```bash
# Resource usage
docker stats olav-agent

# Memory usage
docker inspect olav-agent --format='{{.State.Memory}}'
```

**Kubernetes** (requires metrics-server):
```bash
# Pod metrics
kubectl top pod <pod-name> -n olav

# Node metrics
kubectl top node

# Autoscaler status
kubectl describe hpa olav-hpa -n olav
```

---

## Troubleshooting

### Common Issues

#### Container fails to start

**Docker**:
```bash
# Check logs
docker logs olav-agent

# Check if image exists
docker images | grep olav

# Rebuild image
docker build -t olav:0.8 .

# Run with verbose output
docker run -it olav:0.8 python -m olav.cli.cli_main --help
```

**Kubernetes**:
```bash
# Check pod status
kubectl describe pod <pod-name> -n olav

# Check events
kubectl get events -n olav --sort-by='.lastTimestamp'

# Check init container logs
kubectl logs <pod-name> -n olav -c migrate-config
```

#### Service connectivity issues

**Docker Compose**:
```bash
# Verify network
docker network ls | grep olav
docker network inspect olav_olav-network

# Check DNS resolution
docker run --rm --network olav_olav-network alpine nslookup olav-agent
```

**Kubernetes**:
```bash
# Check service
kubectl get svc -n olav

# Test connectivity from pod
kubectl run -it --rm debug --image=alpine --restart=Never -n olav -- sh
# Inside pod: nslookup olav-service.olav.svc.cluster.local

# Check network policies
kubectl get networkpolicies -n olav
```

#### Configuration not loading

**Docker**:
```bash
# Verify volume mounts
docker inspect olav-agent | grep -A 5 Mounts

# Check settings.json exists
docker exec olav-agent ls -la .olav/

# Validate JSON
docker exec olav-agent python -c "import json; json.load(open('.olav/settings.json'))"
```

**Kubernetes**:
```bash
# Check ConfigMap
kubectl get configmap olav-config -n olav -o yaml

# Check volume mounts
kubectl describe pod <pod-name> -n olav | grep -A 5 "Mounts"

# Verify config in running pod
kubectl exec <pod-name> -n olav -- cat .olav/settings.json
```

#### Memory/CPU issues

**Docker**:
```bash
# Check resource limits in docker-compose.yml
# Monitor usage
docker stats olav-agent

# Increase limits
# Edit docker-compose.yml and restart
```

**Kubernetes**:
```bash
# Check current requests/limits
kubectl describe pod <pod-name> -n olav

# Update limits in deployment
kubectl set resources deployment olav-agent \
  -c=olav-agent \
  --limits=cpu=2,memory=2Gi \
  -n olav

# Verify
kubectl describe deployment olav-agent -n olav
```

### Debug Mode

**Docker**:
```bash
# Start with debug logging
docker run -e LOG_LEVEL=DEBUG olav:0.8

# Interactive shell
docker run -it olav:0.8 /bin/bash
```

**Kubernetes**:
```bash
# Update log level in ConfigMap
kubectl edit configmap olav-config -n olav
# Change LOG_LEVEL to DEBUG

# Restart pods
kubectl rollout restart deployment/olav-agent -n olav

# Check logs
kubectl logs -f <pod-name> -n olav
```

---

## Performance Tuning

### Docker Compose

```yaml
# Optimize resource allocation
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
    reservations:
      cpus: '1'
      memory: 1G
```

### Kubernetes

```yaml
# Adjust resource requests/limits in deployment
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2"
```

---

## Production Checklist

- [ ] Use production-grade image registry (not local builds)
- [ ] Set production secrets (OPENAI_API_KEY, database passwords)
- [ ] Configure persistent volumes for production storage
- [ ] Set up log aggregation (ELK, DataDog, etc.)
- [ ] Configure monitoring and alerting
- [ ] Set up backup strategies for data volumes
- [ ] Test disaster recovery procedures
- [ ] Set up TLS/SSL certificates
- [ ] Configure RBAC for Kubernetes access
- [ ] Set up network policies for security
- [ ] Document runbooks for common operations
- [ ] Schedule regular security updates

---

## Support & Resources

- **OLAV GitHub**: <repo-url>
- **Docker Docs**: https://docs.docker.com
- **Kubernetes Docs**: https://kubernetes.io/docs
- **OLAV Design Doc**: See DESIGN_V0.81.md

---

**Last Updated**: 2025-01-10  
**Phase C-4 Status**: Complete ✅
