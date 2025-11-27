import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
from werkzeug.utils import secure_filename
from sqlalchemy import desc, asc

load_dotenv()

app = Flask(__name__)

# --- アップロード設定 ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS_PLANNER = {'pdf', 'txt', 'doc', 'docx'}
ALLOWED_EXTENSIONS_DESIGNER = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_EXTENSIONS_VIDEO = {'mp4', 'webm', 'mov'} 
ALLOWED_EXTENSIONS_DESIGNER.update(ALLOWED_EXTENSIONS_VIDEO)
ALLOWED_EXTENSIONS_PROGRAMMER = ALLOWED_EXTENSIONS_VIDEO.copy() # 動画のみを許可

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'your_secret_key'

def allowed_file(filename, category):
    """ファイル名が、担当職種で許可された拡張子かチェックする関数"""
    allowed_extensions = set()
    if category == 'プランナー':
        allowed_extensions = ALLOWED_EXTENSIONS_PLANNER
    elif category == 'デザイナー':
        allowed_extensions = ALLOWED_EXTENSIONS_DESIGNER
    elif category == 'プログラマー':
        allowed_extensions = ALLOWED_EXTENSIONS_PROGRAMMER
    
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def is_video_file(filename):
    """ファイル名が動画形式かどうかを判定します。"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_VIDEO

# この関数をHTMLテンプレート内で使えるように登録
@app.context_processor
def utility_processor():
    return dict(is_video_file=is_video_file)

# --- データベース設定 ---
db_url = os.environ.get('DATABASE_URL')
if not db_url:
    raise ValueError("DATABASE_URLが.envファイルに設定されていません。")
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 選択肢の定義 ---
TASK_STATUSES = ['ToDo', 'InProgress', 'Review', 'Done']
TASK_CATEGORIES = ['プランナー', 'デザイナー', 'プログラマー']

# --- モデル定義 ---
class TaskItem(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='ToDo')
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    due_date = db.Column(db.Date, nullable=True)
    category = db.Column(db.String(50), nullable=False, default='プログラマー')
    files = db.relationship('UploadedFile', backref='task', lazy=True, cascade="all, delete-orphan")

class UploadedFile(db.Model):
    __tablename__ = 'uploaded_files'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# --- ルート（URL）とビュー関数 ---
@app.route('/')
def home():
    sort_orders = {
        'プランナー': request.args.get('sort_planner', 'upload_date_desc'),
        'デザイナー': request.args.get('sort_designer', 'created_at_desc'),
        'プログラマー': request.args.get('sort_programmer', 'due_date_asc'),
    }

    tasks_by_category = {category: [] for category in TASK_CATEGORIES}
    
    for category in TASK_CATEGORIES:
        query = TaskItem.query.filter_by(category=category)
        sort_key = sort_orders[category]

        if category == 'プランナー':
            query = query.join(TaskItem.files, isouter=True).group_by(TaskItem.id)
            if sort_key == 'upload_date_desc':
                query = query.order_by(desc(db.func.max(UploadedFile.uploaded_at)))
            elif sort_key == 'upload_date_asc':
                query = query.order_by(asc(db.func.max(UploadedFile.uploaded_at)))
            elif sort_key == 'title_asc':
                query = query.order_by(asc(TaskItem.title))
        elif category == 'デザイナー':
            if sort_key == 'created_at_desc':
                query = query.order_by(desc(TaskItem.created_at))
            elif sort_key == 'created_at_asc':
                query = query.order_by(asc(TaskItem.created_at))
            elif sort_key == 'title_asc':
                query = query.order_by(asc(TaskItem.title))
        elif category == 'プログラマー':
            if sort_key == 'due_date_asc':
                query = query.order_by(TaskItem.due_date.asc().nulls_last())
            elif sort_key == 'due_date_desc':
                query = query.order_by(TaskItem.due_date.desc().nulls_first())
            elif sort_key == 'status_asc':
                query = query.order_by(asc(TaskItem.status))
        
        tasks_by_category[category] = query.all()

        if category == 'プランナー':
            for task in tasks_by_category[category]:
                latest_file = UploadedFile.query.filter_by(task_id=task.id).order_by(desc(UploadedFile.uploaded_at)).first()
                task.latest_upload_date = latest_file.uploaded_at if latest_file else None

    return render_template('index.html', tasks=tasks_by_category, task_statuses=TASK_STATUSES, task_categories=TASK_CATEGORIES, sort_orders=sort_orders)

@app.route('/add', methods=['POST'])
def add_task():
    title = request.form.get('title')
    description = request.form.get('description')
    category = request.form.get('category')
    due_date_str = request.form.get('due_date')

    if title and category in TASK_CATEGORIES:
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        new_task = TaskItem(title=title, description=description, category=category, due_date=due_date)
        db.session.add(new_task)
        db.session.commit()
    return redirect(url_for('home', **request.args))

@app.route('/upload/<int:task_id>', methods=['POST'])
def upload_file(task_id):
    task = TaskItem.query.get_or_404(task_id)
    if 'file' not in request.files:
        flash('ファイルが選択されていません')
        return redirect(url_for('home', **request.args))
    
    file = request.files['file']
    if file.filename == '':
        flash('ファイル名がありません')
        return redirect(url_for('home', **request.args))

    if file and allowed_file(file.filename, task.category):
        filename = secure_filename(file.filename)
        unique_filename = f"{int(datetime.now().timestamp())}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
        
        new_file = UploadedFile(filename=unique_filename, task_id=task.id)
        db.session.add(new_file)
        db.session.commit()
    else:
        flash('許可されていないファイル形式です')
    return redirect(url_for('home', **request.args))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/delete/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    task = TaskItem.query.get_or_404(task_id)
    for file in task.files:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for('home', **request.args))

@app.route('/update/status/<int:task_id>', methods=['POST'])
def update_status(task_id):
    task = TaskItem.query.get_or_404(task_id)
    new_status = request.form.get('status')
    if new_status in TASK_STATUSES:
        task.status = new_status
        db.session.commit()
    return redirect(url_for('home', **request.args))

# --- カスタムコマンド ---
@app.cli.command('db-init')
def db_init():
    with app.app_context():
        db.create_all()
    print("データベースの初期化が完了しました。")

# --- 実行ブロック ---
if __name__ == '__main__':
    app.run(debug=True)