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
    
    # Procesar la entrada del usuario y obtener el mensaje limpio y las URLs de imágenes
    response_text, image_urls = process_user_input(user_id, user_text)
    
    # Enviar el mensaje de texto sin las URLs de imágenes
    send_whatsapp_message(user_id, response_text)
    
    # Enviar las imágenes una por una
    for image_url in image_urls:
        send_whatsapp_image(user_id, image_url)

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
    response = requests.post(url, headers=headers, json=data)
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
        
        # Extraer URLs de imágenes
        image_urls = extract_all_image_urls_from_text(bot_message)

        # Eliminar las URLs de imágenes del texto
        cleaned_message = remove_image_urls_from_text(bot_message)
    else:
        cleaned_message = "Lo siento, no pude obtener una respuesta en este momento."
        image_urls = []

    return cleaned_message, image_urls

def extract_all_image_urls_from_text(text):
    """Extrae todas las URLs de imágenes del texto"""
    url_pattern = r'https?://[^\s]+(?:jpg|jpeg|png|gif)'
    return re.findall(url_pattern, text)

def remove_image_urls_from_text(text):
    """Elimina las URLs de imágenes del texto"""
    url_pattern = r'https?://[^\s]+(?:jpg|jpeg|png|gif)'
    return re.sub(url_pattern, '', text).strip()


@app.route('/reset', methods=['POST'])
def reset():
    global threads
    threads = {}  # Limpia el almacenamiento de threads


if __name__ == "__main__":
    app.run(debug=True)
