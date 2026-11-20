"""Presentation of verified retained bytes; no solver calls or performance inference."""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from physimesh.drone.provenance import canonical_json

REPORT_VERSION = 'retained_local_study_pdf_v1'
RENDERER_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
MAX_DIFFS = 500


def evidence_lines(value, indent=0):
    """Readable JSON with short scalar vectors on one line; no evidence omitted."""
    prefix = ' '*indent
    if isinstance(value, dict) and value:
        lines = ['{']
        for index, (key, child) in enumerate(sorted(value.items())):
            child_lines = evidence_lines(child, indent+2)
            lines.append(prefix+'  '+json.dumps(key, ensure_ascii=True)+': '+child_lines[0])
            lines.extend(child_lines[1:])
            if index < len(value)-1:
                lines[-1] += ','
        return lines+[prefix+'}']
    if isinstance(value, list) and value:
        encoded = json.dumps(value, ensure_ascii=True, allow_nan=False)
        if all(not isinstance(child, (dict, list)) for child in value) and len(encoded) <= 100-indent:
            return [encoded]
        lines = ['[']
        for index, child in enumerate(value):
            child_lines = evidence_lines(child, indent+2)
            lines.append(prefix+'  '+child_lines[0])
            lines.extend(child_lines[1:])
            if index < len(value)-1:
                lines[-1] += ','
        return lines+[prefix+']']
    return [json.dumps(value, ensure_ascii=True, allow_nan=False)]


def input_changes(before, after, path='', changes=None):
    """Ordered JSON-pointer changes. Arrays are whole values, never inferred identities."""
    changes = [] if changes is None else changes
    if canonical_json(before) == canonical_json(after):
        return changes
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            child = path + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in before:
                changes.append({'path': child, 'kind': 'added', 'after': after[key]})
            elif key not in after:
                changes.append({'path': child, 'kind': 'removed', 'before': before[key]})
            else:
                input_changes(before[key], after[key], child, changes)
            if len(changes) > MAX_DIFFS:
                raise ValueError('comparison exceeds 500 changed fields; export the retained input records')
    else:
        changes.append({'path': path or '/', 'kind': 'changed', 'before': before, 'after': after})
    return changes


def compare_records(before: dict, after: dict, before_snapshot: dict, after_snapshot: dict) -> dict:
    same_model = before['specification']['model'] == after['specification']['model']
    same_semantics = before.get('mission_semantics') == after.get('mission_semantics')
    comparable = (same_model and same_semantics and before.get('schema_version') == after.get('schema_version')
                  and before.get('data_scope') == after.get('data_scope')
                  and before.get('outcome') == after.get('outcome') == 'feasible')
    def summary(record):
        return {key: record.get(key) for key in ('study_sha256', 'outcome', 'payload_lower_bound_kg',
                'limiting_case_id', 'aggregate_limit', 'mission_semantics', 'data_scope', 'engineering_approval')}
    return {'schema_version': 'retained_study_comparison_v1', 'before': summary(before), 'after': summary(after),
            'same_model': same_model, 'same_mission_semantics': same_semantics,
            'comparable_numeric_results': comparable,
            'payload_change_kg': after['payload_lower_bound_kg']-before['payload_lower_bound_kg']
            if comparable else None,
            'input_changes': input_changes(before_snapshot, after_snapshot),
            'qualification': 'Differences between retained local studies. Changed inputs are not causal '
                             'attribution. Numeric change is omitted when model, schema, scope, mission '
                             'semantics or feasible outcomes differ. Engineering approval remains pending.'}


