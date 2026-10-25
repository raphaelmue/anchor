# Project Spec: Self-Hosted Goal-Oriented Relaxation & Self-Hypnosis Coach

> Name: **Anchor** (trademark / app-store check pending, see §16) Status: Draft v0.4 · 2026-10-25
>
> Changes vs v0.3:
> - **Goal Patterns + optional Domains:** goals map to a curated Goal Pattern (how the goal is reached); Domains are optional refinements of a Pattern. Code is goal-agnostic (§5).
> - **Orientation moved out of the Program:** Onboarding = Safety Notice → optional Orientation → Intake. The `orientation` Phase is removed (§4.2a).
> - **CBT-I removed from the app** (no sleep diary); it becomes a Referral item. `sleep` becomes the `sleep_onset` Domain. New Domain `waking_up`.
> - **Method availability** (`enabled` / `planned`); Cue Word moved to M4 so MVP Programs can run all Phases.
> - **Privacy:** local Scope Pre-Check and LLM Consent before a Goal Statement leaves the server.
> - **Content Snapshot** pinning per Program, with safety override; **Program Style Sheet** and **Suggestion Ledger** against LLM drift.
> - **Audio assembly rules** (pacing, no crossfade over speech, noise floor), **Segment Cache**, elastic pauses, **Stop & Ground** as FR, new **Non-Functional Requirements** (§4.10).
> - **Android first**, PWA default; iOS/Flutter only if iOS support is added.
>
> Changes vs v0.2: optional, skippable Orientation with Lessons and a Taster Session; just-in-time Method Lessons; name set to Anchor. Changes vs v0.1: goals generalized beyond sleep, Method catalog with evidence tiers, fading from guided to self-guided practice, TTS engine landscape (Appendix A), evidence references (Appendix B).

---

## 1. Vision

A self-hosted application that coaches a single Practitioner through a structured, progressive self-practice program toward **one personal goal** — e.g. *falling asleep more easily*, *waking up more easily*, *overcoming exam anxiety*, *reducing stress*.

On first use, the Practitioner acknowledges a Safety Notice and may take an optional, skippable **Orientation** (what relaxation and hypnosis are, common myths, realistic expectations, a short taster exercise). The Practitioner then states a goal in their own words. The system checks it locally, analyzes it, maps it to a curated **Goal Pattern** (optionally refined by a **Goal Domain**), selects **evidence-based Methods**, and generates a **Program** of weekly **Stages**. Each Stage delivers new **Sessions** — AI-generated audio rendered with **locally hosted TTS** — that build relaxation skills first, then introduce a personal **Cue Word**, then goal-specific **Suggestions**, if-then plans and **Mental Rehearsal**. Over time, practice moves from fully guided audio to self-guided application in real situations.

Scripts, Goal Analysis and Programs are authored by external LLMs (Anthropic, OpenAI) within strict guardrails. A smartphone client (Android first) plays Sessions offline and records practice.

### 1.1 Goals

- Gentle introduction for newcomers (Orientation), skippable for experienced Practitioners.
- Free-form goal input, always mapped to a curated, evidence-informed Goal Pattern; goal-specific refinement where a Domain exists.
- Goal-agnostic code: new goals are added as curated content (Pattern/Domain Blueprints), never as code branches.
- Structured progression instead of random audios; personalization by goal, experience, language, voice.
- Methods and suggestion strategies chosen by documented evidence, with the evidence visible to the Practitioner.
- A Cue Word built up over time and reusable across goals.
- Local TTS (CPU-only must work); pluggable TTS and LLM providers.
- Offline playback on the phone.

### 1.2 Non-goals

- Not a medical device; no diagnosis, no treatment of mental or physical disorders (§12).
- No CBT-I or other treatment programs; no sleep diary. Persistent sleep problems get a Referral (§5.4).
- No multiple simultaneously active goals.
- No real-time voice conversation, no on-device TTS.
- No alarm-clock function (a PWA cannot reliably start audio at a set time).
- No "learning while asleep" or subliminal content (§5.5).
- No multi-tenant SaaS.

---

## 2. Ubiquitous Language (Domain Glossary)

All code, APIs, database tables and UI copy MUST use these terms consistently.

### 2.1 Goals

| Term | Definition |
| --- | --- |
| **Practitioner** | The person doing the exercises. Exactly one per installation in v1. |
| **Goal Statement** | The goal in the Practitioner's own words, e.g. "Ich will morgens leichter aus dem Bett kommen." |
| **Goal Pattern** | A curated category describing *how* a goal is reached, with its own Methods, Suggestion Strategies, Phase lengths, Outcome Measures and exclusions (§5.2): `calm_in_situation`, `habit_consistency`, `performance_rehearsal`. Every in-scope goal maps to exactly one Pattern. |
| **Goal Domain** | Optional curated refinement of one Goal Pattern for a specific topic (§5.3), e.g. `sleep_onset`, `waking_up`, `performance_anxiety`. Adds or overrides Lessons, Strategies, Modules, Outcome Measures, exclusions and Evidence Tiers. |
| **Goal Analysis** | LLM-assisted step that turns a Goal Statement into a Goal Profile and runs the Scope Check. |
| **Goal Profile** | Structured result of Goal Analysis: Goal Pattern, optional Goal Domain, mapping confidence, target situation(s), triggers, desired state, optional **Target Date**, constraints, language. |
| **Target Date** | Optional date of a concrete event (exam, talk). Programs with a Target Date are time-boxed and include Pre-Event Sessions. |
| **Scope Pre-Check** | Local, rule-based check of the Goal Statement (per Supported Language) that runs **before** any LLM call. Matches lead directly to a Referral Notice. |
| **Scope Check** | Rule- and LLM-based check whether a goal is in scope, using Pattern and Domain exclusions. Out-of-scope goals get a **Referral Notice** instead of a Program (§5.4). |
| **LLM Consent** | The Practitioner's acknowledgement, shown before the Goal Statement is sent to an LLM Provider, naming the provider; the text can be edited first. |
| **Active Goal** | The single goal currently being trained. Others are archived. |
| **Supported Language** | A language for which Formulas, Lessons, Safety Notice and Grounding Audio exist. Programs are only generated in Supported Languages (v1: `de-DE`). |

### 2.2 Methods & Programs

