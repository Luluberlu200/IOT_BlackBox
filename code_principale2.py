#!/usr/bin/env python

import time
import json
import threading
import smbus as smsbus2
from grovepi import *
from grove_rgb_lcd import *
import paho.mqtt.client as mqtt


# ==============================
# CONFIGURATION GENERALE
# ==============================

GAS_SENSOR = 0          # A0
POTENTIOMETRE = 1       # A1
LED_ROUGE = 3           # D3
BUZZER = 4              # D4
ULTRASON = 8            # D8

SEUIL_GAZ = 250
SEUIL_CHUTE = 0.5

BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "isen/blackbox"
TOPIC_COMMANDES = "isen/blackbox/commandes"

ADDR_ACCEL = 0x19
CTRL_REG1 = 0x20
CTRL_REG4 = 0x23
OUT_X_L = 0x28

VITESSE_LCD = {
    "moteur_arrete": "MOTEUR ARRETE",
    "ralenti": "RALENTI      ",
    "vitesse_normale": "VIT. NORMALE ",
    "acceleration": "ACCELERATION ",
    "pleine_puissance": "PLEINE PUISS."
}

commande_recue = threading.Event()
lcd_alerte_jusqu_a = 0
bus_i2c = None
accel_ok = False


# ==============================
# INITIALISATION
# ==============================

def initialiser_grovepi():
    pinMode(GAS_SENSOR, "INPUT")
    pinMode(POTENTIOMETRE, "INPUT")
    pinMode(LED_ROUGE, "OUTPUT")
    pinMode(BUZZER, "OUTPUT")


def initialiser_lcd():
    setRGB(0, 128, 64)
    setText("BlackBox ISEN\n")


def initialiser_accelerometre():
    global bus_i2c

    try:
        bus_i2c = smbus2.SMBus(1)
        bus_i2c.write_byte_data(ADDR_ACCEL, CTRL_REG1, 0x57)
        bus_i2c.write_byte_data(ADDR_ACCEL, CTRL_REG4, 0x88)
        time.sleep(0.1)

        print("LIS3DHTR initialise (seuil chute < {} g)".format(SEUIL_CHUTE))
        return True

    except Exception as e:
        print("Accelerometre non disponible :", e)
        return False


# ==============================
# MQTT
# ==============================

def on_connect(client, *_):
    client.subscribe(TOPIC_COMMANDES)


def on_message(_client, _userdata, msg):
    try:
        data = json.loads(msg.payload.decode())

        if data.get("commande") == "ATTERRISSAGE_INTERDIT":
            print("\n" + "=" * 50)
            print("  COMMANDE TOUR : ATTERRISSAGE INTERDIT")
            print("  Raison   :", data.get("raison", "—"))
            print("  Severite :", data.get("severite", "—"))
            print("  Source   :", data.get("source", "—"))
            print("=" * 50 + "\n")

            commande_recue.set()

    except Exception as e:
        print("Erreur commande :", e)


def initialiser_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    client.loop_start()
    return client


# ==============================
# LECTURE DES CAPTEURS
# ==============================

def lire_z_accel():
    data = bus_i2c.read_i2c_block_data(ADDR_ACCEL, OUT_X_L | 0x80, 6)

    val = (data[5] << 8) | data[4]

    if val >= 0x8000:
        val -= 0x10000

    return (val >> 4) * 0.001


def lire_distance():
    try:
        return ultrasonicRead(ULTRASON)
    except Exception:
        return -1


def lire_accelerometre():
    if not accel_ok:
        return None, False

    try:
        z_accel = lire_z_accel()
        chute = z_accel < SEUIL_CHUTE
        return z_accel, chute

    except Exception:
        return None, False


def lire_potentiometre():
    potar_brut = analogRead(POTENTIOMETRE)
    potar_pct = round((potar_brut / 1023.0) * 100, 1)
    return potar_pct


def determiner_vitesse(potar_pct):
    if potar_pct < 10:
        return "moteur_arrete"
    elif potar_pct < 30:
        return "ralenti"
    elif potar_pct < 60:
        return "vitesse_normale"
    elif potar_pct < 85:
        return "acceleration"
    else:
        return "pleine_puissance"


def lire_capteurs():
    gas_value = analogRead(GAS_SENSOR)
    distance = lire_distance()
    z_accel, chute = lire_accelerometre()
    potar_pct = lire_potentiometre()
    vitesse = determiner_vitesse(potar_pct)

    return gas_value, distance, z_accel, chute, potar_pct, vitesse


