from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import spacy
import time
from openai import OpenAI

# Configuración inicial
app = Flask(__name__)

# Configuración de CORS
CORS(app, resources={r"/*": {"origins": "*"}})

# Configuración de OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
assistant_id = os.getenv("ASSISTANT_ID")

# Cargar el modelo de lenguaje en español
nlp = spacy.load("es_core_news_md")

# Almacenamiento en memoria para los thread_id
threads = None

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
    response_text = process_user_input(user_id, user_text)
    send_whatsapp_message(user_id, response_text)

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
    # Usar un identificador único por usuario si es necesario
    if user_id not in threads:
        print(f"[DEBUG] No se encontró thread_id para el usuario {user_id}. Creando uno nuevo...")
        new_thread = client.beta.threads.create()
        threads[user_id] = new_thread.id
        print(f"[DEBUG] Nuevo thread_id creado para el usuario {user_id}: {threads[user_id]}")
    else:
        print(f"[DEBUG] thread_id existente encontrado para el usuario {user_id}: {threads[user_id]}")

    thread_id = threads[user_id]

    print(f"[DEBUG] Enviando entrada del usuario al thread_id: {thread_id}")
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_input,
    )
    print(f"[DEBUG] Entrada del usuario enviada: {user_input}")

    print("[DEBUG] Ejecutando conversación con el asistente...")
    run = client.beta.threads.runs.create(
        assistant_id=assistant_id,
        thread_id=thread_id
    )
    run_id = run.id
    print(f"[DEBUG] Run creado con run_id: {run_id}")

    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run_id
        )
        print(f"[DEBUG] Verificando estado del run: {run.status}")
        if run.status == 'completed':
            print("[DEBUG] Ejecución completada.")
            break
        time.sleep(3)

    print("[DEBUG] Recuperando mensajes del hilo...")
    output_messages = client.beta.threads.messages.list(
        thread_id=thread_id
    )

    print(f"[DEBUG] Mensajes recuperados: {output_messages.data}")

    if output_messages.data:
        print(f"[DEBUG] Primer mensaje del asistente encontrado: {output_messages.data[0]}")
        bot_message = output_messages.data[0].content[0].text.value
        print(f"[DEBUG] Respuesta del asistente: {bot_message}")
    else:
        bot_message = "Lo siento, no pude obtener una respuesta en este momento."
        print("[DEBUG] No se encontraron mensajes del asistente.")

    return bot_message

@app.route('/reset', methods=['POST'])
def reset():
    global threads
    threads = {}  # Limpia el almacenamiento de threads
    return jsonify({"status": "success", "message": "Threads reset"}), 200

if __name__ == "__main__":
    app.run(debug=True)
