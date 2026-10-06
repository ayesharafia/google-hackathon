#!/usr/bin/env bash
set -euo pipefail
: "${PHYSIMESH_PYTHON_BASE:?Supply an approved python image including @sha256:digest}"
[[ "$PHYSIMESH_PYTHON_BASE" =~ @sha256:[a-f0-9]{64}$ ]] || { echo 'base image must be immutable' >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'commit the release sources before building images' >&2; exit 1; }
export SOURCE_DATE_EPOCH="$(git show -s --format=%ct HEAD)"
python scripts/release/download-wheels.py
python -m build --wheel --no-isolation
release_revision="$(git rev-parse HEAD)"
release_builder="${PHYSIMESH_RELEASE_BUILDER:-physimesh-release}"
buildkit_base='moby/buildkit@sha256:6eceb8971ce4fceb3daca562832642706238b7eea72941fcf9896c93c3c4a53e'
if ! docker buildx inspect "$release_builder" >/dev/null 2>&1; then
  docker buildx create --name "$release_builder" --driver docker-container \
    --driver-opt "image=$buildkit_base,memory=2g,cpu-quota=200000,cpu-period=100000" --bootstrap
fi
docker buildx inspect "$release_builder" | rg -q '^Driver:[[:space:]]+docker-container$' || {
  echo 'timestamp rewriting requires the dedicated docker-container exporter' >&2; exit 1;
}
[[ "$(docker inspect "buildx_buildkit_${release_builder}0" --format '{{.Config.Image}}')" == "$buildkit_base" ]] || {
  echo 'release builder must use the pinned BuildKit image' >&2; exit 1;
}
python scripts/release/prepare-base.py "$PHYSIMESH_PYTHON_BASE" .backend/approved-base-oci
for release_target in application worker; do
  docker buildx build --builder "$release_builder" --platform linux/amd64 --network none \
    --build-context "verified-base=oci-layout://$PWD/.backend/approved-base-oci" \
    --build-arg "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH" --output type=docker,rewrite-timestamp=true \
    --build-arg PYTHON_BASE=verified-base --target "$release_target" \
    --label "org.opencontainers.image.revision=$release_revision" \
    -t "physimesh-$release_target:$release_revision" -f deployment/Dockerfile .
done
