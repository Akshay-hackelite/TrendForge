"""Excel-derived script templates: duration, timing map, hook, CTA, checklist."""

from __future__ import annotations

from typing import Any

# Long video templates (from "Long Video Templates" sheet)
LONG_TEMPLATES: dict[str, dict[str, str]] = {
    "Explainer": {
        "target_duration": "3:30-4:00",
        "timing_map": (
            "0-10s hook; 10-25s direct answer; 25-45s promise; "
            "45-120s explain; 120-200s examples; "
            "200-235s mistakes; 235-240s CTA"
        ),
        "opening_hook_formula": "Result/confusion + should I panic or ignore?",
        "structure": (
            "Hook -> direct answer -> 3 promises -> simple explanation -> "
            "examples -> what to do next -> mistakes -> CTA"
        ),
        "emotional_angle": "Relief first, stakes second",
        "retention_line": "At the end, I will tell you the mistake that quietly kills results.",
        "mid_video_line": (
            "Before you copy a tactic, understand this one thing: the symptom is not the cause."
        ),
        "ending_cta": "If this matches your situation, save it and apply the next step — don't guess.",
        "example_opener": (
            "Views dropped overnight? First, don't panic. But don't ignore it either. "
            "In 4 minutes, let's understand what it means and what to do next."
        ),
        "avoid": "Starting with a textbook definition",
    },
    "How-to": {
        "target_duration": "3:00-4:00",
        "timing_map": (
            "0-10s viewer question; 10-25s direct rule; 25-90s why; "
            "90-180s options; 180-220s mistake; 220-240s CTA"
        ),
        "opening_hook_formula": "Can I skip / change / shortcut this step?",
        "structure": (
            "Question -> direct rule -> why it works -> options -> "
            "how you decide -> mistake -> follow-up"
        ),
        "emotional_angle": "Fear of wasting time on the wrong method",
        "retention_line": (
            "The biggest mistake usually happens after the metric looks better."
        ),
        "mid_video_line": (
            "Do not copy someone else's playbook blindly; "
            "the reason behind their result may be different."
        ),
        "ending_cta": "Review the plan before you change anything.",
        "example_opener": (
            "CTR looks fine now? Great. But that does not automatically mean "
            "the video is working. It may mean only the thumbnail is working."
        ),
        "avoid": "Universal one-size advice",
    },
    "Report decode": {
        "target_duration": "3:00-3:45",
        "timing_map": (
            "0-8s exact value; 8-20s direct meaning; 20-45s promise; "
            "45-140s meaning; 140-200s what it can/cannot mean; 200-225s next step"
        ),
        "opening_hook_formula": "Exact metric + what now?",
        "structure": (
            "Value/term -> simple meaning -> what it does not mean -> "
            "when it matters -> next step"
        ),
        "emotional_angle": "Dashboard anxiety to clarity",
        "retention_line": "One number is useful, but it is not the whole story.",
        "mid_video_line": (
            "Now comes the important part: what you should not assume from this number."
        ),
        "ending_cta": "Bring the full screenshot and context before you overreact.",
        "example_opener": (
            "CTR 2.1%? This is not a random number. It tells how the packaging "
            "performed for people who saw the title and thumbnail."
        ),
        "avoid": "Overexplaining every dashboard range",
    },
    "Lifestyle": {
        "target_duration": "3:00-4:00",
        "timing_map": (
            "0-10s wrong habit; 10-25s correction; 25-60s why; "
            "60-180s 3 actions; 180-220s what not to do; 220-240s CTA"
        ),
        "opening_hook_formula": "Common wrong shortcut",
        "structure": (
            "Wrong practice -> why people do it -> 3 useful changes -> "
            "what won't help -> when to get help"
        ),
        "emotional_angle": "Frustration + realistic hope",
        "retention_line": (
            "The third point is where most people fail, even when they know what to do."
        ),
        "mid_video_line": (
            "A routine works only when it is specific and sustainable, not extreme."
        ),
        "ending_cta": "Save the routine; adjust if the results keep sliding.",
        "example_opener": (
            "A content routine does not mean posting 3 times a day. It means fixing "
            "the daily habits quietly killing consistency."
        ),
        "avoid": "Generic productivity tips",
    },
    "Comparison": {
        "target_duration": "3:00-4:00",
        "timing_map": (
            "0-10s confusion; 10-30s stakes; 30-120s difference; "
            "120-190s signals; 190-230s when to act"
        ),
        "opening_hook_formula": "Two options feel similar, but action differs",
        "structure": (
            "Confusion -> difference -> visible signs -> tests -> "
            "action difference -> danger signs"
        ),
        "emotional_angle": "Confusion + urgency",
        "retention_line": "Stay till the end for the signs where waiting is risky.",
        "mid_video_line": (
            "The goal is not picking a winner in theory; the goal is knowing which one fits now."
        ),
        "ending_cta": "If the high-stakes signs match, act this week — don't sit on it.",
        "example_opener": (
            "A weak hook and a weak thumbnail can feel the same in analytics. "
            "The dangerous mistake is fixing the wrong one first."
        ),
        "avoid": "Making the choice sound obvious without criteria",
    },
    "Story-led": {
        "target_duration": "3:00-4:00",
        "timing_map": (
            "0-15s viewer scenario; 15-60s what they assumed; "
            "60-150s key detail; 150-220s learning; 220-240s CTA"
        ),
        "opening_hook_formula": "They assumed X, but the real signal was Y",
        "structure": "Situation -> assumption -> key detail -> what changed -> lesson -> action",
        "emotional_angle": "Curiosity + practical learning",
        "retention_line": (
            "The important detail was not the headline metric; it was the small thing "
            "they ignored."
        ),
        "mid_video_line": (
            "This is why context and follow-up matter more than guessing from one number."
        ),
        "ending_cta": "If your situation is similar, apply the same check before you overhaul.",
        "example_opener": (
            "A creator thought the algorithm was broken. The real sign was "
            "average view duration collapsing after the first 20 seconds."
        ),
        "avoid": "Making it promotional",
    },
}

