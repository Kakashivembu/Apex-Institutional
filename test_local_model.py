import urllib.request, json
req = urllib.request.Request(
    'http://172.17.16.1:1234/v1/chat/completions',
    data=json.dumps({
        'model':'local-model',
        'messages':[
            {
                'role':'system',
                'content':"You are running in a strict machine-to-machine JSON evaluation pipeline. YOU MUST OUTPUT ONLY VALID RAW JSON. Do NOT wrap your output in markdown code blocks. Do NOT output conversational text like 'I apologize'. Do NOT attempt to use any function calls or tool calls. Just output the final JSON dictionary directly."
            },
            {
                'role':'user',
                'content':'Generate a test JSON object.'
            }
        ]
    }).encode(),
    headers={'Content-Type':'application/json'}
)
print(urllib.request.urlopen(req).read().decode())
