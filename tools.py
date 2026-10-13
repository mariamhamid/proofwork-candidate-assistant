"""
tools.py - the agent's 3 tools.

1. search_handbook   -> finds the handbook entry that answers a question (uses embeddings)
2. match_projects    -> picks projects with fixed Python rules (no AI involved)
3. flag_coordinator  -> alerts Lina (simulated: printed + saved to flags.log)
"""

import json
import os
from datetime import datetime

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()  # reads OPENAI_API_KEY from .env

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
MIN_SCORE = 0.30          # below this similarity, we say "not found" (tuned on test #6)
MIN_HOURS = 3             # handbook rule H2: minimum is 3 hours per week

# ---------- Load the data once ----------
with open("data/handbook.json", encoding="utf-8") as f:
    HANDBOOK = json.load(f)

with open("data/projects.json", encoding="utf-8") as f:
    PROJECTS = json.load(f)


# =====================================================
# Tool 1: search_handbook
# =====================================================
def embed(texts):
    """Turn a list of texts into vectors (lists of numbers that capture meaning)."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return np.array([item.embedding for item in response.data])


_handbook_vectors = None  # filled the first time we search, then reused


def search_handbook(query, top_k=3):  # 3, not 2: H5 ranked 3rd for "job after 3 projects" (test 5)
    """Return the handbook entries closest in meaning to the query, with their IDs."""
    global _handbook_vectors
    if _handbook_vectors is None:
        texts = [entry["title"] + ": " + entry["text"] for entry in HANDBOOK]
        _handbook_vectors = embed(texts)

    query_vector = embed([query])[0]

    # Cosine similarity: 1 = same meaning, 0 = unrelated
    scores = _handbook_vectors @ query_vector / (
        np.linalg.norm(_handbook_vectors, axis=1) * np.linalg.norm(query_vector)
    )

    best = np.argsort(scores)[::-1][:top_k]  # indexes of highest scores
    results = [
        {
            "id": HANDBOOK[i]["id"],
            "title": HANDBOOK[i]["title"],
            "text": HANDBOOK[i]["text"],
            "score": round(float(scores[i]), 3),
        }
        for i in best
        if scores[i] >= MIN_SCORE
    ]

    if not results:
        return {"found": False, "message": "No handbook entry answers this question."}
    return {"found": True, "results": results}


# =====================================================
# Tool 2: match_projects  (pure rules, no AI)
# =====================================================
# Different words people use -> the skill name used in projects.json
SKILL_SYNONYMS = {
    "spreadsheet": "excel",
    "spreadsheets": "excel",
    "llm": "llm apis",
    "llms": "llm apis",
    "llm api": "llm apis",
    "openai api": "llm apis",
    "user experience": "ux",
    "ui/ux": "ux",
    "translation": "arabic",
}


def normalize_skill(skill):
    skill = skill.strip().lower()
    return SKILL_SYNONYMS.get(skill, skill)


def match_projects(skills, hours_per_week):
    """Rule 1: minimum hours. Rule 2: hours filter. Rule 3: skill score. Rule 4: rank."""
    candidate_skills = {normalize_skill(s) for s in skills}

    # Rule 1: handbook minimum (H2)
    if hours_per_week < MIN_HOURS:
        return {
            "matches": [],
            "reason": f"Projects need at least {MIN_HOURS} hours per week (handbook H2).",
        }

    matches = []
    too_many_hours = []

    for project in PROJECTS:
        needed = set(project["skills"])
        have = needed & candidate_skills
        score = len(have) / len(needed)

        if score == 0:
            continue  # no shared skills, skip

        # Rule 2: hours are a hard limit
        if project["hours_per_week"] > hours_per_week:
            too_many_hours.append(
                {"id": project["id"], "title": project["title"],
                 "hours_per_week": project["hours_per_week"]}
            )
            continue

        matches.append(
            {
                "id": project["id"],
                "title": project["title"],
                "skills_needed": project["skills"],
                "skills_matched": sorted(have),
                "skills_missing": sorted(needed - have),
                "hours_per_week": project["hours_per_week"],
                "duration_weeks": project["duration_weeks"],
                "score": round(score, 2),
            }
        )

    # Rule 4: best skill match first; if tied, fewer hours first
    matches.sort(key=lambda m: (-m["score"], m["hours_per_week"]))

    result = {"matches": matches}
    if too_many_hours:
        result["skill_fit_but_too_many_hours"] = too_many_hours
    if not matches:
        result["reason"] = "No open project fits these skills within these hours."
    return result


# =====================================================
# Tool 3: flag_coordinator
# =====================================================
def flag_coordinator(message, reason):
    """Alert Lina. In the pilot this prints and logs; later it could email or Slack her."""
    alert = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "reason": reason,
        "message": message,
    }
    print(f"\n🚩 ALERT FOR LINA [{alert['reason']}]: {alert['message']}\n")
    with open("flags.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(alert, ensure_ascii=False) + "\n")
    return {"flagged": True, "note": "Lina has been alerted and replies within 48 hours (handbook H4)."}