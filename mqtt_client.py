import json
import time
import paho.mqtt.client as mqtt

BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "isen/blackbox"

LOG_FILE = "logs.json"

# ==============================
# FONCTION LOG (1 heure)
# ==============================

def sauvegarder_log(data):
    try:
        # Charger anciens logs
        try:
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
        except:
            logs = []

        # Ajouter timestamp
        data["timestamp"] = time.time()
        logs.append(data)

        # Garder seulement 1 heure
        maintenant = time.time()
        logs = [log for log in logs if maintenant - log["timestamp"] <= 3600]

        # Sauvegarder
        with open(LOG_FILE, "w") as f:
            json.dump(logs, f, indent=2)

    except Exception as e:
        print("Erreur log :", e)

# ==============================
# MQTT
# ==============================

def on_connect(client, userdata, flags, rc):
    print("Connecte au broker")
    client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        print("Donnees recues :", data)

        print("Gaz :", data["gaz"])
        print("Etat air :", data["etat_air"])
        print("Alarme :", data["alarme"])
        print("-----------------------")

        # Sauvegarde dans le fichier
        sauvegarder_log(data)

    except Exception as e:
        print("Erreur reception :", e)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)

client.loop_forever()