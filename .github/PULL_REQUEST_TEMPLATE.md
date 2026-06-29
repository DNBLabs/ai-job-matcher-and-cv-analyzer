## Summary
<!-- What changed and why — matches the commit message. -->

## Acceptance Criteria
<!-- Copy AC items from the issue. Tick each before merging.
     This replaces the post-merge "docs: tick off Task X" commit. -->
- [ ] 
- [ ] 

## Checklist
- [ ] Local CI green (lint · types · tests · build · audit)
- [ ] No diagnostic-only commits — debug/print statements from investigation removed or promoted to permanent structured logging
- [ ] No secrets in diff
- [ ] Scope clean — no out-of-task file changes
- [ ] PR CI green

### Infra / Deploy only — delete section if not applicable
- [ ] Prod-vs-local delta enumerated in Phase B (env vars, secret names, network rules, CORS, cloud-extension behaviour)
- [ ] Each delta item listed as an explicit AC with a Phase I BEHAVIORAL VERIFY block
