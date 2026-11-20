import hashlib

import pytest

from physimesh.postpro.publication import identity_bytes, publication_identity, validate_identity


def manifest():
    return {name: hashlib.sha256(data).hexdigest() for name, data in
            [('results.json', b'first'), ('run_group.json', b'group'), ('recipes/plot.json', b'original recipe')]}


def test_same_study_with_changed_content_has_distinct_full_revision():
    first = publication_identity(manifest(), 'a'*64)
    changed = manifest() | {'recipes/plot.json': hashlib.sha256(b'changed recipe').hexdigest()}
    second = publication_identity(changed, 'a'*64)
    assert first.study_id == second.study_id == 'a'*16
    assert first.package_revision_sha256 != second.package_revision_sha256
    assert first.payload_manifest_sha256 != second.payload_manifest_sha256
    with pytest.raises(ValueError, match='differs'):
        validate_identity(identity_bytes(first), second)


def test_order_and_envelope_do_not_create_a_circular_identity():
    first = publication_identity(manifest(), 'a'*64)
    reordered = dict(reversed(list(manifest().items())))
    reordered['publication.json'] = hashlib.sha256(identity_bytes(first)).hexdigest()
    assert publication_identity(reordered, 'a'*64) == first


def test_revision_cannot_accept_an_incomplete_manifest():
    with pytest.raises(ValueError):
        publication_identity({'results.json': 'b'*64}, 'a'*64)
