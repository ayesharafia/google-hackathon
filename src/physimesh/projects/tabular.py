"""Bounded literal measurement import; no fitting, interpolation or inferred physics."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
import zipfile
from pathlib import PurePosixPath
from threading import BoundedSemaphore
from typing import Literal

from defusedxml import ElementTree as XML
from openpyxl import load_workbook
from pydantic import BaseModel, ConfigDict, Field

from physimesh.drone.provenance import canonical_json
from physimesh.platform.database import Overloaded
from physimesh.projects.performance import parse_map

MAX_FILE = 2 * 1024 * 1024
MAX_EXPANDED = 20 * 1024 * 1024
MAX_ROWS, MAX_COLS = 5000, 64
_READERS = BoundedSemaphore(4)
FIELDS = ('rpm', 'thrust_n', 'shaft_torque_nm', 'power_w')
# NIST SP 811 Appendix B.9 force factors. Ncm and kW use exact SI prefixes.
FACTORS = {'rpm': {'rpm': 1.0}, 'thrust_n': {'N': 1.0, 'gf': .00980665, 'kgf': 9.80665},
           'shaft_torque_nm': {'Nm': 1.0, 'Ncm': .01}, 'power_w': {'W': 1.0, 'kW': 1000.0}}
NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')


class TableSelection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    delimiter: Literal[',', ';', '\t'] = ','
    sheet: str = Field(default='', max_length=160)
    header_row: int = Field(default=1, ge=1, le=MAX_ROWS)


class ImportSelection(TableSelection):
    start_row: int = Field(ge=2, le=MAX_ROWS)
    end_row: int = Field(ge=2, le=MAX_ROWS)
    columns: dict[str, int]
    units: dict[str, str]
    declarations: dict


def _archive(raw):
    """Validate actual expanded XML before handing a bounded archive to openpyxl."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        names = [item.filename for item in members]
        if len(names) > 256 or len(set(names)) != len(names):
            raise ValueError('Workbook has too many or duplicate archive members.')
        total = 0
        for info in members:
            name = info.filename
            if (len(name) > 256 or name.startswith('/') or '\\' in name or '..' in PurePosixPath(name).parts
                    or info.flag_bits & 1 or 'vbaproject' in name.lower() or 'externallinks/' in name.lower()):
                raise ValueError('Unsupported encrypted, macro, external-link or unsafe workbook member.')
            if info.file_size > MAX_EXPANDED or total + info.file_size > MAX_EXPANDED:
                raise ValueError('Workbook expanded contents exceed 20 MiB.')
            with archive.open(info) as stream:
                content = stream.read(MAX_EXPANDED - total + 1)
            total += len(content)
            if total > MAX_EXPANDED:
                raise ValueError('Workbook expanded contents exceed 20 MiB.')
            if name.endswith(('.xml', '.rels')):
                root = XML.fromstring(content)
                if name == '[Content_Types].xml' and any('macroEnabled' in str(v) for e in root for v in e.attrib.values()):
                    raise ValueError('Macro-enabled workbooks are not supported. Save literal values as .xlsx.')
                for element in root.iter():
                    if element.attrib.get('TargetMode') == 'External':
                        raise ValueError('External workbook relationships are not supported.')
                    if name.startswith('xl/worksheets/') and element.tag.endswith('}row'):
                        row_index = element.attrib.get('r', '')
                        if not row_index.isdigit() or not 1 <= int(row_index) <= MAX_ROWS:
                            raise ValueError('Workbook exceeds 5000 rows or has invalid row coordinates.')
                    if name.startswith('xl/worksheets/') and element.tag.endswith('}c'):
                        match = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', element.attrib.get('r', ''))
                        if not match:
                            raise ValueError('Invalid worksheet cell coordinate.')
                        col = 0
                        for char in match[1]:
                            col = col * 26 + ord(char) - 64
                        if col > MAX_COLS or int(match[2]) > MAX_ROWS:
                            raise ValueError('Workbook exceeds 5000 rows or 64 columns.')
                    if element.tag.endswith('}t') and len(element.text or '') > 2048:
                        raise ValueError('Workbook cell text exceeds 2048 characters.')


def read_table(raw: bytes, filename: str, selection: TableSelection):
    if not _READERS.acquire(blocking=False):
        raise Overloaded('Tabular readers are busy; retry this source request later.')
    try:
        return _read_table(raw, filename, selection)
    finally:
        _READERS.release()


