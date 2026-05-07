from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ..models import KnowledgeArticle, Category, User
from .. import db
from functools import wraps
from sqlalchemy import or_

knowledge_bp = Blueprint('knowledge', __name__, url_prefix='/knowledge')


def admin_or_manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['Admin', 'Manager']:
            flash('คุณไม่มีสิทธิ์เข้าถึงส่วนจัดการบทความ', 'danger')
            return redirect(url_for('knowledge.index'))
        return f(*args, **kwargs)
    return decorated_function


@knowledge_bp.route('/')
@login_required
def index():
    """หน้าหลัก Knowledge Base - ค้นหาและดูบทความ"""
    search = request.args.get('search', '').strip()
    category_id = request.args.get('category', type=int)

    query = KnowledgeArticle.query.filter_by(is_published=True)

    if search:
        query = query.filter(
            or_(
                KnowledgeArticle.title.ilike(f'%{search}%'),
                KnowledgeArticle.content.ilike(f'%{search}%')
            )
        )
    if category_id:
        query = query.filter_by(category_id=category_id)

    articles = query.order_by(KnowledgeArticle.created_at.desc()).all()
    categories = Category.query.all()

    # ดึงบทความยอดฮิต 5 อันดับ
    popular_articles = KnowledgeArticle.query.filter_by(is_published=True)\
        .order_by(KnowledgeArticle.view_count.desc()).limit(5).all()

    return render_template('knowledge_list.html', 
                           articles=articles, 
                           categories=categories, 
                           search=search, 
                           category_filter=category_id,
                           popular_articles=popular_articles)


@knowledge_bp.route('/<int:article_id>')
@login_required
def view(article_id):
    """ดูรายละเอียดบทความ"""
    article = KnowledgeArticle.query.get_or_404(article_id)
    
    if not article.is_published and current_user.role not in ['Admin', 'Manager']:
        flash('บทความนี้ยังไม่เปิดให้อ่าน', 'warning')
        return redirect(url_for('knowledge.index'))

    # เพิ่มยอดวิว
    article.view_count += 1
    db.session.commit()

    return render_template('knowledge_view.html', article=article)


@knowledge_bp.route('/manage')
@login_required
@admin_or_manager_required
def manage():
    """จัดการบทความ (Admin/Manager)"""
    articles = KnowledgeArticle.query.order_by(KnowledgeArticle.created_at.desc()).all()
    return render_template('knowledge_manage.html', articles=articles)


@knowledge_bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_or_manager_required
def create():
    """สร้างบทความใหม่"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        category_id = request.form.get('category_id', type=int)
        is_published = request.form.get('is_published') == '1'

        if not title or not content:
            flash('กรุณากรอกหัวข้อและเนื้อหา', 'danger')
            return redirect(url_for('knowledge.create'))

        article = KnowledgeArticle(
            title=title,
            content=content,
            category_id=category_id,
            author_id=current_user.id,
            is_published=is_published
        )
        db.session.add(article)
        db.session.commit()
        
        flash('สร้างบทความสำเร็จ', 'success')
        return redirect(url_for('knowledge.manage'))

    categories = Category.query.all()
    return render_template('knowledge_form.html', categories=categories, action='create')


@knowledge_bp.route('/<int:article_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_or_manager_required
def edit(article_id):
    """แก้ไขบทความ"""
    article = KnowledgeArticle.query.get_or_404(article_id)

    if request.method == 'POST':
        article.title = request.form.get('title', '').strip()
        article.content = request.form.get('content', '').strip()
        article.category_id = request.form.get('category_id', type=int)
        article.is_published = request.form.get('is_published') == '1'

        if not article.title or not article.content:
            flash('กรุณากรอกหัวข้อและเนื้อหา', 'danger')
            return redirect(url_for('knowledge.edit', article_id=article.id))

        db.session.commit()
        flash('บันทึกการแก้ไขบทความสำเร็จ', 'success')
        return redirect(url_for('knowledge.manage'))

    categories = Category.query.all()
    return render_template('knowledge_form.html', article=article, categories=categories, action='edit')


@knowledge_bp.route('/<int:article_id>/delete', methods=['POST'])
@login_required
@admin_or_manager_required
def delete(article_id):
    """ลบบทความ"""
    article = KnowledgeArticle.query.get_or_404(article_id)
    db.session.delete(article)
    db.session.commit()
    flash('ลบบทความเรียบร้อยแล้ว', 'success')
    return redirect(url_for('knowledge.manage'))