# Short video templates (from "Short Video Templates" sheet)
SHORT_TEMPLATES: dict[str, dict[str, str]] = {
    "Myth buster": {
        "target_duration": "25-45 sec",
        "timing_map": "0-5s myth hook; 5-15s half-truth; 15-30s risk; 30-45s better action + CTA",
        "core_formula": "Myth -> half-truth -> risk -> better action",
        "hook_style": "Start with contradiction",
        "ending_cta": "Share this with someone still repeating the myth.",
        "avoid": "Flat 'myth vs fact' tone",
        "example_script": (
            "Posting every day means you will grow? Not always. Often, it means you "
            "are shipping unfinished ideas. The mistake is doubling volume instead of "
            "fixing the first 10 seconds."
        ),
    },
    "FAQ": {
        "target_duration": "20-45 sec",
        "timing_map": "0-5s question; 5-12s answer; 12-30s reason; 30-45s action + CTA",
        "core_formula": "Question -> answer first -> reason -> action",
        "hook_style": "Use the exact audience question",
        "ending_cta": "Comment your next question.",
        "avoid": "Long background",
        "example_script": (
            "Is 2% CTR bad? It is usually not a panic number, but it is also not a "
            "'leave it' number. It is your early warning to fix packaging."
        ),
    },
    "When to act": {
        "target_duration": "30-60 sec",
        "timing_map": (
            "0-8s common symptom; 8-25s warning version; 25-50s 3 warning signs; "
            "50-60s action + CTA"
        ),
        "core_formula": "Common symptom -> warning version -> action",
        "hook_style": "Most X is common, but Y is not",
        "ending_cta": "Save this warning list.",
        "avoid": "Fear in every line",
        "example_script": (
            "A slow week is common. A slow week plus skip-rate jumping, comments dying, "
            "and returning viewers vanishing is not a normal dip. That needs a change."
        ),
    },
    "Common mistake": {
        "target_duration": "30-60 sec",
        "timing_map": (
            "0-8s mistake after improvement; 8-20s why it feels logical; "
            "20-40s consequence; 40-60s better action + CTA"
        ),
        "core_formula": "Mistake -> why it feels logical -> consequence -> better action",
        "hook_style": "This mistake happens after improvement",
        "ending_cta": "Save before you change the plan.",
        "avoid": "Scolding the audience",
        "example_script": (
            "Views recovered? Great. But this is where many creators stop tracking, "
            "stop testing thumbnails, and come back with a worse month. A good week "
            "means review the plan, not disappear."
        ),
    },
    "Quick term": {
        "target_duration": "30-45 sec",
        "timing_map": (
            "0-8s value/term; 8-20s meaning; 20-35s what not to assume; "
            "35-45s next step + CTA"
        ),
        "core_formula": "Value -> meaning -> what not to assume -> next step",
        "hook_style": "If your dashboard says...",
        "ending_cta": "Save before your next analytics review.",
        "avoid": "Explaining the entire strategy",
        "example_script": (
            "Average view duration 40% means people left around the midpoint. It does "
            "not tell you the full reason. Do not panic, but do not delay fixing the open."
        ),
    },
    "Single tip": {
        "target_duration": "30-60 sec",
        "timing_map": (
            "0-8s problem; 8-25s one tip; 25-45s who should skip; "
            "45-60s next step + CTA"
        ),
        "core_formula": "Problem -> one tip -> who should skip -> next step",
        "hook_style": "Try this only if...",
        "ending_cta": "Save, but stop if it makes the video worse.",
        "avoid": "Multiple tactics in one short",
        "example_script": (
            "For a weak first 10 seconds, try a visual payoff before the intro. "
            "But if the topic itself is unclear, don't decorate a confusing hook."
        ),
    },
    "Creator reacts": {
        "target_duration": "30-60 sec",
        "timing_map": (
            "0-8s claim; 8-20s true part; 20-40s wrong part; 40-60s safer advice + CTA"
        ),
        "core_formula": "Claim -> true part -> wrong part -> safer advice",
        "hook_style": "This sounds simple, but...",
        "ending_cta": "Follow for practical creator clarity.",
        "avoid": "Personal attacks",
        "example_script": (
            "This viral growth hack sounds easy. The true part: consistency matters. "
            "The wrong part: one hack cannot replace a clear hook, packaging, and follow-up."
        ),
    },
    "Seasonal alert": {
        "target_duration": "30-60 sec",
        "timing_map": (
            "0-8s season hook; 8-20s common confusion; 20-45s signs; "
            "45-60s action + CTA"
        ),
        "core_formula": "Season -> confusion -> sign -> action",
        "hook_style": "This season, don't ignore...",
        "ending_cta": "Save for the season.",
        "avoid": "Generic seasonal advice",
        "example_script": (
            "In festival weeks, every dip is not 'the algorithm'. But a drop with "
            "weaker packaging and no timely hook still needs a real test."
        ),
    },
}

