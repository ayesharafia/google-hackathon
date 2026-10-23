# Case Trim Evidence

Open a retained study in the workbench, then use **Case trim evidence** to select
its recorded mission case and evidence point:

- **At reported mission payload** reads that case's retained
  `headline_candidate_checks` entry.
- **Individual case candidate** reads the entry in `cases`. Its payload
  and rotor commands can differ from the reported mission-payload check.

Each point displays its recorded outcome, reason when present, scope, candidate
payload/mass, electrical power and case energy. The command table shows thrust
(N), shaft torque (Nm), signed RPM, electrical power (W) and DC input current (A)
in retained rotor order. Zero values and signs are preserved. Source scope is
available in a disclosure; the exact selected record and full result JSON remain
available.

The residual table displays the candidate's three body-axis force components
(N), moment components about CG (Nm) and the selected record's numerical
`tolerance` values. A retained torque-band moment interval, allowance and source
note are also displayed when present. These are recorded software evidence;
measurement accuracy, aircraft acceptance and a new pass/fail are not inferred.

## Binding and unavailable evidence

The sheet identifies its study and frozen revision. Missing candidates, commands,
quantities or policies remain unavailable. Missing shared checks never borrow an
individual case's commands. Duplicate case/check records are ambiguous and refuse
presentation at that point. Diagnostic candidates retain their unresolved or
unsupported outcome and an explicit diagnostic explanation. Historical result
warnings retain their existing scope.

**View this frozen case in 3D** uses the existing same-project/study/revision
navigation and restores the frozen view while preserving unsaved draft edits.
That viewer uses its existing shared-payload case context. Selecting an individual
candidate changes this evidence sheet; it does not redraw a different operating
point. A missing or nonunique referenced case disables navigation. Detached old
controls, changed workspace/study identities and pending actions cannot reopen
old evidence. Case/point selection survives restoration of the same frozen study.

Tables scroll horizontally to preserve complete numbers. The visible status
repeats the selected point and case when a native selector's display is narrow.
The feature projects existing data in the browser; it requires no API, model,
result schema, dependency or access-setting change. Refresh the workbench to load
its versioned JavaScript and CSS. No server restart or deployment was performed
for this increment; the earlier Review Pack API activation remains a separate
runtime step.
