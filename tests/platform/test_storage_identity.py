import concurrent.futures
import hashlib
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import boto3
import jwt
import pytest
from botocore.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from moto.server import ThreadedMotoServer

from physimesh.platform.database import MetadataDB
from physimesh.platform.identity import Identity, InvalidSession, OIDCVerifier
from physimesh.platform.object_storage import S3Artifacts


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.delenv('AWS_PROFILE', raising=False)
    monkeypatch.delenv('AWS_DEFAULT_PROFILE', raising=False)
    server = ThreadedMotoServer(ip_address='127.0.0.1', port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    client = boto3.client('s3', endpoint_url=f'http://{host}:{port}', region_name='us-east-1',
                          aws_access_key_id='synthetic-key', aws_secret_access_key='synthetic-secret',
                          config=Config(proxies={}))
    bucket = 'synthetic-'+uuid4().hex
    client.create_bucket(Bucket=bucket)
    yield client, bucket
    server.stop()


def test_s3_http_conditional_publication_integrity_and_private_configuration(s3):
    client, bucket = s3
    store = S3Artifacts(client, bucket)
    store.verify_private_bucket()
    with concurrent.futures.ThreadPoolExecutor(10) as pool:
        digests = list(pool.map(lambda n: store.put_bytes(b'private fixture bytes', kind='fixture', meta={'first': n}),
                               range(10)))
    assert len(set(digests)) == 1
    digest = digests[0]
    assert store.open(digest).read() == b'private fixture bytes'
    assert store.meta(digest)['first'] in range(10)
    client.put_object(Bucket=bucket, Key=store._key(digest), Body=b'corrupted object')
    with pytest.raises(ValueError, match='integrity'):
        store.open(digest)
    client.put_bucket_acl(Bucket=bucket, ACL='public-read')
    with pytest.raises(ValueError, match='public'):
        store.verify_private_bucket()
    client.put_bucket_acl(Bucket=bucket, ACL='private')
    owner = client.get_bucket_acl(Bucket=bucket)['Owner']
    client.put_bucket_acl(Bucket=bucket, AccessControlPolicy={'Owner': owner, 'Grants': [
        {'Grantee': {'Type': 'CanonicalUser', 'ID': owner['ID']}, 'Permission': 'FULL_CONTROL'},
        {'Grantee': {'Type': 'CanonicalUser', 'ID': 'a'*64}, 'Permission': 'READ'}]})
    with pytest.raises(ValueError, match='non-owner'):
        store.verify_private_bucket()
    client.put_bucket_acl(Bucket=bucket, ACL='private')
    policy = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': '*',
        'Action': 's3:GetObject', 'Resource': f'arn:aws:s3:::{bucket}/*'}]}
    client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
    with pytest.raises(ValueError, match='anonymous'):
        store.verify_private_bucket()


def test_s3_byte_limits_and_digest_validation(s3):
    client, bucket = s3
    store = S3Artifacts(client, bucket, max_bytes=16)
    with pytest.raises(ValueError, match='byte budget'):
        store.put_bytes(b'x'*17, kind='fixture', meta={})
    digest = hashlib.sha256(b'x'*17).hexdigest()
    client.put_object(Bucket=bucket, Key=store._key(digest), Body=b'x'*17)
    with pytest.raises(ValueError, match='byte budget'):
        store.open(digest)
    with pytest.raises(ValueError, match='digest'):
        store.open('../other')
    with pytest.raises(KeyError):
        store.open('a'*64)


def test_oidc_verifies_signature_issuer_audience_expiry_and_individual_revocation(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = OIDCVerifier('https://identity.example.test', 'engineering-api', 'https://identity.example.test/jwks')
    # Substitute transport/key retrieval only; exercise actual cryptographic JWT validation.
    verifier.keys = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private.public_key()))
    base = {'iss': 'https://identity.example.test', 'aud': 'engineering-api', 'sub': 'subject-fixture',
            'iat': int(time.time()), 'exp': int(time.time())+600}
    token = jwt.encode(base, private, algorithm='RS256', headers={'kid': 'fixture'})
    assert verifier.verify(token)['sub'] == 'subject-fixture'
    for changed in ({'aud': 'wrong-api'}, {'iss': 'https://wrong.example.test'}, {'exp': int(time.time())-1}):
        with pytest.raises(InvalidSession):
            verifier.verify(jwt.encode({**base, **changed}, private, algorithm='RS256'))
    with pytest.raises(InvalidSession):
        verifier.verify(jwt.encode(base, 'untrusted-secret'*3, algorithm='HS256'))
    identity = Identity(MetadataDB(tmp_path/'oidc.sqlite'))
    with pytest.raises(InvalidSession, match='not provisioned'):
        identity.oidc_session(token, verifier.verify(token))
    identity.provision('engineer@example.test', issuer=base['iss'], subject=base['sub'])
    principal = identity.oidc_session(token, verifier.verify(token))
    assert identity.session(token) == principal
    identity.revoke(principal)
    with pytest.raises(InvalidSession):
        identity.session(token)
    with pytest.raises(InvalidSession, match='revoked'):
        identity.oidc_session(token, verifier.verify(token))
    with pytest.raises(ValueError, match='HTTPS'):
        OIDCVerifier('http://identity.example.test', 'api', 'http://identity.example.test/jwks')
