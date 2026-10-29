---
name: new-milestone-plan
description: Draft the next Aegis Guard milestone plan as docs/working plans/PLAN_NN.md in the project's established format. Use when asked to plan, scope, or write up a new milestone.
argument-hint: "[milestone goal]"
---

# Draft a milestone plan

Each milestone has a plan in `docs/working plans/PLAN_NN.md`, numbered with two digits. The folder name contains a space, so quote it in shell commands. PLAN_01–PLAN_06 cover milestones 1–6. Milestone 7 (`feature/milestone-7`, merged as PR #31: the v1.0 docs pass) has no plan, and neither does the Terraform work on `feature/aws-terraform-deployment`.

Milestone goal from the user: $ARGUMENTS

## Steps

1. If no goal was given above, ask the user for it before drafting.
2. Pick the number. Check the highest `PLAN_NN.md` in `ls "docs/working plans"` and the milestone branches in `git branch -a --list '*milestone-*'`. Because milestone 7 exists without a plan, ask the user whether the new plan is PLAN_07 or PLAN_08 before writing.
3. Check what already exists for this goal: `git log --oneline origin/main..HEAD`, recent `feat(infra)`/`feat` commits, and `gh issue list --state all --search "task N."`. If work has already shipped, mark those tasks ` (DONE)` and reuse existing issue titles.
4. Read the reference plans and the code the milestone touches. PLAN_04 follows every rule below; PLAN_05/PLAN_06 are the most recent; PLAN_06 is the model for tooling or infrastructure milestones. File paths and component names in the plan must be real or clearly new.
5. Fill in [template.md](template.md) and write it to `docs/working plans/PLAN_NN.md`.
6. Show the user the objective and the roadmap. Don't create GitHub issues, branches or commits unless they ask. If they want issues, use the roadmap titles exactly: `task N.M: <title>`.

## Style (as in PLAN_02–PLAN_06)

- **Voice**: English, formal "we" voice, no emojis. LaTeX is fine for math (`$O(1)$`, `$$...$$`).
- **Objective**: line 1 is `# Milestone N Objective`. One paragraph follows, opening with an imperative verb (Evolve, Upgrade, Secure, Optimize, Finalize) and usually naming "Aegis Guard". It says what the milestone delivers, the constraint it respects, and the goal it is measured against.
- **Section headings**, exactly:
  - `### 1. Core Dependencies and Technical Justification`
  - `### 2. Architectural Design and Pattern Justification`
  - `### 3. Technical Execution Roadmap`
- **Section 1** opens with one sentence:
  - the number of new production dependencies via Poetry (PLAN_02–PLAN_05), e.g. "we introduce **exactly zero new production dependencies** via Poetry";
  - or, for a tooling or infrastructure milestone, "we introduce the following industry-standard tools:" (PLAN_06).

  Each item is a bold name (a package, a tool, or a native capability) with exactly two sub-bullets: `*What it is:*` and `*Why we use it:*`.
- **Section 2**:
  - An intro paragraph naming the problems to prevent.
  - `#### The Problem We Avoid: <A> and <B>` (PLAN_03/PLAN_04 name three), with a paragraph on what goes wrong without the design.
  - `- **Step N: <Component Title>**` bullets, each with its description on the next line. When a step maps to one main file, put it in parentheses: (`src/proxy/auth.py`) or (`terraform/ecs.tf`), as PLAN_02–PLAN_04 do.
- **Section 3**:
  - Starts with "The implementation sequence inside the repository will follow these exact steps:".
  - Then numbered `**task N.M: <lowercase short title>**` items, each with one or two sentences on the next line. The text starts with a third-person verb (Provisions, Builds, Implements, Integrates, Configures, Develops, Writes, Executes) and names the deliverable and the files.
- **(DONE) markers**: tasks that haven't shipped get none; ` (DONE)` goes at the end of a shipped task's description line.
- **Indentation**: sub-bullets 3 spaces, step and task descriptions 2–3 spaces, as in PLAN_04–PLAN_06.
