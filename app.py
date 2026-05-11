from flask import Flask, request, jsonify
import requests
import tempfile
import os

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    return 'Backend rilievo componenti attivo'

@app.route('/rilievo', methods=['POST'])
def rilievo():

    try:
        data = request.get_json()

        print("Nuovo rilievo ricevuto")
        print(data)

        foto_url = data.get("foto")

        if not foto_url:
            return jsonify({
                "status": "errore",
                "message": "URL foto mancante"
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

        print("Immagine salvata in:")
        print(temp_file.name)

        file_size = os.path.getsize(temp_file.name)

        print("Dimensione file:")
        print(file_size)

        return jsonify({
            "status": "ok",
            "message": "Immagine scaricata correttamente",
            "file_temporaneo": temp_file.name,
            "dimensione_file": file_size
        })

    except Exception as error:

        print(error)

        return jsonify({
            "status": "errore",
            "message": str(error)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
