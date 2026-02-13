import ollama

response = ollama.chat(
    model='phi3',   # change to llama3 if you installed that
    messages=[{'role': 'user', 'content': 'Explain AI in one line'}]
)

print(response['message']['content'])