def _read_table(raw: bytes, filename: str, selection: TableSelection):
    if not raw or len(raw) > MAX_FILE:
        raise ValueError('Choose a nonempty file no larger than 2 MiB.')
    suffix = PurePosixPath(filename.lower()).suffix
    sheets = []
    if suffix == '.csv':
        try:
            rows = []
            for row in csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''),
                                  delimiter=selection.delimiter, strict=True):
                if len(rows) >= MAX_ROWS or len(row) > MAX_COLS:
                    raise ValueError('CSV exceeds 5000 rows or 64 columns.')
                if any(len(cell) > 2048 for cell in row):
                    raise ValueError('CSV cell text exceeds 2048 characters.')
                rows.append(row)
        except (UnicodeError, csv.Error) as exc:
            raise ValueError('CSV must be valid UTF-8 with the selected delimiter.') from exc
    elif suffix == '.xlsx':
        try:
            _archive(raw)
            workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=False, keep_links=False)
            try:
                sheets = workbook.sheetnames
                if len(sheets) > 16:
                    raise ValueError('Workbook exceeds 16 sheets.')
                if selection.sheet not in sheets:
                    return [], sheets
                sheet = workbook[selection.sheet]
                if not hasattr(sheet, 'reset_dimensions'):
                    raise ValueError('Choose a worksheet containing measurement cells.')
                sheet.reset_dimensions()
                rows = []
                for row in sheet.iter_rows():
                    values = []
                    for cell in row:
                        value = cell.value
                        if cell.data_type in ('f', 'e', 'd'):
                            value = 'Unsupported Excel formula/error/date: ' + str(value)[:128]
                        if isinstance(value, float) and not math.isfinite(value):
                            value = 'Unsupported non-finite numeric cell'
                        if value is not None and not isinstance(value, (str, float, int, bool)):
                            value = 'Unsupported Excel cell type'
                        values.append(value)
                    if len(rows) >= MAX_ROWS or len(values) > MAX_COLS:
                        raise ValueError('Workbook exceeds 5000 rows or 64 columns.')
                    rows.append(values)
            finally:
                workbook.close()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('Cannot read this workbook. Use a plain, unencrypted .xlsx with literal values.') from exc
    else:
        raise ValueError('Choose CSV or modern .xlsx. Legacy .xls and macro-enabled files are unsupported.')
    return rows, sheets


def inspect_table(raw, filename, selection):
    rows, sheets = read_table(raw, filename, selection)
    if not rows and sheets and selection.sheet not in sheets:
        return {'sheets': sheets, 'needs_sheet': True}
    if len(rows) < selection.header_row:
        raise ValueError('Header row is outside the table.')
    return {'sheets': sheets, 'needs_sheet': False, 'row_count': len(rows),
            'headers': [str(v or '') for v in rows[selection.header_row - 1]],
            'sample': rows[selection.header_row:selection.header_row + 5],
            'file_sha256': hashlib.sha256(raw).hexdigest()}


def preview_import(raw, filename, selection: ImportSelection):
    rows, sheets = read_table(raw, filename, selection)
    if sheets and selection.sheet not in sheets:
        raise ValueError('Choose a worksheet explicitly.')
    if not selection.header_row < selection.start_row <= selection.end_row <= len(rows):
        raise ValueError('Choose a data range after the header and within the table.')
    if (set(selection.columns) != set(FIELDS) or set(selection.units) != set(FIELDS)
            or len(set(selection.columns.values())) != 4
            or any(type(v) is not int or not 1 <= v <= MAX_COLS for v in selection.columns.values())):
        raise ValueError('Map four distinct columns for RPM, thrust, shaft torque and power.')
    if any(selection.units[key] not in FACTORS[key] for key in FIELDS):
        raise ValueError('Choose an explicitly supported unit for every measurement.')
    # Declarations must not overwrite the generated measurements or fixed wire units.
    forbidden = {'points', 'units', 'schema_version'} & set(selection.declarations)
    if forbidden:
        raise ValueError('Measurement points and wire units are generated from the explicit mapping.')
    diagnostics, converted, preview, blanks = [], [], [], 0
    for number in range(selection.start_row, selection.end_row + 1):
        row = rows[number - 1]
        if all(value is None or isinstance(value, str) and not value.strip() for value in row):
            blanks += 1
            continue
        point, original = {}, {}
        for key in FIELDS:
            index = selection.columns[key] - 1
            value = row[index] if index < len(row) else None
            original[key] = value
            try:
                if isinstance(value, bool) or value is None or not isinstance(value, (int, float, str)):
                    raise ValueError
                if isinstance(value, str) and not NUMBER.fullmatch(value.strip()):
                    raise ValueError
                numeric = float(value) * FACTORS[key][selection.units[key]]
                if not math.isfinite(numeric) or numeric < 0:
                    raise ValueError
                point[key] = numeric
            except (ValueError, OverflowError):
                if len(diagnostics) < 100:
                    diagnostics.append({'row': number, 'field': key,
                                        'message': 'A finite nonnegative literal number is required.'})
        if len(point) == 4:
            converted.append(point)
        if len(preview) < 64:
            preview.append({'row': number, 'original': original, 'si': point})
    if not 2 <= len(converted) <= 64:
        diagnostics.append({'row': None, 'field': 'range', 'message': 'Select 2–64 complete measurement rows.'})
    candidate = None
    if not diagnostics:
        try:
            data = {**selection.declarations, 'schema_version': 'rotor_map_v1', 'units': 'rpm_N_Nm_W',
                    'points': converted}
            candidate = parse_map(canonical_json(data).encode()).model_dump(mode='json')
        except ValueError as exc:
            diagnostics.append({'row': None, 'field': 'declarations / map', 'message': str(exc)[:8000]})
    return {'valid': candidate is not None, 'errors': diagnostics, 'rows': preview,
            'included_rows': len(converted), 'blank_rows': blanks,
            'selected_rows': selection.end_row - selection.start_row + 1,
            'factors': {key: FACTORS[key][selection.units[key]] for key in FIELDS},
            'file_sha256': hashlib.sha256(raw).hexdigest(), 'dataset': candidate}
