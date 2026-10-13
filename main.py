"""
main.py - simple command-line chat for the live demo.
Run:  python main.py      (type 'exit' to stop)
"""

import sys

from agent import run_agent

sys.stdout.reconfigure(encoding="utf-8")  # so Arabic prints correctly on Windows

print("Proofwork candidate assistant. Type 'exit' to stop.\n")

while True:
    message = input("Candidate: ").strip()
    if message.lower() in ("exit", "quit"):
        break
    if not message:
        continue

    result = run_agent(message)

    tools_used = ", ".join(step["tool"] for step in result["tools"]) or "none"
    print(f"\n[tools used: {tools_used}]")
    print(f"Assistant: {result['reply']}\n")