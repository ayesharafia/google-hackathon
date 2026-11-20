from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "physimesh-project-manual.pdf"
NAVY = colors.HexColor("#123047")
TEAL = colors.HexColor("#0E7490")
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#5B6770")
PALE = colors.HexColor("#F1F7F8")
BLUE = colors.HexColor("#EEF4FA")
LINE = colors.HexColor("#C7D5D9")

s = getSampleStyleSheet()
s.add(ParagraphStyle(name="Kicker", parent=s["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=TEAL, spaceAfter=7))
s.add(ParagraphStyle(name="TitleX", parent=s["Title"], fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=NAVY, spaceAfter=13))
s.add(ParagraphStyle(name="Sub", parent=s["Normal"], fontName="Helvetica", fontSize=11, leading=16, textColor=INK, spaceAfter=16))
s.add(ParagraphStyle(name="H1X", parent=s["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=NAVY, spaceBefore=2, spaceAfter=8))
s.add(ParagraphStyle(name="H2X", parent=s["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=TEAL, spaceBefore=8, spaceAfter=4))
s.add(ParagraphStyle(name="BodyX", parent=s["BodyText"], fontName="Helvetica", fontSize=9.2, leading=13.2, textColor=INK, spaceAfter=6))
s.add(ParagraphStyle(name="SmallX", parent=s["BodyText"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=MUTED, spaceAfter=4))
s.add(ParagraphStyle(name="CodeX", parent=s["Code"], fontName="Courier", fontSize=8.2, leading=11.2, textColor=NAVY, leftIndent=7, rightIndent=7))
s.add(ParagraphStyle(name="HeadCell", parent=s["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white))
s.add(ParagraphStyle(name="Cell", parent=s["Normal"], fontName="Helvetica", fontSize=7.8, leading=10.2, textColor=INK))


def p(t, style="BodyX"):
    return Paragraph(t, s[style])


def box(t, code=False):
    rendered = t.replace("\n", "<br/>") if code else t
    q = Table([[p(rendered, "CodeX" if code else "BodyX")]], colWidths=[168 * mm])
    q.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLUE if code else PALE),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return q


def tbl(headers, rows, widths):
    data = [[p(h, "HeadCell") for h in headers]] + [[p(str(x), "Cell") for x in r] for r in rows]
    q = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    q.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return q


def footer(canvas, doc):
    canvas.saveState(); w, _ = A4
    canvas.setStrokeColor(LINE); canvas.setLineWidth(0.5); canvas.line(18*mm, 14*mm, w-18*mm, 14*mm)
    canvas.setFont("Helvetica", 7.5); canvas.setFillColor(MUTED)
    canvas.drawString(18*mm, 9*mm, "PhysiMesh project manual | local workbench and evidence desk")
    canvas.drawRightString(w-18*mm, 9*mm, str(doc.page)); canvas.restoreState()


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=21*mm, leftMargin=21*mm, topMargin=18*mm, bottomMargin=19*mm,
                            title="PhysiMesh Project Manual", author="OpenAI Codex", subject="Operating manual for Drone-Project-main")
    st = []
    st += [Spacer(1, 17*mm), p("PHYSIMESH / DRONE PROJECT", "Kicker"), p("Project manual", "TitleX"),
           p("A practical guide to running the local design workbench, creating a bounded hover study, reading evidence, and sharing a temporary Cloudflare link.", "Sub"),
           box("This manual describes the repository state at the time of creation. The application is a local engineering workflow with synthetic fixtures and explicit readiness gates. It is not an aircraft approval, flight-control system, or production multi-user service."),
           Spacer(1, 8*mm), tbl(["Audience", "Start here"], [
               ["Presenter or reviewer", "Sections 2, 3, 5, and 6"],
               ["Local operator", "Sections 2-5 and troubleshooting"],
               ["Developer", "Sections 7 and 8 plus the equation handbook"],
           ], [42*mm, 126*mm]), Spacer(1, 8*mm), p("Repository checkpoint: 5 October 2026", "SmallX"), PageBreak()]

    st += [p("1. What this project does", "H1X"),
           p("The repository combines a local saved-design workbench with a controlled OpenFOAM sphere verification path. The workbench stores project drafts, freezes immutable revisions, evaluates a restricted static-hover model, retains study evidence, and exports JSON/PDF. The sphere path generates a pinned CFD case, reads native fields and force-object outputs, integrates loads independently, and publishes diagnostic plots."),
           tbl(["Capability", "Current behavior", "Do not infer"], [
               ["Design workbench", "Mass ledger, atmosphere, rotor declarations, cases, fixed pack, revisions.", "A complete form is not engineering approval."],
               ["Local hover study", "Bounded convex static allocation with source-bound rotor maps.", "No transient dynamics, installed interference, sag, thermal state, or structure."],
               ["Sphere CFD", "Steady incompressible laminar sphere at Re=100.", "It is not a rotorcraft or aircraft CFD model."],
               ["Evidence desk", "Native loads, reconciliation, drift, GCI, plots, hashes.", "A passing numerical gate is not validation."],
           ], [34*mm, 70*mm, 64*mm]), Spacer(1, 5*mm),
           box("The retained reference_impl directory is a comparison suite. The active runtime is under src/physimesh; the current local model and its limits are documented in docs/technical/local-workbench-and-physics-guide.md."), PageBreak()]

    st += [p("2. Install and launch locally", "H1X"), p("Use Python 3.11 or newer. The project declares its dependencies in pyproject.toml and requirements.lock."),
           p("PowerShell setup", "H2X"), box("cd C:\\path\\to\\Drone-Project-main\\Drone-Project-main\npython -m venv .venv\n.venv\\Scripts\\Activate.ps1\npython -m pip install -r requirements.lock\npython -m pip install -e .", True),
           p("If PowerShell blocks activation, run the commands from an already configured Python environment and set PYTHONPATH=src instead. The FastAPI upload route requires python-multipart."),
           p("Start the local workbench", "H2X"), box("$env:PYTHONPATH='src'\n$env:PHYSIMESH_DATA_ROOT='.backend/local-workbench'\n$env:PHYSIMESH_API_TOKEN='choose-a-local-token'\npython -m uvicorn physimesh.api.app:app_from_environment --factory --host 127.0.0.1 --port 8768", True),
           p("Open http://127.0.0.1:8768/web/workbench.html. Keep the terminal open while using the app. The data root preserves projects, revisions, maps, and results across restarts."),
           p("Smoke-check the server", "H2X"), box("Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8768/api/health", True),
           p("A healthy response has status=ok. workflow_ready can remain false when no pinned OpenFOAM backend is configured; that does not block the local hover workbench."), PageBreak()]

    st += [p("3. Share the running app with a temporary Cloudflare link", "H1X"),
           p("A Cloudflare Quick Tunnel publishes the local port without requiring a named tunnel. It is intended for short demonstrations only and has no uptime guarantee."),
           p("Start the tunnel in a second terminal", "H2X"), box("cloudflared tunnel --url http://127.0.0.1:8768", True),
           p("Cloudflare prints a URL like https://random-words.trycloudflare.com. Open that URL plus /web/workbench.html. The public page can load without the API token; project actions still require the token entered into the workbench."),
           box("Keep both the Uvicorn terminal and cloudflared terminal running. Stop either process with Ctrl+C to take the public link offline."),
           p("Security note", "H2X"), p("Use a throwaway local token for a temporary tunnel. Do not expose client data, credentials, or a persistent database through a Quick Tunnel. For production use, configure an authenticated named tunnel and a proper identity/access layer; the repository does not provide that deployment."),
           p("The current app exposes the workbench and evidence desk at /web/workbench.html and /web/results.html. API routes are under /api/drone; /api/health is a public status route."), PageBreak()]

    st += [p("4. Workbench workflow", "H1X"),
           tbl(["Step", "Action", "Expected result"], [
               ["1", "Enter the API token and select Connect.", "Connection status changes and project controls enable."],
               ["2", "Select Create labelled hover example.", "A clearly synthetic four-rotor design is loaded."],
               ["3", "Inspect the JSON and structured editors.", "Unknowns remain visible; mass, pack, atmosphere, cases, rotors, and model are explicit."],
               ["4", "Select Save draft.", "A new draft version is retained."],
               ["5", "Select Inspect saved mass and readiness.", "Mass, CG, pack consistency, and missing inputs are summarized."],
               ["6", "Select Freeze saved revision.", "The exact input snapshot becomes immutable and receives a revision hash."],
               ["7", "Select Evaluate frozen hover design.", "The bounded static-hover study runs synchronously."],
               ["8", "Inspect candidate checks and energy ledger.", "Outcome, limiting case or aggregate energy, residuals, and qualification are visible."],
               ["9", "Export retained JSON or study PDF.", "The exact retained record is downloaded."],
           ], [12*mm, 70*mm, 86*mm]), Spacer(1, 5*mm),
           p("Editing rules", "H2X"), p("Draft edits never rewrite an existing revision or result. A dirty draft cannot be frozen or evaluated. A frozen revision is a software snapshot, not aircraft approval. Candidate payload replaces installed payload ledger entries at one declared position; battery remains installed."),
           box("If a control is disabled, read the status text first. The usual causes are: no token connection, no open project, unsaved changes, an incomplete mass/pack declaration, or no frozen revision."), PageBreak()]

    st += [p("5. Inputs and model eligibility", "H1X"),
           p("The local pilot accepts only a bounded static-hover case in body frame x-forward/y-left/z-up and world frame ENU z-up. Attitude, velocity, acceleration, angular velocity, and angular acceleration must be zero."),
           tbl(["Input group", "Minimum declaration", "Typical failure"], [
               ["Mass ledger", "All six categories, mass in kg, body CG in m.", "Missing category or nonfinite mass/position."],
               ["Atmosphere", "Absolute pressure, temperature, source, map-compatible density.", "Density differs from retained map."],
               ["Rotor", "Centre, unit axis, sign, pitch, map reference, sustained RPM/power/current.", "Map coverage gap or non-unit axis."],
               ["Body loads", "Force and moment about origin, including explicit zero-load source.", "No provenance or unsupported state."],
               ["Fixed pack", "Voltage, current/power limits, usable energy, reserve convention.", "Declared usable energy disagrees with mass-derived budget."],
               ["Mission case", "Sourced hover case and positive duration.", "Nonzero motion or unsupported ground/mass declarations."],
           ], [32*mm, 74*mm, 62*mm]), Spacer(1, 5*mm),
           p("The model uses retained rotor curves only inside their declared RPM interval. It does not infer thrust or motor limits from CAD appearance. Missing or unsupported physics yields a reasoned refusal rather than an invented result."), PageBreak()]

    st += [p("6. Reading results and the evidence desk", "H1X"),
           p("A feasible local study means an independently recomputed point passed the declared static model. It is not a global aircraft maximum or operational payload allowance."),
           tbl(["Outcome", "Meaning"], [
               ["feasible", "Checked candidate satisfies force, moment, power, energy, and bound policies."],
               ["infeasible", "A checked bounded linear contradiction exists within the declared model."],
               ["unsupported", "Coverage, source, physics, duty, or domain prevents the claim."],
               ["unresolved", "Solver failure, timeout, invalid recomputation, or evidence disagreement."],
           ], [35*mm, 133*mm]), Spacer(1, 5*mm),
           p("Use the evidence desk at /web/results.html for retained sphere packages. Read the native force and moment reconciliation, final residuals, drift windows, effective refinement ratios, GCI qualification, field semantics, and refusal reasons. Plots are explanatory; native arrays and retained JSON remain authoritative."),
           p("The equation handbook", "H2X"), p("The companion PDF physimesh-equations-handbook.pdf catalogs the active equations and their source modules, including mass/CG, atmosphere, rotor maps, trim, energy, CFD, loads, GCI, and slice eligibility."),
           box("Do not report the synthetic hover example as client-aircraft performance. Every local record retains engineering_approval=pending and a qualification string stating its bounded scope."), PageBreak()]

    st += [p("7. Data, exports, and project layout", "H1X"),
           tbl(["Path", "Purpose"], [
               ["src/physimesh", "Active Python package: API, drone model, solver, post-processing, projects."],
               ["web", "Workbench, results desk, CSS, JavaScript, and vendored Three.js assets."],
               [".backend/local-workbench", "Runtime data root: SQLite, artifacts, revisions, studies, and reports."],
               ["output/pdf", "Generated PDFs, including this manual and the equation handbook."],
               ["docs/technical", "Current physics/model guide and local workbench guide."],
               ["docs/validation", "Fixture validation notes and model boundaries."],
               ["reference_impl", "Retained historical comparison implementation and tests."],
           ], [55*mm, 113*mm]), Spacer(1, 5*mm),
           p("Exports are source-bound and deterministic within their declared record. Hashes detect mutation and bind stored bytes; they do not authenticate human approval or prove physical accuracy."),
           p("To preserve a study, keep the full data root and its database together. Do not copy only a PDF and assume the underlying evidence traveled with it."), PageBreak()]

    st += [p("8. Troubleshooting and safe shutdown", "H1X"),
           tbl(["Symptom", "Likely cause", "Fix"], [
               ["App fails at import with multipart error", "python-multipart is missing.", "Install requirements.lock or python-multipart in the active environment."],
               ["Page loads but controls are disabled", "Token not connected or API unreachable.", "Use the exact token from PHYSIMESH_API_TOKEN and check /api/health."],
               ["Port 8768 is occupied", "Another server is using the port.", "Stop it or choose another port and update the tunnel URL."],
               ["Quick Tunnel cannot be created", "Network policy, DNS, or Cloudflare outage.", "Retry with network access; test the local URL independently."],
               ["Study refuses inputs", "Missing source, map coverage, pack consistency, or unsupported motion.", "Read the refusal reason and correct the declared input; do not bypass the gate."],
               ["Public link stopped", "Quick Tunnel or local server exited.", "Restart both terminals; a new temporary URL may be issued."],
           ], [48*mm, 57*mm, 63*mm]), Spacer(1, 6*mm),
           p("Safe shutdown", "H2X"), p("Press Ctrl+C in the cloudflared terminal, then Ctrl+C in the Uvicorn terminal. The local data root remains on disk. If a run is in progress, let the app finish or record the interrupted state before closing the terminal."),
           p("Developer entry points", "H2X"), p("Start with api/app.py and api/projects.py for routes, drone/trim.py and drone/mission_capacity.py for local allocation, projects/studies.py for evaluation and retention, postpro/results.py and loads3d.py for evidence, and the tests beside each module."),
           box("For changes that affect equations or qualification language, regenerate both the manual and the equation handbook, rerun the relevant tests, and visually inspect the exported PDFs."),
           Spacer(1, 8*mm), p("End of manual", "Kicker")]
    doc.build(st, onFirstPage=footer, onLaterPages=footer)
    return OUT


if __name__ == "__main__":
    print(build())
