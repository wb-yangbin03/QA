from flask import Flask, request, redirect, url_for, render_template, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
import os
from werkzeug.utils import secure_filename
from datetime import datetime
import time
import webbrowser
import threading
import socket
import sys
#------------
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
TEXT_SAVE_FOLDER = 'saved_texts'
socketio = SocketIO(app, cors_allowed_origins='*')  # 支持跨设备连接
MAX_FILES = 5
shared_text = ''

# 创建上传目录（如果不存在）
for folder in [app.config['UPLOAD_FOLDER'], TEXT_SAVE_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)


def format_size(bytes_size):
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size/1024:.1f} KB"
    else:
        return f"{bytes_size/1024/1024:.1f} MB"


def format_time(ts):
    diff = time.time() - ts
    if diff < 60:
        return "刚刚"
    elif diff < 3600:
        return f"{int(diff/60)} 分钟前"
    elif diff < 86400:
        return f"{int(diff/3600)} 小时前"
    else:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    return ip

def get_files_info():
    files = []
    for fname in sorted(os.listdir(app.config['UPLOAD_FOLDER']),
                        key=lambda f: os.path.getmtime(os.path.join(app.config['UPLOAD_FOLDER'], f)), reverse=True):
        path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
        size = os.path.getsize(path)
        mtime = os.path.getmtime(path)
        files.append({
            'name': fname,
            'size': format_size(size),
            'time': format_time(mtime),
            'timestamp': int(mtime)
        })
    return files[:MAX_FILES]


def get_saved_texts():
    file_list = []
    for fname in sorted(os.listdir(TEXT_SAVE_FOLDER),
                        key=lambda f: os.path.getmtime(os.path.join(TEXT_SAVE_FOLDER, f)), reverse=True):
        fpath = os.path.join(TEXT_SAVE_FOLDER, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
            timestamp = os.path.getmtime(fpath)
            file_list.append({
                'name': fname,
                'content': content,
                'time': datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M'),
                'url': url_for('download_text', filename=fname)
            })
        except Exception as e:
            continue
    return file_list[:10]

def open_browser():  #打开H5页面
    ip = get_local_ip()
    url = f"http://{ip}:5000"
    webbrowser.open(url)


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files['file']
        if file:
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)

            # 删除超出限制的最早文件
            files = sorted(os.listdir(app.config['UPLOAD_FOLDER']),
                           key=lambda f: os.path.getmtime(os.path.join(app.config['UPLOAD_FOLDER'], f)))
            if len(files) > MAX_FILES:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], files[0]))

            return redirect(url_for('index'))

    files_info = get_files_info()
    local_ip = get_local_ip()

    return render_template(
        'index.html',
        files=files_info,
        local_ip=local_ip
    )
 #   return render_template('index.html', files=files_info)



@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    try:
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(path):
            os.remove(path)
            return jsonify({'status': 'success'})
    except:
        pass
    return jsonify({'status': 'error'})


@app.route('/save_text', methods=['POST'])
def save_text():
    content = request.json.get('text', '')
    if not content.strip():
        return jsonify({'status': 'error', 'message': '内容为空'})

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"text_{timestamp}.txt"
    save_path = os.path.join(TEXT_SAVE_FOLDER, filename)
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # 限制最多10个
    files = sorted(os.listdir(TEXT_SAVE_FOLDER), key=lambda f: os.path.getmtime(os.path.join(TEXT_SAVE_FOLDER, f)))
    if len(files) > 10:
        os.remove(os.path.join(TEXT_SAVE_FOLDER, files[0]))

    return jsonify({'status': 'success'})

@app.route('/get_current_text')
def get_current_text():
    global shared_text
    return jsonify({'status': 'success', 'text': shared_text})


@app.route('/upload_bg', methods=['POST'])
def upload_bg():
    file = request.files.get('bg')
    if file:
        file.save(os.path.join('static', 'bg.jpg'))
        return 'ok'
    return 'no file', 400


@app.route('/update_saved_text/<filename>', methods=['POST'])
def update_saved_text(filename):
    """更新已保存的文本内容"""
    # 验证文件名安全性
    safe_filename = secure_filename(filename)
    if safe_filename != filename:
        return jsonify({'status': 'error', 'message': '文件名不合法'})

    # 获取新的文本内容
    new_content = request.json.get('text', '')
    file_path = os.path.join(TEXT_SAVE_FOLDER, filename)

    # 检查文件是否存在
    if not os.path.exists(file_path):
        return jsonify({'status': 'error', 'message': '文件不存在'})

    # 更新文件内容
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        # 更新文件修改时间，使其在列表中排序更合理
        os.utime(file_path)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/upload_file', methods=['POST'])
def upload_file():
    files = request.files.getlist('file')
    saved_count = 0

    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            saved_count += 1

    # 限制最多保存 MAX_FILES 个文件
    existing_files = sorted(
        os.listdir(app.config['UPLOAD_FOLDER']),
        key=lambda f: os.path.getmtime(os.path.join(app.config['UPLOAD_FOLDER'], f))
    )

    while len(existing_files) > MAX_FILES:
        to_delete = existing_files.pop(0)
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], to_delete))

    if saved_count > 0:
        return jsonify({'status': 'success', 'message': f'成功上传 {saved_count} 个文件'})

    return jsonify({'status': 'error', 'message': '未接收到文件'})


@app.route('/saved_texts')
def list_saved_texts():
    return jsonify(get_saved_texts())


@app.route('/saved_texts/<filename>')
def download_text(filename):
    return send_from_directory(TEXT_SAVE_FOLDER, filename, as_attachment=True)


@app.route('/delete_saved_text/<filename>', methods=['POST'])
def delete_saved_text(filename):
    path = os.path.join(TEXT_SAVE_FOLDER, filename)
    if os.path.exists(path):
        os.remove(path)
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'})


@socketio.on('text_update')
def handle_text_update(data):
    global shared_text
    shared_text = data
    emit('update_textbox', data, broadcast=True)


if __name__ == '__main__':
    threading.Timer(1, open_browser).start()  # 1秒后自动打开浏览器
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)

input("按回车退出")