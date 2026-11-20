from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "physimesh-user-manual.pdf"
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
        ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
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
    canvas.setStrokeColor(LINE); canvas.line(18*mm, 14*mm, w-18*mm, 14*mm)
    canvas.setFont("Helvetica", 7.5); canvas.setFillColor(MUTED)
    canvas.drawString(18*mm, 9*mm, "PhysiMesh user manual | workbench guide")
    canvas.drawRightString(w-18*mm, 9*mm, str(doc.page)); canvas.restoreState()


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=21*mm, leftMargin=21*mm, topMargin=18*mm, bottomMargin=19*mm,
                            title="PhysiMesh User Manual", author="OpenAI Codex", subject="End-user guide for the PhysiMesh design workbench")
    st = []
    st += [Spacer(1, 17*mm), p("PHYSIMESH / DRONE PROJECT", "Kicker"), p("User manual", "TitleX"),
           p("How to use the local design workbench and inspect a bounded hover study.", "Sub"),
           box("This guide is for people using the browser workbench. It explains what to click, what each result means, and what information the application still needs. It does not replace engineering review or aircraft validation."),
           Spacer(1, 8*mm), tbl(["You want to...", "Read"], [
               ["Open the app", "1. Open the workbench"], ["Create a first example", "2. Create a design"],
               ["Enter real inputs", "3. Complete the design"], ["Run and interpret a study", "4. Evaluate and read results"],
               ["Fix a problem", "5. Messages and troubleshooting"],
           ], [55*mm, 113*mm]), Spacer(1, 8*mm), p("Revision: 5 October 2026", "SmallX"), PageBreak()]

    st += [p("1. Open the workbench", "H1X"),
           p("The workbench is a browser page backed by a local API. Do not open the HTML file directly from a file browser; the page needs the API server."),
           p("If the project is already running", "H2X"), box("http://127.0.0.1:8768/web/workbench.html"),
           p("If you were given a temporary Cloudflare address, open that address and add /web/workbench.html. A Quick Tunnel is temporary; it works only while the owner keeps the local server and tunnel running."),
           p("Connect", "H2X"),
           tbl(["Control", "What to do"], [
               ["Local API token", "Enter the token supplied by the person running the app."],
               ["Connect", "Select Connect once the token is entered."],
               ["Connection status", "Wait for the project list and buttons to become enabled."],
           ], [45*mm, 123*mm]),
           box("A token is required for project actions. Do not paste a token into a public message or share it with people who should not edit the workspace."), PageBreak()]

    st += [p("2. Create or open a design", "H1X"),
           p("For a guided demonstration, select Create labelled hover example. The example is synthetic and clearly labelled; it is useful for learning the workflow, not for making an aircraft claim."),
           p("For a real or reviewed design, use New project name and Create project, then open it from Saved projects."),
           tbl(["Area", "What it contains"], [
               ["Mass and payload placement", "Mass items in kg and their body-frame CG positions. Payload position is explicit."],
               ["Fixed battery pack", "Pack ledger items, voltage, current/power limits, usable energy, and reserve."],
               ["Required alternative cases", "Sourced operating cases, duration, body force, and body moment."],
               ["Study model and provenance", "Data scope, local pilot model version, payload domain, and auxiliary power."],
               ["Rotors and retained sources", "Rotor centres, unit axes, pitch, rotation sign, limits, and imported map references."],
               ["Ordered mission segments", "Optional constant-power segments for a shared fixed-pack energy check."],
           ], [52*mm, 116*mm]),
           p("Use the structured editors when possible. Design input JSON is available for inspection and advanced editing, but invalid or incomplete JSON will keep the structured editor closed."), PageBreak()]

    st += [p("3. Complete the design", "H1X"),
           p("The app intentionally keeps unknown values blank. Complete only values you can support with a source or an explicit engineering assumption."),
           p("Recommended order", "H2X"),
           tbl(["Order", "Action", "Why"], [
               ["1", "Complete every mass category, including explicit zero entries.", "The total mass and centre of gravity must be computable."],
               ["2", "Declare atmosphere pressure, temperature, and source.", "Rotor maps are density-specific."],
               ["3", "Add rotor centres, unit axes, signs, pitch, limits, and map references.", "The hover model cannot infer rotor behavior from geometry."],
               ["4", "Add sourced body force and moment for every required case.", "The balance equations need the non-rotor loads."],
               ["5", "Check fixed-pack consistency and reserve convention.", "Usable energy must agree with the ledger-derived budget."],
               ["6", "Set the model version and payload domain.", "The local pilot is bounded and refuses unsupported conditions."],
           ], [13*mm, 83*mm, 72*mm]),
           p("Select Inspect saved mass and readiness before freezing. Read the missing and error lists from top to bottom; the first missing source often explains later disabled controls."),
           box("The initial model accepts static hover only: zero attitude, velocity, acceleration, angular velocity, and angular acceleration. Nonzero motion belongs to a different model and is refused."), PageBreak()]

    st += [p("4. Save, freeze, and evaluate", "H1X"),
           tbl(["Button", "Effect", "What you should see"], [
               ["Save draft", "Stores the current editable version.", "A new draft version and saved-state message."],
               ["Freeze saved revision", "Creates an immutable input snapshot.", "A revision SHA-256 and engineering-approval-pending wording."],
               ["Evaluate frozen hover design", "Runs the bounded static-hover study.", "Outcome, payload lower bound, candidate checks, residuals, and energy evidence."],
               ["Export retained JSON", "Downloads the exact retained study record.", "A machine-readable source of truth."],
               ["Export study PDF", "Downloads a report for the retained study.", "Human-readable summary with evidence and qualification."],
           ], [43*mm, 67*mm, 58*mm]),
           p("Edits after a freeze do not rewrite the old revision. Save and freeze again to create a new revision for a changed design. The first accepted result remains associated with its frozen inputs."),
           p("What a feasible result means", "H2X"), p("It is a numerically checked point inside the declared restricted model. It is not a global maximum, a guaranteed payload allowance, installed-aircraft validation, or engineering approval."), PageBreak()]

    st += [p("5. Read the result", "H1X"),
           tbl(["Result area", "How to read it"], [
               ["Outcome", "feasible means the checked point passed; unsupported means the model/data coverage is insufficient; unresolved means the numerical or recomputation checks could not conclude."],
               ["Payload lower bound", "A checked payload value within the declared payload domain. Display rounding does not replace the exact retained value."],
               ["Limiting case", "The required case with the smallest individual capacity, unless shared sequence energy is the aggregate limit."],
               ["Candidate checks", "Mass, CG, rotor commands, RPM, thrust, electrical power, current, force residual, moment residual, and required energy."],
               ["Active constraints", "The declared limit(s) that bind the checked allocation, such as pack power/current or case energy."],
               ["Qualification", "The scope statement you must preserve when quoting the result."],
           ], [43*mm, 125*mm]),
           p("If the result is unsupported or unresolved, use the listed reason as the next action. Do not replace a missing source with a guessed number just to make the button succeed."),
           p("Evidence desk", "H2X"), p("Open /web/results.html to inspect retained CFD packages: native force integration, reconciliation, window drift, grid sensitivity, field semantics, plots, and refusal messages."), PageBreak()]

    st += [p("6. Messages and troubleshooting", "H1X"),
           tbl(["Message or symptom", "What it usually means", "What to do"], [
               ["Connect is disabled", "The page has not loaded the API controls.", "Check the server URL and /api/health, then reload."],
               ["No project open", "You connected but have not created or opened a project.", "Create the labelled example or select a saved project."],
               ["Mass incomplete", "A category, mass, or CG is missing/invalid.", "Add explicit values or a zero item and inspect again."],
               ["Pack inconsistent", "Declared usable energy disagrees with the ledger-derived pack budget.", "Check pack item names, Wh/kg, usable fraction, reserve, and declared joules."],
               ["Map coverage refusal", "The requested density, pitch, inflow, RPM, or duty is outside the retained source.", "Use a matching source or change the declared case only with support."],
               ["Study button disabled", "No frozen revision, dirty edits, or readiness failure.", "Save, inspect, freeze, and read the readiness report."],
               ["Public link stopped", "The temporary Cloudflare tunnel or local server ended.", "Restart both; a new temporary URL may be issued."],
           ], [48*mm, 58*mm, 62*mm]),
           p("Safe shutdown", "H2X"), p("Close the public link by stopping the Cloudflare terminal. Stop the local server with Ctrl+C. Your local data root remains on disk; keep it with the database if you need to preserve the study."), PageBreak()]

    st += [p("7. Important boundaries", "H1X"),
           p("This application is deliberately conservative. It separates a completed software workflow from a validated aircraft conclusion."),
           tbl(["The app can do", "The app does not claim"], [
               ["Retain declared inputs, revisions, source hashes, and study results.", "That the input sources are accurate or approved."],
               ["Check a bounded static-hover allocation and fixed-pack energy ledger.", "Transient maneuver feasibility, battery sag, thermal limits, or structural margins."],
               ["Integrate and reconcile retained native CFD sphere outputs.", "Aircraft rotor/propulsion prediction from the sphere case."],
               ["Explain missing inputs and refuse unsupported scope.", "A refusal can be bypassed safely by guessing a value."],
           ], [84*mm, 84*mm]), Spacer(1, 5*mm),
           box("Before using a result for an aircraft decision, provide real geometry and roles, a complete mass/CG ledger, measured or reviewed rotor performance, applicable body loads, mission conditions, battery limits, uncertainty treatment, validation evidence, and named engineering approval."),
           p("For equations and implementation details, use the companion PDF physimesh-equations-handbook.pdf. For deployment and operations, use the project manual physimesh-project-manual.pdf."),
           Spacer(1, 8*mm), p("End of user manual", "Kicker")]
    doc.build(st, onFirstPage=footer, onLaterPages=footer)
    return OUT


if __name__ == "__main__":
    print(build())
