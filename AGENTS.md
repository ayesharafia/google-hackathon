# PhysiCore Drone project instructions

The user replaced the old simulation-kit workflow with PhysiCore Autonomy
Portfolio v3 on 22 October 2026. Use the managed v3 bridge below. Historical
workflow snapshots under `.physicore/legacy/` are records, not active instructions.

## Project boundaries retained

- This checkout is the drone payload/mission project. Other company domains and
  sibling repositories are outside this installation scope.
- Retain all Git branches under the owner's latest instruction.
- Preserve source provenance, retained results, historical contracts and existing
  approved tolerances. No invented inputs, tuned benchmark coefficients or
  automatic physics acceptance. Existing qualified-review and flight-critical
  boundaries remain in force; AI review cannot grant human scientific approval.
- The owner's interface design law still applies to interface work. This workflow
  migration changes no UI and does not replace those design requirements.
- `plan.md` records application/release status; `ROADMAP.md` retains the previous
  physics evidence audit. Use `.physicore/ops/STATE.md` and `TASKS.json` to resume.
- Publish to GitHub only when the owner explicitly requests it, with scope
  recorded in `.physicore/ops/APPROVALS.md`. Publication does not authorize
  deployment, contact, spending or branch deletion.

<!-- PHYSICORE AUTONOMY V3 START -->
## PhysiCore autonomous project work
When given an actual task, perform that task using the relevant repo context. When the user says only "work", "continue", "build", or "keep going", follow `.physicore/ops/WORKFLOW.md`: inspect `.physicore/ops/STATE.md`, choose an eligible evidenced task using `python3 .physicore/tools/workflow.py next`, implement one meaningful safe slice, verify it, and persist the result. Treat project code and existing repository rules as authoritative. Never infer physical validity from passing code tests. Do not merge, deploy, spend money, message people, or make safety-critical changes without explicit authorization. Keep existing narrower safety and domain rules; use `.physicore/AGENT_POLICY.md` for extended operating guidance. If this kit conflicts with an existing policy, preserve the stricter boundary and report the conflict. Never claim to operate when no tool session is active.
<!-- PHYSICORE AUTONOMY V3 END -->
