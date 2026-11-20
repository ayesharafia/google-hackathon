from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "physimesh-equations-handbook.pdf"

NAVY = colors.HexColor("#123047")
TEAL = colors.HexColor("#0E7490")
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#5B6770")
PALE = colors.HexColor("#F1F7F8")
PALE_BLUE = colors.HexColor("#EEF4FA")
ORANGE = colors.HexColor("#C2410C")
LINE = colors.HexColor("#C7D5D9")


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="CoverKicker", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=10, leading=13, textColor=TEAL, tracking=1.3, spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=27, leading=31, textColor=NAVY, spaceAfter=14,
))
styles.add(ParagraphStyle(
    name="CoverSub", parent=styles["Normal"], fontName="Helvetica",
    fontSize=12, leading=18, textColor=INK, spaceAfter=18,
))
styles.add(ParagraphStyle(
    name="H1x", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=17, leading=21, textColor=NAVY, spaceBefore=3, spaceAfter=9,
))
styles.add(ParagraphStyle(
    name="H2x", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=11.5, leading=14, textColor=TEAL, spaceBefore=9, spaceAfter=4,
))
styles.add(ParagraphStyle(
    name="Bodyx", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=9.2, leading=13.2, textColor=INK, spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="Smallx", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=7.4, leading=10, textColor=MUTED, spaceAfter=4,
))
styles.add(ParagraphStyle(
    name="Eqx", parent=styles["Code"], fontName="Courier",
    fontSize=8.6, leading=12.2, textColor=NAVY, leftIndent=8, rightIndent=8,
))
styles.add(ParagraphStyle(
    name="Calloutx", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=9, leading=13, textColor=INK, leftIndent=8, rightIndent=8,
))
styles.add(ParagraphStyle(
    name="TableHeadx", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=8, leading=10, textColor=colors.white,
))
styles.add(ParagraphStyle(
    name="TableCellx", parent=styles["Normal"], fontName="Helvetica",
    fontSize=7.8, leading=10.2, textColor=INK,
))


def p(text: str, style: str = "Bodyx"):
    return Paragraph(text, styles[style])


