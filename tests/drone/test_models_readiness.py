import pathlib

import pytest

from physimesh.drone.models import AircraftStatus, load_project, readiness

TEMPLATE = pathlib.Path("src/physimesh/drone/schema/drone_manifest_v1.yaml")


def test_template_loads_and_preserves_nulls():
    snap = load_project(TEMPLATE)
    assert snap.identity["schema_version"] == "drone_manifest_v1"
    assert snap.mission["payload_mass_kg"] == 750
    assert snap.units_and_frames["source_units"] is None


def test_template_is_inputs_incomplete_for_every_purpose():
    snap = load_project(TEMPLATE)
    for purpose in ("screening", "cfd_run", "feasibility"):
        rep = readiness(snap, purpose)
        assert rep.status is AircraftStatus.INPUTS_INCOMPLETE
        assert rep.ready is False
        assert "units_and_frames.source_units" in rep.blocking or purpose == "screening"


def test_unknown_schema_version_rejected(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text(TEMPLATE.read_text().replace("drone_manifest_v1", "drone_manifest_v9"))
    with pytest.raises(ValueError, match="schema_version"):
        load_project(p)


def test_missing_group_rejected(tmp_path):
    text = TEMPLATE.read_text()
    p = tmp_path / "x.yaml"
    p.write_text(text.replace("symmetry:", "symmetry_typo:"))
    with pytest.raises(ValueError, match="symmetry"):
        load_project(p)


def test_symmetry_execution_default_off():
    assert load_project(TEMPLATE).symmetry["execution"] == "off"


def test_cfd_run_blocked_by_null_backend_digest():
    rep = readiness(load_project(TEMPLATE), "cfd_run")
    assert "execution.backend_image_digest" in rep.blocking


def _screening_project():
    import yaml
    data = yaml.safe_load(TEMPLATE.read_text())
    data["masses"]["items"] = [
        {"name": c, "category": c, "mass_kg": 750 if c == "payload" else 0, "cg_body_m": [0, 0, 0]}
        for c in ("payload", "structure", "propulsion", "energy", "avionics", "other")
    ]
    data["atmosphere"].update(source="fixture", pressure_pa=101325, temperature_k=288.15,
                             viscosity={"law": "sutherland"})
    data["rotors"] = [{"rotor_id": "r1", "radius_m": 1, "map_ref": "fixture-map"}]
    return data


def _load(tmp_path, data):
    import yaml
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_project(path)


def _cfd_project():
    data = _screening_project()
    data["units_and_frames"]["source_units"] = "m"
    data["assembly"].update(geometry_revision_sha256="a" * 64,
                            components=[{"component_id": "fixture", "role": "body"}])
    data["rotors"][0].update(center_body_m=[1, 0, 0], axis_body=[0, 0, 1], signed_rpm=1000.0)
    data["mesh"].update(global_cell_m=0.1, max_cells=1000, rotation_zones={"r1": {"radius_m": 1.1}})
    data["domain"]["bounds_m"] = [[-2, -2, -2], [2, 2, 2]]
    data["execution"].update(backend_version="v2606", backend_image_digest="fixture/image@sha256:" + "b" * 64)
    data["flow"]["pressure_dimensions"] = [1, -1, -2, 0, 0, 0, 0]
    data["boundaries"].update(far_field={"kind": "fixture"}, outlet={"kind": "fixture"},
                              ground_model="none", walls={"kind": "fixture"})
    return data


def test_complete_screening_inputs_do_not_claim_validation(tmp_path):
    report = readiness(_load(tmp_path, _screening_project()), "screening")
    assert report.blocking == []
    assert report.ready is True
    assert report.status is None          # no screening has run; readiness never upgrades status


def test_snapshot_is_deeply_immutable(tmp_path):
    snapshot = _load(tmp_path, _screening_project())
    with pytest.raises(TypeError):
        snapshot.atmosphere["viscosity"]["law"] = "invented"
    with pytest.raises(TypeError):
        snapshot.rotors[0]["radius_m"] = 9


def test_unknown_nested_keys_are_retained_and_reported(tmp_path):
    data = _screening_project()
    data["fidelity"]["bem"]["custom_tuning"] = None
    data["rotors"][0]["client_label"] = "port"
    snapshot = _load(tmp_path, data)
    assert snapshot.fidelity["bem"]["custom_tuning"] is None
    report = readiness(snapshot, "screening")
    assert "unknown key retained: fidelity.bem.custom_tuning" in report.warnings
    assert "unknown key retained: rotors[0].client_label" in report.warnings


def test_input_complete_cfd_does_not_claim_backend_capability(tmp_path):
    report = readiness(_load(tmp_path, _cfd_project()), "cfd_run")
    assert report.blocking == []
    assert report.ready is True and report.status is None
    assert any("does not establish backend capability" in warning for warning in report.warnings)


def test_null_inside_boundary_cannot_pass_readiness(tmp_path):
    data = _cfd_project()
    data["boundaries"]["far_field"] = {"kind": "inlet", "velocity_world_m_s": None}
    report = readiness(_load(tmp_path, data), "cfd_run")
    assert "boundaries.far_field.velocity_world_m_s" in report.blocking


@pytest.mark.parametrize("value", [None, -1, float("inf")])
def test_bad_rotor_radius_blocks_screening(tmp_path, value):
    data = _screening_project()
    data["rotors"][0]["radius_m"] = value
    assert "rotors[0].radius_m" in readiness(_load(tmp_path, data), "screening").blocking


def test_null_motor_limits_and_energy_block_feasibility(tmp_path):
    report = readiness(_load(tmp_path, _cfd_project()), "feasibility")
    assert "rotors[0].sustained_limits" in report.blocking
    assert "rotors[0].peak_limits" in report.blocking
    assert "mission.energy_system" in report.blocking
    assert "mission.duration_s" in report.blocking
    assert "mission.reserve_policy" in report.blocking


def test_mutable_backend_tag_and_bad_geometry_hash_block_cfd(tmp_path):
    data = _cfd_project()
    data["execution"]["backend_image_digest"] = "fixture/image:latest"
    data["assembly"]["geometry_revision_sha256"] = "abc"
    report = readiness(_load(tmp_path, data), "cfd_run")
    assert any("execution.backend_image_digest" in item for item in report.blocking)
    assert "assembly.geometry_revision_sha256" in report.blocking


def test_unknown_readiness_purpose_rejected():
    with pytest.raises(ValueError, match="purpose"):
        readiness(load_project(TEMPLATE), "publish")


def test_direct_snapshot_freezes_tuple_members():
    from dataclasses import fields

    from physimesh.drone.models import ProjectSnapshot
    original = load_project(TEMPLATE)
    data = {field.name: getattr(original, field.name) for field in fields(original)}
    rotor = {"rotor_id": "r1", "radius_m": 1}
    data["rotors"] = (rotor,)
    snapshot = ProjectSnapshot(**data)
    rotor["radius_m"] = 9
    assert snapshot.rotors[0]["radius_m"] == 1


def test_null_rotation_zone_child_blocks_cfd(tmp_path):
    data = _cfd_project()
    data["mesh"]["rotation_zones"]["r1"]["radius_m"] = None
    assert "mesh.rotation_zones[0].radius_m" in readiness(_load(tmp_path, data), "cfd_run").blocking


@pytest.mark.parametrize("bounds", [[[2, 2, 2], [-2, -2, -2]], [0, 1], [[0, 0, 0], [1, 1, float("nan")]]])
def test_malformed_domain_blocks_cfd(tmp_path, bounds):
    data = _cfd_project()
    data["domain"]["bounds_m"] = bounds
    assert "domain.bounds_m" in readiness(_load(tmp_path, data), "cfd_run").blocking


def test_unknown_component_and_case_keys_warn(tmp_path):
    data = _cfd_project()
    data["assembly"]["components"][0]["client_label"] = "fuselage"
    data["mission"]["cases"][0]["client_case"] = "A"
    report = readiness(_load(tmp_path, data), "cfd_run")
    assert "unknown key retained: assembly.components[0].client_label" in report.warnings
    assert "unknown key retained: mission.cases[0].client_case" in report.warnings


def test_yaml_set_extension_is_frozen(tmp_path):
    data = _screening_project()
    data["identity"]["client_labels"] = {"A", "B"}
    snapshot = _load(tmp_path, data)
    assert isinstance(snapshot.identity["client_labels"], frozenset)


# ---- Review fixes (2026-10-02): record-shaped nulls, component roles, rotor frames ----
_ROTOR_KEYS = ("rotor_id", "center_body_m", "axis_body", "signed_rpm", "pitch_deg", "n_blades", "radius_m",
               "root_cutout_m", "azimuth_zero_deg", "phase_offset_deg", "model", "map_ref", "blade_ref",
               "polar_ref", "sustained_limits", "peak_limits")   # plan Appendix A record shape


def _record_rotor(**overrides):
    rotor = dict.fromkeys(_ROTOR_KEYS)
    rotor.update(rotor_id="r1", radius_m=1, model="measured_map", map_ref="fixture-map")
    rotor.update(overrides)
    return rotor


def test_map_rotor_with_null_blade_and_phase_fields_is_screening_ready(tmp_path):
    data = _screening_project()
    data["rotors"] = [_record_rotor()]
    report = readiness(_load(tmp_path, data), "screening")
    assert report.blocking == [] and report.ready is True


def test_blade_rotor_needs_both_blade_and_polar(tmp_path):
    data = _screening_project()
    data["rotors"] = [_record_rotor(model="bem", map_ref=None, blade_ref="blade-1")]
    assert "rotors[0].map_ref or blade_ref + polar_ref" in readiness(_load(tmp_path, data), "screening").blocking


def test_missing_rotors_message_is_clean(tmp_path):
    data = _screening_project()
    data["rotors"] = []
    blocking = readiness(_load(tmp_path, data), "screening").blocking
    assert "rotors (count must be declared)" in blocking
    assert not any(b.startswith("rotors (count must be declared)[") for b in blocking)


def test_unknown_rotor_model_blocks(tmp_path):
    data = _screening_project()
    data["rotors"] = [_record_rotor(model="magic")]
    assert "rotors[0].model" in readiness(_load(tmp_path, data), "screening").blocking


def test_static_component_with_null_rotor_id_is_cfd_ready(tmp_path):
    data = _cfd_project()
    data["assembly"]["components"] = [{"component_id": "body", "role": "body", "rotor_id": None,
                                       "requires_user_tag": False}]
    assert readiness(_load(tmp_path, data), "cfd_run").blocking == []


def test_invalid_component_role_blocks(tmp_path):
    data = _cfd_project()
    data["assembly"]["components"][0]["role"] = "static_wall"
    assert "assembly.components[0].role" in readiness(_load(tmp_path, data), "cfd_run").blocking


def test_blade_component_needs_declared_rotor(tmp_path):
    data = _cfd_project()
    data["assembly"]["components"] = [{"component_id": "b1", "role": "blade", "rotor_id": "r9"}]
    assert "assembly.components[0].rotor_id" in readiness(_load(tmp_path, data), "cfd_run").blocking


def test_split_candidate_needing_user_tag_blocks(tmp_path):
    data = _cfd_project()
    data["assembly"]["components"][0]["requires_user_tag"] = True
    assert "assembly.components[0].requires_user_tag" in readiness(_load(tmp_path, data), "cfd_run").blocking


def test_cfd_rotor_needs_frame_and_signed_rpm(tmp_path):
    data = _cfd_project()
    data["rotors"] = [_record_rotor()]
    blocking = readiness(_load(tmp_path, data), "cfd_run").blocking
    for key in ("center_body_m", "axis_body", "signed_rpm"):
        assert f"rotors[0].{key}" in blocking


def test_zero_rotor_axis_blocks_cfd(tmp_path):
    data = _cfd_project()
    data["rotors"][0]["axis_body"] = [0, 0, 0]
    assert "rotors[0].axis_body" in readiness(_load(tmp_path, data), "cfd_run").blocking


def test_blade_resolved_rotor_without_phase_warns_not_blocks(tmp_path):
    data = _cfd_project()
    data["rotors"] = [_record_rotor(model="blade_resolved", map_ref=None, blade_ref="b", polar_ref="p",
                                    center_body_m=[1, 0, 0], axis_body=[0, 0, 1], signed_rpm=1000.0)]
    report = readiness(_load(tmp_path, data), "cfd_run")
    assert report.blocking == []
    assert any("azimuth_zero_deg" in w and "transient" in w for w in report.warnings)


def test_whitespace_string_is_not_a_value(tmp_path):
    data = _screening_project()
    data["atmosphere"]["source"] = "   "
    assert "atmosphere.source" in readiness(_load(tmp_path, data), "screening").blocking
