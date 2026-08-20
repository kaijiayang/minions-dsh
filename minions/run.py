from clients.ollama import OllamaClient
from clients.openai import OpenAIClient


# vanilla ollama
from ollama import chat
from ollama import ChatResponse

messages = [
    [
        {
            'role': 'user',
            'content': 'Why is the sky blue?'
        }
    ],
    [
        {
            'role': 'user', 
            'content': 'What is the capital of France?'
        },
    ]
]

# for message in messages:
#     response: ChatResponse = chat(model='llama3.2', messages=message)
#     print(response)
# or access fields directly from the response object


# commented out everything below 
# initialize the ollama client
client_local = OllamaClient(model_name='llama3.2')

responses = client_local.chat(messages=messages)

print(responses)

# initialize the openai client
client_remote = OpenAIClient(model_name='gpt-4o')



# print("response from remote client:")
# print(response['message'])