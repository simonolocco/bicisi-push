from flask import Flask, request, jsonify
import requests
import json

app = Flask(__name__)

# Configuración
TOKEN = "EAAPG3mWTNbQBQk1uV5TzKWPi2X08ohDxl2TE2ZAjfgPtqjfBfJhFLxcTYlEZCpdmMHNnE4DULaw2yFOO0ti5BaVeG1PTmFpeWje5qit2VLKUd09LiYludhvJtR6YgqXxcCBxYF03vZBjRIiZCSLBnGV74kCIKRjnnWKqT6bbK6P4ZAePdGHUWIB7q0GREyyJZCZATJNMHl7q24xRoy8Lkk0gukhdSw7IVaHA8fLzHZAF"
PHONE_ID = "823208770885097"
VERIFY_TOKEN = "javier"
VERSION = "v19.0"

# Payloads de botones
PAYLOAD_MENU = "MENU_PRINCIPAL"
PAYLOAD_PLANES = "VER_PLANES"
PAYLOAD_RESERVAR = "COMO_RESERVAR"
PAYLOAD_UBICACION = "VER_UBICACION"
PAYLOAD_ECO = "DETALLE_ECO"
PAYLOAD_FULL = "DETALLE_FULL"
PAYLOAD_PAGO = "DATOS_PAGO"

def send_whatsapp_message(to, data):
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "recipient_type": "individual",
    }
    payload.update(data)
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error enviando mensaje: {e}")
        if response:
             print(f"Detalle error: {response.text}")

def send_text(to, text):
    data = {
        "type": "text",
        "text": {"body": text}
    }
    send_whatsapp_message(to, data)

def send_buttons(to, text, buttons):
    # buttons es una lista de tuplas (id, titulo)
    # max 3 botones permitidos por WhatsApp en interactive messages
    action_buttons = []
    for btn_id, btn_title in buttons:
        action_buttons.append({
            "type": "reply",
            "reply": {
                "id": btn_id,
                "title": btn_title
            }
        })
    
    data = {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text},
            "action": {"buttons": action_buttons}
        }
    }
    send_whatsapp_message(to, data)

