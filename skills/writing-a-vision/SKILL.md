---
name: writing-a-vision
description: Use when creating or writing a vision.md / project vision document for a repo.
---

# Writing a Vision

## Overview

A `vision.md` tells an agent (and every contributor) what a project is for, who it serves, and how it fits the wider org. Its job is to settle **"which way should I build this?"** decisions — architecture, MVP-vs-gold-plate, what to over- or under-build, which issues are even worth doing.

A good vision prevents four failure modes. None of these are the model writing *bad* code — the code is fine, it's just wrong for the project:

- **Building the wrong thing** — solved a misunderstood problem, never saw the real goal.
- **Mis-sizing** — over-engineered something simple, or under-built something load-bearing.
- **Ignoring a hard constraint** — cost, scale, compliance it had no way of knowing existed.
- **Gold-plating** — features nobody asked for.

**Core principle: you facilitate and structure; the human owns the content.** You organize what the team said into a short draft. You never invent the vision.

This skill is collaborative and interactive, not autonomous. Run the phases with the user.

## The Flow

### Phase 0 — Orient
Briefly tell the user what a vision is for (settle direction, prevent the four failure modes), then hand them the brain-dump prompts below. Tell them *how* to do it well:

- Do it **with the team**, out loud, into speech-to-text. Let more than one person talk — if the first misses something, the next fills it in.
- Aim for ~10–15 minutes of word-vomit. Don't write polished prose.
- Point me at related repos or existing material if it helps ground the draft.
- **Describe everything about the project that matters — except literal code implementation.** The prompts above are a floor, not a limit. Anything that doesn't belong in the short vision is **not thrown away**: it goes into a companion notes file you own (see Phase 3).

Then wait for their dump. **Do not interrogate before they have brain-dumped.** Prompts first, dump second, targeted questions third.

### Phase 1 — Intake
Accept a messy, rambling, multi-voice, possibly contradictory transcript, plus any source docs they point you at. Don't make them clean it up first.

### Phase 2 — Structure & gap-check
Organize the dump into the light template (below). Then:

