from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__, static_folder='../frontend')
CORS(app, supports_credentials=True)  # 允许跨域请求并支持credentials

# 设置应用密钥（用于session加密）
app.secret_key = 'qwertyuioplmnbvcxza'

# 登录检查装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated_function

# 数据库初始化
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 用户表
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 任务表
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            completed BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# 用户注册
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        c.execute('SELECT id FROM users WHERE username = ?', (username,))
        if c.fetchone():
            return jsonify({'error': '用户名已存在'}), 400
            
        password_hash = generate_password_hash(password)
        c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                 (username, password_hash))
        user_id = c.lastrowid
        
        # 为新用户创建空任务列表
        c.execute('INSERT INTO tasks (user_id, text, completed) VALUES (?, ?, ?)',
                 (user_id, '欢迎使用FocusFlow', False))
        
        conn.commit()
        
        session['user_id'] = user_id
        session['username'] = username
        
        return jsonify({
            'success': True,
            'message': '注册成功！欢迎使用FocusFlow',
            'user': {
                'id': user_id,
                'username': username
            }
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 用户登录
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        c.execute('SELECT id, username, password_hash FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        
        if not user or not check_password_hash(user[2], password):
            return jsonify({'error': '用户名或密码错误'}), 401
            
        session['user_id'] = user[0]
        session['username'] = user[1]
        
        return jsonify({
            'success': True,
            'user': {
                'id': user[0],
                'username': user[1]
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 用户登出
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

# 获取当前用户信息
@app.route('/api/me')
def get_current_user():
    if 'user_id' not in session:
        return jsonify({'error': '未登录'}), 401
    
    return jsonify({
        'id': session['user_id'],
        'username': session['username']
    })

# 任务同步接口
@app.route('/api/tasks', methods=['GET', 'POST'])
@login_required
def handle_tasks():
    user_id = session['user_id']
    
    # 从后端获取任务数据
    if request.method == 'GET':
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM tasks WHERE user_id = ? ORDER BY completed, created_at DESC', (user_id,))
        tasks = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(tasks)
    # 将任务数据传递到后端进行保存
    elif request.method == 'POST':
        data = request.get_json()
        if not data or 'tasks' not in data:
            return jsonify({'error': 'Invalid data'}), 400
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        
        try:
            c.execute('DELETE FROM tasks WHERE user_id = ?', (user_id,))
            
            for task in data['tasks']:
                c.execute('INSERT INTO tasks (user_id, text, completed) VALUES (?, ?, ?)',
                         (user_id, task['text'], task['completed']))
            
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()

# 更新或删除任务
@app.route('/api/tasks/<int:task_id>', methods=['PUT', 'DELETE'])
@login_required
def task_operations(task_id):
    user_id = session['user_id']
    
    # 添加任务
    if request.method == 'PUT':
        data = request.get_json()
        if 'completed' not in data:
            return jsonify({'error': 'Missing completed status'}), 400
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        
        try:
            c.execute('UPDATE tasks SET completed = ? WHERE id = ? AND user_id = ?', 
                     (data['completed'], task_id, user_id))
            
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()
    # 删除任务
    elif request.method == 'DELETE':
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        
        try:
            c.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (task_id, user_id))
            
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()

# 前端静态文件
@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')

# 音频文件服务
@app.route('/audio/<path:filename>')
def serve_audio(filename):
    return send_from_directory('../audio', filename)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)