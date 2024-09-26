from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import time
import re
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
last_message_sent = {}  # Almacenará el último mensaje enviado por cada usuario

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
    if request.method == 'GET':
        if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
            if request.args.get("hub.verify_token") == verify_token:
                return request.args["hub.challenge"], 200
            return "Verification token mismatch", 403
        return "Hello world", 200

    elif request.method == 'POST':
        data = request.get_json()
        if 'object' in data:
            if data['object'] == 'whatsapp_business_account':
                for entry in data['entry']:
                    for change in entry['changes']:
                        if 'messages' in change['value']:
                            for message in change['value']['messages']:
                                handle_whatsapp_message(message)
            elif data['object'] == 'instagram':
                for entry in data['entry']:
                    for change in entry['changes']:
                        if 'messaging' in change['value']:
                            for message in change['value']['messaging']:
                                handle_instagram_message(message)
            elif data['object'] == 'page':
                for entry in data['entry']:
                    for messaging_event in entry['messaging']:
                        handle_messenger_message(messaging_event)
        return "Event received", 200

def handle_whatsapp_message(message):
    user_id = message['from']
    user_text = message['text']['body']
    
    # Procesar la entrada del usuario y obtener las partes de texto e imágenes
    message_parts = process_user_input(user_id, user_text)
    
    # Enviar las partes del mensaje (texto o imágenes) en orden
    for part in message_parts:
        if is_image_url(part):
            send_whatsapp_image(user_id, part)
        else:
            send_whatsapp_message(user_id, part)

def is_image_url(text):
    """Verifica si el texto es una URL de imagen."""
    return re.match(r'https?://[^\s]+(?:jpg|jpeg|png|gif)', text)

def handle_instagram_message(message):
    user_id = message['sender']['id']
    user_text = message['message']['text']
    response_text = process_user_input(user_id, user_text)
    send_instagram_message(user_id, response_text)

def handle_messenger_message(message):
    user_id = message['sender']['id']
    user_text = message['message']['text']
    response_text = process_user_input(user_id, user_text)
    send_messenger_message(user_id, response_text)

def send_whatsapp_message(user_id, text):
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
    print(response.status_code)
    print(response.json())

def send_whatsapp_image(user_id, image_url):
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
    print(response.status_code)
    print(response.json())

def send_instagram_message(user_id, text):
    url = f"https://graph.facebook.com/v19.0/{instagram_user_id}/messages"
    headers = {
        "Authorization": f"Bearer {instagram_access_token}",
        "Content-Type": "application/json"
    }
    data = {
        "recipient": {"id": user_id},
        "message": {"text": text}
    }
    response = requests.post(url, headers=headers, json=data)
    print(response.status_code)
    print(response.json())

def send_messenger_message(user_id, text):
    url = "https://graph.facebook.com/v19.0/me/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {
        "recipient": {"id": user_id},
        "message": {"text": text}
    }
    response = requests.post(url, headers=headers, json(data))
    print(response.status_code)
    print(response.json())

def process_user_input(user_id, user_input):
    if user_id not in threads:
        new_thread = client.beta.threads.create()
        threads[user_id] = new_thread.id

    thread_id = threads[user_id]

    # Enviar el mensaje del usuario al asistente
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_input,
    )

    # Ejecutar el asistente
    run = client.beta.threads.runs.create(
        assistant_id=assistant_id,
        thread_id=thread_id
    )
    run_id = run.id

    # Esperar hasta que la ejecución esté completa
    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run_id
        )
        if run.status == 'completed':
            break
        time.sleep(3)

    # Obtener el mensaje de respuesta del bot
    output_messages = client.beta.threads.messages.list(
        thread_id=thread_id
    )

    if output_messages.data:
        bot_message = output_messages.data[0].content[0].text.value
        
        # Verifica si el mensaje ya fue enviado
        if last_message_sent.get(user_id) == bot_message:
            return ["El mismo mensaje fue repetido, omitiendo respuesta."]
        else:
            last_message_sent[user_id] = bot_message

        # Separar el texto por las URLs de imágenes
        message_parts = split_text_and_urls(bot_message)
    else:
        message_parts = ["Lo siento, no pude obtener una respuesta en este momento."]

    return message_parts

def split_text_and_urls(text):
    url_pattern = r'(https?://[^\s]+(?:jpg|jpeg|png|gif))'
    text = re.sub(r'!\[.*?\]\(', '', text)
    text = re.sub(r'\)', '', text)
    parts = re.split(url_pattern, text)

    cleaned_parts = []
    for part in parts:
        if is_image_url(part):
            part = re.sub(r'\?.*$', '', part)
        cleaned_parts.append(part.strip())

    return [part for part in cleaned_parts if part]


@app.route('/reset', methods=['POST'])
def reset():
    global threads
    threads = {}
    global last_message_sent
    last_message_sent = {}  # Limpia el historial de últimos mensajes enviados


if __name__ == "__main__":
    app.run(debug=True)

