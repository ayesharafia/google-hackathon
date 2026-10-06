"""Private S3-compatible immutable bytes. Authorization belongs to the scoped adapter."""
import hashlib
import io
import json
import time

from botocore.exceptions import BotoCoreError, ClientError

from physimesh.core.artifacts import ArtifactStore

from .database import Overloaded


class S3Artifacts:
    def __init__(self, client, bucket, *, prefix='physimesh', max_bytes=50_000_000):
        self.client, self.bucket = client, bucket
        self.prefix, self.max_bytes = prefix.strip('/'), max_bytes

    def verify_private_bucket(self):
        acl = self.client.get_bucket_acl(Bucket=self.bucket)
        if any('URI' in grant.get('Grantee', {}) for grant in acl.get('Grants', [])):
            raise ValueError('artifact bucket grants public/group access')
        try:
            policy = json.loads(self.client.get_bucket_policy(Bucket=self.bucket)['Policy'])
        except ClientError as exc:
            if exc.response['Error']['Code'] not in ('NoSuchBucketPolicy', 'NoSuchPolicy'):
                raise
            return
        for statement in policy.get('Statement', []):
            if statement.get('Effect') == 'Allow' and ('*' in str(statement.get('Principal', {}))):
                raise ValueError('artifact bucket policy permits anonymous/broad access')

    def _key(self, digest, *, meta=False):
        ArtifactStore._validate_digest(digest)
        return f'{self.prefix}/{"meta" if meta else "objects"}/{digest[:2]}/{digest}'

    def _put(self, key, raw):
        for attempt in range(3):
            try:
                self.client.put_object(Bucket=self.bucket, Key=key, Body=raw, IfNoneMatch='*',
                                       ContentType='application/octet-stream')
                return
            except ClientError as exc:
                code = exc.response['Error']['Code']
                if code in ('PreconditionFailed', '412'):
                    return
                if code in ('ConditionalRequestConflict', '409') and attempt < 2:
                    time.sleep(.05*(attempt+1))
                    continue
                if code in ('ConditionalRequestConflict', '409', 'SlowDown', 'ServiceUnavailable', 'InternalError'):
                    raise Overloaded('private artifact service busy; retry later') from exc
                raise
            except BotoCoreError as exc:
                raise Overloaded('private artifact service unavailable; retry later') from exc

    def put_bytes(self, data, *, kind, meta):
        if len(data) > self.max_bytes:
            raise ValueError('private artifact exceeds byte budget')
        digest = hashlib.sha256(data).hexdigest()
        self._put(self._key(digest), data)
        # Verify a first-writer race against the actual object, including corruption.
        with self.open(digest) as stream:
            if stream.read() != data:
                raise ValueError('private artifact publication integrity failed')
        self._put(self._key(digest, meta=True), json.dumps(
            {**meta, 'kind': kind, 'size': len(data)}, sort_keys=True, allow_nan=False).encode())
        return digest

    def put_file(self, path, *, kind, meta):
        with open(path, 'rb') as stream:
            data = stream.read(self.max_bytes+1)
        return self.put_bytes(data, kind=kind, meta=meta)

    def _read(self, key):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response['Error']['Code'] in ('NoSuchKey', '404'):
                raise KeyError(key) from exc
            if exc.response['Error']['Code'] in ('SlowDown', 'ServiceUnavailable', 'InternalError'):
                raise Overloaded('private artifact service busy; retry later') from exc
            raise
        except BotoCoreError as exc:
            raise Overloaded('private artifact service unavailable; retry later') from exc
        with response['Body'] as stream:
            data = stream.read(self.max_bytes+1)
        if len(data) > self.max_bytes:
            raise ValueError('private artifact exceeds byte budget')
        return data

    def open(self, digest):
        data = self._read(self._key(digest))
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('private artifact byte integrity failed')
        return io.BytesIO(data)

    def meta(self, digest):
        return json.loads(self._read(self._key(digest, meta=True)))
