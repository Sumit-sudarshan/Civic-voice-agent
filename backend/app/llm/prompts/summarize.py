"""
The AI briefing is a scannable, bullet-and-numbers dashboard summary, not a
prose narrative — a busy leader with 10 minutes needs to notice the
important things at a glance, not read paragraphs (this was direct,
specific feedback: the previous prose version, even when factually
grounded, "wasn't actionable because no one reads long paragraphs").

Hallucination risk is handled by doing almost ALL of the rendering in plain
Python from precomputed facts (see app/api/stats.py's build_report_facts) —
every number, bullet, category, and area name in the SNAPSHOT / NEEDS
ATTENTION / RECURRING PATTERNS sections is exact, computed directly from the
DB, never paraphrased by the model. The LLM's only job is a single 1-2
sentence VERDICT line — genuine judgment (is this a normal/worsening/quiet
period, what to prioritize) synthesized from the same facts, which is the
one part that actually benefits from reasoning rather than a fixed formula.
"""

_URGENCY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

VERDICT_SYSTEM_PROMPT = """You are the closing line of a bullet-point civic-issues briefing for a busy
local leader. You are given precomputed statistics — never raw complaint/suggestion text — so you
cannot invent facts.

Write EXACTLY ONE short sentence (at most 25 words) giving your honest verdict: is this period
normal, a worsening trend worth escalating, or a quiet period? Be direct. Do not repeat the numbers
already given to you — the leader has already seen them above your line. Just give the judgment call.
No markdown, no quotation marks, no em dashes or hyphens as punctuation, just the sentence.
"""


def _fmt_tally(items: dict, title_case: bool = True) -> str:
    if not items:
        return "none"
    parts = sorted(items.items(), key=lambda x: -x[1])
    return ", ".join(f"{str(k).title() if title_case else k} ({v})" for k, v in parts)


def build_verdict_user_prompt(facts: dict) -> str:
    """Minimal facts needed for the one-line verdict — deliberately not the
    full bullet data, since the verdict shouldn't restate the numbers."""
    kind = "complaints" if facts["submission_type"] == "complaint" else "suggestions"
    lines = [
        f"Period: {facts['range_label']}",
        f"Total {kind}: {facts['total_current']}"
        + (f" (previous period: {facts['total_previous']})" if facts["total_previous"] is not None else " (no previous-period data yet)"),
    ]
    if facts["submission_type"] == "complaint":
        crit_count = sum(1 for i in facts["critical_items"] if i["urgency"] == "critical")
        lines.append(f"Critical items: {crit_count}")
        lines.append(f"Same-spot hotspots: {len(facts['recurring'])}")
        lines.append(f"Categories recurring across multiple different areas (systemic signal): {len(facts['systemic_categories'])}")
    else:
        lines.append("(These are citizen suggestions/ideas, not urgent complaints — do not use words "
                      "like 'critical' or 'urgent'. Just say whether engagement looks healthy or quiet.)")
    lines.append("")
    lines.append("Write your one-sentence verdict now.")
    return "\n".join(lines)


_URGENCY_TONE_SWAPS = [
    ("critical issues", "notable suggestions"), ("critical items", "notable suggestions"),
    ("needs urgent attention", "is worth prioritizing"), ("need urgent attention", "are worth prioritizing"),
    ("needs attention", "is worth considering"), ("need attention", "are worth considering"),
    ("high-priority", "well-supported"), ("urgent", "notable"), ("critical", "notable"),
]


def _strip_dashes(text: str) -> str:
    """
    Deterministic safety net: the model isn't reliably told-not-to about em
    dashes either, so swap any it uses for a period + capital letter (or a
    comma, for a short trailing clause) rather than trust the prompt alone.
    """
    import re
    parts = re.split(r"\s*[–—]\s*", text)
    if len(parts) == 1:
        return parts[0]
    out = parts[0]
    for part in parts[1:]:
        if not part:
            continue
        joiner = ". " if len(part.split()) > 3 else ", "
        if joiner == ". ":
            part = part[0].upper() + part[1:]
        out += joiner + part
    return out


