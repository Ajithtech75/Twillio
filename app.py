from flask import Flask, request, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import requests
import os
from dotenv import load_dotenv
import urllib.parse
import time
import threading
from azure.ai.openai import ChatCompletionClient
from azure.core.credentials import AzureKeyCredential

load_dotenv()

# ─── CONFIG ────────────────────────────────────────────────────────────────────
# Twilio
account_sid    = os.getenv("TWILIO_SID")         or ''
auth_token     = os.getenv("TWILIO_AUTH_TOKEN")  or '709c4037be3a52b3dc0724ea559a2497'
twilio_number  = os.getenv("TWILIO_NUMBER")      or '+16205248692'
client         = Client(account_sid, auth_token)

# ElevenLabs
ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY") or 'sk_d9f1be11588b6b2845b28f92e4d53bc0a06e7c923b33dc2f'
voice_id = 'd3ThhkptBvTdyy8WfbdW'  

# Azure OpenAI
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY") or '3bDJaP7gC0qqoa9tqTMprPWskG5anntGiwuPquvKdCiQkivBcqUYJQQJ99BDACHYHv6XJ3w3AAAAACOG9riH'
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT") or 'https://ai-muthu9588ai159885313320.services.ai.azure.com/models'
client_azure_openai = ChatCompletionClient(AZURE_OPENAI_ENDPOINT, AzureKeyCredential(AZURE_OPENAI_API_KEY))

# Publicly-accessible base URL
BASE_URL = os.getenv("BASE_URL") or ' https://d5fc-183-82-242-61.ngrok-free.app'

# Conversation script
SCRIPT = [
    "Hi sir Good morning this is shruthi from Getfarms",
    "மாந்தோப்பு விஷயமா enquiry பண்ணியிருந்தீங்க. அதுக்கான டீடெயல்ஸ் கொடுக்கதுக்காக தான் உங்களை contact பண்ணி இருக்கேன்.",
    "நம்முடைய மாந்தோப்பு முப்பது ஏக்கர் property. அதுல 22 சென்ட், 18 லட்ச ரூபாய்க்கு minimum ல குடுத்திட்டு இருக்கோம். இதுல நீங்க கால் ஏக்கர், அரை ஏக்கர், ஒரு ஏக்கர் purchase பண்ணிக்கலாம். இதைப் பற்றிய further information காக நம்ம team உங்களை contact பண்ணுவாங்க."
]
# ────────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)

def generate_audio(text: str) -> bytes:
    """Generate Tamil speech using ElevenLabs"""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {'xi-api-key': ELEVEN_API_KEY, 'Content-Type': 'application/json'}
    payload = {
        'text': text,
        'model_id': 'eleven_multilingual_v2',
        'voice_settings': {'stability': 0.5, 'similarity_boost': 0.8}
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.content

def determine_interest_response(user_input: str) -> str:
    """Determine the appropriate closing response based on user interest"""
    user_input = user_input.lower()
    
    # Keywords that indicate interest
    interest_keywords = ['interested', 'ஆமா', 'சரி', 'ok', 'yes', 'details', 'விவரம்']
    
    # Keywords that indicate disinterest
    disinterest_keywords = ['not interested', 'இல்லை', 'no', 'later', 'வேண்டாம்']
    
    if any(keyword in user_input for keyword in interest_keywords):
        return "நல்லது சர், நன்றி. இப்போ என் manager உங்களை call பண்ணுவாங்க."
    elif any(keyword in user_input for keyword in disinterest_keywords):
        return "சரி சர், future updates காக Getfarms ல contact பண்ணுங்க. உங்க support கும் patience கும் ரொம்ப thanks சர்."
    else:
        return "நன்றி சர், உங்கள் நேரத்திற்கு. எங்களை தொடர்பு கொள்ளவும்."

def get_ai_response(conversation: list) -> str:
    """Get context-aware Tamil response from Azure OpenAI GPT-3.5 Turbo with reduced delay."""
    try:
        system_message = {
            "role": "system",
            "content": (
                "You are Shruthi from Get Farms, a friendly sales agent. Reply briefly and naturally in Tamil. "
                "Always greet, ask if they are interested in farming land, and keep it short and clear."
            )
        }

        # Prepare the request body for the Azure OpenAI API
        messages = [system_message] + conversation
        
        # Call the Azure OpenAI API to get the response (Use GPT-3.5 Turbo model here)
        response = client_azure_openai.get_chat_completions(
            model="gpt-3.5-turbo",  
            messages=messages,
            temperature=0.7,
            max_tokens=100
        )
        
        # Extract the content from the response
        return response.choices[0].message['content']
    except Exception as e:
        print(f"Azure OpenAI Error: {e}")
        return "மன்னிக்கவும், தொழில்நுட்ப சிக்கல் ஏற்பட்டுள்ளது."

@app.route('/tts')
def tts():
    """Text-to-speech endpoint"""
    text = request.args.get('text')
    if not text:
        return "Error: no text provided", 400
    audio = generate_audio(text)
    return Response(audio, mimetype='audio/mpeg')

@app.route('/start_call', methods=['GET'])
def start_call():
    """Initiate outbound call"""
    to = request.args.get('recipient_phone_number')
    if not to:
        return "Error: please provide recipient_phone_number", 400

    try:
        call = client.calls.create(
            to=to,
            from_=twilio_number,
            url=f"{BASE_URL}/conversation?stage=0"
        )
        return f"Call initiated. SID: {call.sid}"
    except Exception as e:
        return f"Error initiating call: {str(e)}", 500

@app.route('/conversation', methods=['GET', 'POST'])
def conversation():
    """Handle the conversation flow"""
    stage = int(request.args.get('stage', 0))
    user_response = request.values.get('SpeechResult', '')

    resp = VoiceResponse()

    # Play scripted prompts for first 3 stages
    if stage < len(SCRIPT):
        prompt = SCRIPT[stage]
        
        gather = resp.gather(
            input='speech',
            action=f'/conversation?stage={stage+1}',
            timeout=10
        )
        gather.play(f"{BASE_URL}/tts?text={urllib.parse.quote(prompt)}")
    else:
        # Use Azure GPT-3.5 Turbo to generate the response based on user input
        response = get_ai_response([{"role": "user", "content": user_response}])
        
        # Play the appropriate closing message
        resp.play(f"{BASE_URL}/tts?text={urllib.parse.quote(response)}")
        resp.hangup()  # End the call after the closing message

    return Response(str(resp), content_type='application/xml')

def start_flask():
    """Run Flask App"""
    app.run(debug=True, port=5000, use_reloader=False)

def start_call_after_input():
    """Collect recipient number and start call"""
    recipient = input("Enter recipient phone number (+91xxxxxxxxxx): ")
    response = requests.get(f"http://localhost:5000/start_call?recipient_phone_number={recipient}")
    print(response.text)

if __name__ == '__main__':
    # Run Flask in a separate thread
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.start()

    # Wait a bit for Flask to be fully initialized
    time.sleep(3)

    # Ask for recipient number and start the call
    start_call_after_input()