# Alias map: content_formats names + legacy doctor CRM keys → template keys
_SHORT_ALIASES: dict[str, str] = {
    "story-led": "Story-led",
    "story-led lesson": "Story-led",
    "story-led lesson (short)": "Story-led",
    "when-to-worry": "When to act",
    "when-to-worry symptom": "When to act",
    "when to act": "When to act",
    "common mistake": "Common mistake",
    "patient mistake": "Common mistake",
    "exercise / home-care tip": "Single tip",
    "single exercise / home care tip": "Single tip",
    "single tip": "Single tip",
    "seasonal alert": "Seasonal alert",
    "seasonal health alert": "Seasonal alert",
    "report / diagnosis explainer": "Report decode",
    "diagnosis / report explanation": "Report decode",
    "report decode": "Report decode",
    "quick report term": "Quick term",
    "quick term": "Quick term",
    "doctor reacts": "Creator reacts",
    "creator reacts": "Creator reacts",
}

_LONG_ALIASES: dict[str, str] = {
    "disease explainer": "Explainer",
    "explainer": "Explainer",
    "treatment / medicine explainer": "How-to",
    "how-to": "How-to",
    "diagnosis / report explanation": "Report decode",
    "report decode": "Report decode",
    "lifestyle / diet / exercise": "Lifestyle",
    "lifestyle": "Lifestyle",
    "comparison explainer": "Comparison",
    "comparison": "Comparison",
    "story-led lesson": "Story-led",
    "story-led": "Story-led",
}

HOOK_BANK: list[dict[str, str]] = [
    {
        "element": "Report hook",
        "use_for": "Report decode",
        "stronger": "CTR 2.1%? This is not just a number. It tells a packaging story.",
    },
    {
        "element": "Panic vs ignore",
        "use_for": "Explainers",
        "stronger": "Views dropped? Don't panic. But don't ignore it either.",
    },
    {
        "element": "Improvement trap",
        "use_for": "How-to / mistake videos",
        "stronger": (
            "The graph looks better? Great. But this is exactly where many creators "
            "make the biggest mistake."
        ),
    },
    {
        "element": "Half-truth",
        "use_for": "Myth busters",
        "stronger": "The dangerous part of this myth is that it is half true.",
    },
    {
        "element": "Common vs serious",
        "use_for": "When to act",
        "stronger": (
            "Most slow weeks are common. A slow week with skip-rate exploding is a different story."
        ),
    },
    {
        "element": "Wrong shortcut",
        "use_for": "Lifestyle / tips",
        "stronger": (
            "Posting more sounds healthy. But a weak hook is not fixed by extra volume."
        ),
    },
    {
        "element": "Creator decision",
        "use_for": "How-to explainers",
        "stronger": (
            "The real question is not which tactic is best. It is which tactic "
            "fits your stage."
        ),
    },
    {
        "element": "Mini-story",
        "use_for": "Story-led lessons",
        "stronger": (
            "They thought it was just the algorithm. The real sign was not the view count, "
            "it was the drop-off."
        ),
    },
    {
        "element": "Viewer promise",
        "use_for": "Long intros",
        "stronger": (
            "In 4 minutes, you will know what this means, what not to assume, "
            "and what to do next."
        ),
    },
    {
        "element": "Section transition",
        "use_for": "Long retention",
        "stronger": "Now comes the part where most creators go wrong.",
    },
    {
        "element": "CTA",
        "use_for": "All videos",
        "stronger": "Save this before you overhaul the strategy or ignore the number.",
    },
]

