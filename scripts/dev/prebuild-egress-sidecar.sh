#!/usr/bin/env bash
# Dev hosts only (Apple Silicon / arm64 daemons running the amd64 SWE-bench images).
#
# Harbor builds its egress-control sidecar for the daemon's native platform and
# names the image with a hash that includes that platform. When we run task
# containers with DOCKER_DEFAULT_PLATFORM=linux/amd64, compose then asks for an
# amd64 variant of that same tag. This script builds the sidecar as a
# multi-platform image under Harbor's exact tag so both variants exist.
# Requires the containerd image store (Colima default; Docker Desktop: enable in settings).
set -euo pipefail
cd "$(dirname "$0")/../.."
IMAGE=$(uv run python - <<'PY'
import asyncio
from harbor.environments.docker.docker import DockerEnvironment
from harbor.environments.docker.utils import default_docker_platform, _compute_image_name
from harbor.utils.container_cache import docker_build_context_hash
ctx = DockerEnvironment._EGRESS_CONTROL_SIDECAR_CONTEXT_PATH
df = DockerEnvironment._egress_control_sidecar_dockerfile_path()
platform = asyncio.run(default_docker_platform())
key = docker_build_context_hash(context=ctx, dockerfile_path=df, build_args={}, platform=platform)
print(_compute_image_name(DockerEnvironment._EGRESS_CONTROL_SIDECAR_DOCKER_NAME, key))
print(ctx); print(df)
PY
)
TAG=$(echo "$IMAGE" | sed -n 1p); CTX=$(echo "$IMAGE" | sed -n 2p); DF=$(echo "$IMAGE" | sed -n 3p)
echo "building $TAG for linux/arm64,linux/amd64"
docker buildx build --file="$DF" --platform=linux/arm64,linux/amd64 --output="type=docker,name=$TAG" "$CTX"
docker image inspect "$TAG" --format '{{.Os}}/{{.Architecture}} {{.Id}}'
