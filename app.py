from flask import Flask, request, jsonify

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

        return jsonify({
            "status": "ok",
            "message": "Rilievo ricevuto correttamente"
        })

    except Exception as error:

        return jsonify({
            "status": "errore",
            "message": str(error)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
