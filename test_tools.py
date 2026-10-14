from tools import flag_coordinator, match_projects, search_handbook


def check(name, condition):
    print(("✅ PASS  " if condition else "❌ FAIL  ") + name)



r = match_projects(["Excel", "Python"], 6)
check("Excel + Python, 6h -> P1 first", r["matches"][0]["id"] == "P1")
check("Excel + Python, 6h -> P2 blocked by hours",
      any(p["id"] == "P2" for p in r.get("skill_fit_but_too_many_hours", [])))

r = match_projects(["Python", "LLM"], 5)
check("Python + LLM, 5h -> no match (P2 needs 8h)", r["matches"] == [])

r = match_projects(["Arabic", "English"], 4)
check("Arabic + English, 4h -> P4", r["matches"][0]["id"] == "P4")

r = match_projects(["Excel"], 2)
check("2 hours -> below minimum", r["matches"] == [] and "3 hours" in r["reason"])

r = match_projects(["Cooking"], 8)
check("Unknown skill -> no match", r["matches"] == [])


r = flag_coordinator("test message", "test")
check("Flag returns flagged=True", r["flagged"] is True)


r = search_handbook("Can I work on more than one project at the same time?")
check("Multiple projects -> H6 (Arabic entry)", r["found"] and r["results"][0]["id"] == "H6")

r = search_handbook("When will I get my badge?")
check("Badge question -> H3", r["found"] and r["results"][0]["id"] == "H3")

r = search_handbook("When will I get the badge after submitting the project?")
check("Arabic question translated to English -> H3", r["found"] and r["results"][0]["id"] == "H3")


r = search_handbook("متى سأحصل على الشارة بعد تسليم المشروع؟")
print("   Known limit, raw Arabic query returns:", [x["id"] for x in r["results"]] if r["found"] else "not found")


print("\nTop result and score for each question:")
for q in [
    "Can I work on more than one project at the same time?",
    "My organization hasn't replied in 2 weeks",
    "When will I get the badge after submitting the project?",
    "Will I definitely get a job?",
    "Do you pay candidates for their projects?",   
    "What is the weather today?",                  
]:
    r = search_handbook(q)
    top = f"{r['results'][0]['id']} {r['results'][0]['score']}" if r["found"] else "not found"
    print(f"   {top:10}  {q}")