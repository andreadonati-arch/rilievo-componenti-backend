from flask import Flask, request, jsonify
import requests
import tempfile
import os
import cv2
import numpy as np

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    return 'Backend rilievo componenti attivo'

def parse_numero_italiano(valore):
    if valore is None:
        return None

    testo = str(valore).strip()
    testo = testo.replace(",", ".")

    try:
        return float(testo)
    except ValueError:
        return None

def analizza_immagine(percorso_file, quota_nota_mm):
    immagine = cv2.imread(percorso_file)

    if immagine is None:
        raise ValueError("Impossibile leggere l'immagine con OpenCV")

    grigio = cv2.cvtColor(immagine, cv2.COLOR_BGR2GRAY)
    sfocata = cv2.GaussianBlur(grigio, (7, 7), 0)

    bordi = cv2.Canny(sfocata, 50, 150)

    contorni, _ = cv2.findContours(
        bordi,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    if not contorni:
        raise ValueError("Nessun contorno rilevato")

    contorno_principale = max(contorni, key=cv2.contourArea)
    area = cv2.contourArea(contorno_principale)

    if area < 100:
        raise ValueError("Contorno troppo piccolo o immagine non valida")

    (x, y), raggio = cv2.minEnclosingCircle(contorno_principale)

    diametro_pixel = raggio * 2

    if diametro_pixel <= 0:
        raise ValueError("Diametro in pixel non valido")

    scala_mm_per_pixel = quota_nota_mm / diametro_pixel

    return {
        "diametro_pixel": round(diametro_pixel, 2),
        "raggio_pixel": round(raggio, 2),
        "centro_x_pixel": round(x, 2),
        "centro_y_pixel": round(y, 2),
        "area_contorno_pixel": round(area, 2),
        "scala_mm_per_pixel": round(scala_mm_per_pixel, 6),
        "diametro_stimato_mm": round(diametro_pixel * scala_mm_per_pixel, 2)
    }

@app.route('/rilievo', methods=['POST'])
def rilievo():

    temp_file_path = None

    try:
        data = request.get_json()

        print("Nuovo rilievo ricevuto")
        print(data)

        foto_url = data.get("foto")
        quota_nota_mm = parse_numero_italiano(data.get("quota_nota_mm"))

        if not foto_url:
            return jsonify({
                "status": "errore",
                "message": "URL foto mancante"
            }), 400

        if quota_nota_mm is None or quota_nota_mm <= 0:
            return jsonify({
                "status": "errore",
                "message": "Quota nota non valida"
            }), 400

        response = requests.get(foto_url)

        if response.status_code != 200:
            return jsonify({
                "status": "errore",
                "message": "Impossibile scaricare immagine"
            }), 500

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        temp_file.write(response.content)
        temp_file.close()

        temp_file_path = temp_file.name

        print("Immagine salvata in:")
        print(temp_file_path)

        file_size = os.path.getsize(temp_file_path)

        print("Dimensione file:")
        print(file_size)

        risultato = analizza_immagine(temp_file_path, quota_nota_mm)

        print("Risultato analisi OpenCV:")
        print(risultato)

        return jsonify({
            "status": "ok",
            "message": "Analisi immagine completata",
            "dimensione_file": file_size,
            "quota_nota_mm": quota_nota_mm,
            "risultato": risultato
        })

    except Exception as error:

        print(error)

        return jsonify({
            "status": "errore",
            "message": str(error)
        }), 500

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