| Term | Definition |
| --- | --- |
| **Method** | A technique family in the **Method Catalog** (§6): `pmr`, `autogenic_training`, `self_hypnosis`, `mindfulness_body_scan`, `paced_breathing`, `mental_rehearsal`, `implementation_intention`. |
| **Method Availability** | `enabled` or `planned`. Program generation uses only `enabled` Methods, so Blueprints are independent of milestones. |
| **Evidence Tier** | Rating of a Method for a Goal Pattern (optionally overridden per Domain): **A** guideline-level or consistent meta-analytic support, **B** meta-analytic support with notable limitations, **C** emerging/mixed, **X** not supported. |
| **Evidence Record** | Curated, versioned entry linking Method × Goal Pattern (or Domain override) to an Evidence Tier and references (Appendix B). Shown to the Practitioner as "Why this exercise?". |
| **Experience Level** | Prior experience with relaxation methods: `novice`, `intermediate`, `advanced`. Pre-set by the Onboarding question, determined during **Intake**, optionally refined by the taster self-rating. |
| **Onboarding** | First-use flow: Safety Notice → experience question → optional Orientation → Intake (§4.2a). |
| **Intake** | Goal Statement, Experience Level, age confirmation, preferences, schedule, Safety Screening. |
| **Orientation** | Optional part of Onboarding, **not part of any Program**: a short sequence of Lessons plus a Taster Session. Can be skipped entirely or per Lesson and reopened anytime from the **Basics Library**. |
| **Lesson** | A short, curated (not LLM-generated) text + audio explainer, 2–4 min. Kinds: `orientation_lesson` (general basics), `method_lesson` (introduces a Method just before its first Session), `topic_lesson` (Pattern/Domain-specific, e.g. sleep regularity). |
| **Basics Library** | Always-available collection of all Lessons, independent of Program progress. |
| **Myth Check** | Lesson element that contrasts a common belief with the evidence (e.g. "Hypnosis means losing control" → no). |
| **Program** | Personalized curriculum for one Goal Profile + Experience Level. Ordered **Phases** containing **Stages**. Generated once, stored, versioned, pinned to a **Content Snapshot**. |
| **Content Snapshot** | The exact versions of Pattern/Domain Blueprint, Method Catalog, Evidence Records, Formulas, Lessons and prompts a Program was generated with (§7.4). |
| **Program Style Sheet** | Personalization fixed at Program generation and passed to every later Script generation: form of address (`du`/`Sie`), tone, recurring imagery (e.g. safe place), Cue Word phrasing, situation vocabulary (§7.5). |
| **Suggestion Ledger** | Record of Suggestions already used in a Program, passed as context so new Suggestions stay consistent and do not contradict earlier ones. |
| **Phase** | Coarse program section with a learning purpose: `foundation` (relaxation skill), `anchoring` (Cue Word), `application` (goal-specific Suggestions, if-then plans, Rehearsal), `transfer` (self-guided use in real situations). |
| **Stage** | Unit of a Phase spanning one **Interval** (default 7 days). Defines objective, elements introduced, Session Types, recommended frequency. |
| **Progression Rule** | Decides advancement to the next Stage (logged Sessions, self-ratings, time). |
| **Guidance Level** | How much of a Session is spoken guidance vs. silent self-practice: `guided` → `semi_guided` → `self_guided`. Decreases over the Program (**Fading**). |
| **Fading** | Systematic reduction of Guidance Level so the Practitioner learns the technique as an independent skill (§7.3). |
| **Module** | A non-audio Program element: text lesson, checklist, planning exercise (e.g. if-then plan builder, preparation plan). |

### 2.3 Sessions & Content

| Term | Definition |
| --- | --- |
| **Session** | One concrete practice unit (usually audio). Has a **Session Type** and a **Session Context**. |
| **Session Context** | `stage` (belongs to a Stage of a Program), `orientation` (taster) or `library` (e.g. Grounding Audio). Only `stage` Sessions reference a Stage. |
| **Session Type** | `day` (ends with Emergence), `sleep` (no Emergence, fades out), `short` (2–5 min), `cue_recall` (1–3 min Cue Word use), `rehearsal` (Mental Rehearsal of target situation), `pre_event` (very short, for use right before the event), `taster` (≈3 min first experience, e.g. paced breathing, used in Orientation). Session Types are playback/structure rules and independent of Goal Pattern or Domain. |
| **Session Script** | Structured, machine-readable script: ordered list of **Segments** (§9). |
| **Segment** | Atomic element: `speech`, `pause`, `silent_practice`, `sound`, `ambience`, `marker`. |
| **Elastic Pause** | A `pause` or `silent_practice` Segment with an allowed range; the mixer adjusts it within the range to hit the target duration. |
| **Induction** | Opening part leading into relaxation. Method-specific (e.g. PMR tension-release cycle, AT Rest Formula). |
| **Deepening** | Part that intensifies relaxation (counting, imagery, repetition). |
| **Formula** | Short standardized phrase of a Method, e.g. AT "Mein rechter Arm ist ganz schwer". Canonical per language; never rewritten by the LLM. |
| **Suggestion** | A goal-related statement presented in the relaxed state, generated from a **Suggestion Strategy** and validated against **Suggestion Rules** (§8). |
| **Suggestion Strategy** | A documented pattern for constructing Suggestions: `calm_competence`, `ego_strengthening`, `mental_rehearsal`, `if_then_cue`, `reframe`, `sleep_permission`. |
| **Intention Formula** | AT "formelhafte Vorsatzbildung": short personal resolution sentence related to the goal. |
| **Mental Rehearsal** | Guided, multisensory imagination of successfully performing the target situation (process-focused, realistic). |
| **Implementation Intention** | If-then plan: "If situation X, then I do Y." Built in a Module and echoed in Sessions. |
| **Cue Word** | Practitioner-chosen word/phrase, conditioned to trigger relaxation. Owned by the Practitioner, reusable across goals. |
| **Cue Training** | Content pairing the Cue Word with the relaxed state, later testing recall in `cue_recall` Sessions. |
| **Emergence** | Structured return from relaxation ("Zurücknehmen"). Mandatory in `day`/`rehearsal`/`pre_event`, forbidden in `sleep`. |

### 2.4 Voice, Rendering, Tracking, Safety

| Term | Definition |
| --- | --- |
| **Voice** | A speaking voice offered by a TTS Engine (preset, designed or cloned). |
| **Voice Profile** | Voice + language + speaking rate + style instruction + measured **Speech Rate** (`chars_per_sec`). |
| **Speech Rate** | Measured characters per second of a Voice Profile, used to estimate Script duration before rendering. Calibrated on preview/first render. |
| **Reference Sample** | Audio used to clone a Voice. Requires **Consent**. |
| **TTS Engine** | Local speech synthesis model/runtime (Piper, Qwen3-TTS, Chatterbox, …). |
| **TTS Backend** | A server process exposing one or more TTS Engines over HTTP (e.g. Speaches, Qwen3-TTS C server, Voicebox). |
| **TTS Adapter** | Code in this project that talks to a TTS Backend through the common interface. |
| **LLM Provider / LLM Adapter** | External LLM service and the code talking to it. |
| **Render Job** | Async job turning a Session Script into an **Audio Asset**. |
| **Segment Cache** | Content-addressed store of rendered speech Segments, keyed by a hash of everything that affects the audio (§9.2). A cache hit skips the TTS Engine. |
| **Noise Floor** | Very quiet background bed (room tone or subtle ambience) under pauses, so silence never drops to digital zero. |
| **Audio Asset** | Final mixed audio file plus metadata. |
| **Practice Log** | Record of a practiced Session: completion, ratings, notes. Also carries one-tap Outcome Measures. |
| **Outcome Measure** | Pattern/Domain-specific one-tap self-report tracked over time (e.g. anxiety 0–10 before/after, waking ease 0–10, sleep quality 1–5, adherence). |
| **Safety Screening / Safety Notice / Referral Notice** | Intake questions on contraindications; general safety information, acknowledged before anything else; message recommending professional help for out-of-scope goals or flagged answers. |
| **Stop & Ground** | Always-available control that immediately stops playback and plays the curated **Grounding Audio** (soft chime + short grounding prompt). |

---

## 3. Users & Context

- Single Practitioner, non-expert in relaxation techniques.
- Server: home machine, **CPU-only**, Linux (assumed), ≥ 4 cores, ≥ 8 GB RAM recommended.
- Client: **Android smartphone first** (installed PWA), often used at bedtime, in the morning, or right before stressful events → dark UI, minimal interaction, offline.

---

## 4. Functional Requirements

### 4.1 Goal Definition

