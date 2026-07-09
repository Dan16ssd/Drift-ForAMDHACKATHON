# DRIFT — Pitch Video Script (~4 minutes)

**How to record:** screen-record the dashboard while `assets/demo.webm` plays
(or run the live replay: `python -m drift.streams.replay tests/fixtures/drift_stream.jsonl
--speed 300 --db sqlite:///demo.db` with the dashboard open) and narrate over it.
The demo video announces each act with a banner ("ACT 1 — GREEN", "ACT 2 — THE
WHISPER"...). **Sync your voice to those banners, not to the clock** — the acts
are event-driven, so timings below are approximate (demo.webm is 3:37; your
narration adds the intro and close on a title card / README shot).

Speak slower than feels natural. Bold lines are the ones to hit hardest.

---

## 0:00 – 0:30 — The hook (over a title card or the README logo)

> Last year, everyone shipped AI into production. This year, everyone is
> discovering the same ugly thing: **AI quality doesn't fail loudly — it
> drifts.** A retrieval index goes quietly stale. A model update changes
> behavior. And nobody notices until customers do — days later. Your dashboards
> logged all of it and told you nothing, because every single response still
> looked "fine."
>
> We built DRIFT: **the early-warning court for AI quality.**

## 0:30 – 1:00 — What DRIFT is (over ACT 1 — the green dashboard)

> DRIFT watches your AI's answers in production and scores every one —
> quality, hedging, truncation, retrieval hits, latency. What you're seeing is
> a healthy support bot. Boring on purpose.
>
> But here's what makes DRIFT different from every observability tool:
> **DRIFT never trusts its own suspicion.** Before anything alerts a human, the
> suspicion goes on trial.

## 1:00 – 1:50 — The court (over ACT 2 "the whisper" and the hearing / role cards)

> Degradation has started — planted retrieval decay. Notice: every individual
> response still passes any reasonable threshold. This is the failure mode that
> kills every threshold-based monitor.
>
> So DRIFT holds a hearing. A **Prosecutor** argues the decline is real — armed
> with regression the *code* computed, never the model. A **Defense** attacks
> with every innocent explanation: did traffic shift toward harder questions?
> One outlier user? Time of day? Scorer noise? Too few samples? And a **Judge**
> rules on a fixed standard of proof — p under 0.01, real effect size, no
> surviving confounder.
>
> **Our CI proves this works.** Three fixture streams run on every commit: the
> court must convict planted drift, must acquit pure noise — and must acquit
> the hard case: a traffic-mix shift where the aggregate trend is genuinely
> negative but nothing is actually broken. That acquittal is a machine-checked
> claim, public in our Actions tab. Every alert-fatigue horror story you've
> heard is that third case, unhandled.

## 1:50 – 2:30 — The countdown (over ACT 3 — the ALERT and countdown banner)

> The trend just survived cross-examination. Now — and this is the product —
> DRIFT doesn't hand you a red dot. It hands you a **countdown**:
>
> *"Quality crosses your floor in three to five hours at the current rate.
> Probable cause: retrieval decay."*
>
> Hours of warning, a cause to investigate, and a confidence range. Pure
> deterministic math — a language model **never** produces a number this
> system acts on. And when the fit is too weak to trust, DRIFT refuses to
> guess. A range is honest; a confident number from a bad fit is theater.

## 2:30 – 3:00 — The receipt (over ACT 4 — prophecy vs ground truth)

> Every forecaster demos well once. So DRIFT grades itself in public. Here's
> the predicted crossing window laid over what actually happened — **the real
> crossing landed inside the predicted window.** The alert's outcome is
> backfilled into the ledger, and the dashboard shows live alert precision.
> **No monitoring vendor shows you their false-alarm rate. We made it the
> headline metric.**

## 3:00 – 3:35 — Business value (over the precision tiles / competitive slide)

> Who pays for this? Anyone whose AI talks to customers. A support bot doing
> ten thousand conversations a day that quietly degrades for three days is
> thirty thousand bad customer experiences — refunds, escalations to human
> agents at dollars per ticket, and churn you can't attribute. DRIFT turns
> that into a **two-hour incident with a named cause.**
>
> LangSmith, Arize, Braintrust — excellent tools that tell you what your
> quality *was*. None of them forecast, and none of them cross-examine their
> own alarms. DRIFT ships both, and self-reports its precision — a metric no
> incumbent publishes.

## 3:35 – 4:10 — Why AMD + the close (over the README / go-live script)

> And this is why AMD matters — not as a sponsor logo, but as the economics.
> Scoring **every** response plus two extra reasoning passes per suspicion is
> exactly the workload per-token API pricing punishes. On one MI300X, 192
> gigabytes of HBM holds our sensing model and the judge **simultaneously**, at
> flat cost. Adversarial verification is the feature incumbents can't afford
> to build on API economics. **Our moat is partly a hardware-cost artifact —
> and we say so.**
>
> Everything you saw is live: real models, one-command onboarding onto any
> OpenAI-compatible endpoint — including a vLLM box on AMD Developer Cloud —
> and a CI tab that machine-checks the court's judgment on every commit.
>
> AI quality doesn't fail loudly. Now it doesn't have to fail silently either.
> **DRIFT — verdict first, alert second.**

---

## Cue sheet (one glance while recording)

| Clock | On screen | Beat |
|---|---|---|
| 0:00 | title card / logo | hook: "AI quality doesn't fail loudly — it drifts" |
| 0:30 | ACT 1 banner, green dashboard | what DRIFT is; "never trusts its own suspicion" |
| 1:00 | ACT 2 banner, hearing + role cards | Prosecutor / Defense / Judge; CI proves the hard acquittal |
| 1:50 | ACT 3 banner, ALERT + countdown | the countdown, cause, honest confidence range |
| 2:30 | ACT 4 banner, overlay chart | prophecy graded; precision as headline metric |
| 3:00 | precision tiles | business value; competitors describe the past |
| 3:35 | README / go_live_amd.sh | AMD economics; close line |

## Business-value crib notes (if judges ask)

- **Cost of silence:** support bot at 10k conv/day, 3-day unnoticed regression,
  even 10% degraded → thousands of bad interactions; human-agent escalation
  costs $3–8/ticket; churn is unattributable after the fact. (Illustrative
  numbers — say them as "order of magnitude," not claims.)
- **Alert fatigue:** monitoring that cries wolf gets muted; DRIFT's confounder
  checklist + self-scored precision is the anti-mute design.
- **Competitive line:** *"Incumbents log the past. DRIFT forecasts the future
  and cross-examines itself before it speaks."*
- **Why now:** every team that shipped LLM features in the last two years is
  hitting silent-regression pain for the first time — budget exists under
  "AI reliability."
- **AMD angle:** flat-cost resident models make per-response scoring + court
  overhead ~free at the margin; on per-token APIs the same design is a cost
  center that scales with traffic.
