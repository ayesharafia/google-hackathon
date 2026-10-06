#!/usr/bin/env bash
set -euo pipefail
: "${PHYSIMESH_PYTHON_BASE:?Supply an approved python image including @sha256:digest}"
[[ "$PHYSIMESH_PYTHON_BASE" =~ @sha256:[a-f0-9]{64}$ ]] || { echo 'base image must be immutable' >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'commit the release sources before building images' >&2; exit 1; }
export SOURCE_DATE_EPOCH="$(git show -s --format=%ct HEAD)"
python scripts/release/download-wheels.py
python -m build --wheel --no-isolation
release_revision="$(git rev-parse HEAD)"
for release_target in application worker; do
  docker build --platform linux/amd64 --network none --build-arg "PYTHON_BASE=$PHYSIMESH_PYTHON_BASE" --target "$release_target" \
    --label "org.opencontainers.image.revision=$release_revision" \
    -t "physimesh-$release_target:$release_revision" -f deployment/Dockerfile .
done
