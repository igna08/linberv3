import openai
import os
import requests
from flask import Flask, request, jsonify, render_template, send_from_directory, session
from flask_cors import CORS
import spacy



# Configuración inicial
openai.api_key = os.getenv('OPENAI_API_KEY')  # Asegúrate de configurar tu variable de entorno
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app, resources={r"/*": {"origins": "*"}})
 # Esto iniciará ngrok cuando se ejecute la app

# Cargar el modelo de lenguaje en español
nlp = spacy.load("es_core_news_md")

access_token = os.getenv('ACCESS_TOKEN')  # Token de acceso para WhatsApp
verify_token = os.getenv('VERIFY_TOKEN')
phone_number_id = os.getenv('PHONE_NUMBER_ID')
instagram_access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN')  # Token de acceso para Instagram
total_conversations = 0
admin_password = os.getenv('ADMIN_PASSWORD', '12345')  # Utiliza variable de entorno para la contraseña de admin
instagram_user_id = os.getenv('INSTAGRAM_USER_ID')

@app.route("/")
def home():
    return render_template("index.html")

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
    response_text = process_user_input(user_text)
    send_whatsapp_message(user_id, response_text)

def handle_instagram_message(message):
    user_id = message['sender']['id']
    user_text = message['message']['text']
    response_text = process_user_input(user_text)
    send_instagram_message(user_id, response_text)

def handle_messenger_message(message):
    user_id = message['sender']['id']
    user_text = message['message']['text']
    response_text = process_user_input(user_text)
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
    requests.post(url, headers=headers, json=data)

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
    requests.post(url, headers=headers, json=data)

def process_user_input(user_input):
    # Obtener o inicializar la lista de mensajes
    if 'messages' not in session:
        session['messages'] = [
            {"role": "system", "content": "You are an assistant at Surcan, a Family company located in the heart of Apóstoles, city of Misiones with more than 40 years of experience in the construction field. Be kind and friendly."}
        ]

    # Añadir el mensaje del usuario a la lista de mensajes
    session['messages'].append({"role": "user", "content": user_input})

    try:
        # Utilizar GPT-4 para detectar frases donde el usuario busca un producto
        if is_product_search_intent(user_input):
            product_name = extract_product_name(user_input)
            products = search_product_in_shopify(product_name)

            if products:
                product_messages = [f"Here is some information about {product['title']}: {product['body_html']}" for product in products]
                bot_message = " ".join(product_messages)
            else:
                bot_message = f"I couldn't find information about '{product_name}'. Please check back later."

        else:
            # Conversación normal con OpenAI GPT-4
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo-0125",  # GPT-4 model
                messages=session['messages']
            )
            bot_message = response.choices[0].message['content'].strip()

        # Añadir el mensaje del bot a la lista de mensajes
        session['messages'].append({"role": "assistant", "content": bot_message})

        return bot_message
    except Exception as e:
        return str(e)

def is_product_search_intent(user_input):
    # Analiza el texto del usuario
    doc = nlp(user_input.lower())
    # Busca patrones en la frase que indiquen una intención de búsqueda
    for token in doc:
        if token.lemma_ in ["buscar", "necesitar", "querer"] and token.pos_ == "VERB":
            return True
    return False

def extract_product_name(user_input):
    # Analiza el texto del usuario
    doc = nlp(user_input.lower())
    product_name = []
    is_searching = False
    for token in doc:
        # Detectar la frase de búsqueda
        if token.lemma_ in ["buscar", "necesitar", "querer"] and token.pos_ == "VERB":
            is_searching = True
        # Extraer sustantivos después del verbo de búsqueda
        if is_searching and token.pos_ in ["NOUN", "PROPN"]:
            product_name.append(token.text)
    return " ".join(product_name)

 

# Función para buscar un producto en Shopify
def search_product_in_shopify(product_name):
    shopify_api_url = 'https://surcansa.myshopify.com/api/2023-07/products.json'  # Reemplaza con tu URL de API de Shopify
    headers = {
        'X-Shopify-Access-Token': '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',
        'Content-Type': 'application/json'
    }
    params = {
        'title': product_name
    }

    try:
        response = requests.get(shopify_api_url, headers=headers, params=params)
        if response.status_code == 200:
            products = response.json()['products']
            if products:
                return products  # Devuelve todos los productos encontrados
            else:
                return []
        else:
            return []
    except Exception as e:
        print(f"Error fetching product from Shopify: {str(e)}")
        return []

@app.route('/reset', methods=['POST'])
def reset():
    session.pop('messages', None)
    return jsonify({'status': 'session reset'})

if __name__ == "__main__":
    app.run(debug=True)