# ==============================
# ALARMES
# ==============================

def gerer_alarme_gaz(gas_value):
    if gas_value >= SEUIL_GAZ:
        digitalWrite(BUZZER, 1)
        digitalWrite(LED_ROUGE, 1)
        return "alerte_gaz", True

    digitalWrite(BUZZER, 0)
    digitalWrite(LED_ROUGE, 0)
    return "normal", False


def faire_bips(nombre, duree_on, duree_off):
    for _ in range(nombre):
        digitalWrite(LED_ROUGE, 1)
        digitalWrite(BUZZER, 1)
        time.sleep(duree_on)

        digitalWrite(LED_ROUGE, 0)
        digitalWrite(BUZZER, 0)
        time.sleep(duree_off)


def gerer_commande_atterrissage():
    global lcd_alerte_jusqu_a

    if commande_recue.is_set():
        commande_recue.clear()

        print(">>> ATTERRISSAGE INTERDIT : LED rouge activee <<<")

        lcd_alerte_jusqu_a = time.time() + 10

        setRGB(255, 0, 0)
        setText("ATTERRISSAGE\nINTERDIT !!!")

        faire_bips(3, 0.25, 0.15)

        digitalWrite(LED_ROUGE, 1)


def gerer_chute(chute, z_accel, alarme):
    global lcd_alerte_jusqu_a

    if chute and time.time() >= lcd_alerte_jusqu_a:
        print(">>> CHUTE DETECTEE : Z = {:+.3f} g <<<".format(z_accel))

        lcd_alerte_jusqu_a = time.time() + 3

        setRGB(255, 128, 0)
        setText("CHUTE DETECTEE\nZ:{:+.3f}g".format(z_accel))

        if not alarme:
            faire_bips(2, 0.1, 0.1)


# ==============================
# LCD
# ==============================

def afficher_lcd_normal(gas_value, distance, vitesse, alarme):
    if time.time() < lcd_alerte_jusqu_a:
        return

    if distance >= 0:
        d_str = "{:3d}cm".format(distance)
    else:
        d_str = " ERR"

    ligne1 = "G:{:4d} D:{}".format(gas_value, d_str)
    ligne2 = VITESSE_LCD.get(vitesse, vitesse)[:16]

    if alarme:
        setRGB(255, 0, 0)
    else:
        setRGB(0, 128, 64)

    setText(ligne1 + "\n" + ligne2)


# ==============================
# JSON / MQTT
# ==============================

def creer_payload(gas_value, etat_air, alarme, potar_pct, vitesse, distance, z_accel, chute):
    data = {
        "capteur": "gas_sensor_v1_5",
        "gaz": gas_value,
        "etat_air": etat_air,
        "alarme": alarme,
        "accelerateur": potar_pct,
        "vitesse": vitesse,
        "distance": distance,
        "z_accel": z_accel,
        "chute": chute
    }

    return json.dumps(data)


def envoyer_donnees(client, payload):
    client.publish(TOPIC, payload)
    print("Donnees envoyees :", payload)


# ==============================
# ARRET PROPRE
# ==============================

def arreter_programme(client):
    digitalWrite(LED_ROUGE, 0)
    digitalWrite(BUZZER, 0)
    setText("")
    setRGB(0, 0, 0)

    client.loop_stop()
    client.disconnect()

    print("Arret du programme")


# ==============================
# PROGRAMME PRINCIPAL
# ==============================

def main():
    global accel_ok

    initialiser_grovepi()
    initialiser_lcd()

    accel_ok = initialiser_accelerometre()

    client = initialiser_mqtt()

    time.sleep(1)

    while True:
        try:
            gas_value, distance, z_accel, chute, potar_pct, vitesse = lire_capteurs()

            etat_air, alarme = gerer_alarme_gaz(gas_value)

            payload = creer_payload(
                gas_value,
                etat_air,
                alarme,
                potar_pct,
                vitesse,
                distance,
                z_accel,
                chute
            )

            envoyer_donnees(client, payload)

            gerer_commande_atterrissage()
            gerer_chute(chute, z_accel, alarme)

            afficher_lcd_normal(gas_value, distance, vitesse, alarme)

            time.sleep(1)

        except KeyboardInterrupt:
            arreter_programme(client)
            break

        except IOError:
            print("Erreur capteur")


if __name__ == "__main__":
    main()