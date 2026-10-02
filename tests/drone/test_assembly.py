from physimesh.drone.frames import RotorFrame
from physimesh.drone.geometry import Assembly, Component, validate_assembly


def comp(cid, role, rotor=None, tag=False):
    return Component(cid, "f" * 64, None, role, rotor, tag)


def test_blade_without_rotor_is_blocking():
    a = Assembly((comp("c1", "blade"),), (), {})
    assert any("c1" in p and "rotor" in p for p in validate_assembly(a))


def test_untagged_component_is_blocking():
    a = Assembly((comp("c1", None),), (), {})
    assert any("role" in p for p in validate_assembly(a))


def test_rotor_needs_rotation_zone_and_rpm_sign_consistency():
    r = RotorFrame("R1", (0, 0, 0), (0, 0, 1), 1000.0)
    a = Assembly((comp("b1", "blade", "R1"), comp("h1", "hub", "R1")), (r,), {})
    assert any("rotation zone" in p for p in validate_assembly(a))


def test_valid_minimal_assembly():
    r = RotorFrame("R1", (0, 0, 0), (0, 0, 1), 1000.0)
    a = Assembly((comp("body", "body"), comp("b1", "blade", "R1")), (r,), {"R1": "rotor1"})
    assert validate_assembly(a) == []


def test_split_candidate_requires_user_tag():
    a = Assembly((comp("s0", "body", tag=True),), (), {})
    assert any("user tag" in p for p in validate_assembly(a))


def test_source_modelled_rotor_requires_explicit_declaration():
    rotor = RotorFrame("r1", (0, 0, 0), (0, 0, 1), 1000.)
    assembly = Assembly((comp("body", "body"),), (rotor,), {"r1": "zone"})
    assert any("rotor_source_model" in p for p in validate_assembly(assembly))
    declared = Assembly(assembly.components, assembly.rotors, assembly.rotation_zones, frozenset({"r1"}))
    assert validate_assembly(declared) == []


def test_rotor_without_signed_rpm_blocks():
    rotor = RotorFrame("r1", (0, 0, 0), (0, 0, 1), None)
    assembly = Assembly((comp("blade", "blade", "r1"),), (rotor,), {"r1": "zone"})
    assert any("signed RPM" in p for p in validate_assembly(assembly))


def test_duplicate_ids_and_shared_rotation_zone_block():
    rotor = RotorFrame("r1", (0, 0, 0), (0, 0, 1), 1000.)
    duplicate = Assembly((comp("c1", "blade", "r1"), comp("c1", "blade", "r1")),
                         (rotor, rotor), {"r1": "zone"})
    assert "duplicate rotor_id" in validate_assembly(duplicate)
    assert "duplicate component_id" in validate_assembly(duplicate)
    other = RotorFrame("r2", (0, 0, 0), (0, 0, 1), -1000.)
    shared = Assembly((comp("b1", "blade", "r1"), comp("b2", "blade", "r2")),
                      (rotor, other), {"r1": "zone", "r2": "zone"})
    assert "rotation zone assigned to multiple rotors" in validate_assembly(shared)


def test_static_role_cannot_be_marked_rotating():
    rotor = RotorFrame("r1", (0, 0, 0), (0, 0, 1), 1000.)
    assembly = Assembly((comp("body", "body", "r1"),), (rotor,), {"r1": "zone"})
    assert any("static role" in p for p in validate_assembly(assembly))