# Lógica de respuestas
def handle_incoming_message(sender, message_body, message_type):
    msg_text = ""
    payload = ""
    
    if message_type == "text":
        msg_text = message_body["text"]["body"].lower().strip()
        print(f"📩 {sender} escribió: {msg_text}")
    elif message_type == "interactive":
        type_interactive = message_body["interactive"]["type"]
        if type_interactive == "button_reply":
            payload = message_body["interactive"]["button_reply"]["id"]
            title = message_body["interactive"]["button_reply"]["title"]
            msg_text = title
            print(f"🔘 {sender} tocó botón: {title} (ID: {payload})")

    # Flujo de conversación
    # 1. Saludo / Inicio
    if payload == PAYLOAD_MENU or any(x in msg_text for x in ["hola", "buen dia", "buenas", "inicio", "menu"]):
        welcome_text = (
            "¡Hola! 👋 Gracias por tu interés en *BiciSí*, Servicio de Alquiler de Bicicletas en Villa Carlos Paz 🚲✨\n\n"
            "⏰ *Horarios:* Todos los días de 9:00 a 19:00 hs.\n"
            "Explora la ciudad de manera cómoda y divertida.\n\n"
            "¿En qué te podemos ayudar hoy?"
        )
        buttons = [
            (PAYLOAD_PLANES, "Ver Planes 🚲"),
            (PAYLOAD_RESERVAR, "Cómo Reservar 📝"),
            (PAYLOAD_UBICACION, "Ubicación 📍")
        ]
        send_buttons(sender, welcome_text, buttons)
        return

    # 2. Ver Planes (Eco vs Full)
    if payload == PAYLOAD_PLANES or "planes" in msg_text or "precio" in msg_text:
        text = (
            "Tenemos dos modalidades principales:\n\n"
            "🔵 *Modo ECO*: Bicis de Aluminio o Acero. Se retiran y devuelven en nuestra Central. Sin cobertura de asistencia.\n\n"
            "🔴 *Modo FULL*: (+$10.000) Incluye entrega y retiro en tu ubicación + Servicio de Asistencia durante el paseo."
        )
        buttons = [
            (PAYLOAD_ECO, "Más sobre ECO"),
            (PAYLOAD_FULL, "Más sobre FULL"),
            (PAYLOAD_RESERVAR, "Quiero Reservar")
        ]
        send_buttons(sender, text, buttons)
        return

    # 3. Detalle Eco
    if payload == PAYLOAD_ECO:
        text = (
            "*Modo ECO* 🌿\n\n"
            "👉 Ideal si vienes a buscar la bici.\n"
            "✅ Opciones: Bicis Aluminio (Azul) o Acero (Amarillo).\n"
            "📍 *Condición:* Retiro y devolución en nuestra Central.\n"
            "❌ No incluye asistencia en calle."
        )
        buttons = [
            (PAYLOAD_RESERVAR, "Reservar ECO"),
            (PAYLOAD_PLANES, "Ver otras opciones")
        ]
        send_buttons(sender, text, buttons)
        return

    # 4. Detalle Full
    if payload == PAYLOAD_FULL:
        text = (
            "*Modo FULL* 🚀\n\n"
            "👉 ¡Relájate, nosotros nos encargamos!\n"
            "💵 Costo adicional: +$10.000 pesos.\n"
            "✅ *Incluye:* Entrega y retiro donde te encuentres (alojamiento).\n"
            "🛠️ *Cobertura:* Asistencia mecánica durante todo el alquiler."
        )
        buttons = [
            (PAYLOAD_RESERVAR, "Reservar FULL"),
            (PAYLOAD_PLANES, "Ver otras opciones")
        ]
        send_buttons(sender, text, buttons)
        return

    # 5. Cómo Reservar
    if payload == PAYLOAD_RESERVAR or "reservar" in msg_text:
        # 1. Enviar Link de Reserva
        link_text = (
            "📝 *Reserva Online*\n\n"
            "Para gestionar tu reserva de forma rápida, ingresa aquí:\n"
            "👉 http://localhost:5000/reserva \n\n"
            "(Completa el formulario y tu reserva quedará agendada)"
        )
        send_text(sender, link_text)
        
        # 2. Volver al Menú Principal
        menu_text = "¿Te gustaría consultar algo más?"
        buttons = [
            (PAYLOAD_PLANES, "Ver Planes 🚲"),
            (PAYLOAD_RESERVAR, "Cómo Reservar 📝"),
            (PAYLOAD_UBICACION, "Ubicación 📍")
        ]
        send_buttons(sender, menu_text, buttons)
        return

    # 6. Datos de Pago
    if payload == PAYLOAD_PAGO or "cbu" in msg_text or "alias" in msg_text or "pago" in msg_text:
        text = (
            "🏦 *Datos Bancarios para la Seña:*\n\n"
            "🔹 *Banco:* Francés BBVA\n"
            "🔹 *Titular:* Lucas Brunazzi\n"
            "🔹 *Alias:* BICISI.26\n"
            "🔹 *CBU:* 0170274540000002278483\n"
            "🔹 *Cuenta:* 274-22784/8\n\n"
            "⚠️ *Importante:* Envía el comprobante por aquí para agendar tu bici."
        )
        send_text(sender, text)
        return

    # 7. Ubicación
    if payload == PAYLOAD_UBICACION or "ubicación" in msg_text or "donde estan" in msg_text:
        text = (
            "📍 *Nuestra Ubicación Central:*\n\n"
            "Estamos listos para recibirte. \nhttps://maps.app.goo.gl/PseNUb16SX2tSZjS9\n"
            "¡Te esperamos!"
        )
        buttons = [(PAYLOAD_MENU, "Volver al Menú")]
        send_buttons(sender, text, buttons)
        return

    # Respuesta por defecto si no entiende
    default_text = "No entendí tu mensaje. Por favor selecciona una opción:"
    buttons = [
        (PAYLOAD_MENU, "Ir al Menú"),
        (PAYLOAD_RESERVAR, "Ayuda / Reservar")
    ]
    send_buttons(sender, default_text, buttons)


@app.route("/webhook", methods=["GET"])
def verify():
    # Verificación del token de Facebook
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def receive():
    data = request.get_json()
    # print(f"Recibido: {data}") # Log raw eliminado para limpieza


    try:
        # Verifica si es un mensaje de WhatsApp válido
        if data.get("object") == "whatsapp_business_account":
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value:
                        for msg in value["messages"]:
                            sender = msg["from"]
                            msg_type = msg["type"]
                            
                            # Evita responder a estados o mensajes viejos si es necesario
                            # Aquí procesamos texto e interactivos
                            handle_incoming_message(sender, msg, msg_type)

        return jsonify(status="ok"), 200

    except Exception as e:
        print(f"Error en webhook: {e}")
        return jsonify(status="error"), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