- For any dimension that's **thin or missing**, ask targeted follow-ups **one at a time**.
- **Don't invent.** If the team has no answer, leave a visible `> Open question: …` line in the draft. Never fabricate a plausible goal or constraint to fill a slot.
- **Capture overflow — never discard it.** Exact requirements, features, data sources, tech choices, schemas, file layout, component internals do **not** belong in a short vision, but they are real and valuable. Everything that doesn't make it into the draft goes into the companion notes file (Phase 3). This is the counterweight to gap-checking — it keeps the vision short without losing what the team said.
- **But keep the high-level *shape*.** The major pieces and how data flows between them ("scrape → adjudicate → store → present") stay in the vision under **Shape** — only the granular detail routes to notes. Don't strip the system's shape as if it were architecture detail; that miss is how a vision ends up not describing what kind of system it even is.
- **Surface direct contradictions** between voices as a question (light touch — you're a gap-checker, not a challenger).
- **Floor, not ceiling.** The template's dimensions are the reliable spine, not the limit. If the dump signals something load-bearing that none of the standard slots capture (a regulatory regime, a key partnership, a data-sensitivity stance, a hard architectural commitment), give it a home — its own short section or folded into the nearest one — provided it's genuinely decision-bearing.

### Phase 3 — Draft & hand off
**Write the draft to a file — use the Write tool to create `draft-vision.md` in the repo root.** Do NOT print the vision into the terminal/chat and call it done; "produce the draft" means write the file. The draft is named `draft-vision.md` (not `vision.md`) precisely because it is not yet owned — the human edits it and promotes it to `vision.md` when they approve.

Keep it **a page or two, directional prose, not exhaustive.** Write each paragraph as a single unwrapped line — do **not** insert manual/hard line breaks mid-paragraph; let the editor soft-wrap. (Same for `project-notes.md`.)

**Then write the overflow to `project-notes.md`** (Write tool, repo root). Everything from the intake that didn't make it into the draft goes here, **grouped thematically by the actual content** — let the themes emerge from what they said (e.g. for a data project: scraping & sources, data adjudication, visualization & UX, open questions); do not impose a fixed header set. This is the owner's raw material for later issues and architecture. It doesn't need to be polished, but nothing the team said should silently vanish. The partition is clean: if it isn't in the vision, it's in the notes.

After writing both files, **stop and hand ownership back:**

- **Give receipts.** Tell the user what went into the vision and what you moved to `project-notes.md`, so they can see nothing was dropped.
- Point them at the files and tell them to read every line and edit it — this is the step they never skip.
- The **project owner approves and owns** the final vision; promoting `draft-vision.md` → `vision.md` is their call, not yours.
- **Do not finalize, rename, or commit on their behalf** without explicit confirmation they've read it. The draft is a starting point; the human's edit is what makes it real.

## Coverage Checklist

Both the Phase 0 prompts and the Phase 2 gap-check run off this. Each dimension exists to prevent a specific failure.

| Dimension | Prompt sounds like | Prevents |
|---|---|---|
| **Problem & purpose** | Why does this project exist? What's broken without it? | Building the wrong thing |
| **Goals / success** | What does success look like? How will you know it worked? | Building the wrong thing |
| **Audience** | Who uses this, and who are they? | Building the wrong thing |
| **Org fit** | How does it fit the wider org / sit next to other systems? | Misaligned decisions |
| **Shape / major pieces** | At a high level, what are the big moving parts and how do they relate? (pieces + data flow only) | Misaligned architecture (monolith vs. pipeline) |
| **Guiding principles** | What rules must always hold — the "when in doubt, do X" commitments? | Decisions that quietly violate an unstated rule |
| **Hard constraints** | What can't move — cost, scale, compliance, deadlines, mandated tech? | Ignoring a constraint |
| **Scope posture** | What's MVP vs. gold-plate? What's the priority order? | Mis-sizing |
| **Non-goals** | What is this explicitly *not* trying to do? | Gold-plating |

## Output Template

Light headings matching the checklist. Short prose under each — not a bullet dump, not a box-filling exercise. Drop a heading that genuinely doesn't apply; add a project-specific heading when something load-bearing earns it.

```markdown
# Vision: <project>

## Problem & Purpose
## Goals
## Audience
## Org Fit
## Shape
## Guiding Principles
## Constraints
## Scope & Non-goals
<!-- + any project-specific section that is genuinely decision-bearing -->
```

**Companion file — `project-notes.md`:** thematic groups derived from the actual brain dump (use whatever themes the content forms, not a canned list). Holds everything that didn't make the vision. Owner's raw material — no length limit, no obligation to maintain it.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Writing the vision *for* them | Structure what they said; ask, don't invent. Gaps stay visible. |
| Letting it grow past two pages | Move requirements/architecture/feature detail to `project-notes.md`. |
| Discarding non-vision detail | It goes to `project-notes.md`, never the bin. |
| Treating the draft as done | It's a draft. Stop, hand it back, let the owner edit and approve. |
| Interrogating before the dump | Prompts → brain dump → *then* targeted gap questions. |
| Forcing everything into the standard slots | Floor not ceiling — give load-bearing specifics their own home. |
| Stripping the system's shape as "architecture" | High-level pieces + data flow stay in **Shape**; only granular detail routes to notes. |

## Red Flags — STOP

- You're about to write a goal/constraint the team never stated → that's inventing. Ask or leave an open question.
- The draft is past two pages → you're hoarding downstream detail. Move it to `project-notes.md`.
- You dropped something the team said without putting it in the vision *or* the notes → silent loss. Everything lands in one file or the other.
- You're finalizing/committing without the user confirming they read it → stop; ownership is theirs.