def _soften_suggestion_language(text: str) -> str:
    """
    Deterministic safety net: verified empirically (twice) that this model
    doesn't reliably avoid urgency-toned words for suggestions even when
    told to directly, so a substitution pass is more reliable than further
    prompt tuning for this specific, narrow tone issue.
    """
    import re
    result = text
    for bad, good in _URGENCY_TONE_SWAPS:
        result = re.sub(re.escape(bad), good, result, flags=re.IGNORECASE)
    return result


def render_report(facts: dict, verdict: str) -> str:
    """
    Renders the full scannable briefing: SNAPSHOT / NEEDS ATTENTION (or
    MOST-SUPPORTED for suggestions) / RECURRING PATTERNS are built directly
    from facts (zero LLM involvement — always exact), with the LLM's single
    verdict sentence appended at the end.

    Plain text only: no emoji, no em/en dashes (the frontend bolds any
    **word** span, which is the only markup this string relies on).
    """
    kind = facts["submission_type"]
    kind_label = "complaints" if kind == "complaint" else "suggestions"
    lines = []

    # ── SNAPSHOT ──
    lines.append(f"**SNAPSHOT ({facts['range_label']})**")
    delta_str = ""
    if facts["total_previous"] is not None:
        delta = facts["total_current"] - facts["total_previous"]
        delta_str = f" ({'+' if delta >= 0 else ''}{delta} vs previous period)"
    lines.append(f"• **{facts['total_current']} {kind_label}**{delta_str}")

    if kind == "complaint" and facts.get("urgency_tally"):
        parts = sorted(facts["urgency_tally"].items(), key=lambda x: _URGENCY_ORDER.get(x[0], 9))
        lines.append("• " + " · ".join(f"**{v}** {k}" for k, v in parts))

    if facts.get("category_tally"):
        top_cats = sorted(facts["category_tally"].items(), key=lambda x: -x[1])[:3]
        lines.append("• Top categories: " + ", ".join(f"**{k.title()} ({v})**" for k, v in top_cats))

    if facts.get("area_tally"):
        top_area = max(facts["area_tally"].items(), key=lambda x: x[1])
        lines.append(f"• Most affected area: **{top_area[0]}** ({top_area[1]} reports)")

    if facts.get("category_deltas"):
        delta_parts = [f"{str(k).title()} {'+' if v > 0 else ''}{v}" for k, v in facts["category_deltas"].items() if abs(v) >= 1]
        if delta_parts:
            lines.append("• Trend vs last period: " + ", ".join(delta_parts))

    # ── NEEDS ATTENTION (complaints) / MOST-SUPPORTED (suggestions) ──
    if kind == "complaint" and facts.get("critical_items"):
        lines.append("")
        lines.append("**NEEDS ATTENTION**")
        for item in facts["critical_items"]:
            lines.append(
                f"• **[{item['urgency'].upper()}]** {item['category'].title()} at {item['location']}: "
                f"{item['issue_summary']} ({item['report_count']} report(s), open {item['days_open']}d)"
            )
    elif kind == "suggestion" and facts.get("top_supported"):
        lines.append("")
        lines.append("**MOST-SUPPORTED SUGGESTIONS**")
        for s in facts["top_supported"]:
            lines.append(f"• {s['category'].title()} at {s['location']}: {s['issue_summary']} (**{s['report_count']} supporter(s)**)")

    # ── RECURRING PATTERNS ──
    if facts.get("recurring") or facts.get("systemic_categories"):
        lines.append("")
        lines.append("**RECURRING PATTERNS**")
        for r in facts.get("recurring", []):
            lines.append(f"• {r['category'].title()} reported **{r['report_count']}x** at the same spot ({r['location']}), unresolved hotspot")
        for s in facts.get("systemic_categories", []):
            lines.append(f"• {s['category'].title()} issues recurring across **{s['area_count']} different areas**, likely systemic, not isolated")

    # ── VERDICT (the only LLM-generated line) ──
    final_verdict = verdict.strip() if verdict else "Not enough data to draw a conclusion this period."
    final_verdict = _strip_dashes(final_verdict)
    if kind == "suggestion":
        final_verdict = _soften_suggestion_language(final_verdict)
    lines.append("")
    lines.append("**VERDICT**")
    lines.append(final_verdict)

    return "\n".join(lines)
