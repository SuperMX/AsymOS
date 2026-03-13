import pyautogui
import base64
import requests
import io
import json
import threading
import time

GLOBAL_GOAL_PROMPT = "open a Browser with the Wikipedia page"

# where the local model is hosted
OLLAMA_URL = "http://localhost:11434/api/generate"
# timeout for the model to respond, in seconds
TIMEOUT_SECONDS = 10*60

# takes a screenshot
def screenshot():
    img = pyautogui.screenshot()
    #img = img.resize((640, 360))
    img.save("screenshot.png")  # save for debugging
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()

# Timer thread
def start_timer(stop_event):
    seconds = 0
    while not stop_event.is_set():
        print(f"[Timer] Waiting: {seconds}s / {TIMEOUT_SECONDS}s", end="\r")
        time.sleep(1)
        seconds += 1

# input: read screenshot, output: decide on an action
def ask_agent(image_bytes):

    img_base64 = base64.b64encode(image_bytes).decode()

    prompt = """
You are controlling a computer. Your goal is to achieve the following: """ + GLOBAL_GOAL_PROMPT + """
Look at the screenshot and decide ONE action.

STRICT RULES:
- Output ONLY ONE JSON object.
- DO NOT add explanations or text.
- DO NOT use code blocks.
- Must be valid JSON parseable by Python.
- If you cannot decide, return {"action":"wait"}.

Example of valid output:
{"action":"click","x":500,"y":400}
"""
    
    json_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["click","type","wait"]
            },
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "text": {"type": "string"}
        },
        "required": ["action"],
        "additionalProperties": False
    }

    stop_event = threading.Event()
    timer_thread = threading.Thread(target=start_timer, args=(stop_event,))
    timer_thread.start()

    try:
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": "llama3.2-vision",
                "prompt": prompt,
                "images": [img_base64],
                "stream": False,
                "json_schema": json_schema
            },
            timeout=TIMEOUT_SECONDS  # <-- timeout in seconds
        )
        r.raise_for_status()
        return r.json()["response"]
    except requests.exceptions.Timeout:
        print(f"[Warning] Ollama request timed out after {TIMEOUT_SECONDS}s")
        return '{"action":"wait"}'  # fallback action
    except requests.exceptions.RequestException as e:
        print(f"[Error] Ollama request failed: {e}")
        return '{"action":"wait"}'
    finally:
        stop_event.set()
        timer_thread.join()

# input: action, pyautogui executes the action
# Execute action safely
def execute(action):
    try:
        a = json.loads(action)
    except json.JSONDecodeError:
        print(f"[Error] Failed to parse JSON: {action}. Defaulting to wait.")
        a = {"action":"wait"}

    if a.get("action") == "click" and "x" in a and "y" in a:
        pyautogui.click(a["x"], a["y"])
    elif a.get("action") == "type" and "text" in a:
        pyautogui.write(a["text"])
    elif a.get("action") == "wait":
        pyautogui.sleep(2)
    else:
        print(f"[Warning] Unknown or malformed action: {a}. Defaulting to wait.")
        pyautogui.sleep(2)

# Run AsymOS agent
print("Starting AsymOS agent. Kill ollama to stop.")
execute('{"action":"wait"}')

# loop: screenshot -> ask agent -> execute action
while True:

    print("Taking screenshot...")
    img = screenshot()
    #print(img) # print the raw bytes for debugging
    print("Screenshot taken. Asking agent for action...")
    decision = ask_agent(img)

    print("AGENT decision:", decision)

    execute(decision)