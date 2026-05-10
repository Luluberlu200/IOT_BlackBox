# Projet IoT — BlackBox ISEN

## `code_principale2.py` — Raspberry Pi

Code à déployer sur la Raspberry Pi.

- Lit les capteurs (gaz, ultrason, accéléromètre, potentiomètre)
- Publie les données sur MQTT (`isen/blackbox`)
- Écoute les commandes MQTT (`isen/blackbox/commandes`)
- Gère les alarmes (LED, buzzer, LCD)

```bash
python code_principale2.py
```

---

## `dashboard.py` — PC (tour de contrôle)

À lancer sur **ta machine**. Démarre un site web local et un client MQTT.

- Affiche les données des capteurs en temps réel
- Permet d'envoyer la commande `ATTERRISSAGE_INTERDIT`
- Se connecte au broker HiveMQ (`broker.hivemq.com:1883`)

```bash
python dashboard.py
```

Puis ouvrir : [http://localhost:5000](http://localhost:5000)
