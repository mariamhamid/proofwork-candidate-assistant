"""
agent.py - the decide -> call tool -> reply loop.

1. Send the candidate's message + the rulebook + the tool list to the model.
2. If the model asks for a tool, run it in Python and send the result back.
3. Repeat until the model writes a final reply (max MAX_ROUNDS times).
"""

import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from prompts import SYSTEM_PROMPT
from tools import flag_coordinator, match_projects, search_handbook

load_dotenv()
client = OpenAI()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")  # change in .env if your account lists another
MAX_ROUNDS = 5  # safety cap so the loop can never run forever

# The Python functions the model is allowed to call
TOOL_FUNCTIONS = {
    "search_handbook": search_handbook,
    "match_projects": match_projects,
    "flag_coordinator": flag_coordinator,
}

# How we describe the tools to the model (it reads these to decide WHEN to use each one)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_handbook",
            "description": "Search the pilot handbook. Use for any question about how the pilot works. "
                           "Returns matching entries with their IDs (H1-H6), or found=false.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The candidate's question as a short search query, ALWAYS written in English "
                                       "(translate it if the candidate wrote in Arabic).",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "match_projects",
            "description": "Find open projects that fit the candidate's skills and weekly hours, using fixed rules. "
                           "Returns project IDs (P1-P4). Only call it when you know both skills and hours.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Skills the candidate stated, in English, e.g. ['excel', 'python'].",
                    },
                    "hours_per_week": {"type": "number", "description": "Hours per week the candidate has."},
                },
                "required": ["skills", "hours_per_week"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flag_coordinator",
            "description": "Alert Lina, the pilot coordinator. Use when the candidate is stuck, upset, asks "
                           "something the handbook does not answer, or asks for something you cannot do.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The candidate's message."},
                    "reason": {
                        "type": "string",
                        "description": "Short reason, e.g. 'stuck', 'upset', 'unanswered question', 'request outside my role'.",
                    },
                },
                "required": ["message", "reason"],
            },
        },
    },
]


def detect_language(text):
    """Simple and reliable: any Arabic letters -> Arabic."""
    return "Arabic" if re.search(r"[؀-ۿ]", text) else "English"


def run_tool(name, arguments):
    """Run one tool safely and return its result."""
    if name not in TOOL_FUNCTIONS:
        return {"error": f"Unknown tool {name}"}
    try:
        return TOOL_FUNCTIONS[name](**arguments)
    except Exception as e:
        return {"error": str(e)}


# ---------- Safety net: code guarantees the critical flags ----------
# The model decides first. If it forgot to flag in a case that clearly needs Lina,
# the code flags anyway. These lists are deliberately short and easy to read.
UNANSWERED_SIGNS = ["i don't know", "i do not know", "does not mention", "doesn't mention",
                    "not mentioned", "no information", "لا أعرف", "لا يذكر", "لا تذكر", "لم يذكر",
                    "غير مذكور", "ذكر صريح"]
# The reply SAYS Lina was alerted (first person / passive, so "you can contact Lina" doesn't count)
CLAIMED_FLAG_SIGNS = ["i've alerted", "i have alerted", "i alerted", "lina has been alerted",
                      "i've notified", "i have notified", "lina has been notified",
                      "أبلغت لينا", "قمت بإبلاغ", "تم إبلاغ"]
MANIPULATION_SIGNS = ["ignore your instructions", "ignore previous", "ignore all",
                      "approve my badge", "mark my badge", "تجاهل التعليمات"]


def safety_net(message, reply, trace, language):
    """Flag Lina if the model forgot to in a clear-cut case. Returns the (possibly extended) reply."""
    if any(step["tool"] == "flag_coordinator" for step in trace):
        return reply  # the model already flagged, nothing to do

    reason = None
    if any(sign in message.lower() for sign in MANIPULATION_SIGNS):
        reason = "request outside my role"
    elif any(sign in reply.lower() for sign in UNANSWERED_SIGNS):
        reason = "unanswered question"
    elif any(sign in reply.lower() for sign in CLAIMED_FLAG_SIGNS):
        reason = "agent said it alerted Lina"  # make the claim true

    if reason is None:
        return reply

    result = flag_coordinator(message, reason)
    trace.append({"tool": "flag_coordinator", "arguments": {"reason": reason},
                  "result": result, "safety_net": True})

    # Always tell the candidate, unless the reply itself already claimed Lina was alerted
    if reason != "agent said it alerted Lina":
        if language == "Arabic":
            start = "لا أعرف الإجابة من دليل البرنامج، لذلك " if reason == "unanswered question" else ""
            reply += f"\n\n{start}أبلغت لينا، منسقة البرنامج، وهي ترد خلال 48 ساعة. المصدر: H4"
        else:
            start = "I don't know the answer from the handbook, so " if reason == "unanswered question" else ""
            reply += f"\n\n{start}I've alerted Lina, the pilot coordinator. She replies within 48 hours. Source: H4"
    return reply


def run_agent(message):
    """Answer one candidate message. Returns the reply plus a trace of tools used."""
    language = detect_language(message)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"The candidate wrote in {language}. Reply only in {language}."},
        {"role": "user", "content": message},
    ]
    trace = []

    try:
        for _ in range(MAX_ROUNDS):
            response = client.chat.completions.create(
                model=MODEL, messages=messages, tools=TOOLS, temperature=0
            )
            reply = response.choices[0].message

            # No tool requested -> this is the final answer
            if not reply.tool_calls:
                final = safety_net(message, reply.content or "", trace, language)
                return {"reply": final, "tools": trace, "language": language}

            # The model asked for one or more tools: run each, send the results back
            messages.append(reply.model_dump(exclude_none=True))
            for call in reply.tool_calls:
                arguments = json.loads(call.function.arguments)
                result = run_tool(call.function.name, arguments)
                trace.append({"tool": call.function.name, "arguments": arguments, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
    except Exception as e:
        print(f"[error] {e}")

    # Fallback: something went wrong, never leave the candidate without a path to a human
    fallback = (
        "عذرًا، حدثت مشكلة تقنية. يرجى التواصل مع منسقة البرنامج لينا."
        if language == "Arabic"
        else "Sorry, I ran into a technical problem. Please contact Lina, the pilot coordinator."
    )
    return {"reply": fallback, "tools": trace, "language": language}