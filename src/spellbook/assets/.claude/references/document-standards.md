# Document Standards

Reference for archive document quality and structure.

## Document Types

| Type | Purpose |
|------|---------|
| `decision` | A choice made with rationale |
| `insight` | A learning or realization |
| `code` | Implementation with context |
| `reference` | Factual information, specs |
| `research` | Investigation with findings and synthesis |
| `analysis` | Deep examination of a problem/system |
| `design` | Evolving design document (lives in knowledge/docs/, not knowledge/log/) |

## Complexity Assessment

| Source Content | Archive Length | What to Include |
|----------------|----------------|-----------------|
| Trivial exchange | Skip | Don't archive |
| Simple Q&A (1-2 exchanges) | 10-30 lines | Question + concise answer |
| Technical decision (3-8 exchanges) | 30-80 lines | Decision, rationale, alternatives, tradeoffs |
| Research session (10+ exchanges) | 80-200+ lines | Key findings, evidence, sources, synthesis |
| Code discussion | 50-150+ lines | Code examples, context, explanation, gotchas |
| Architecture design | 100-300+ lines | Design, components, rationale, constraints |
| Multi-topic session | Multiple docs | Split into atomic units, preserve depth in each |

**When content is rich, the archive SHOULD be rich.** Don't artificially compress substantive work.

## Quality Principles

- **Atomic**: One topic per doc
- **Self-contained**: Readable without conversation context
- **Distilled**: Remove noise and conversational artifacts, NOT depth
- **Tagged**: Entities extracted for retrieval

## Distillation vs Compression

**Remove:**
- Conversational back-and-forth ("User asked...", "Claude responded...")
- Redundant explanations
- Off-topic tangents

**Preserve:**
- Technical depth and complexity
- Code examples and snippets
- Detailed reasoning and alternatives considered
- Research findings with context
- Multi-step decision processes

## Document Structure

```markdown
---
type: decision|insight|code|reference|research|analysis
date: YYYY-MM-DD
entities:
  person: [names]
  project: [projects]
  tool: [tools]
  concept: [concepts]
---

# Title

[Distilled content]

Key points:
- ...
```

## Examples

### Bad Document (Transcript Dump)
```
User asked about X. Claude said Y. User clarified Z...
```

### Bad Document (Over-Condensed)
```
# Redis Caching Decision

Using Redis at gateway.
```

### Good Document (Appropriately Detailed)
```
# Caching Strategy Decision

Decided to use Redis at API gateway with 5-min TTL for GET endpoints.

## Rationale
- Reduces database load for repeated lookups (80% of traffic is reads)
- 5 minutes balances freshness vs performance
- Gateway placement intercepts before auth overhead

## Alternatives Considered
- Application-level caching: More granular but harder to maintain
- CDN caching: Cheaper but can't handle user-specific data

## Implementation Details
- Invalidation via Redis pub/sub on writes
- Cache keys include API version for safe schema migrations

## Scope
GET endpoints only. POST/PUT/DELETE bypass cache.
```
