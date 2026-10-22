"""Literal conversion and resource bounds do not validate real rotor performance."""
import io
import zipfile

import pytest
from openpyxl import Workbook

from physimesh.projects.tabular import (
    MAX_FILE,
    ImportSelection,
    TableSelection,
    inspect_table,
    preview_import,
)

CSV = b'rpm,force,torque,power\r\n1000,1,0,10\r\n2000,2,0,20\r\n'
DECLARATIONS = {'dataset_id': 'synthetic-measurements', 'configuration_id': 'fixture-rotor',
                'source_kind': 'analytic_fixture', 'source_description': 'Synthetic import fixture only',
                'torque_convention': 'absorbed_shaft_magnitude', 'density_kg_m3': 1.225,
                'axial_inflow_m_s': 0.0, 'pitch_deg': 0.0, 'max_continuous_duration_s': 600.0,
                'power_basis': 'electrical', 'covered_intervals_rpm': [[1000.0, 2000.0]]}


def selection(**changes):
    base = {'start_row': 2, 'end_row': 3, 'columns': dict(zip(('rpm', 'thrust_n', 'shaft_torque_nm', 'power_w'), range(1, 5))),
            'units': {'rpm': 'rpm', 'thrust_n': 'N', 'shaft_torque_nm': 'Nm', 'power_w': 'W'},
            'declarations': DECLARATIONS}
    base.update(changes)
    return ImportSelection.model_validate(base)


def xlsx(rows, *, sheet='Measurements'):
    workbook = Workbook()
    workbook.active.title = sheet
    for row in rows:
        workbook.active.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def rewrite(raw, name, change):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(output, 'w') as target:
        for member in source.namelist():
            value = source.read(member)
            target.writestr(member, change(value) if member == name else value)
    return output.getvalue()


def test_explicit_mapping_and_exact_unit_factors():
    selected = selection(units={'rpm': 'rpm', 'thrust_n': 'kgf', 'shaft_torque_nm': 'Ncm', 'power_w': 'kW'})
    result = preview_import(CSV, 'data.csv', selected)
    assert result['valid']
    assert result['dataset']['points'][0] == {'rpm': 1000.0, 'thrust_n': 9.80665,
                                             'shaft_torque_nm': 0.0, 'power_w': 10000.0}
    assert result['rows'][0]['original']['thrust_n'] == '1'
    assert result['rows'][0]['row'] == 2
    assert result['factors']['shaft_torque_nm'] == .01
    result = preview_import(CSV, 'data.csv', selection(units={**selection().units, 'thrust_n': 'gf'}))
    assert result['dataset']['points'][0]['thrust_n'] == .00980665


@pytest.mark.parametrize('delimiter', [',', ';', '\t'])
def test_csv_dialects_bom_and_quoted_headers(delimiter):
    raw = ('\ufeff"speed"'+delimiter+'"force"'+delimiter+'torque'+delimiter+'power\n1000'+delimiter+'1'+delimiter+'0'+delimiter+'10\n2000'+delimiter+'2'+delimiter+'0'+delimiter+'20\n').encode()
    report = inspect_table(raw, 'data.csv', TableSelection(delimiter=delimiter))
    assert report['headers'] == ['speed', 'force', 'torque', 'power']
    assert preview_import(raw, 'data.csv', selection(delimiter=delimiter))['valid']


@pytest.mark.parametrize('value', ['=1+1', 'NaN', 'inf', '-1', '', '1_000', '1,000', 'text'])
def test_bad_measurement_is_visible_and_never_dropped(value):
    raw = f'r,f,q,p\n1000;{value};0;10\n2000;2;0;20'.replace('r,f,q,p', 'r;f;q;p').encode()
    result = preview_import(raw, 'data.csv', selection(delimiter=';'))
    assert not result['valid'] and result['dataset'] is None
    assert any(error['row'] == 2 and error['field'] == 'thrust_n' for error in result['errors'])


def test_blank_rows_are_counted_and_physical_row_numbers_preserved():
    result = preview_import(CSV.replace(b'2000', b'\r\n2000'), 'data.csv', selection(end_row=4))
    assert result['valid'] and result['blank_rows'] == 1
    assert [row['row'] for row in result['rows']] == [2, 4]


def test_no_sort_deduplicate_fit_or_coverage_inference():
    raw = b'r,f,q,p\n2000,2,0,20\n1000,1,0,10'
    assert not preview_import(raw, 'data.csv', selection())['valid']
    declaration = {**DECLARATIONS}
    del declaration['density_kg_m3']
    assert not preview_import(CSV, 'data.csv', selection(declarations=declaration))['valid']
    declaration = {**DECLARATIONS, 'covered_intervals_rpm': [[999.0, 2000.0]]}
    assert not preview_import(CSV, 'data.csv', selection(declarations=declaration))['valid']


