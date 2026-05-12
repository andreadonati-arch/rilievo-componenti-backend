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

def info_contorno(contorno):
    (x, y), raggio = cv2.minEnclosingCircle(contorno)
    area = cv2.contourArea(contorno)
    perimetro = cv2.arcLength(contorno, True)

    if perimetro > 0:
        circolarita = (4 * np.pi * area) / (perimetro * perimetro)
    else:
        circolarita = 0

    return {
        "centro_x_pixel": float(x),
        "centro_y_pixel": float(y),
        "raggio_pixel": float(raggio),
        "diametro_pixel": float(raggio * 2),
        "area_pixel": float(area),
        "perimetro_pixel": float(perimetro),
        "circolarita": float(circolarita)
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
        info = info_contorno(contorno)

        if info["area_pixel"] >= 40 and info["diametro_pixel"] > 0:
            contorni_validi.append((idx, contorno, info))

    if not contorni_validi:
        raise ValueError("Nessun contorno valido rilevato")

    contorni_validi.sort(key=lambda item: item[2]["area_pixel"], reverse=True)

    esterno = contorni_validi[0][2]
    diametro_esterno_pixel = esterno["diametro_pixel"]

    if diametro_esterno_pixel <= 0:
        raise ValueError("Diametro esterno in pixel non valido")

    scala_mm_per_pixel = quota_nota_mm / diametro_esterno_pixel

    centro_esterno = np.array([
        esterno["centro_x_pixel"],
        esterno["centro_y_pixel"]
    ])

    diametro_interno_pixel = None
    diametro_interno_stimato_mm = None
    candidato_scelto = None
    candidati_debug = []

    if str(tipo_componente or "").strip().lower() in ["anello", "tubo", "flangia"]:
        candidati_interni = []

        for idx, contorno, info in contorni_validi[1:]:
            diametro = info["diametro_pixel"]
            area = info["area_pixel"]
            circolarita = info["circolarita"]

            centro = np.array([
                info["centro_x_pixel"],
                info["centro_y_pixel"]
            ])

            distanza_centri = np.linalg.norm(centro - centro_esterno)
            rapporto_diametro = diametro / diametro_esterno_pixel
            rapporto_area = area / esterno["area_pixel"] if esterno["area_pixel"] else 0
            distanza_relativa = distanza_centri / diametro_esterno_pixel

            motivo_scarto = ""

            if rapporto_diametro >= 0.97:
                motivo_scarto = "troppo_simile_esterno"
            elif rapporto_diametro <= 0.03:
                motivo_scarto = "troppo_piccolo"
            elif distanza_relativa > 0.45:
                motivo_scarto = "troppo_decentrato"
            elif circolarita < 0.25:
                motivo_scarto = "poco_circolare"
            else:
                punteggio = (
                    (circolarita * 4.0)
                    - (distanza_relativa * 3.0)
                    + (min(rapporto_area, 0.8) * 0.5)
                )

                candidati_interni.append((punteggio, area, info))

            candidati_debug.append({
                "diametro_pixel": round(diametro, 2),
                "diametro_stimato_mm": round(diametro * scala_mm_per_pixel, 2),
                "area_pixel": round(area, 2),
                "rapporto_diametro": round(rapporto_diametro, 3),
                "rapporto_area": round(rapporto_area, 3),
                "distanza_centri": round(float(distanza_centri), 2),
                "distanza_relativa": round(float(distanza_relativa), 3),
                "circolarita": round(circolarita, 3),
                "motivo_scarto": motivo_scarto
            })

        if candidati_interni:
            candidati_interni.sort(key=lambda item: item[0], reverse=True)
            punteggio, area, interno = candidati_interni[0]

            candidato_scelto = {
                "punteggio": round(float(punteggio), 4),
                "diametro_pixel": round(interno["diametro_pixel"], 2),
                "diametro_stimato_mm": round(interno["diametro_pixel"] * scala_mm_per_pixel, 2),
                "circolarita": round(interno["circolarita"], 3),
                "area_pixel": round(interno["area_pixel"], 2)
            }

            diametro_interno_pixel = interno["diametro_pixel"]
            diametro_interno_stimato_mm = diametro_interno_pixel * scala_mm_per_pixel

    risultato = {
        "diametro_esterno_pixel": round(diametro_esterno_pixel, 2),
        "raggio_esterno_pixel": round(esterno["raggio_pixel"], 2),
        "centro_esterno_x_pixel": round(esterno["centro_x_pixel"], 2),
        "centro_esterno_y_pixel": round(esterno["centro_y_pixel"], 2),
        "area_contorno_esterno_pixel": round(esterno["area_pixel"], 2),
        "circolarita_esterno": round(esterno["circolarita"], 3),
        "scala_mm_per_pixel": round(scala_mm_per_pixel, 6),
        "diametro_stimato_mm": round(diametro_esterno_pixel * scala_mm_per_pixel, 2),
        "diametro_interno_pixel": round(diametro_interno_pixel, 2) if diametro_interno_pixel else None,
        "diametro_interno_stimato_mm": round(diametro_interno_stimato_mm, 2) if diametro_interno_stimato_mm else None,
        "numero_contorni_validi": len(contorni_validi),
        "candidato_interno_scelto": candidato_scelto,
        "candidati_interni_debug": candidati_debug[:15]
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
