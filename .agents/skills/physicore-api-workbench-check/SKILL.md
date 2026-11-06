---
name: physicore-api-workbench-check
description: Verify PhysiCore stateless model APIs and workbench panels after route, schema, authentication, hashing or UI changes. Check real application behavior and stale-result handling, not only isolated handlers or screenshots.
---

# API and workbench verification

Read the affected route, schema, kernel, `create_app`, authentication policy, workbench module and tests. Preserve any existing public-access mode; do not claim authentication is universal when configuration deliberately permits public access. Use `$physicore-numerical-regression` for changes to equations, units, assumptions, applicability or physical-result meaning. Numerical regression owns numerical evidence; `$scientific-review` owns scientific claims and review boundaries; this skill owns API transport and presentation integrity.

## API contract

- Mount the real `create_app` with actual middleware and exception handlers. An isolated route is useful for schema tests but cannot establish application authentication, CSRF, body-budget or error-sanitization behavior.
- Use strict bounded request types and explicit extra-field rules. Exercise nested extras, missing fields, wrong scalar/container types, booleans, oversized integers, nonfinite numbers, over-limit arrays and broken raw JSON.
- Check default local and hosted authentication, invalid tokens, cookie-origin/CSRF requirements, wrong verbs, nearby/prefix/suffix paths and trailing-slash behavior. Keep a new stateless allowance exact; it must not open adjacent mutation routes.
- Verify malformed requests receive the intended sanitized error without submitted private data or tracebacks. Test escaped lone Unicode surrogates through raw JSON and preserve valid non-BMP text. 
- Independently recompute submitted-input and result hashes using the repository's canonical serialization. Hashes bind recorded bytes, not authorship, truth or physical validity. Do not change canonical encoding or expected hashes merely to suppress failures.
- Check component refusals propagate with empty outputs/plan and non-authorizing evidence. Confirm no saved project/study or execution job was created by a stateless calculation.

## Workbench behavior

Exercise the actual panel against the real API, not only a mocked success response. Keep physical inputs blank unless the specification explicitly supplies an example; label synthetic fixtures clearly.

Check input edits, rapid double submission, delayed response bodies, context/account/project changes and late rejection. Stale results must not overwrite a newer request or appear in a different context. Render source/declaration text as text, not executable markup. Corrupted status, schema, echo, unit, output or hash-format responses must not produce a successful result.

Inspect actual rendered desktop and narrow-phone views, keyboard focus, labels, wrapping, result hashes and errors. State tested viewport sizes and what was actually inspected; one cropped screenshot is not complete mobile coverage. Recheck pixels after visual changes.

## Report

List the exact source revision, real-app tests versus isolated checks, tested modes, numerical example, screenshots and remaining limits. Keep response-shape verification separate from independent equation verification, backend execution and physical validation. 