SCRIPT_CHECKLIST: list[dict[str, str]] = [
    {
        "check": "One objective",
        "question": "Is the video answering one main audience doubt?",
        "long": "One clear question; all sections support it.",
        "short": "Only one question or one myth.",
        "priority": "High",
    },
    {
        "check": "First 5-10 seconds",
        "question": "Does it start with audience fear/confusion/value?",
        "long": "Hook before intro; no textbook start.",
        "short": "Direct hook immediately.",
        "priority": "High",
    },
    {
        "check": "Early answer",
        "question": "Does the viewer get a useful answer early?",
        "long": "Give direct answer in first 20-30 seconds.",
        "short": "Answer in first 5 seconds.",
        "priority": "High",
    },
    {
        "check": "4-minute discipline",
        "question": "Can this be completed without rushing?",
        "long": "Max 5-6 sections; cut extra background.",
        "short": "One idea only.",
        "priority": "High",
    },
    {
        "check": "Emotional angle",
        "question": "Is there a real reason to care?",
        "long": "Use panic, confusion, regret, relief, or consequence naturally.",
        "short": "One emotional hook only.",
        "priority": "Medium",
    },
    {
        "check": "Retention",
        "question": "Is there a reason to keep watching?",
        "long": "Add one open loop: mistake/red flag/what not to assume.",
        "short": "Use one reveal or contrast.",
        "priority": "High",
    },
    {
        "check": "Audience language",
        "question": "Would a new viewer understand this without niche jargon?",
        "long": "Explain technical words after using them.",
        "short": "Avoid complex words.",
        "priority": "High",
    },
    {
        "check": "Structure",
        "question": "Does the flow feel like a conversation?",
        "long": "Hook -> answer -> explain -> action.",
        "short": "Hook -> answer -> action.",
        "priority": "High",
    },
    {
        "check": "CTA",
        "question": "Is the next step clear and natural?",
        "long": "End with save/comment/follow based on topic.",
        "short": "One CTA only.",
        "priority": "Medium",
    },
    {
        "check": "Freshness",
        "question": "Does this sound different from last videos?",
        "long": "Rotate hook type and transition lines.",
        "short": "Rotate hook pattern.",
        "priority": "Medium",
    },
]


def _resolve_template_key(video_type: str, fmt: str) -> str | None:
    name = (video_type or "").strip()
    if not name:
        return None
    lower = name.lower()
    if fmt == "Short":
        aliased = _SHORT_ALIASES.get(lower)
        if aliased:
            return aliased
        for key in SHORT_TEMPLATES:
            if key.lower() == lower:
                return key
        return None
    aliased = _LONG_ALIASES.get(lower)
    if aliased:
        return aliased
    for key in LONG_TEMPLATES:
        if key.lower() == lower:
            return key
    if "report" in lower or "diagnosis" in lower or "metric" in lower:
        return "Report decode"
    return None


def template_for(video_type: str, fmt: str) -> dict[str, Any]:
    """Return the Excel template for a video type + Long/Short format."""
    key = _resolve_template_key(video_type, fmt)
    if fmt == "Short":
        base = SHORT_TEMPLATES.get(key or "") or SHORT_TEMPLATES["FAQ"]
        return {"format": "Short", "video_type": key or "FAQ", **base}
    base = LONG_TEMPLATES.get(key or "") or LONG_TEMPLATES["Explainer"]
    return {
        "format": "Long",
        "video_type": key or "Explainer",
        **base,
    }


def catalog_for_script_prompt() -> dict[str, Any]:
    return {
        "long_templates": LONG_TEMPLATES,
        "short_templates": SHORT_TEMPLATES,
        "hook_bank": HOOK_BANK,
        "checklist": SCRIPT_CHECKLIST,
        "rules": {
            "max_long_duration": "4 minutes",
            "core_approach": "Attention-first but host-like",
            "engagement_style": "Emotional, not dramatic",
            "long_structure_principle": (
                "Start with audience fear/confusion/a concrete number, give an early "
                "answer, then explain."
            ),
        },
    }
