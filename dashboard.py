from flask import Flask, render_template, jsonify, make_response
import json
import os
import time
import paho.mqtt.client as mqtt

app = Flask(__name__)
app.jinja_env.auto_reload = True

BROKER          = "broker.hivemq.com"
PORT            = 1883
TOPIC_COMMANDES = "isen/blackbox/commandes"

# Cherche logs.json dans le dossier courant ou le dossier parent
def get_log_path():
    if os.path.exists("logs.json"):
        return "logs.json"
    parent = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs.json")
    return parent

def read_logs():
    try:
        with open(get_log_path(), "r") as f:
            return json.load(f)
    except Exception:
        return []

@app.route("/")
def index():
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp

@app.route("/api/latest")
def latest():
    logs = read_logs()
    return jsonify(logs[-1] if logs else None)

@app.route("/api/logs")
def get_logs():
    logs = read_logs()
    return jsonify(logs[-120:] if len(logs) > 120 else logs)

@app.route("/api/commande/atterrissage", methods=["POST"])
def commande_atterrissage():
    try:
        payload = json.dumps({
            "commande"  : "ATTERRISSAGE_INTERDIT",
            "raison"    : "ZONE_CONTAMINEE",
            "severite"  : "CRITIQUE",
            "source"    : "TOUR_DE_CONTROLE",
            "timestamp" : time.time()
        })
        pub = mqtt.Client(client_id="dashboard-tour")
        pub.connect(BROKER, PORT, 10)
        pub.publish(TOPIC_COMMANDES, payload)
        pub.loop(1)
        pub.disconnect()
        return jsonify({"status": "ok", "message": "Commande transmise"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    print("Dashboard disponible sur http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