- **FR-1** Practitioner enters a Goal Statement in free text. Statements in a language that is not a Supported Language get a "not yet supported" notice.
- **FR-2** Goal Analysis produces a Goal Profile: Goal Pattern (always), Goal Domain (optional), mapping confidence, target situation(s), triggers, desired state, optional Target Date. Uncertain fields or low mapping confidence trigger at most 3 follow-up questions. One primary Pattern per goal; secondary levers appear only as Strategies.
- **FR-3** The Practitioner confirms or edits the Goal Profile before a Program is generated.
- **FR-4** Scope Check: goals matching Pattern/Domain exclusion criteria or the general exclusions (§5.4) produce a Referral Notice. Every goal not excluded maps to a Pattern; "no matching Domain" is never a reason for a Referral — the Program then uses the bare Pattern.
- **FR-5** Exactly one Active Goal. Switching archives the current Program; the Cue Word and acquired skills carry over (returning Practitioners can skip parts of the `foundation` Phase).
- **FR-45** Scope Pre-Check: before any LLM call, the Goal Statement is checked locally against rule lists per Supported Language (diagnoses, medication, minors, other people, excluded techniques). A match leads directly to a Referral Notice; nothing is sent to an LLM Provider.
- **FR-46** LLM Consent: before the Goal Statement is sent, the Practitioner sees which provider receives it and may edit the text. Without consent, no Goal Analysis runs.

### 4.2 Intake & Safety

- **FR-6** Intake captures Experience Level (self-assessment + short questions), age confirmation (18 or older, self-declared; otherwise Referral), preferred Session lengths, practice times, language, Safety Screening.
- **FR-7** Safety Screening answers can exclude Methods/Formulas (e.g. hypnosis, AT heart exercise) and trigger Safety or Referral Notices.

### 4.2a Onboarding & Orientation

