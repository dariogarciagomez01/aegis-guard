# Milestone <N> Objective
<Imperative verb> <the Aegis Guard gateway / reverse proxy> <what this milestone delivers>. <The constraint it must respect: async, lightweight, zero-ops, OpenAI-compatible...>. <The goal or metric it is measured against.>

### 1. Core Dependencies and Technical Justification
<Code milestone:> To <goal> while <constraint>, we introduce **exactly <zero|one|two|...>** new production <dependency|dependencies> via Poetry:
<Tooling / infrastructure milestone (PLAN_06 style):> To <goal>, we introduce the following industry-standard tools:

1. **<package, tool, or native capability>**
   - *What it is:* <one-sentence definition>.
   - *Why we use it:* <why it fits Aegis Guard's async / lightweight / zero-ops goals, and which heavier alternative it avoids>.
2. **<...>**
   - *What it is:* <...>
   - *Why we use it:* <...>

### 2. Architectural Design and Pattern Justification
As we <scale / move into / evolve toward> <area>, we must prevent two <critical|systemic> <problems|flaws|traps>: **<Problem A>** (<short explanation>) and **<Problem B>** (<short explanation>).

#### The Problem We Avoid: <Problem A> and <Problem B>
<What goes wrong without this design, concretely, for this gateway. Optionally end with "We solve this by ...".>

- **Step 1: <Component Title>** (`<main file, e.g. src/proxy/limiter.py or terraform/ecs.tf>`)
  <What gets built there and why. Drop the parentheses when the step spans several files.>
- **Step 2: <Component Title>** (`<main file>`)
  <...>
- **Step 3: <Component Title>**
  <...>

### 3. Technical Execution Roadmap
The implementation sequence inside the repository will follow these exact steps:

1. **task <N>.1: <lowercase short title>**
   <Third-person verb (Provisions / Builds / Implements / Integrates / Configures / Develops / Writes / Executes) + the deliverable + the files involved.>
2. **task <N>.2: <lowercase short title>**
   <...>
3. **task <N>.3: <lowercase short title>**
   <...>
