from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import time
from openai import OpenAI

# Configuración inicial
app = Flask(__name__)

# Configuración de CORS
CORS(app, resources={r"/*": {"origins": "*"}})

# Configuración de OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
assistant_id = os.getenv("ASSISTANT_ID")

# Almacenamiento en memoria para los thread_id
threads = {}

# Variables de entorno para WhatsApp e Instagram
access_token = os.getenv('ACCESS_TOKEN')
verify_token = os.getenv('VERIFY_TOKEN')
phone_number_id = os.getenv('PHONE_NUMBER_ID')
instagram_user_id = os.getenv('INSTAGRAM_USER_ID')
instagram_access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN')
WEBHOOK_VERIFY_TOKEN = os.getenv('WEBHOOK_VERIFY_TOKEN')

# Leer el contexto inicial desde el archivo de texto
with open('initial_context.txt', 'r') as file:
    initial_context = file.read().strip()

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    print("[DEBUG] webhook endpoint hit")
    if request.method == 'GET':
        print(f"[DEBUG] GET request received with args: {request.args}")
        if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
            if request.args.get("hub.verify_token") == verify_token:
                print("[DEBUG] Verification successful")
                return request.args["hub.challenge"], 200
            print("[DEBUG] Verification token mismatch")
            return "Verification token mismatch", 403
        return "Hello world", 200

    elif request.method == 'POST':
        print(f"[DEBUG] POST request received with data: {request.get_json()}")
        data = request.get_json()
        if 'object' in data:
            if data['object'] == 'whatsapp_business_account':
                print("[DEBUG] Handling WhatsApp Business Account")
                for entry in data['entry']:
                    for change in entry['changes']:
                        if 'messages' in change['value']:
                            for message in change['value']['messages']:
                                handle_whatsapp_message(message)
            elif data['object'] == 'instagram':
                print("[DEBUG] Handling Instagram")
                for entry in data['entry']:
                    for change in entry['changes']:
                        if 'messaging' in change['value']:
                            for message in change['value']['messaging']:
                                handle_instagram_message(message)
            elif data['object'] == 'page':
                print("[DEBUG] Handling Facebook Page")
                for entry in data['entry']:
                    for messaging_event in entry['messaging']:
                        handle_messenger_message(messaging_event)
        return "Event received", 200

def handle_whatsapp_message(message):
    print(f"[DEBUG] WhatsApp message received: {message}")
    user_id = message['from']
    user_text = message['text']['body']
    response_data = process_user_input(user_id, user_text)
    send_whatsapp_message(user_id, response_data)

def handle_instagram_message(message):
    print(f"[DEBUG] Instagram message received: {message}")
    user_id = message['sender']['id']
    user_text = message['message']['text']
    response_data = process_user_input(user_id, user_text)
    send_instagram_message(user_id, response_data)

def handle_messenger_message(message):
    print(f"[DEBUG] Messenger message received: {message}")
    user_id = message['sender']['id']
    user_text = message['message']['text']
    response_data = process_user_input(user_id, user_text)
    send_messenger_message(user_id, response_data)

def send_whatsapp_message(user_id, response_data):
    print(f"[DEBUG] Sending WhatsApp message to {user_id} with response data: {response_data}")
    for item in response_data:
        if 'text' in item:
            send_whatsapp_text_message(user_id, item['text'])
        if 'image' in item:
            send_whatsapp_image_or_link(user_id, item['image'])

# Función para enviar mensajes de texto por WhatsApp
def send_whatsapp_text_message(user_id, text):
    print(f"[DEBUG] Sending WhatsApp text message: {text} to user_id: {user_id}")
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": user_id,
        "type": "text",
        "text": {"body": text}
    }
    response = requests.post(url, headers=headers, json=data)
    print(f"[DEBUG] WhatsApp text message response status: {response.status_code}")
    print(response.json())

# Función para enviar imágenes o enlaces dependiendo del tipo
def send_whatsapp_image_or_link(user_id, url):
    print(f"[DEBUG] Determining if the link is an image: {url}")
    if is_image_url(url):
        send_whatsapp_image_message(user_id, url)
    else:
        send_whatsapp_text_message(user_id, f"Puedes verlo aquí: {url}")

# Función para enviar una imagen por WhatsApp
def send_whatsapp_image_message(user_id, image_url):
    print(f"[DEBUG] Sending WhatsApp image message: {image_url} to user_id: {user_id}")
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": user_id,
        "type": "image",
        "image": {"link": image_url}
    }
    response = requests.post(url, headers=headers, json=data)
    print(f"[DEBUG] WhatsApp image message response status: {response.status_code}")
    print(response.json())

# Función para verificar si la URL es de una imagen
def is_image_url(url):
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    result = any(url.lower().endswith(ext) for ext in image_extensions)
    print(f"[DEBUG] is_image_url result for {url}: {result}")
    return result

def process_user_input(user_id, user_input):
    print(f"[DEBUG] Processing input from user {user_id}: {user_input}")
    if user_id not in threads:
        print(f"[DEBUG] No thread found for user {user_id}. Creating a new thread...")
        new_thread = client.beta.threads.create()
        threads[user_id] = new_thread.id
        print(f"[DEBUG] New thread created for user {user_id}: {threads[user_id]}")
    else:
        print(f"[DEBUG] Existing thread found for user {user_id}: {threads[user_id]}")

    thread_id = threads[user_id]

    print(f"[DEBUG] Sending user input to thread {thread_id}")
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_input,
    )
    print(f"[DEBUG] User input sent: {user_input}")

    print(f"[DEBUG] Running conversation with assistant {assistant_id} on thread {thread_id}")
    run = client.beta.threads.runs.create(
        assistant_id=assistant_id,
        thread_id=thread_id
    )
    run_id = run.id
    print(f"[DEBUG] Run created with run_id: {run_id}")

    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run_id
        )
        print(f"[DEBUG] Run status: {run.status}")
        if run.status == 'completed':
            print("[DEBUG] Run completed.")
            break
        time.sleep(3)

    print(f"[DEBUG] Retrieving messages from thread {thread_id}")
    output_messages = client.beta.threads.messages.list(
        thread_id=thread_id
    )

    response_data = []
    if output_messages.data:
        for message in output_messages.data:
            if 'content' in message:
                text_segments = [segment.text.value for segment in message.content if segment.type == 'text']
                image_segments = [segment.image.url for segment in message.content if segment.type == 'image']

                for text in text_segments:
                    response_data.append({"text": text})
                for image_url in image_segments:
                    response_data.append({"image": image_url})

    if not response_data:
        response_data.append({"text": "Lo siento, no pude obtener una respuesta en este momento."})

    print(f"[DEBUG] Response data for user {user_id}: {response_data}")
    return response_data

@app.route('/reset', methods=['POST'])
def reset():
    global threads
    threads = {}  # Limpia el almacenamiento de threads
    print("[DEBUG] All threads have been reset")
    return jsonify({"status": "success", "message": "Threads reset"}), 200

if __name__ == "__main__":
    print("[DEBUG] Starting Flask app")
    app.run(debug=True)