def test_map_limit_and_no_silent_sampling():
    raw = ('r,f,q,p\n' + '\n'.join(f'{1000+i},{i+1},0,{i+10}' for i in range(65))).encode()
    result = preview_import(raw, 'data.csv', selection(end_row=66))
    assert not result['valid'] and result['included_rows'] == 65


@pytest.mark.parametrize('patch', [{'units': {**selection().units, 'thrust_n': 'kg'}},
                                  {'columns': {**selection().columns, 'power_w': 1}},
                                  {'start_row': 3, 'end_row': 2},
                                  {'declarations': {**DECLARATIONS, 'points': []}}])
def test_mapping_range_and_declaration_refusals(patch):
    with pytest.raises(ValueError):
        preview_import(CSV, 'data.csv', selection(**patch))


def test_xlsx_sheet_selection_and_literal_cells():
    raw = xlsx([['r', 'f', 'q', 'p'], [1000, 1, 0, 10], [2000, 2, 0, 20]])
    assert inspect_table(raw, 'data.xlsx', TableSelection()) == {'sheets': ['Measurements'], 'needs_sheet': True}
    assert preview_import(raw, 'data.xlsx', selection(sheet='Measurements'))['valid']
    with pytest.raises(ValueError, match='worksheet explicitly'):
        preview_import(raw, 'data.xlsx', selection())


@pytest.mark.parametrize('value', [True, '=1+1', '#DIV/0!'])
def test_xlsx_formula_boolean_and_error_refuse(value):
    raw = xlsx([['r', 'f', 'q', 'p'], [1000, value, 0, 10], [2000, 2, 0, 20]])
    result = preview_import(raw, 'data.xlsx', selection(sheet='Measurements'))
    assert not result['valid'] and result['errors'][0]['row'] == 2


def test_workbook_forged_dimensions_do_not_hide_cells():
    raw = xlsx([['r', 'f', 'q', 'p'], [1000, 1, 0, 10], [2000, 2, 0, 20]])
    raw = rewrite(raw, 'xl/worksheets/sheet1.xml', lambda b: b.replace(b'A1:D3', b'A1:A1'))
    assert preview_import(raw, 'data.xlsx', selection(sheet='Measurements'))['valid']
    raw = rewrite(raw, 'xl/worksheets/sheet1.xml', lambda b: b.replace(b'r="A3"', b'r="A99999999"'))
    with pytest.raises(ValueError, match='5000 rows'):
        inspect_table(raw, 'data.xlsx', TableSelection(sheet='Measurements'))


def test_external_relationship_entity_and_expanded_archive_refuse():
    raw = xlsx([['r', 'f', 'q', 'p']])
    external = rewrite(raw, '_rels/.rels', lambda b: b.replace(b'Type=', b'TargetMode="External" Type=', 1))
    with pytest.raises(ValueError, match='External'):
        inspect_table(external, 'data.xlsx', TableSelection())
    entity = rewrite(raw, 'xl/workbook.xml', lambda b: b'<!DOCTYPE x [<!ENTITY x "boom">]>' + b)
    with pytest.raises(ValueError):
        inspect_table(entity, 'data.xlsx', TableSelection())
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as target:
        target.writestr('oversized', b'0' * (20 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match='expanded'):
        inspect_table(output.getvalue(), 'data.xlsx', TableSelection())


@pytest.mark.parametrize('name,raw', [('legacy.xls', b'data'), ('macro.xlsm', b'data'),
                                    ('data.csv', b'\xff'), ('data.csv', b'x' * (MAX_FILE + 1)),
                                    ('data.xlsx', b'not a workbook')])
def test_unsupported_or_bounded_inputs(name, raw):
    with pytest.raises(ValueError):
        inspect_table(raw, name, TableSelection())


def test_parser_admission_is_bounded():
    from physimesh.platform.database import Overloaded
    from physimesh.projects.tabular import _READERS
    for _ in range(4):
        assert _READERS.acquire(blocking=False)
    try:
        with pytest.raises(Overloaded, match='busy'):
            inspect_table(CSV, 'data.csv', TableSelection())
    finally:
        for _ in range(4):
            _READERS.release()


def test_nonfinite_excel_cell_cannot_break_json_preview():
    import json
    raw = xlsx([['r', 'f', 'q', 'p'], [1000, 1, 0, 10], [2000, 2, 0, 20]])
    raw = rewrite(raw, 'xl/worksheets/sheet1.xml', lambda b: b.replace(b'<v>1</v>', b'<v>1e999</v>'))
    json.dumps(inspect_table(raw, 'data.xlsx', TableSelection(sheet='Measurements')), allow_nan=False)
    result = preview_import(raw, 'data.xlsx', selection(sheet='Measurements'))
    assert not result['valid']
    json.dumps(result, allow_nan=False)
