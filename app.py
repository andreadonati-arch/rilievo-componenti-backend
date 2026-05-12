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

def diametro_contorno(contorno):
    (x, y), raggio = cv2.minEnclosingCircle(contorno)
    return {
        "centro_x_pixel": float(x),
        "centro_y_pixel": float(y),
        "raggio_pixel": float(raggio),
        "diametro_pixel": float(raggio * 2),
        "area_pixel": float(cv2.contourArea(contorno))
    }

def analizza_immagine(percorso_file, quota_nota_mm, tipo_quota_nota, tipo_componente):
    immagine = cv2.imread(percorso_file)

    if immagine is None:
        raise ValueError("Impossibile leggere l'immagine con OpenCV")

    grigio = cv2.cvtColor(immagine, cv2.COLOR_BGR2GRAY)
    sfocata = cv2.GaussianBlur(grigio, (7, 7), 0)

    bordi = cv2.Canny(sfocata, 35, 120)

    kernel = np.ones((3, 3), np.uint8)
    bordi = cv2.dilate(bordi, kernel, iterations=1)

    contorni, gerarchia = cv2.findContours(
        bordi,
        cv2.RETR_TREE,
        cv2.CHAIN_APPROX_SIMPLE
    )

    if not contorni:
        raise ValueError("Nessun contorno rilevato")

    contorni_validi = []
    for idx, contorno in enumerate(contorni):
        area = cv2.contourArea(contorno)
        if area >= 40:
            contorni_validi.append((idx, contorno, area))

    if not contorni_validi:
        raise ValueError("Nessun contorno valido rilevato")

    contorni_validi.sort(key=lambda item: item[2], reverse=True)

    contorno_esterno = contorni_validi[0][1]
    esterno = diametro_contorno(contorno_esterno)

    diametro_esterno_pixel = esterno["diametro_pixel"]

    if diametro_esterno_pixel <= 0:
        raise ValueError("Diametro esterno in pixel non valido")

    scala_mm_per_pixel = quota_nota_mm / diametro_esterno_pixel

    diametro_interno_pixel = None
    diametro_interno_stimato_mm = None
    candidati_debug = []

    if str(tipo_componente or "").strip().lower() in ["anello", "tubo", "flangia"]:
        candidati_interni = []

        centro_esterno = np.array([
            esterno["centro_x_pixel"],
            esterno["centro_y_pixel"]
        ])

        for idx, contorno, area in contorni_validi[1:]:
            info = diametro_contorno(contorno)
            diametro = info["diametro_pixel"]

            if diametro <= 0:
                continue

            centro = np.array([
                info["centro_x_pixel"],
                info["centro_y_pixel"]
            ])

            distanza_centri = np.linalg.norm(centro - centro_esterno)
            rapporto_diametro = diametro / diametro_esterno_pixel
            rapporto_area = area / esterno["area_pixel"] if esterno["area_pixel"] else 0

            candidati_debug.append({
                "diametro_pixel": round(diametro, 2),
                "area_pixel": round(area, 2),
                "rapporto_diametro": round(rapporto_diametro, 3),
                "rapporto_area": round(rapporto_area, 3),
                "distanza_centri": round(float(distanza_centri), 2)
            })

            if rapporto_diametro >= 0.98:
                continue

            if rapporto_diametro <= 0.05:
                continue

            if distanza_centri > diametro_esterno_pixel * 0.60:
                continue

            candidati_interni.append((area, info))

        if candidati_interni:
            candidati_interni.sort(key=lambda item: item[0], reverse=True)
            interno = candidati_interni[0][1]
            diametro_interno_pixel = interno["diametro_pixel"]
            diametro_interno_stimato_mm = diametro_interno_pixel * scala_mm_per_pixel

    risultato = {
        "diametro_esterno_pixel": round(diametro_esterno_pixel, 2),
        "raggio_esterno_pixel": round(esterno["raggio_pixel"], 2),
        "centro_esterno_x_pixel": round(esterno["centro_x_pixel"], 2),
        "centro_esterno_y_pixel": round(esterno["centro_y_pixel"], 2),
        "area_contorno_esterno_pixel": round(esterno["area_pixel"], 2),
        "scala_mm_per_pixel": round(scala_mm_per_pixel, 6),
        "diametro_stimato_mm": round(diametro_esterno_pixel * scala_mm_per_pixel, 2),
        "diametro_interno_pixel": round(diametro_interno_pixel, 2) if diametro_interno_pixel else None,
        "diametro_interno_stimato_mm": round(diametro_interno_stimato_mm, 2) if diametro_interno_stimato_mm else None,
        "numero_contorni_validi": len(contorni_validi),
        "candidati_interni_debug": candidati_debug[:10]
    }

    return risultato

@app.route('/rilievo', methods=['POST'])
def rilievo():

    temp_file_path = None

    try:
        data = request.get_json()

        print("Nuovo rilievo ricevuto")
        print(data)

        foto_url = data.get("foto")
        quota_nota_mm = parse_numero_italiano(data.get("quota_nota_mm"))
        tipo_quota_nota = data.get("tipo_quota_nota")
        tipo_componente = data.get("tipo_componente")

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

        risultato = analizza_immagine(
            temp_file_path,
            quota_nota_mm,
            tipo_quota_nota,
            tipo_componente
        )

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
