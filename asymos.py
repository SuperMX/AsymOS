import pyautogui
import base64
import requests
import io
import json
import threading
import time
import sys
from queue import Queue

GLOBAL_GOAL_PROMPT = "open a Browser with the Wikipedia page"

# where the local model is hosted
OLLAMA_URL = "http://localhost:11434/api/generate"
# timeout for the model to respond, in seconds
TIMEOUT_SECONDS = 12*60

global width, height
width, height = 0, 0

pyautogui.FAILSAFE = True

# takes a screenshot
def screenshot():
    img = pyautogui.screenshot()
    global width, height
    width, height = img.size
    #img = img.resize((640, 360))
    img.save("screenshot.png")  # save for debugging
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()

# Timer thread
def start_timer(stop_event):
    seconds = 0
    try:
        while not stop_event.is_set():
            print(f"[Timer] Waiting: {seconds}s / {TIMEOUT_SECONDS}s", end="\r")
            time.sleep(1)
            seconds += 1
    except KeyboardInterrupt:
        print("\n[Interrupt] Stopping request.")
        sys.exit()

def ask_agent_thread(image_bytes, output_queue):
    try:
        result = ask_agent(image_bytes)
        output_queue.put(result)
    except Exception as e:
        output_queue.put(str(e))

# input: read screenshot, output: decide on an action
def ask_agent(image_bytes):

    img_base64 = base64.b64encode(image_bytes).decode()

    prompt = f"""
    You are an AI controlling a computer using mouse and keyboard.

    GOAL:
    {GLOBAL_GOAL_PROMPT}

    SCREENSHOT SIZE:
    width = {width}
    height = {height}

    Return ONE action to progress toward the goal.

    Actions allowed:
    - click (x,y)
    - type (text)
    - wait

    Rules:
    - Output ONLY valid JSON
    - No explanations
    - Coordinates must be inside the screenshot
    - If unsure return {{"action":"wait"}}

    Examples:
    {{"action":"click","x":300,"y":500}}
    {{"action":"type","text":"wikipedia"}}
    {{"action":"wait"}}
    """

    stop_event = threading.Event()
    timer_thread = threading.Thread(target=start_timer, args=(stop_event,))
    timer_thread.start()

    try:
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": "qwen3-vl",
                "prompt": prompt,
                "images": [img_base64],
                "stream": True,
                #"json_schema": json_schema
            },
            stream=True,
            timeout=TIMEOUT_SECONDS
        )

        r.raise_for_status()

        full_response = ""

        try:
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue

                chunk = json.loads(line)
                print(chunk)
                # print reasoning tokens
                if "thinking" in chunk:
                    print(chunk["thinking"], end="", flush=True)

                if "reasoning" in chunk:
                    print(chunk["reasoning"], end="", flush=True)

                # print normal output tokens
                if "response" in chunk:
                    token = chunk["response"]
                    print(token, end="", flush=True)
                    full_response += token

                if chunk.get("done"):
                    print()
                    break

        except KeyboardInterrupt:
            print("\n[Interrupt] Stopping request.")
            sys.exit()

        return full_response

    except requests.exceptions.Timeout:
        print(f"[Warning] Ollama request timed out after {TIMEOUT_SECONDS}s")
        return '{"action":"wait"}'

    except requests.exceptions.RequestException as e:
        print(f"[Error] Ollama request failed: {e}")
        return '{"action":"wait"}'
    
    except KeyboardInterrupt:
        print("\n[Shutdown] Ctrl+C received. Exiting agent.")
        sys.exit()

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

# Main loop
output_queue = Queue()

try:
    while True:
        img = screenshot()

        t = threading.Thread(target=ask_agent_thread, args=(img, output_queue), daemon=True)
        t.start()

        # Wait for the agent response, but still allow Ctrl+C
        while t.is_alive():
            t.join(timeout=0.1)  # small timeout so KeyboardInterrupt can be caught

        decision = output_queue.get()
        print("AGENT decision:", decision)
        execute(decision)

except KeyboardInterrupt:
    print("\n[Shutdown] Ctrl+C received. Exiting agent.")
    sys.exit(0)