def eq(text: str, label: str | None = None):
    body = f"<b>{label}</b>  {text}" if label else text
    t = Table([[Paragraph(body, styles["Eqx"])]], colWidths=[168 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return KeepTogether([t, Spacer(1, 2.5 * mm)])


def callout(text: str):
    t = Table([[p(text, "Calloutx")]], colWidths=[168 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
        ("BOX", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return KeepTogether([t, Spacer(1, 3 * mm)])


def source(text: str):
    return p("Source: " + text, "Smallx")


def table(headers, rows, widths):
    data = [[p(h, "TableHeadx") for h in headers]]
    data += [[p(str(c), "TableCellx") for c in row] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return KeepTogether([t, Spacer(1, 4 * mm)])


def footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9 * mm, "PhysiMesh equation handbook | active project equations")
    canvas.drawRightString(w - 18 * mm, 9 * mm, f"{doc.page}")
    canvas.restoreState()


def section(title: str, intro: str, src: str):
    return [p(title, "H1x"), p(intro), source(src)]


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4, rightMargin=21 * mm, leftMargin=21 * mm,
        topMargin=18 * mm, bottomMargin=19 * mm, title="PhysiMesh Equation Handbook",
        author="OpenAI Codex", subject="Equations used in the Drone-Project-main active codebase",
    )
    story = []

    # Cover
    story += [Spacer(1, 17 * mm), p("PHYSIMESH / DRONE PROJECT", "CoverKicker"),
              p("Equation handbook", "CoverTitle"),
              p("A compact, source-linked reference for the mathematical models and diagnostic operators implemented in the active repository.", "CoverSub")]
    story += [callout("Scope. This handbook covers the active runtime under <b>src/physimesh</b>, the generated OpenFOAM sphere profile, and the browser-visible diagnostic operators that consume those results. The retained <b>reference_impl</b> is a comparison suite, not the runtime path, so its historical formulas are not silently presented as current capability."),
              Spacer(1, 4 * mm),
              table(["Model family", "What the equations do"], [
                  ["Design and frames", "Convert units, transform vectors/tensors, and assemble rotor/body geometry."],
                  ["Mass and atmosphere", "Compute total mass, CG, inertia, air state, and local flow diagnostics."],
                  ["Rotor and trim", "Interpolate retained maps and solve bounded static-hover allocation."],
                  ["Mission and energy", "Apply pack limits, exact constant-power energy, and battery fixed-point sizing."],
                  ["CFD and loads", "Define the incompressible sphere solve and integrate native pressure/shear loads."],
                  ["Numerical evidence", "Measure window statistics, drift, grid sensitivity, and slice eligibility."],
              ], [42 * mm, 126 * mm]),
              Spacer(1, 8 * mm),
              p("Repository checkpoint: 5 October 2026", "Smallx"),
              p("Notation uses ASCII names (rho, Omega, mu, etc.) so equations remain searchable in a plain PDF text layer.", "Smallx"),
              PageBreak()]

    # Quick map
    story += [p("Reading map", "H1x"), p("The equation IDs below are local to this handbook. Each group points to the implementation or technical guide that defines it."),
              table(["Section", "Equation groups", "Primary source"], [
                  ["1. Units and frames", "U1-U7", "drone/units.py; drone/frames.py"],
                  ["2. Geometry", "G1-G8", "drone/geometry.py; drone/api.py; solver/foam_ascii.py"],
                  ["3. Mass and CG", "M1-M5", "drone/mass.py; drone/authoring.py"],
                  ["4. Atmosphere", "A1-A12", "drone/atmosphere.py; technical guide section 6"],
                  ["5. Rotor maps", "R1-R8", "drone/performance.py; frames.py"],
                  ["6. Static trim", "T1-T12", "drone/trim.py; drone/mission_capacity.py"],
                  ["7. Screening and battery", "S1-S10", "drone/screening.py; mission.py"],
                  ["8. CFD model", "C1-C7", "technical guide section 9; OpenFOAM templates"],
                  ["9. Loads and coefficients", "L1-L12", "postpro/loads3d.py; postpro/results.py"],
                  ["10. Statistics and GCI", "N1-N11", "postpro/statistics.py"],
                  ["11. Slice and display diagnostics", "V1-V7", "postpro/slice_eligibility.py; plots.py; viewer3d.js"],
              ], [39 * mm, 37 * mm, 92 * mm]),
              Spacer(1, 4 * mm),
              callout("Important reading rule. A formula can be mathematically correct while its inputs remain synthetic, source-bound, or outside aircraft validation. The handbook preserves those qualifiers beside each model family."),
              PageBreak()]

    # 1 Units and frames
    story += section("1. Units, frames, and rigid transforms", "All internal calculations are SI. Unit declarations are explicit; geometry size is never used to infer a missing unit.", "src/physimesh/drone/units.py; docs/technical/mvp-code-and-physics-guide.md:98-121")
    story += [p("Length conversion and OpenFOAM dimensions", "H2x"),
              eq("x_m = f_unit * x_source", "U1"),
              eq("dim = [kg, m, s, K, mol, A, cd] exponents", "U2"),
              p("The supported length factors are m=1, mm=1e-3, cm=1e-2, in=0.0254, and ft=0.3048. The parser retains dimensions as a seven-component integer tuple.")]
    story += [p("ZYX attitude and point/vector/tensor transforms", "H2x"),
              eq("R = Rz(yaw) * Ry(pitch) * Rx(roll);  Rz=[ [cy,-sy,0], [sy,cy,0], [0,0,1] ]", "U3"),
              eq("x_world = x_body * R^T + t", "U4"),
              eq("v_world = v_body * R^T", "U5"),
              eq("v_axial_world = det(R) * (v_axial_body * R^T)", "U6"),
              eq("I_world = R * I_body * R^T;  R * R^T = Identity", "U7"),
              p("Polar vectors such as force and velocity do not receive translation. Axial vectors such as moments and angular velocity receive the determinant factor so an explicitly reflected frame keeps its sign convention."),
              eq("Omega_vector = signed_RPM * (2*pi/60) * unit_axis", "U8"),
              source("drone/frames.py: rotation_matrix_zyx, transform_points, transform_axial_vectors, transform_tensor, RotorFrame.omega_vector")]
    story += [PageBreak()]

    # 2 Geometry
    story += section("2. Geometry intake and mesh metrics", "Geometry equations describe measurement and topology diagnostics. They do not infer mass, rotor identity, or aircraft validity from an STL.", "src/physimesh/drone/geometry.py; src/physimesh/drone/api.py; src/physimesh/solver/foam_ascii.py")
    story += [p("Triangle, shell, and tolerance metrics", "H2x"),
              eq("A_triangle = 0.5 * |(b-a) cross (c-a)|", "G1"),
              eq("A_surface = sum_f A_triangle,f", "G2"),
              eq("V_signed = sum_f [a_f dot (b_f cross c_f)] / 6", "G3"),
              eq("D_bbox = |ptp(all_vertices)|_2", "G4"),
              eq("tol_resolved = max(tol_absolute, tol_relative * D_bbox)", "G5"),
              eq("q_grid = round(x / grid_m);  x_key = q_grid", "G6"),
              p("The grid key is used for exact scale-relative welding diagnostics after SI conversion. Duplicate, boundary, non-manifold, winding, and degenerate-face checks are reported as topology evidence.")]
    story += [p("Polygon reconstruction and repair distance", "H2x"),
              eq("A_face = 0.5 * |sum_k (v_{k+1}-v_k) cross (c-v_k)|", "G7"),
              eq("c_face = sum_k [A_k * (v_k + v_{k+1} + c)] / (3 * sum_k A_k)", "G8"),
              eq("d_surface = max( max_x min_y dist(x, triangle_y), max_y min_x dist(y, triangle_x) )", "G9"),
              p("The repair distance is a sampled bidirectional surface metric using source vertices and triangle centroids. It is not a certified continuous Hausdorff bound."),
              source("solver/foam_ascii.py: face_centres_and_areas; geometry.py: _metrics, resolve_topology_tolerance, _sampled_surface_distance")]
    story += [PageBreak()]

    # 3 Mass
    story += section("3. Mass ledger, centre of gravity, and inertia", "The ledger requires explicit entries for payload, structure, propulsion, energy, avionics, and other. An omitted category stays unknown.", "src/physimesh/drone/mass.py; docs/technical/mvp-code-and-physics-guide.md:130-149")
    story += [eq("m_total = sum_i m_i", "M1"),
              eq("x_cg = sum_i (m_i * x_i) / m_total", "M2"),
              eq("m_empty = m_total - m_installed_payload", "M3"),
              eq("d_i = x_i - x_cg", "M4"),
              eq("I_cg = sum_i [ I_i + m_i * ( (d_i dot d_i) * Identity - d_i outer d_i ) ]", "M5"),
              p("For a candidate payload query, installed payload entries are replaced by one candidate mass at the declared candidate position; the battery remains an installed ledger item. Inertia is computed only when the requesting purpose needs it.")]
    story += [p("Physical admissibility checks", "H2x"),
              eq("I = I^T;  lambda_min(I) >= 0;  lambda_max <= lambda_1 + lambda_2", "M6"),
              p("The last inequality is the principal-moment triangle inequality. The current vertical/static hover capacity path does not use inertia to establish controllability."),
              source("mass.py: summarize; authoring.py: candidate_mass; technical guide section 5"), PageBreak()]

    # 4 Atmosphere
    story += section("4. Atmosphere and local-flow diagnostics", "The atmosphere model uses declared absolute pressure and temperature, with either a declared viscosity or the approved Sutherland law.", "src/physimesh/drone/atmosphere.py; docs/technical/mvp-code-and-physics-guide.md:151-190")
    story += [eq("rho = p_absolute / (R_air * T)", "A1"),
              eq("a_sound = sqrt(gamma * R_air * T)", "A2"),
              eq("nu = mu / rho", "A3"),
              eq("mu(T) = mu_ref * (T/T_ref)^1.5 * (T_ref+S)/(T+S)", "A4"),
              eq("Re_chord = rho * V_relative * chord / mu", "A5"),
              eq("Mach = V_relative / a_sound", "A6"),
              eq("Mach_tip = sqrt( (Omega*R)^2 + V_axial^2 ) / a_sound", "A7"),
              p("Constants: R_air=287.05 J/(kg K), g0=9.80665 m/s^2, gamma defaults to 1.4, mu_ref=1.716e-5 Pa s, T_ref=273.15 K, and S=110.4 K."),
              eq("T_ISA(h) = 288.15 - 0.0065*h", "A8"),
              eq("p_ISA(h) = 101325 * (T_ISA/288.15)^(g0/(0.0065*R_air))", "A9"),
              eq("A_disk = pi * R^2", "A10"),
              eq("v_induced = sqrt( T / (2*rho*A_disk) )", "A11"),
              eq("P_ideal_hover = T * v_induced = T^1.5 / sqrt(2*rho*A_disk)", "A12"),
              callout("The ideal-hover power equation is a diagnostic lower bound for isolated, zero-inflow hover. It is not an installed-aircraft electrical-power prediction or a climb model."),
              source("atmosphere.py; screening_diagnostics.py; technical guide section 6")]
    story += [PageBreak()]

    # 5 Rotor maps
    story += section("5. Rotor maps and power representation", "Rotor maps are retained source data at a fixed density, inflow, pitch, and covered RPM interval. Queries outside coverage are refused; no density scaling or extrapolation is performed.", "src/physimesh/drone/performance.py; src/physimesh/drone/frames.py")
    story += [eq("Omega = RPM * 2*pi/60", "R1"),
              eq("P_shaft = Q_absorbed * Omega", "R2"),
              eq("P_electrical = P_shaft / eta   (shaft-basis map)", "R3"),
              eq("P_electrical = P_map   (electrical-basis map)", "R4"),
              eq("y(rpm) = y_k + (rpm-rpm_k)*(y_{k+1}-y_k)/(rpm_{k+1}-rpm_k)", "R5"),
              p("The same linear interpolation is applied to thrust, torque, and stored power. At a query, shaft power is recomputed from interpolated torque and RPM and checked against the stored electrical value.")]
    story += [p("Restricted convex static profile", "H2x"),
              eq("s_k = (P_{k+1}-P_k)/(T_{k+1}-T_k);  b_k = P_k - s_k*T_k", "R6"),
              eq("P_e(T) = max_k (s_k*T + b_k)", "R7"),
              eq("Q(T) = q_slope*T + q_offset", "R8"),
              eq("s_{k+1} >= s_k >= 0;  q_slope >= 0", "R9"),
              p("The trim model accepts a complete covered interval, strictly increasing thrust, nondecreasing convex electrical power, and affine nondecreasing absorbed torque. Shaft-basis maps are converted to electrical watts once using the declared efficiency."),
              source("performance.py: RotorMapV1.consistency, evaluate, convex_static_profile"), PageBreak()]

    # 6 Trim
    story += section("6. Static-hover trim and bounded allocation", "The local pilot is a restricted convex static-hover model. It allocates rotor thrust, electrical epigraph variables, and one common payload variable.", "src/physimesh/drone/trim.py; docs/validation/local-hover-and-energy.md")
    story += [p("Rotor forces, reaction couples, and residual wrench", "H2x"),
              eq("F_i = a_i * T_i", "T1"),
              eq("reaction_i = -rotation_sign_i * a_i * Q_i", "T2"),
              eq("F_residual = sum_i F_i + F_body + (0,0,-m*g0)", "T3"),
              eq("M_residual_CG = sum_i [ (r_i-CG) cross F_i + reaction_i ] + M_body_origin - CG cross F_body", "T4"),
              eq("I_i = [ a_i ; cross(r_i,a_i) + reaction_i*q_slope ]", "T5"),
              eq("gravity = (0,0,-g0);  gravity_moment = payload_position cross gravity", "T6"),
              p("The six force/moment balance rows are assembled about the fixed origin for linear allocation; every candidate is then independently recomputed about its actual payload-dependent CG.")]
    story += [p("Linear program rows", "H2x"),
              eq("A_eq * z = b_eq,  z = [T_1..T_n, e_1..e_n, payload]", "T7"),
              eq("s_k*T_i - e_i <= -b_k", "T8"),
              eq("sum_i e_i <= P_pack_limit - P_aux", "T9"),
              eq("sum_i e_i <= E_usable / duration - P_aux", "T10"),
              eq("T_i in [T_i,min,T_i,max];  e_i in [0,P_i,limit];  payload in [p_min,p_max]", "T11"),
              eq("maximize payload;  or, at fixed payload, minimize sum_i e_i", "T12"),
              eq("I_i = e_i / V_bus", "T13"),
              p("A fixed-payload solve holds payload at one value and minimizes demand. Pack power and current are represented through the common limit min(P_declared, V_bus*I_pack_limit)."),
              source("trim.py: constraints, solve_hover, recompute; mission_capacity.py: joint_constraints"), PageBreak()]

    # 7 screening / mission
    story += section("7. Legacy vertical screening and mission energy", "The older screening endpoint remains in the project alongside the newer local convex hover model. Its equations are useful for interpreting retained synthetic examples.", "src/physimesh/drone/screening.py; src/physimesh/drone/mission.py; docs/technical/mvp-code-and-physics-guide.md:192-305")
    story += [p("Per-case vertical capacity", "H2x"),
              eq("F_z,c = sum_i F_rotor,i,z + F_body,z", "S1"),
              eq("m_supported,c = F_z,c / (g0 + a_z,c)", "S2"),
              eq("Delta_m_c = m_supported,c - m_empty", "S3"),
              eq("m_payload,c = max(0, Delta_m_c)", "S4"),
              eq("m_headline = min_c m_payload,c   (after every required case passes)", "S5"),
              eq("E_required,c = (sum_i P_electrical,i) * duration_c", "S6"),
              p("The acceleration denominator must be positive. Power, energy, and sustained per-rotor limits are checked before a headline is returned. A negative raw margin is retained as a requirement-not-met result rather than silently treated as an aircraft payload claim.")]
    story += [p("Fixed-pack chronological mission", "H2x"),
              eq("E_usable = battery_kg * Wh_per_kg * 3600 * usable_fraction * (1-reserve_fraction)", "S7"),
              eq("E_segment = P_segment * duration_segment", "S8"),
              eq("E_sequence = sum_j E_segment,j", "S9"),
              eq("E_remaining,k = E_usable - sum_{j<=k} E_segment,j", "S10"),
              p("Constant-power integration is exact multiplication. One payload is shared across participating cases; the sequence must fit the common usable pack budget and continuous-duration coverage.")]
    story += [p("Separate battery-mass fixed point", "H2x"),
              eq("P_electric(m) = sum_i [P_shaft,i/(eta_motor,i*eta_inverter,i*eta_drive,i)] + P_aux", "S11"),
              eq("E_mission(m) = P_electric(m) * duration", "S12"),
              eq("m_battery = E_mission*(1+reserve_fraction)/(e_pack*3600*usable_fraction)", "S13"),
              eq("m_next = m_without_battery + m_battery", "S14"),
              eq("|m_next-m| <= relative_tolerance*m_next", "S15"),
              source("screening.py; mission.py; mission_capacity.py; screening_scope.py"), PageBreak()]

    # 8 CFD
    story += section("8. OpenFOAM sphere model", "The CFD path is a stationary, incompressible, laminar sphere verification profile. Python generates dictionaries and reads outputs; it does not implement a substitute CFD solver.", "docs/technical/mvp-code-and-physics-guide.md:307-355; src/physimesh/solver/openfoam_templates/v2606/external_steady")
    story += [eq("Re = U_inf * D / nu", "C1"),
              eq("A_ref = pi * D^2 / 4", "C2"),
              eq("div(U) = 0", "C3"),
              eq("(U dot grad)U = -grad(p_kinematic) + nu * laplacian(U)", "C4"),
              p("The inspected fixture uses D=1 m, U_inf=(1,0,0) m/s, nu=0.01 m2/s, rho=1 kg/m3, hence Re=100. SIMPLE pressure/velocity coupling, finite-volume discretization, linear solvers, relaxation, and boundary dictionaries remain in the pinned OpenFOAM source/templates.")]
    story += [p("Convergence trigger and residual policy", "H2x"),
              eq("abs(Cd_running_mean - Cd_current) < 1e-3", "C5"),
              eq("window drift = |mean_last - mean_previous| / max(|mean_last|, absolute_scale)", "C6"),
              p("The controller starts after its configured startup iteration. The post-processing gate checks complete final windows; iteration count is not physical time."),
              source("technical guide section 9; solver/openfoam_templates/v2606/external_steady/system/controlDict and fvSolution"), PageBreak()]

    # 9 loads
    story += section("9. Native loads, moments, and coefficients", "Load integration uses native mesh polygons, native field values, and declared field dimensions. Display triangulation and interpolated contours never enter the force sum.", "src/physimesh/postpro/loads3d.py; src/physimesh/postpro/results.py; docs/technical/mvp-code-and-physics-guide.md:373-451")
    story += [p("Pressure, viscous, and total loads", "H2x"),
              eq("p_Pa = p_native                  [physical pressure]", "L1"),
              eq("p_Pa = rho * p_native             [kinematic pressure]", "L2"),
              eq("S_solid = -S_fluid", "L3"),
              eq("F_pressure = sum_f [ -(p_f-p_ref) * S_solid,f ]", "L4"),
              eq("F_viscous = sum_f [ t_v,f * |S_solid,f| ]", "L5"),
              eq("F_total = F_pressure + F_viscous", "L6"),
              eq("M_origin = sum_f [ (x_f-x_origin) cross F_f ]", "L7"),
              eq("M_O = M_A + (x_A-x_O) cross F", "L8"),
              eq("T_rotor = F dot axis", "L9"),
              eq("Q_aero = M_rotor_centre dot axis", "L10"),
              eq("P_shaft = - M_aero dot Omega", "L11"),
              eq("F_aircraft = -sum_cells(f_volume * V_cell)", "L12"),
              eq("M_rotor = -sum_cells[(x_cell-x_rotor) cross (f_volume*V_cell)]", "L13"),
              eq("Cd = F_x / (0.5*rho*U_inf^2*A_ref)", "L14"),
              p("The force ledger prevents double-counting rotor source reaction and rotor-wall traction for the same rotor. Gravity is not part of the aerodynamic total."),
              source("loads3d.py: integrate_surface, transfer_moment, rotor_loads, source_loads; results.py: coefficient scale")]
    story += [PageBreak()]

    # 10 numerical
    story += section("10. Statistics, drift, and grid convergence", "These equations quantify numerical behavior and sensitivity. They are diagnostic estimates, not universal error bounds or aircraft validation.", "src/physimesh/postpro/statistics.py; docs/technical/mvp-code-and-physics-guide.md:432-491")
    story += [p("Trapezoidal integration and window metrics", "H2x"),
              eq("Integral(f dxi) approx sum_j 0.5*(f_{j+1}+f_j)*(xi_{j+1}-xi_j)", "N1"),
              eq("mean = Integral(f dxi) / Delta_xi", "N2"),
              eq("RMS_fluct = sqrt( Integral((f-mean)^2 dxi) / Delta_xi )", "N3"),
              eq("drift = |mean_last-mean_previous| / max(|mean_last|, abs_scale)", "N4"),
              p("For the steady sphere, xi is iteration rather than physical time. Revolution windows are formed from a period and complete-window count for transient-capable diagnostics.")]
    story += [p("Richardson and GCI estimates", "H2x"),
              eq("h = (V/N)^(1/3);  r21=h2/h1;  r32=h3/h2", "N5"),
              eq("f(h) = f0 + C*h^p", "N6"),
              eq("e21=f2-f1;  e32=f3-f2", "N7"),
              eq("e32/e21 = r21^p * (r32^p-1)/(r21^p-1)", "N8"),
              eq("f_extrap = f1 + (f1-f2)/(r21^p-1)", "N9"),
              eq("GCI_fine = Fs * |(f1-f2)/f1| / (r21^p-1)", "N10"),
              eq("p_used = min(p_observed, p_nominal_cap)", "N11"),
              eq("GCI_capped = Fs*|(f1-f2)/f1| / expm1(p_used*log(r21))", "N12"),
              p("Unequal refinement ratios are solved numerically for positive p. Oscillatory, divergent, zero-difference, or non-positive-order behavior returns no forced GCI."),
              source("statistics.py: grid_convergence, grid_convergence_unequal, order_capped_gci")]
    story += [PageBreak()]

    # 11 slice and display
    story += section("11. Slice eligibility, visualization ranges, and browser mapping", "Visualization operators are evidence-preserving diagnostics. They do not feed back into loads or payload screening.", "src/physimesh/postpro/slice_eligibility.py; src/physimesh/postpro/plots.py; web/js/viewer3d.js")
    story += [p("Slice geometry and coverage", "H2x"),
              eq("plane_tolerance = tolerance_fraction * diameter", "V1"),
              eq("external_coverage = finite_external_nodes / all_external_nodes", "V2"),
              eq("scale = span, if span > 64*eps*magnitude; else max(magnitude,tiny)", "V3"),
              eq("RMS_normalized = sqrt(mean(difference^2)) / scale", "V4"),
              eq("peak_normalized = max(|difference|) / scale", "V5"),
              p("Vector differences use the full world vector; scalar differences retain sign. A slice is eligible only when coverage, RMS, peak, and geometry gates all pass for the registered tolerances.")]
    story += [p("Weighted display range operators", "H2x"),
              eq("clipped_fraction = sum(weights_outside_range) / sum(weights)", "V6"),
              eq("color_t = clamp((value-lo)/(hi-lo),0,1)", "V7"),
              eq("Cumulative_weight(v_k) = sum_{j<=k} w_j / sum_j w_j;  q_alpha = first v_k with Cumulative_weight >= alpha", "V8"),
              p("The browser maps a face value to a color stop using the normalized t above. For signed pressure, the range is symmetric about zero; for nonnegative magnitudes, the lower bound is zero. These are display equations only."),
              source("slice_eligibility.py: evaluate_slice; plots.py: choose_range; viewer3d.js: setField")]
    story += [PageBreak()]

    # 12 contract and qualification
    story += section("12. Qualification and equation boundaries", "A final equation reference must also state what the formulas do not prove. This section collects the operational boundaries encoded by the active implementation.", "docs/technical/local-workbench-and-physics-guide.md; docs/contracts/mission-capacity.md; docs/validation/local-hover-and-energy.md")
    story += [table(["Equation family", "Implemented meaning", "Explicit boundary"], [
        ["Mass / CG", "Consistent SI ledger and candidate placement.", "Not a CAD-derived mass estimate; inertia is not a controllability proof."],
        ["Atmosphere", "Declared pressure/temperature/viscosity and diagnostics.", "No automatic density scaling of a rotor map."],
        ["Rotor maps", "Source-bound interpolation and convex profile.", "No extrapolation; isolated fixed-condition curves are not installed-aircraft validation."],
        ["Static trim", "Checked point in a bounded convex hover model.", "No transient dynamics, rotor interference, sag, thermal state, or structural feasibility."],
        ["Energy", "Exact constant-power multiplication and fixed-pack budget.", "No variable-power quadrature, cooling/reset model, or battery ageing."],
        ["OpenFOAM sphere", "Steady incompressible laminar verification chain.", "Not an aircraft rotor/propulsion solver; evidence remains unverified pending independent physics review."],
        ["GCI / slice metrics", "Numerical sensitivity and visualization eligibility.", "Not total uncertainty, an error bound, or flight certification."],
    ], [35 * mm, 61 * mm, 72 * mm]),
    Spacer(1, 4 * mm),
    callout("Outcome semantics. The project distinguishes feasible (checked point inside the declared restricted model), infeasible (checked bounded contradiction), unsupported (missing model/data/coverage), and unresolved (numerical or recomputation failure). A successful solver flag alone is never the equation-level acceptance criterion."),
    p("The active code also records source hashes, model fingerprints, map coverage, and retained native bytes. Those provenance equations are intentionally not mixed with physical equations: integrity metadata binds evidence but does not authenticate engineering approval."),
    PageBreak()]

    # Appendix source index
    story += [p("Appendix A - source index", "H1x"),
              p("The following files were inspected to assemble this handbook. Line numbers are intentionally approximate where a module evolves; the equation labels above point to the named functions and technical-guide sections."),
              table(["Path", "Key equation-bearing symbols or sections"], [
                  ["src/physimesh/drone/units.py", "LENGTH_TO_M, to_si_length, parse_foam_dimensions"],
                  ["src/physimesh/drone/frames.py", "rotation_matrix_zyx, transform_points, transform_axial_vectors, transform_tensor, RotorFrame.omega_vector"],
                  ["src/physimesh/drone/geometry.py", "topology area/volume, tolerance, repair and sampled surface distance"],
                  ["src/physimesh/solver/foam_ascii.py", "face_centres_and_areas polygon area and centroid"],
                  ["src/physimesh/drone/mass.py", "summarize total, CG, empty mass, parallel-axis inertia"],
                  ["src/physimesh/drone/atmosphere.py", "density, sound speed, viscosity, ISA, Re, Mach"],
                  ["src/physimesh/drone/performance.py", "map consistency, interpolation, convex_static_profile"],
                  ["src/physimesh/drone/trim.py", "constraints, recompute, solve_hover, infeasibility certificate"],
                  ["src/physimesh/drone/screening.py", "vertical capacity and case energy"],
                  ["src/physimesh/drone/mission.py", "electrical_power and size_battery fixed point"],
                  ["src/physimesh/drone/demo_screening.py", "S16 fixture proxy: A=8*pi*R^2; P(m)=(m*g0)^1.5/(sqrt(2*rho*A)*FM*eta_elec)+P_aux"],
                  ["src/physimesh/drone/mission_capacity.py", "joint constraints and sequence ledger"],
                  ["src/physimesh/postpro/loads3d.py", "surface loads, moment transfer, rotor/source loads"],
                  ["src/physimesh/postpro/statistics.py", "window statistics, drift, Richardson/GCI"],
                  ["src/physimesh/postpro/slice_eligibility.py", "coverage and normalized sensitivity"],
                  ["src/physimesh/postpro/results.py", "pressure conversion and Cd scale"],
                  ["docs/technical/mvp-code-and-physics-guide.md", "sections 4-12: project-level equation definitions and qualifiers"],
                  ["docs/technical/local-workbench-and-physics-guide.md", "active local hover, power, and chronological energy model"],
                  ["docs/validation/local-hover-and-energy.md", "fixture equations and retained model boundaries"],
              ], [65 * mm, 103 * mm]),
              Spacer(1, 5 * mm),
              callout("Version note. This handbook is a generated snapshot of the repository state at the time of creation. If equations change, regenerate it so the source index and qualification language remain aligned with the implementation."),
              Spacer(1, 8 * mm),
              p("End of handbook", "CoverKicker")]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return OUT


if __name__ == "__main__":
    print(build())