def render_pdf(raw: bytes, snapshot_raw: str) -> bytes:
    """Deterministic, bounded report with complete study and frozen-input appendices."""
    data = json.loads(raw)
    source_digest = hashlib.sha256(raw).hexdigest()
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    ink = colors.HexColor('#20382b')
    body = ParagraphStyle('ReportBody', parent=styles['BodyText'], fontName='Helvetica', fontSize=10,
                          leading=15, textColor=ink, spaceAfter=7)
    title = ParagraphStyle('ReportTitle', parent=body, fontSize=24, leading=29, spaceAfter=18)
    payload_style = ParagraphStyle('Payload', parent=body, fontSize=34, leading=42, spaceAfter=10)
    heading = ParagraphStyle('ReportHeading', parent=body, fontSize=15, leading=20,
                             spaceBefore=14, keepWithNext=True)
    mono = ParagraphStyle('Evidence', parent=body, fontName='Courier', fontSize=7.5, leading=11,
                          spaceAfter=1, splitLongWords=True, alignment=TA_LEFT)
    def text(value):
        # Built-in PDF fonts cannot represent every author-provided Unicode glyph.
        # Escapes retain the exact characters without silently dropping source content.
        return escape(str(value).encode('ascii', 'backslashreplace').decode()).replace('\n', '<br/>')
    def para(value, style=body):
        content = text(value)
        return Paragraph(content.replace(' ', '&nbsp;') if style is mono else content, style)
    story = [para('PhysiCore | Retained design study', title),
             para('Local static-hover model. Engineering approval pending.'),
             para('Analytic fixture' if data.get('data_scope') == 'analytic_fixture'
                  else 'Client inputs are unvalidated; this report is not an aircraft approval.'),
             para(data.get('qualification', 'Qualification unavailable in historical record.')),
             para('Result', heading), para('Outcome: ' + data['outcome'])]
    historical = data.get('schema_version') != 'local_mission_capacity_v3'
    if historical:
        story.append(para('Historical local result with earlier acceptance semantics. Preserved as recorded; '
                          'not reassessed under current V3 rules. Re-evaluate a saved design for current evidence.'))
    value = data.get('payload_lower_bound_kg')
    if data['outcome'] == 'feasible' and value is not None:
        story += [para(f'{math.floor(value*100)/100:.2f} kg', payload_style),
                  para(('Reported historical payload bound' if historical else 'Verified local payload lower bound')
                       + ', rounded down. Exact retained value: ' + repr(value) + ' kg.'),
                  para('Reported limiting constraint: ' + str(data.get('aggregate_limit')
                                                            or data.get('limiting_case_id')))]
    else:
        story.append(para('No payload capacity is published for this outcome.'))
    for reason in data.get('reasons', []):
        story.append(para(reason))
    if data.get('reason'):
        story.append(para(data['reason']))
    story += [para('Record identity', heading)]
    identity = [('Study', data['study_sha256']), ('Revision', data['specification']['revision_sha256']),
                ('Retained JSON SHA-256', source_digest), ('Renderer', REPORT_VERSION),
                ('Renderer source SHA-256', RENDERER_SOURCE_SHA256),
                ('ReportLab version', reportlab.Version)]
    for label, value in identity:
        story += [para(label), para(value, mono)]
    story += [para('Case outcomes', heading)]
    rows = [[para('Case'), para('Required'), para('Outcome'), para('Individual bound (kg)')]]
    for case in data['cases']:
        candidate = case.get('candidate') or {}
        bound = repr(candidate['payload_kg']) if case['outcome'] == 'feasible' and 'payload_kg' in candidate else 'Unavailable'
        rows.append([para(case['case_id']), para(str(case.get('required'))), para(case['outcome']), para(bound)])
    table = Table(rows, colWidths=[55*mm, 23*mm, 35*mm, 57*mm], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dae5de')),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('LEFTPADDING', (0, 0), (-1, -1), 7),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 7),
                               ('TOPPADDING', (0, 0), (-1, -1), 7),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
    story.append(table)
    sequence = data.get('sequence_evidence')
    if sequence:
        story += [para('Ordered mission energy', heading),
                  para('Constant-power exact integration: segment energy = electrical power x duration.'),
                  para('Held reserve is applied once. Total energy: ' + repr(sequence['total_energy_j'])
                       + ' J; usable budget: ' + repr(sequence['usable_energy_j']) + ' J.')]
        for segment in sequence['segments']:
            story.append(para(segment['segment_id'] + ': case ' + segment['case_id'] + ', '
                + repr(segment['duration_s']) + ' s, ' + repr(segment['electrical_power_w']) + ' W, '
                + repr(segment['energy_required_j']) + ' J, remaining '
                + repr(segment['remaining_usable_energy_j']) + ' J.'))
    story += [para('Interpreting this report', heading),
              para('The recorded solver uses declared rotor maps, loads and mass inputs. A feasible outcome '
                   'contains recomputed force and moment residuals. Unsupported inputs or unresolved solver '
                   'results do not establish physical infeasibility. Source coverage and numerical tolerances '
                   'are retained below. This report does not rerun the solver.'),
              para('Complete retained evidence', heading),
              para('The JSON export identified above is authoritative. Unicode in these appendices is shown '
                   'with ASCII escape sequences so every source character remains identifiable.')]
    evidence = evidence_lines(data)
    inputs = evidence_lines(json.loads(snapshot_raw))
    if (sum(len(line) for line in evidence + inputs) > 1_000_000
            or sum(max(1, (len(line)+99)//100) for line in evidence+inputs) > 12_000):
        raise ValueError('report exceeds bounded PDF rendering size; use the exact retained JSON export')
    for lines, label in ((evidence, None), (inputs, 'Frozen input snapshot')):
        if label:
            story += [Spacer(1, 8*mm), para(label, heading)]
        for line in lines:
            # Split long strings explicitly to avoid one enormous unbreakable paragraph.
            for start in range(0, max(1, len(line)), 100):
                story.append(para(line[start:start+100], mono))
    def footer(canvas, doc):
        canvas.setFillColor(ink)
        canvas.setFont('Helvetica', 8)
        canvas.drawString(20*mm, 12*mm, 'Local study ' + data['study_sha256'][:12] + ' | Approval pending')
        canvas.drawRightString(190*mm, 12*mm, str(doc.page))
    doc = SimpleDocTemplate(output, pagesize=(210*mm, 297*mm), leftMargin=20*mm, rightMargin=20*mm,
                           topMargin=20*mm, bottomMargin=23*mm, title='PhysiCore retained local study',
                           author='PhysiCore', pageCompression=1, invariant=1)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def report_identity(raw: bytes, snapshot_raw: str) -> dict:
    return {'renderer_version': REPORT_VERSION,
            'renderer_source_sha256': RENDERER_SOURCE_SHA256,
            'reportlab_version': reportlab.Version,
            'study_json_sha256': hashlib.sha256(raw).hexdigest(),
            'snapshot_sha256': hashlib.sha256(canonical_json(json.loads(snapshot_raw)).encode()).hexdigest()}
