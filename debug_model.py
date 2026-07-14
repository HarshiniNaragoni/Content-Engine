import sys, json
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()
import requests, os

key = os.getenv('OPENROUTER_API_KEY', '')

# Extended list — test reasoning models specifically
test_models = [
    'google/gemma-4-26b-a4b-it:free',
    'google/gemma-4-31b-it:free',
    'nvidia/nemotron-3-nano-30b-a3b:free',
    'nvidia/nemotron-3-super-120b-a12b:free',
    'qwen/qwen3-next-80b-a3b-instruct:free',
]

for model in test_models:
    try:
        r = requests.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
            json={
                'model': model,
                'messages': [
                    {'role': 'system', 'content': 'Output ONE tagline only. Max 8 words.'},
                    {'role': 'user',   'content': 'AquaFlow water bottle | eco tone'},
                ],
                'temperature': 0.7,
                'max_tokens': 200,
                include_reasoning: false
            },
            timeout=25
        )
        if r.ok:
            data     = r.json()
            choices  = data.get('choices', [{}])
            msg      = choices[0].get('message', {}) if choices else {}
            content  = msg.get('content') or ''
            reasoning = msg.get('reasoning') or msg.get('thinking') or ''
            print(f"MODEL: {model}")
            print(f"  content   ({len(content)} chars): {repr(content[:200])}")
            if reasoning:
                print(f"  reasoning ({len(reasoning)} chars): {repr(str(reasoning)[:100])}")
            else:
                print("  reasoning : none")
            print()
        else:
            print(f"FAIL {model}: {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"ERROR {model}: {e}")
