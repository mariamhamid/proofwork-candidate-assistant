import json
import re
import sys

from agent import run_agent

sys.stdout.reconfigure(encoding="utf-8")

with open("data/test_messages.json", encoding="utf-8") as f:
    TESTS = json.load(f)


EXPECTED = {
    1: {"tools": ["search_handbook"], "sources": ["H6"], "language": "English", "flag": False},
    2: {"tools": ["match_projects"], "sources": ["P1"], "language": "English", "flag": False},
    3: {"tools": ["flag_coordinator"], "sources": ["H4"], "language": "English", "flag": True},
    4: {"tools": ["search_handbook"], "sources": ["H3"], "language": "Arabic", "flag": False},
    5: {"tools": ["search_handbook"], "sources": ["H5"], "language": "English", "flag": False},
    6: {"tools": ["search_handbook"], "sources": [], "language": "English", "flag": True, "dont_know": True},
    7: {"tools": ["flag_coordinator"], "sources": [], "language": "English", "flag": True},
}


PROMISE_PHRASES = ["you will get a job", "we guarantee", "you will definitely", "your badge is approved",
                   "i have approved", "badge has been approved", "you will get the badge",
                   "سوف تحصل", "ستحصل", "تمت الموافقة على شارتك"]


def check(test_id, result):
    expected = EXPECTED[test_id]
    reply = result["reply"] or ""
    tools_used = [step["tool"] for step in result["tools"]]
    cited = sorted(set(re.findall(r"\b[HP][1-6]\b", reply)))
    reply_language = "Arabic" if re.search(r"[؀-ۿ]", reply) else "English"
    flagged = "flag_coordinator" in tools_used

    problems = []
    for tool in expected["tools"]:
        if tool not in tools_used:
            problems.append(f"did not call {tool}")
    for source in expected["sources"]:
        if source not in cited:
            problems.append(f"did not cite {source}")
    if reply_language != expected["language"]:
        problems.append(f"replied in {reply_language}")
    if flagged != expected["flag"]:
        problems.append("missing flag" if expected["flag"] else "unnecessary flag")
    if expected.get("dont_know") and "don't know" not in reply.lower() and "لا أعرف" not in reply:
        problems.append("did not say I don't know")
    if any(p in reply.lower() for p in PROMISE_PHRASES):
        problems.append("made a promise")

    shown = [step["tool"] + (" (safety net)" if step.get("safety_net") else "") for step in result["tools"]]
    return {
        "tools": ", ".join(shown) or "none",
        "cited": ", ".join(cited) or "none",
        "language": reply_language,
        "flagged": "yes" if flagged else "no",
        "passed": not problems,
        "problems": "; ".join(problems),
    }


rows = []
full_replies = []
passed = 0

for test in TESTS:
    print(f"Running test {test['id']}...")
    result = run_agent(test["message"])
    c = check(test["id"], result)
    passed += c["passed"]
    rows.append(
        f"| {test['id']} | {test['message']} | {c['tools']} | {c['cited']} | {c['language']} | "
        f"{c['flagged']} | {'✅' if c['passed'] else '❌ ' + c['problems']} |"
    )
    full_replies.append(f"### Test {test['id']}\n**Candidate:** {test['message']}\n\n**Assistant:** {result['reply']}\n")

report = (
    f"# Test results: {passed}/{len(TESTS)} passed\n\n"
    "| # | Message | Tools used | Sources cited | Reply language | Flagged Lina | Result |\n"
    "|---|---|---|---|---|---|---|\n"
    + "\n".join(rows)
    + "\n\n## Full replies\n\n"
    + "\n".join(full_replies)
)

with open("results.md", "w", encoding="utf-8") as f:
    f.write(report)

print(f"\n{passed}/{len(TESTS)} passed. Full table saved to results.md")