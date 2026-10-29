"""Optional live Ollama check. Uses only synthetic university data."""
import json
from pathlib import Path
import time
from assistant_service import generate

context={"courses":["ICT","Calculus"],"deadlines":[{"title":"Assignment 3","course":"ICT","date":"30 октября 2026","time":"23:59"}],
         "note":"Synthetic test data, not a real student"}
questions=["Где найти карту AITU?","Когда дедлайн Assignment 3?","Какие курсы есть в моих данных?",
           "Свободна ли аудитория C1.101?","Кто преподаёт Calculus?"]
results=[]
for question in questions:
    started=time.monotonic()
    answer=generate(question,context)
    item={"question":question,"answer":answer,"seconds":round(time.monotonic()-started,2)}
    results.append(item)
    print(json.dumps(item,ensure_ascii=False),flush=True)
Path(__file__).with_name("ai-test-results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n")
assert "https://yuujiso.github.io/aitumap/" in results[0]["answer"]
assert "30" in results[1]["answer"] and "23:59" in results[1]["answer"]
assert "ICT" in results[2]["answer"] and "Calculus" in results[2]["answer"]
for item in results[3:]:
    assert any(term in item["answer"].lower() for term in ("нет","не указ","отсутств","не предостав"))
print("PASS: five live answers include known facts and acknowledge missing occupancy/teacher data.")
