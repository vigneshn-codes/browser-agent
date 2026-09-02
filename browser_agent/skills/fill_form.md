# Skill: fill_form

## Description
Fill out a web form reliably: locate fields by label, type values, and submit.

## When to use
The user asks to complete a signup, contact, search, or checkout form (excluding
payment card entry, which requires explicit confirmation).

## Procedure
1. `browser_snapshot` to inventory the form controls.
2. For each field the user gave a value for, match it by its label text and call
   `browser_type` with `replace: true`.
3. If a dropdown (`<select>`) is present, click it and choose the option by number.
4. Before submitting, snapshot once more and verify each field shows the intended
   value (sensitive fields will read `••••` — that is expected).
5. Click the submit control. Snapshot to confirm success or capture any error text.

## Guardrails
- Never invent values the user did not provide.
- If a field looks like a password or card number, do not fill it unless the user
  explicitly supplied it in this session, and confirm first.
