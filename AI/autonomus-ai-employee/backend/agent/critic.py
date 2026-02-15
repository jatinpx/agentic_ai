from services.llm_client import chat

CRITIC_PROMPT = """
You are a strict AI critic.

Check the quality of the answer.

If the answer is weak, incomplete, or vague → say IMPROVE.
If the answer is good → say GOOD.

Reply only:
GOOD
or
IMPROVE
"""

def review_answer(task, answer):

    return chat(
        messages=[
            {"role": "system", "content": CRITIC_PROMPT},
            {"role": "user", "content": f"Task: {task}\nAnswer: {answer}"}
        ],
        model="phi3"
    ).strip()
