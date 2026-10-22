"""Project-owned tabular sources; cross-project reuse never grants implicit reads."""
from __future__ import annotations

import hashlib
import json
import re

from physimesh.drone.provenance import canonical_json
from physimesh.platform.identity import Denied
from physimesh.platform.scoped_artifacts import artifact_scope
from physimesh.projects.performance import parse_map
from physimesh.projects.repository import ProjectMissing
from physimesh.projects.tabular import MAX_FILE, ImportSelection, preview_import


class SourceLibrary:
    def __init__(self, database, projects, identity=None):
        self.database, self.projects, self.identity = database, projects, identity
        with database.connection(write=True) as db:
            if database.postgres:
                db.execute('SELECT pg_advisory_xact_lock(17010603)')
            db.execute('CREATE TABLE IF NOT EXISTS source_library_migrations(version INTEGER PRIMARY KEY)')
            versions = [r[0] for r in db.execute('SELECT version FROM source_library_migrations').fetchall()]
            if versions not in ([], [1]):
                raise ValueError('unsupported source library migration')
            if not versions:
                db.execute('CREATE TABLE source_library ('
                           'entry_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project_meta(project_id), '
                           'manifest_sha256 TEXT NOT NULL, dataset_id TEXT NOT NULL, configuration_id TEXT NOT NULL, '
                           'source_kind TEXT NOT NULL, UNIQUE(project_id,manifest_sha256))')
                db.execute('CREATE INDEX library_owner ON source_library(project_id,entry_id)')
                db.execute('INSERT INTO source_library_migrations VALUES(1)')

    def authorize(self, project_id, principal=None, *, write=False):
        if self.identity:
            return self.identity.authorize(principal, project_id, write=write)
        self.projects.repository.get(project_id)
        return None

    def page(self, project_id, principal=None, *, query='', after='', limit=25):
        org = self.authorize(project_id, principal)
        if not isinstance(query, str) or len(query) > 160 or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('Library query/limit is outside its bounds.')
        if after and not re.fullmatch('[0-9a-f]{64}', after):
            raise ValueError('Invalid library cursor.')
        where, args = ['l.entry_id>?'], [after]
        if self.identity:
            where.append('EXISTS (SELECT 1 FROM platform_projects p JOIN org_members om '
                         'ON om.org_id=p.org_id LEFT JOIN project_members pm '
                         'ON pm.project_id=p.project_id AND pm.user_id=om.user_id '
                         "WHERE p.project_id=l.project_id AND p.org_id=? AND om.user_id=? "
                         "AND (om.role='admin' OR pm.role IN ('engineer','reviewer','viewer')))")
            args.extend([org, principal.user_id])
        if query:
            escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            where.append("(LOWER(l.dataset_id) LIKE LOWER(?) ESCAPE '\\' OR "
                         "LOWER(l.configuration_id) LIKE LOWER(?) ESCAPE '\\')")
            args.extend(['%' + escaped + '%'] * 2)
        with self.database.connection() as db:
            rows = db.execute('SELECT l.* FROM source_library l WHERE ' + ' AND '.join(where)
                              + ' ORDER BY l.entry_id LIMIT ?', (*args, limit + 1)).fetchall()
        return {'entries': [dict(row) for row in rows[:limit]],
                'next_cursor': rows[limit - 1]['entry_id'] if len(rows) > limit else None}

    def _entry(self, target_project, entry_id, principal=None):
        org = self.authorize(target_project, principal)
        with self.database.connection() as db:
            row = db.execute('SELECT * FROM source_library WHERE entry_id=?', (entry_id,)).fetchone()
        if row is None:
            raise ProjectMissing('library entry unavailable')
        source_org = self.authorize(row['project_id'], principal)
        if self.identity and source_org != org:
            raise Denied('library source must belong to the selected organization')
        return dict(row)

    @staticmethod
    def manifest(raw, filename, selection, preview, map_digest):
        return {'schema_version': 'rotor_tabular_import_v1', 'conversion_version': 'literal_si_v1',
                'filename': filename, 'file_sha256': hashlib.sha256(raw).hexdigest(),
                'map_sha256': map_digest, 'selection': selection.model_dump(mode='json'),
                'factors': preview['factors'], 'rows': preview['rows'],
                'blank_rows': preview['blank_rows'], 'selected_rows': preview['selected_rows']}

    def _index(self, project_id, manifest_digest, dataset):
        entry_id = hashlib.sha256((project_id + ':' + manifest_digest).encode()).hexdigest()
        with self.database.connection(write=True) as db:
            db.execute('INSERT OR IGNORE INTO source_library VALUES(?,?,?,?,?,?)',
                       (entry_id, project_id, manifest_digest, dataset['dataset_id'],
                        dataset['configuration_id'], dataset['source_kind']))
        return entry_id

    def save(self, project_id, raw, filename, selection, principal=None):
        self.authorize(project_id, principal, write=True)
        filename = filename.replace('\\', '/').split('/')[-1]
        if not filename or len(filename) > 160:
            raise ValueError('Filename must contain 1–160 characters.')
        preview = preview_import(raw, filename, selection)
        if not preview['valid']:
            raise ValueError('Preview contains errors. Correct them before saving to the library.')
        map_raw = canonical_json(preview['dataset']).encode()
        if len(map_raw) > 500_000:
            raise ValueError('Normalized map exceeds the existing 500000-byte limit.')
        map_digest = hashlib.sha256(map_raw).hexdigest()
        manifest = self.manifest(raw, filename, selection, preview, map_digest)
        with artifact_scope(project_id):
            store = self.projects.artifacts
            store.put_bytes(raw, kind='rotor_tabular_original_v1', meta={})
            store.put_bytes(map_raw, kind='rotor_map_v1', meta={'source_kind': preview['dataset']['source_kind']})
            digest = store.put_bytes(canonical_json(manifest).encode(), kind='rotor_tabular_import_v1', meta={})
        entry = self._index(project_id, digest, preview['dataset'])
        return self.detail(project_id, entry, principal)

    def _read(self, digest, bound):
        with self.projects.artifacts.open(digest) as stream:
            raw = stream.read(bound + 1)
        if len(raw) > bound or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Library source integrity failed.')
        return raw

    def bundle(self, target_project, entry_id, principal=None):
        entry = self._entry(target_project, entry_id, principal)
        with artifact_scope(entry['project_id']):
            manifest_raw = self._read(entry['manifest_sha256'], MAX_FILE)
            manifest = json.loads(manifest_raw)
            if manifest.get('schema_version') != 'rotor_tabular_import_v1':
                raise ValueError('Unsupported library manifest.')
            raw = self._read(manifest['file_sha256'], MAX_FILE)
            map_raw = self._read(manifest['map_sha256'], 500_000)
            dataset = parse_map(map_raw).model_dump(mode='json')
            selection = ImportSelection.model_validate_json(canonical_json(manifest['selection']))
            preview = preview_import(raw, manifest['filename'], selection)
            expected = self.manifest(raw, manifest['filename'], selection, preview, manifest['map_sha256'])
            if (not preview['valid'] or canonical_json(preview['dataset']).encode() != map_raw
                    or canonical_json(expected).encode() != manifest_raw
                    or any(entry[key] != dataset[key] for key in ('dataset_id', 'configuration_id', 'source_kind'))):
                raise ValueError('Library provenance differs from its retained source.')
        return entry, manifest, dataset, [(raw, 'rotor_tabular_original_v1'),
                                          (map_raw, 'rotor_map_v1'), (manifest_raw, 'rotor_tabular_import_v1')]

    def detail(self, target_project, entry_id, principal=None):
        entry, manifest, dataset, _ = self.bundle(target_project, entry_id, principal)
        return {'entry': entry, 'manifest': manifest, 'dataset': dataset,
                'source_sha256': manifest['map_sha256'],
                'qualification': 'Retained declarations and unit conversion; physical applicability remains unverified.'}

    def reuse(self, target_project, entry_id, principal=None):
        self.authorize(target_project, principal, write=True)
        entry, _, dataset, objects = self.bundle(target_project, entry_id, principal)
        with artifact_scope(target_project):
            for raw, kind in objects:
                self.projects.artifacts.put_bytes(raw, kind=kind, meta={})
        copied = self._index(target_project, entry['manifest_sha256'], dataset)
        return self.detail(target_project, copied, principal)