- **FR-38** Onboarding order: (1) Safety Notice, (2) one question "Are you new to relaxation or hypnosis?", (3) optional Orientation, (4) Intake. Orientation default from the question: recommended for newcomers, offered but pre-skipped otherwise.
- **FR-39** Orientation is fully skippable: skip all, skip individual Lessons, or leave it at any point. Skipping never blocks Intake or the Program. All Lessons remain available in the Basics Library.
- **FR-40** Orientation content (curated, versioned, per Supported Language): (1) what relaxation is and how practice works; (2) what hypnosis and self-hypnosis are (focused attention, not sleep, no loss of control); (3) Myth Checks; (4) realistic expectations: effects build over weeks, responsiveness to hypnosis differs between people; (5) how the Program and the Cue Word work; (6) how evidence is rated ("Why this exercise?").
- **FR-41** Orientation ends with a `taster` Session (≈3 min, `paced_breathing`, Session Context `orientation`) and an optional short self-rating ("How did that feel?") that can refine the Experience Level.
- **FR-42** The **Safety Notice is never skippable**: it is the first Onboarding step and must be acknowledged before any Lesson, taster or Intake.
- **FR-43** Just-in-time `method_lesson`: before the first Session of a newly introduced Method, a short Lesson is offered — also skippable.
- **FR-44** Lessons are curated content, not LLM-generated; the LLM may only select and order them. Lessons exist as text and audio; audio is pre-rendered once per content version with a default Voice (no dependency on the Practitioner's Voice selection).

### 4.3 Program & Progression

- **FR-8** Program generation combines (a) the **Pattern Blueprint** and, if mapped, the **Domain Blueprint** (curated, §5, §7.1) with (b) the `enabled` Methods of the Method Catalog + Evidence Records and (c) LLM personalization. The LLM personalizes; it does not invent structure or Methods.
- **FR-9** Every Program follows the Phase order `foundation → anchoring → application → transfer`; Phase lengths come from the Pattern (optionally overridden by the Domain) and depend on Experience Level and Target Date. Methods are introduced from body-based to imagination-based (e.g. `pmr` → `autogenic_training` → `self_hypnosis`).
- **FR-10** Target-Date Programs are time-boxed backwards from the date; if time is short, the system compresses Phases and states the trade-off.
- **FR-11** Progression Rules (default: ≥ 5 logged Sessions per Interval and Interval elapsed); manual advance/repeat/step back allowed.
- **FR-12** Guidance Level decreases across Stages (Fading, §7.3).
- **FR-13** Programs may include Modules (e.g. if-then plan builder for `habit_consistency`, preparation plan for `performance_anxiety`).
- **FR-14** Each Method in a Program shows its Evidence Record ("Why this exercise?"), including tiers that are only B/C.
- **FR-47** A Program is pinned to its Content Snapshot. Content updates do not change a running Program; at Phase boundaries the Practitioner is offered a migration to the new content version (accept or keep).
- **FR-48** Safety override: changes to exclusion criteria, Scope rules, Safety Screening logic, Safety Notice or Grounding Audio apply immediately to all Programs, regardless of the pin. Affected not-yet-played Sessions are invalidated and regenerated.
- **FR-49** A Program Style Sheet is created at Program generation and used for every Script of that Program.
- **FR-50** A Suggestion Ledger is kept per Program and passed (summarized) to Script generation.

### 4.4 Sessions & Suggestions

- **FR-15** Per Stage, Session Scripts are generated for the Stage's Session Types.
- **FR-16** Scripts are structured JSON (§9), validated by schema and domain rules (FR-17) before rendering; invalid → retry with error feedback (max N) → visible failure.
- **FR-17** Validator rules: canonical Formulas unchanged; Emergence rules per Session Type; only introduced elements appear; Suggestions pass Suggestion Rules (§8.2); form of address matches the Program Style Sheet; estimated duration (speech chars ÷ Speech Rate + fixed pauses + Elastic Pause ranges) can reach the target within ±10 %; language consistent.
- **FR-18** Regenerate a Session (new variation, same Stage).

### 4.5 Cue Word

- **FR-19** Cue Word chosen at the start of the `anchoring` Phase (with suggestions), not on day one.
- **FR-20** Cue Training spans several Stages; later Stages include `cue_recall` and `pre_event` Sessions using the Cue Word.
- **FR-21** Cue Word persists across goals and is reused.

### 4.6 Voice & Language

- **FR-22** Select language and Voice from all enabled TTS Backends, filtered by language support and capabilities.
- **FR-23** Voice preview on demand; the preview also calibrates the Voice Profile's Speech Rate.
- **FR-24** Optional cloning of own voice from a Reference Sample (consent required, stored locally).
- **FR-25** Speaking rate / style instruction per Voice Profile where supported.

### 4.7 Rendering

- **FR-26** Async Render Jobs with status and progress.
- **FR-27** Pauses, silent practice, sounds, ambience and Noise Floor are inserted by the Audio Mixer, never by the TTS Engine.
- **FR-28** Loudness normalization, fades at joins, long fade-out for `sleep`; assembly follows the rules in §9.1.
- **FR-29** Pre-render the next Stage (e.g. nightly).
- **FR-30** Optional quality gate: transcribe rendered speech (local Whisper) and compare to script; re-render mismatching segments.
- **FR-51** Segment Cache: every rendered speech Segment is stored content-addressed (§9.2). Before synthesis, the cache is checked; a hit skips the TTS Engine. Formulas and other canonical text are thereby rendered once per Voice Profile.
- **FR-52** Elastic Pauses are fitted by the mixer so the final Audio Asset is within ±10 % of the target duration; the final duration is checked after rendering.
- **FR-53** On-demand renders (first Stage after Program generation, FR-18 regenerate) may use a fast fallback Voice (Piper) if the selected Voice would exceed the latency budget (NFR-2); the Practitioner sees which Voice was used and the asset is re-rendered with the selected Voice in the next nightly run.

### 4.8 Client & Tracking

- **FR-31** Show current Phase/Stage, Sessions, Modules, progress; download Audio Assets for offline use.
- **FR-32** Lock-screen playback, lock-screen controls, sleep timer.
- **FR-33** Quick Practice Log after a Session (1–2 taps), including the Pattern/Domain's one-tap Outcome Measures on their schedule (§5.2, §5.3). No separate diary.
- **FR-34** Quick-access "pre-event" button: plays the shortest `pre_event`/`cue_recall` Session immediately.
- **FR-35** Logs sync when online (append-only).
- **FR-54** Stop & Ground: visible during every Session (including `sleep`, visually calm), one tap stops playback immediately and plays the Grounding Audio. Grounding Audio is curated, pre-rendered and always available offline.
- **FR-55** After install, the client requests persistent storage so downloaded Audio Assets are not evicted under storage pressure; it shows a warning if persistence is denied.

### 4.9 Administration

- **FR-36** Configure TTS Backends, LLM Providers, API keys, default models.
- **FR-37** View Render Job history/errors; export/backup all data.

### 4.10 Non-Functional Requirements

Targets are initial values, to be confirmed by benchmarks on the target hardware (§15).

- **NFR-1 Throughput:** all Sessions of the next Stage are rendered with the selected Voice before the Stage's Interval starts (nightly pre-render, FR-29). Sizing assumption: a session's speech is ~40–60 % of its duration; Qwen3-TTS 0.6B int8 ≈ 3× real-time on 4 vCPU → ≈ 120 min of speech per 6 h night.
- **NFR-2 Latency:** first playable Session after Program generation ≤ 10 min; Session regenerate ≤ 10 min; Voice preview ≤ 15 s (FR-53 fallback allowed to meet these).
- **NFR-3 Hardware:** everything runs CPU-only on ≥ 4 cores, 8 GB RAM, with at most one heavy TTS Engine loaded at a time.
- **NFR-4 Offline:** downloaded Sessions, all Lessons and the Grounding Audio play without network; Practice Logs are stored locally and synced later.
- **NFR-5 Audio:** consistent integrated loudness across all assets (target set in M1 listening test, e.g. −18 LUFS), true peak ≤ −1 dBTP, single internal sample rate, no clicks at joins, no digital-zero silence.
- **NFR-6 Privacy:** only data listed in §12 leaves the server.
- **NFR-7 Reproducibility:** a Program can be regenerated from its Content Snapshot, Style Sheet and stored LLM outputs.

---

## 5. Goal Patterns & Domains

### 5.1 Principles

- Goal Patterns and Domains are **curated** (by humans, versioned in the repo as Blueprints): description, typical Goal Statements, Methods with Evidence Tiers, Suggestion Strategies, Phase lengths, Lessons, Modules, Outcome Measures, exclusion criteria.
- **Code is goal-agnostic.** It knows only Pattern, Domain, Method, Strategy, Session Type, Module and Lesson as concepts; no code branches on a specific Pattern or Domain. A new goal type is a new Blueprint, never a code change.
- Goal Analysis always maps to one Pattern; a Domain is used when one matches. New Patterns/Domains require a new Blueprint, not just a prompt.
- All Patterns share the `foundation` Phase (a relaxation Method), because relaxation reliably reduces arousal and is the base for Cue Word and Suggestions. Its length differs per Pattern.

### 5.2 Goal Pattern Catalog

| Pattern | What it is | Core Methods (tier) | Suggestion Strategies | Phase emphasis | Default Outcome Measure | MVP |
| --- | --- | --- | --- | --- | --- | --- |
| `calm_in_situation` | Lower arousal in a specific situation or in general | `pmr`/`autogenic_training` (B), `self_hypnosis` (B), `mindfulness_body_scan` (B), `paced_breathing` (C) | `calm_competence`, `ego_strengthening`, `reframe` | long `foundation`, Cue Word central | tension/anxiety 0–10 before/after | yes |
| `habit_consistency` | Do a behavior reliably (routine, getting up, studying) | `implementation_intention` (A/B), `mental_rehearsal` (B), relaxation as support (C) | `if_then_cue`, `ego_strengthening`, `calm_competence` | short `foundation`, long `application` | adherence (planned vs done) | yes |
| `performance_rehearsal` | Perform a skill well | `mental_rehearsal` (B) as complement to physical practice | `mental_rehearsal`, `calm_competence` | `rehearsal` Sessions dominate `application` | self-rated performance, adherence | later |

### 5.3 Domain Catalog (refinements)

| Domain | Pattern | Example goals | Additions / overrides | Outcome Measures | MVP |
| --- | --- | --- | --- | --- | --- |
| `stress` | `calm_in_situation` | general stress reduction, calmer workdays | Module: stressor log | stress 0–10 daily | yes |
| `performance_anxiety` | `calm_in_situation` | exam anxiety, presentation nerves | Strategies + `mental_rehearsal`, `if_then_cue`; Modules: preparation plan, if-then plans; Target Date supported | anxiety 0–10 before/after and on event day | yes |
| `sleep_onset` | `calm_in_situation` | fall asleep faster, stop rumination at bedtime | situation = bedtime; Strategy + `sleep_permission`; Session Type `sleep`; topic Lessons: sleep education, stimulus control; Referral item: CBT-I | sleep quality 1–5 (morning, one tap) | yes |
| `waking_up` | `habit_consistency` | wake up more easily, get out of bed without snoozing | topic Lessons: sleep regularity, sleep inertia & morning light; if-then plans for the alarm moment ("When the alarm rings, I put my feet on the floor and open the curtain"); exclusions: persistent daytime sleepiness, snoring with breathing pauses | waking ease 0–10 (morning, one tap), adherence | yes |
| `learning_habits` | `habit_consistency` | learn a language consistently, study focus | relaxation as pre-study routine; Module: study schedule; topic Lesson: sleep protection | adherence | later |
| `skill_rehearsal` | `performance_rehearsal` | sports or music performance, motor skills | practice log Module | self-rated performance, adherence | later |

Notes:

- `performance_anxiety`: interventions reduce self-reported anxiety much more than they improve measured performance → combine with preparation Modules; never promise better grades.
- `sleep_onset`: the app does **not** offer CBT-I, the first-line treatment for insomnia. Evidence Records show relaxation/hypnosis for sleep honestly as B/C. For persistent sleep problems, the Referral Notice points to CBT-I (in Germany available as prescribable DiGA).
- `waking_up`: little direct evidence for relaxation/hypnosis; the main levers are regular wake times, sufficient sleep, morning light and if-then plans. The app does not wake the Practitioner (no alarm function); morning Sessions are started manually.
- `learning_habits`: the app does **not** teach content via suggestion or during sleep. Targeted memory reactivation is lab research with replication problems → not a feature.
- Tiers are initial working values and must be confirmed by the research backlog (§15).

### 5.4 Out of Scope → Referral

The Scope Pre-Check (FR-45) and Scope Check (FR-4) MUST route these to a Referral Notice:

- Diagnosed or suspected mental disorders as the goal: depression, PTSD/trauma processing, panic disorder treatment, OCD, psychosis, bipolar disorder, dissociative disorders, eating disorders, addiction/substance use.
- Medical goals: pain treatment, symptoms of physical illness, medication changes.
- Persistent insomnia as a treatment goal → Referral to CBT-I.
- Persistent excessive daytime sleepiness, snoring with breathing pauses → Referral to a physician (possible sleep disorder).
- Smoking cessation and weight loss (sparse evidence for hypnosis; eating-disorder risk).
- Recovering memories, age regression, past-life content.
- Goals concerning other people (influencing someone else).
- Practitioners under 18.

Pattern- and Domain-specific exclusions are added on top (e.g. `performance_anxiety`: panic disorder as goal).

### 5.5 Explicitly Excluded Techniques

Subliminal messages, sleep-learning of content, "deep trance" claims, age regression, any technique implying loss of control.

---

## 6. Method Catalog

| Method | What it is | Audio? | Availability | Notes for implementation |
| --- | --- | --- | --- | --- |
| `pmr` | Progressive Muscle Relaxation: tense/release muscle groups, later shortened (16 → 7 → 4 groups → recall-only) | yes | enabled (M3) | Easiest entry for novices; concrete and body-based. Avoid tensing injured areas. |
| `autogenic_training` | AT basic level: Rest → Heaviness → Warmth → Breathing → Heart → Solar plexus → Forehead coolness; Intention Formulas | yes | enabled (M3) | Slower to learn (weeks). Canonical Formulas per language. Heart exercise excluded on cardiac screening. Intention Formulas carry goal-related content in the MVP `application` Phase. |
| `paced_breathing` | Slow, regular breathing with tone pacing | yes | enabled (M3) | `taster`, `pre_event` and `cue_recall` building block. Pacing by tones, not TTS. |
| `implementation_intention` | If-then planning | Module (+ echo in audio) | enabled (M4) | Strong, broad evidence for goal attainment; cheap. Core of `habit_consistency`. |
| `self_hypnosis` | Induction + Deepening + Suggestions + Emergence; taught as a self-directed skill | yes | planned (M8) | Best evidence when taught as an independent skill with practice → Fading is mandatory. Screening required. |
| `mental_rehearsal` | Multisensory imagination of performing the target situation calmly and competently | yes | planned (M8) | Process-focused, realistic, includes handling a difficulty; complements real practice. |
| `mindfulness_body_scan` | Attention to body/breath, non-judgmental awareness | yes | planned (later) | Good for rumination. |

CBT-I is not part of the Method Catalog; it is a Referral item (§5.4).

---

## 7. Program Composition

### 7.1 Blueprints (YAML, curated)

Pattern Blueprint:

```yaml
pattern: habit_consistency
version: 1
phases:
  foundation:   { methods: [pmr|autogenic_training], stages: {novice: 2, intermediate: 1, advanced: 1} }
  anchoring:    { cue_word: true, stages: 1 }
  application:  { methods: [implementation_intention, mental_rehearsal],
                  strategies: [if_then_cue, ego_strengthening, calm_competence], stages: 3 }
  transfer:     { session_types: [cue_recall, short], stages: 1 }
modules: [if_then_builder]
outcome_measures: [adherence]
target_date: { supported: false }
exclusions: []
```

Domain Blueprint (refinement):

```yaml
domain: waking_up
extends: habit_consistency
version: 1
lessons_add: [sleep_regularity, sleep_inertia_morning_light]
strategies_add: [calm_competence]
outcome_measures_add: [waking_ease_0_10]
exclusions_add: [persistent_daytime_sleepiness, snoring_breathing_pauses]
evidence_overrides: {}
```

```yaml
domain: performance_anxiety
extends: calm_in_situation
version: 1
phases:
  application:  { strategies_add: [mental_rehearsal, if_then_cue] }
  transfer:     { session_types: [pre_event, cue_recall] }
modules_add: [preparation_plan, if_then_builder]
outcome_measures: [anxiety_0_10_pre_post, event_day_anxiety]
target_date: { supported: true, min_days: 14, compression: [foundation, application] }
exclusions_add: [panic_disorder_as_goal, diagnosed_anxiety_disorder_treatment]
```

Rules: a Domain may add or override fields of its Pattern, but may not remove Pattern exclusions. Methods listed but not `enabled` are skipped during generation; if a Phase would become empty, the Blueprint must name an enabled alternative (e.g. AT Intention Formulas instead of `self_hypnosis`).

### 7.2 Generation Flow

1. Onboarding (Safety Notice → optional Orientation) and Intake.
2. Scope Pre-Check (local) → LLM Consent → Goal Analysis → Goal Profile (Pattern + optional Domain) → Scope Check.
3. Resolve Blueprints (Pattern + Domain), filter Methods by availability and Safety Screening exclusions, freeze the Content Snapshot.
4. LLM proposes Stage objectives, the Program Style Sheet and personalization (situations, imagery, wording) as JSON; validator checks structure against the resolved Blueprint.
5. Program stored and shown; Session Scripts generated per Stage on demand / ahead of time, with Style Sheet and Suggestion Ledger as context.

### 7.3 Fading

- `foundation`: `guided` — full spoken guidance.
- `anchoring`: `semi_guided` — guidance plus growing `silent_practice` Segments ("Continue on your own for 60 seconds…").
- `application`: mixed; Suggestions and if-then echoes spoken, relaxation increasingly self-induced via Cue Word.
- `transfer`: `self_guided` — short prompts only; Practitioner applies Cue Word / if-then plans in real situations; app logs real-world uses.

### 7.4 Versioning & Content Snapshot

- Every Blueprint, Method Catalog entry, Evidence Record, Formula, Lesson and prompt carries a version; a Program stores the full set as its Content Snapshot.
- Default: a running Program stays on its snapshot. At Phase boundaries, if newer content exists, the Practitioner is offered a migration with a short change summary (FR-47).
- Safety-relevant content (exclusions, Scope rules, Safety Screening logic, Safety Notice, Grounding Audio) is never pinned (FR-48).

### 7.5 Consistency over Time

- **Program Style Sheet** (FR-49): form of address (`du`/`Sie`), tone, recurring imagery, Cue Word phrasing, situation vocabulary. Frozen at generation; changed only by explicit Practitioner edit.
- **Suggestion Ledger** (FR-50): Suggestions used so far, summarized per Stage, passed as context.
- Model ID and prompt version are pinned per Program; changing them is a migration like a content update.

---

## 8. Suggestions

### 8.1 Construction

Suggestions are generated from Suggestion Strategies + Goal Profile + Program Style Sheet, e.g.:

- `calm_competence`: present-tense, realistic statements about staying calm and capable in the target situation.
- `mental_rehearsal`: walk through the situation step by step with senses, including a small difficulty handled calmly.
- `if_then_cue`: link a concrete situational cue to the Cue Word or a helpful action ("When the alarm rings, I breathe in deeply and put my feet on the floor.").
- `ego_strengthening`: general self-efficacy statements grounded in the Practitioner's real resources.
- `reframe`: perceive arousal as energy/readiness rather than danger.
- `sleep_permission`: reduce effort to sleep ("nothing to do, nothing to achieve right now").

### 8.2 Suggestion Rules (validator + system prompt)

- Positive or neutral framing; present tense or near future; realistic, process-focused.
- Permissive language ("you may notice…"), no commands implying loss of control.
- No guarantees or absolutes ("never again anxious", "you will pass").
- No medical/therapeutic claims; no content about diagnoses, medication, trauma.
- Only content related to the Active Goal; no suggestions about other people.
- Cue Word only paired with calm/relaxation/helpful action.
- Consistent with the Program Style Sheet; not contradicting the Suggestion Ledger.
- Respect Safety Screening exclusions.

---

## 9. Session Script Format

```json
{
  "schema_version": "1.2",
  "session_type": "rehearsal",
  "session_context": "stage",
  "language": "de-DE",
  "goal_pattern": "calm_in_situation",
  "goal_domain": "performance_anxiety",
  "method": "self_hypnosis",
  "guidance_level": "semi_guided",
  "target_duration_sec": 720,
  "stage_ref": "pa-application-02",
  "content_snapshot": "cs-2026-10-25-01",
  "segments": [
    { "type": "sound", "sound": "bell_soft" },
    { "type": "speech", "text": "Mach es dir bequem.", "style": "calm" },
    { "type": "speech", "formula": "at.rest.01" },
    { "type": "silent_practice", "seconds": 60, "elastic": [45, 90], "prompt": "Entspanne dich jetzt selbstständig mit deinem Ruhewort." },
    { "type": "speech", "text": "…", "strategy": "mental_rehearsal" },
    { "type": "pause", "seconds": 15, "elastic": [10, 25] },
    { "type": "speech", "text": "…", "role": "emergence" }
  ]
}
```

- `speech.text` ≤ ~300 characters per segment.
- `formula` references canonical Formula IDs (text resolved from the Content Snapshot); `strategy` references Suggestion Strategies; `role` marks induction/deepening/emergence for validation.
- `elastic` gives the allowed range for mixer fitting (FR-52); without it, the duration is fixed.
- `stage_ref` is omitted for `orientation`/`library` contexts.

### 9.1 Audio Assembly Rules

- **Trim** leading/trailing silence of every TTS clip to a fixed small margin before joining; engines pad clips inconsistently, which otherwise makes pause lengths drift.
- **Never crossfade over speech.** Fades only go into or out of silence/Noise Floor; word endings are never shortened.
- **No digital-zero silence.** Pauses and `silent_practice` carry the Noise Floor (subtle room tone or ambience bed).
- **Breath pacing by tones**, not by TTS (`paced_breathing`, `cue_recall`).
- **Pacing parameters per Session Type** (sentence gap, speaking rate factor, default pause lengths), e.g. slower and longer gaps for `sleep`, tighter for `pre_event`.
- **Per-segment loudness normalization** before the final loudness pass, so cached and fresh Segments match in level.
- `sleep`: long final fade-out, no Emergence, no end sound.
- M1 acceptance includes a **listening test** of a full Session against these rules.

### 9.2 Segment Cache

- Key = hash of (normalized text, text-normalization version, TTS Engine + model version, Voice, rate, style instruction, seed, sample rate).
- Formula Segments and other canonical text (Lesson audio, Grounding Audio, standard instructions) are hits after their first render.
- An engine/model upgrade changes the key, so old and new voices are never mixed silently.

---

## 10. Architecture

```
Smartphone (PWA, Android first) <--> API (FastAPI)
                     +- Goal Service      -> Scope Pre-Check (local rules)
                     |                    -> LLM Adapter -> Anthropic / OpenAI
                     +- Program Service   -> Pattern/Domain Blueprints, Method Catalog,
                     |                       Evidence Records, Lessons (repo, versioned)
                     |                    -> Content Snapshots, Style Sheets, Suggestion Ledger
                     +- Script Service    -> Validator
                     +- Render Worker     -> Segment Cache -> TTS Adapters -> TTS Backends (separate containers)
                     |                    -> Audio Mixer (ffmpeg), optional STT QA
                     +- Storage (SQLite + files)
```

### 10.1 Provider Abstractions

```python
class TTSAdapter(Protocol):
    id: str
    def capabilities(self) -> TTSCapabilities: ...
        # languages, cloning, voice_design, style_instructions, emotion_tags,
        # rate_control, sample_rate, max_chars, license_notes, engine_version
    def list_voices(self, language: str | None = None) -> list[Voice]: ...
    def synthesize(self, text: str, voice: Voice, *, language: str,
                   style: str | None = None, rate: float = 1.0,
                   seed: int | None = None) -> AudioChunk: ...
    def clone_voice(self, sample: ReferenceSample) -> Voice: ...   # optional
    def health(self) -> HealthStatus: ...

class STTAdapter(Protocol):          # quality gate
    def transcribe(self, audio: AudioChunk, language: str) -> str: ...

class LLMAdapter(Protocol):
    def generate_structured(self, system: str, user: str,
                            schema: type[BaseModel], *, model: str,
                            temperature: float = 0.7) -> BaseModel: ...
```

Concrete TTS Backends are an implementation detail — see Appendix A.

### 10.2 Domain Model (sketch)

```
Practitioner 1-0..1 CueWord
Practitioner 1-* Goal (one active) 1-1 GoalProfile -> GoalPattern, GoalDomain?
GoalDomain *-1 GoalPattern (extends)
Goal 1-* Program (versions) 1-1 ContentSnapshot, 1-1 ProgramStyleSheet, 1-1 SuggestionLedger
Program 1-* Phase 1-* Stage 1-* Session
Session (context: stage|orientation|library; stage nullable) 1-* SessionScript 1-* RenderJob 1-0..1 AudioAsset
Stage 1-* Module
Lesson (kind: orientation|method|topic, versioned) 1-0..1 AudioAsset
Session 1-* PracticeLog;  Goal 1-* OutcomeMeasurement
GoalPattern/GoalDomain 1-* EvidenceRecord -> Method (availability)
Practitioner 1-* VoiceProfile -> Voice -> TTSBackend
SegmentCacheEntry (content hash) -> audio file
```

---

## 11. Proposed Stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Language | Python 3.12 | |
| API | FastAPI + Pydantic v2 | Schemas reused for LLM structured output. |
| DB | SQLite (SQLModel/SQLAlchemy) | Single user. |
| Jobs | Huey (SQLite) or DB-backed worker | No Redis. |
| Content | YAML in repo: Pattern/Domain Blueprints, Method Catalog, Formulas, Evidence Records, Lessons, Scope Pre-Check rules, prompts | Versioned, reviewable. |
| Audio | ffmpeg (+ numpy/soundfile) | `loudnorm`, trimming, fades, Opus/MP3. |
| Segment Cache | Content-addressed files on disk + SQLite index | §9.2. |
| TTS | Separate containers behind OpenAI-compatible HTTP where possible | See Appendix A. |
| STT (QA) | faster-whisper via Speaches | Optional quality gate. |
| LLM | Anthropic & OpenAI via LiteLLM or SDKs | Structured JSON. |
| Client | PWA (SvelteKit or React + Vite, Workbox, Media Session API), Android first | Flutter only if iOS support is added. |
| Deploy | Docker Compose | `api`, `worker`, `tts-*`, `stt`. |
| Access | Tailscale | No public exposure. |

---

## 12. Safety, Ethics & Regulatory

- **Not a medical device.** Wellness/self-practice. No claims to treat conditions (in the EU, software with a medical purpose may fall under MDR). No CBT-I or other treatment programs.
- **Safety Notice** is the first Onboarding step and must be acknowledged; don't use while driving/operating machinery; seek professional help for persistent problems.
- **Screening:** psychosis/history of psychosis, dissociative disorders, severe personality disorders, active substance abuse, epilepsy → exclude `self_hypnosis` (and recommend professional guidance); cardiac conditions → exclude AT heart exercise; pregnancy/injuries → adapt PMR. Age under 18 → Referral.
- **Adverse effects** of hypnosis/relaxation are usually mild and short (headache, dizziness, anxiety) → Stop & Ground (FR-54) with curated, offline Grounding Audio, visible in every Session.
- **Out-of-scope goals** → Referral Notice (§5.4), first via the local Scope Pre-Check.
- **Safety content is never pinned**: changes apply to all Programs immediately (FR-48).
- **Voice cloning** only of own voice or with explicit consent; respect model and voice licenses.
- **Privacy:**
  - The Goal Statement leaves the server only after the local Scope Pre-Check and with LLM Consent (FR-45, FR-46); the Practitioner may edit it first.
  - Later LLM calls receive only the Goal Profile essentials, Program Style Sheet and Suggestion Ledger; no names.
  - Safety Screening answers, Practice Logs and Outcome Measures never leave the server.

---

## 13. Pitfalls & Risks

### Product / Domain

- **Goal sprawl:** free-form goals invite unsupported promises → curated Patterns/Domains, Scope Pre-Check + Scope Check, Referral.
- **Goal-specific code creeping in** (`if domain == …`) → all goal behavior in Blueprints; code review rule.
- **Over-claiming** (grades, cures, "better sleep") → Suggestion Rules, copy review, show Evidence Records honestly (B/C for sleep).
- **Passive listening only** reduces effect for self-hypnosis → Fading, `silent_practice`, real-world `transfer`.
- **Too fast progression** (common AT mistake) → conservative defaults, log-based Progression Rules.
- **Relaxation-only for sleep** underperforms CBT-I → honest framing in `sleep_onset`, Referral item for persistent insomnia.
- **Waking problems as symptom** (sleep deprivation, sleep disorder, depression) → `waking_up` exclusions and Referral.
- **Anxiety ↓ ≠ performance ↑** → pair with preparation Modules.
- **Cue Word** needs many pairings before recall tests.
- **Sleep Sessions** must not wake the user (no Emergence, no end bell).
- **Skipped Orientation** can leave wrong expectations (e.g. instant effects) → Safety Notice first, just-in-time Method Lessons, Basics Library always one tap away.
- **Lesson accuracy:** explanations about hypnosis must stay balanced (strong for anxiety/pain, weak for sleep) → curated content with references, no LLM-written Lessons.
- **Blueprint changes mid-Program** disrupt progress → Content Snapshot pinning, migration only at Phase boundaries, safety override.

### TTS / Audio

- **Pacing / "uncanny valley":** inconsistent TTS padding, clipped word endings, digital-zero silence, robotic breath pacing → assembly rules §9.1, listening test in M1.
- **CPU render time:** risk is latency at specific moments (first Stage, regenerate, preview), not nightly throughput → nightly pre-render, Segment Cache, Piper fallback for on-demand (FR-53), NFR-1/2.
- Long pauses only via mixer; default TTS speed too fast; autoregressive glitches (skips/repeats) → short segments, fixed seed, STT gate; voice drift → fixed seed/reference, Segment Cache; clicks/level jumps → fades into silence only, single sample rate, per-segment and final loudness normalization; pronunciation → text normalization, avoid digits.
- **Licenses:** engine licenses differ (e.g. Piper engine GPL-3.0 → keep it in its own container/process); each voice has its own license; some cloning models restrict impersonation or commercial use.

### LLM

- Invalid/drifting output → schema + domain validator + retry; Formula rewriting → canonical IDs; drift over weeks (tone, `du`/`Sie`, contradicting Suggestions, objective drift) → Program generated once, Program Style Sheet, Suggestion Ledger, Stage objectives as context, pinned model + prompt versions; language mixing → validator heuristic; provider changes → adapters.

### Client / Ops / Security

- **Android PWA:** request persistent storage (FR-55); test long screen-off playback (≥ 45 min `sleep` Session) with battery optimization enabled; bedtime UX (dark, no sounds).
- **No alarm function in a PWA** → morning Sessions started manually; native alarm integration only if a native client is ever built.
- **iOS** (only if added later): background audio and storage eviction limits → spike first, Flutter fallback.
- Append-only logs; VPN only; API keys outside repo with spending limits; some TTS backends have **no built-in auth** → never expose them, only internal Docker network.

---

## 14. MVP Scope (Milestones)

1. **M1 – Render pipeline:** hand-written Script JSON → Piper (via Speaches) → mixer with assembly rules (§9.1) and Elastic Pauses → MP3 (CLI). Segment Cache. Acceptance: listening test of a full Session.
2. **M2 – LLM scripts + validator** (one provider), Program Style Sheet as script context.
3. **M3 – Content base (de-DE):** Method Catalog (`pmr`, `autogenic_training`, `paced_breathing`) with availability; Pattern Blueprints `calm_in_situation`, `habit_consistency`; Domain Blueprints `stress`, `performance_anxiety`, `sleep_onset`, `waking_up`; Evidence Records; Orientation, method and topic Lessons (text + pre-rendered audio); `taster` Session; Safety Notice; Grounding Audio; Scope Pre-Check rules.
4. **M4 – Goal Analysis + Scope Pre-Check + LLM Consent + Scope Check + Program generation** with Content Snapshot and Suggestion Ledger; **Cue Word**, `cue_recall`, `pre_event`; `implementation_intention` with if-then plan builder Module.
5. **M5 – API + worker + SQLite**, nightly pre-render, on-demand fallback (FR-53).
6. **M6 – PWA client (Android):** Onboarding (Safety Notice → Orientation → Intake), Basics Library, current Stage, offline download with persistent storage, playback, Stop & Ground, Practice Log with one-tap Outcome Measures, pre-event button.
7. **M7 – Qwen3-TTS backend**, voice selection/preview with Speech Rate calibration, Voice Profiles, STT quality gate.
8. **M8 – `self_hypnosis`, `mental_rehearsal`, full Fading.**
9. **Later:** `performance_rehearsal` Pattern, `learning_habits` + `skill_rehearsal` Domains, `mindfulness_body_scan`, content migration UX polish, voice cloning, more Supported Languages, Ambience library, iOS support.

---

## 15. Research Backlog

- Confirm Evidence Tiers per Method × Pattern (and Domain overrides); add newer meta-analyses (2023–2026).
- `waking_up`: evidence on sleep inertia, regular wake times, morning light, if-then plans for morning routines; self-awakening research (Born et al. 1999) — research only, not a feature claim.
- Source canonical protocols: PMR (e.g. Bernstein & Borkovec format, shortening steps), AT basic level (German Formulas), body scan scripts, self-hypnosis teaching protocols, Mental Rehearsal guidelines (e.g. PETTLEP).
- Best practices for suggestion wording; evidence on permissive vs. direct suggestions.
- Orientation content: definition of hypnosis (APA Division 30, 2015), hypnotizability (stable trait, varies between people), common myths and their evidence, state vs. socio-cognitive theories — written in plain language with references.
- Referral content: current DiGA for insomnia (CBT-I) and how to describe them neutrally.
- Scope Pre-Check: rule lists (de-DE) for diagnoses, medication, minors, other people; false-positive rate on sample Goal Statements.
- Outcome Measures: keep to one-tap ratings; check whether any validated short item is usable (licensing!).
- MDR/regulatory boundary for wellness apps in the EU.
- TTS: German quality comparison (Piper vs Qwen3-TTS vs Chatterbox) for calm, slow speech; CPU render benchmarks on target hardware (validates NFR-1/2).
- Audio: loudness target for phone speaker/headphone listening at night; Noise Floor level and character.

## 16. Open Questions

- Name "Anchor": check trademarks (DPMA, EUIPO) and app stores; "Anchor" was previously used by Spotify's podcast platform → consider a distinguishing suffix (e.g. "Anchor – Ruhe & Fokus").
- Server hardware details (cores, RAM, x86/ARM)?
- Which LLM Provider first? Default models?
- Default Interval and Session lengths?
- Auth: static token vs passkey?
- A `wake` Session Type (short, activating, extended Emergence, played after getting up) for `waking_up`?
- Content migration UX: how much detail in the change summary at Phase boundaries?

Resolved in v0.4: Orientation Lessons are text + audio (FR-44); Android first (§3); Formula segments are rendered once and reused via the Segment Cache (FR-51); Ambience in MVP only as a subtle Noise Floor, full library later.

---

## Appendix A — TTS Engine & Backend Landscape (implementation detail, status Oct 2026)

### A.1 Engines (models)

| Engine | German | Cloning | Style/emotion | CPU suitability | License | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| **Piper** (OHF-Voice/piper1-gpl) | yes (e.g. `de_DE-thorsten`, CC0 voices available) | no | rate only | real-time even on Raspberry Pi 4 | engine GPL-3.0 (since 2025; archived original was MIT); voices individually licensed | Fast default/fallback; robotic-ish but clear. |
| **Kokoro-82M** | **no** (8 languages: EN, ES, FR, HI, IT, PT, JA, ZH) | no | preset voices | very fast | Apache-2.0 | Only for non-German languages. |
| **Qwen3-TTS** (0.6B / 1.7B) | yes (10 languages) | yes (from a few seconds), plus voice design from text | instructions, emotion tags | 0.6B int8 roughly 3× slower than real-time on 4 vCPU; ~3 GB RAM | Apache-2.0 | Best German quality candidate; pick a CPU runtime (below). |
| **Chatterbox Multilingual** (V3, 0.5B) | yes (23 languages) | yes (zero-shot) | emotion exaggeration | CPU supported, slower | MIT | All outputs carry Resemble's imperceptible PerTh watermark. |
| **XTTS-v2, F5-TTS, Parler** (via AllTalk) | varies | XTTS/F5 yes | varies | GPU-oriented | check model licenses individually | Only if a GPU becomes available. |

### A.2 Backends (servers exposing engines)

| Backend | Engines | API | Model management | CPU | Auth | Fit |
| --- | --- | --- | --- | --- | --- | --- |
| **Speaches** | Piper, Kokoro (TTS); faster-whisper, Parakeet (STT) | OpenAI-compatible `/v1/audio/speech`, `/v1/audio/transcriptions` | "Ollama for TTS/STT": `/v1/registry`, `POST /v1/models/{id}`, auto load/unload | yes (~2 GB RAM) | API key | **Primary** for Piper + STT quality gate. MIT. |
| **Qwen3-TTS C engine** (gabriele-mastrapasqua/qwen3-tts) | Qwen3-TTS 0.6B/1.7B | `--serve`: `/v1/tts`, streaming, OpenAI-compatible `/v1/audio/speech`; emotion/instruct/rate fields | CLI download; `.qvoice` profiles for cloned voices | CPU-default, int8 | none built-in | **Primary** for high-quality German. MIT. Alternative: LunaVox (C++/ONNX Runtime). |
| **Voicebox** (jamiepine) | Qwen3-TTS, Chatterbox, LuxTTS, TADA, Kokoro … | REST API, web UI, MCP | profiles, cloning, per-model unload | Docker headless possible; torch-based → heavy on CPU | **none** built-in (reverse proxy needed) | Optional adapter; good UI for creating cloned voice profiles. |
| **vocald** | Voicebox fork, preset voices | REST + MCP | small | torch-free, light | bearer key | No cloning; not needed if Speaches is used. |
| **AllTalk TTS v2** | XTTS, VITS, Piper, Parler, F5 | own API + OpenAI-compatible; capability flags per engine | engine/model switching via API | mostly GPU-oriented | — | Only with GPU. |
| **vocal-ai** | Kokoro, Piper, Qwen3-TTS (CUDA), Chatterbox … | OpenAI-compatible | Ollama-style pull/list | Qwen3 needs CUDA | — | SSPL license → avoid. |

### A.3 Recommendation

- Implement one **OpenAI-compatible TTS Adapter** (covers Speaches and the Qwen3-TTS C server) plus thin extensions for backend-specific features (voice list, cloning, instructions).
- Start: **Speaches (Piper German voices + Whisper)** → add **Qwen3-TTS C server** for quality and cloning → optional **Chatterbox** or **Voicebox** adapter later. Piper stays as the on-demand fallback (FR-53).
- Keep every backend in its own container on an internal network (license boundary + no exposed unauthenticated APIs).
- Adapters report engine/model version so the Segment Cache key changes on upgrades (§9.2).

---

## Appendix B — Evidence References (starting set)

| Topic | Source | Key finding (paraphrased) |
| --- | --- | --- |
| Insomnia guideline (US) | AASM 2021, J Clin Sleep Med 17(2):255–262 | Strong recommendation for multicomponent CBT-I; conditional for relaxation therapy, stimulus control, sleep restriction; against sleep hygiene alone. Basis for the CBT-I Referral item. |
| Insomnia guideline (DE) | S3-Leitlinie Insomnie bei Erwachsenen, Update 2025 (AWMF 063-003) | CBT-I (KVT-I) recommended as first-line treatment for all adults with insomnia. |
| CBT-I components | Furukawa et al. 2024, JAMA Psychiatry 81(4):357–365 (241 trials) | Cognitive restructuring, third-wave components, sleep restriction, stimulus control beneficial; relaxation not shown beneficial within CBT-I packages. |
| PMR & sleep | Meta-analysis 2026 (31 RCTs, 2,277 adults) | PMR improved sleep quality and reduced anxiety. |
| Mindfulness & sleep | Rusch et al. 2019 (18 RCTs) | Better than nonspecific controls; not better than specific evidence-based sleep treatments. |
| Hypnosis & insomnia | Lam et al. 2015, Complement Ther Med | Shorter sleep latency vs waitlist, not vs sham; low study quality (also for AT/guided imagery). |
| Hypnosis & sleep | Chamine et al. 2018, J Clin Sleep Med (24 studies) | Promising, more high-quality studies needed; adverse events rare. |
| Relaxation & anxiety | Manzoni et al. 2008, BMC Psychiatry (27 studies) | Medium effect (d ≈ 0.51 between-group) of PMR, AT, applied relaxation, meditation on anxiety. |
| Hypnosis & anxiety | Valentine et al. 2019, IJCEH (17 trials) | Mean effect ≈ 0.79; stronger when combined with other psychological interventions. |
| Self-hypnosis | Eason & Parris 2019, Psychol Consciousness (22 RCTs) | Medium-to-large effect; best when taught as a self-directed skill with practice; audio-only listening studies often showed no effect. |
| Hypnosis umbrella review | Rosendahl et al. 2024, Front Psychol (49 meta-analyses) | Largest effects for pain and medical procedures; sparse evidence for smoking cessation and obesity. |
| Test anxiety | Ergene 2003 (56 studies, ES 0.65); Thompson 1986 (195 studies) | Treatments reduce test anxiety; effect on actual performance much smaller. |
| Mindfulness & test anxiety | Frontiers Psychol 2024 meta-analysis | Moderate-to-large reduction of test anxiety. |
| Implementation intentions | Gollwitzer & Sheeran 2006 (94 tests, d = 0.65); Sheeran et al. 2024/25 (642 tests, d 0.27–0.66) | If-then plans improve goal attainment across behavioural, cognitive, affective outcomes. Core of `habit_consistency`. |
| Mental practice | Driskell et al. 1994, J Appl Psychol; 24-year follow-up replication | Mental practice improves performance; complements but doesn't replace physical practice. |
| Sleep & language learning | Schreiner & Rasch 2017; Wick & Rasch 2023 | Sleep supports vocabulary consolidation; cueing during sleep is lab research with replication issues. |
| Self-awakening | Born et al. 1999, Nature 397:29–30 | Anticipating an intended wake time was associated with a pre-waking rise in ACTH; small study, research backlog only. |
| Hypnosis adverse effects | Gruzelier 2000, Contemporary Hypnosis 17(4) | Mostly mild, short-lived; serious effects mainly in clinical/stage settings; screen vulnerable individuals. |
