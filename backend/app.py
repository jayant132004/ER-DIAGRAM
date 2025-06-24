from flask import Flask, request, jsonify, session
from flask_cors import CORS
import openai
import os
from dotenv import load_dotenv
import json
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import time
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True)  # Enable CORS for all routes
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'devsecret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)

# Initialize Flask-Limiter
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"])

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    queries = db.relationship('QueryHistory', backref='user', lazy=True)
    verified = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Query history model
class QueryHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    query = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())

# In-memory store for password reset tokens (for demo only)
password_reset_tokens = {}  # token: (email, expiry)
RESET_TOKEN_EXPIRY = 15 * 60  # 15 minutes

# In-memory store for email verification tokens (for demo only)
email_verification_tokens = {}  # token: email

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/api/signup', methods=['POST'])
@limiter.limit("5 per minute")
def signup():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 400
    user = User(email=email, verified=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    # Generate verification token
    token = secrets.token_urlsafe(32)
    email_verification_tokens[token] = email
    print(f"[Email Verification] Token for {email}: {token}")
    login_user(user)
    return jsonify({'message': 'Signup successful. Please verify your email.', 'user': {'id': user.id, 'email': user.email}, 'verification_required': True})

@app.route('/api/verify-email', methods=['POST'])
def verify_email():
    data = request.get_json()
    token = data.get('token')
    if not token:
        return jsonify({'error': 'Verification token required.'}), 400
    email = email_verification_tokens.get(token)
    if not email:
        return jsonify({'error': 'Invalid or expired token.'}), 400
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'User not found.'}), 400
    user.verified = True
    db.session.commit()
    del email_verification_tokens[token]
    return jsonify({'message': 'Email verified successfully.'})

@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        if not user.verified:
            return jsonify({'error': 'Email not verified. Please check your email for the verification link.'}), 403
        login_user(user)
        return jsonify({'message': 'Login successful', 'user': {'id': user.id, 'email': user.email}})
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logged out'})

@app.route('/api/history', methods=['GET'])
@login_required
def get_history():
    history = QueryHistory.query.filter_by(user_id=current_user.id).order_by(QueryHistory.timestamp.desc()).all()
    return jsonify([
        {
            'id': q.id,
            'query': q.query,
            'description': q.description,
            'timestamp': q.timestamp.isoformat()
        } for q in history
    ])

# Configure OpenAI (you'll need to set OPENAI_API_KEY in .env file)
openai.api_key = os.getenv('OPENAI_API_KEY')

@app.route('/api/generate-sql', methods=['POST'])
@limiter.limit("20 per minute")
def generate_sql():
    try:
        data = request.get_json()
        er_diagram_data = data.get('erDiagramData')
        query_description = data.get('queryDescription')
        
        if not er_diagram_data or not query_description:
            return jsonify({'error': 'Missing required data'}), 400
        
        # Format the ER diagram data for the prompt
        entities_text = "\n".join([
            f"- {entity['name']}: {', '.join(entity['attributes'])}"
            for entity in er_diagram_data.get('entities', [])
        ])
        
        relationships_text = "\n".join([
            f"- {rel['from']} -> {rel['to']} ({rel['type']})"
            for rel in er_diagram_data.get('relationships', [])
        ])
        
        # Create the prompt for SQL generation
        prompt = f"""
You are a SQL expert. Given the following ER diagram structure and query description, generate a valid SQL query.

ER Diagram Structure:
Entities:
{entities_text}

Relationships:
{relationships_text}

Query Description: {query_description}

Generate a SQL query that answers this description. Return only the SQL query without any explanations or markdown formatting.
"""
        
        # Call OpenAI API
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            # Mock SQL generation based on the query description
            mock_sql = generate_mock_sql(er_diagram_data, query_description)
            return jsonify({'sql': mock_sql})
        
        try:
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a SQL expert. Generate only valid SQL queries without explanations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.3
            )
            
            sql_query = response.choices[0].message.content
            if sql_query:
                sql_query = sql_query.strip()
            else:
                sql_query = "SELECT * FROM table;"
                
        except Exception as e:
            print(f"OpenAI API error: {str(e)}")
            # Fallback to mock SQL generation
            mock_sql = generate_mock_sql(er_diagram_data, query_description)
            return jsonify({'sql': mock_sql})
        
        if current_user.is_authenticated:
            qh = QueryHistory(user_id=current_user.id, query=sql_query, description=query_description)
            db.session.add(qh)
            db.session.commit()
        
        return jsonify({'sql': sql_query})
        
    except Exception as e:
        print(f"Error generating SQL: {str(e)}")
        return jsonify({'error': 'Failed to generate SQL query'}), 500

def generate_mock_sql(er_diagram_data, query_description):
    """Generate intelligent mock SQL when OpenAI API is not available"""
    entities = er_diagram_data.get('entities', [])
    relationships = er_diagram_data.get('relationships', [])
    query_lower = query_description.lower()
    entity_names = [entity['name'] for entity in entities]

    def find_entity_by_type(entity_type):
        for entity in entities:
            if entity['name'].lower() in [entity_type, entity_type + 's']:
                return entity
        return None

    def find_relationship(from_entity, to_entity):
        for rel in relationships:
            if (rel['from'].lower() == from_entity.lower() and rel['to'].lower() == to_entity.lower()):
                return rel
        return None

    # --- NEW: Multi-entity JOIN logic ---
    # Try to detect multiple entities in the query
    detected_entities = []
    for entity in entities:
        if entity['name'].lower()[:-1] in query_lower or entity['name'].lower() in query_lower:
            detected_entities.append(entity)
    
    # Special handling for academic queries with bridge tables
    if 'student' in query_lower and 'grade' in query_lower and 'course' in query_lower:
        student_entity = find_entity_by_type('student')
        enrollment_entity = None
        course_entity = find_entity_by_type('course')
        
        # Find enrollment entity (bridge table)
        for entity in entities:
            if 'enrollment' in entity['name'].lower():
                enrollment_entity = entity
                break
        
        if student_entity and enrollment_entity and course_entity:
            return f"""
SELECT s.student_id, s.name, s.email, e.grade, c.title as course_title
FROM Students s
JOIN Enrollments e ON s.student_id = e.student_id
JOIN Courses c ON e.course_id = c.course_id
ORDER BY s.name, c.title;
"""
    
    # Special handling for instructor-department queries
    if 'instructor' in query_lower and 'department' in query_lower:
        instructor_entity = find_entity_by_type('instructor')
        department_entity = find_entity_by_type('department')
        if instructor_entity and department_entity:
            return f"""
SELECT i.instructor_id, i.name, i.email, i.phone, d.name as department_name
FROM Instructors i
JOIN Departments d ON i.department = d.department_id
ORDER BY d.name, i.name;
"""
    
    # Special handling for schedule-course queries
    if 'schedule' in query_lower and 'course' in query_lower:
        schedule_entity = None
        course_entity = find_entity_by_type('course')
        for entity in entities:
            if 'schedule' in entity['name'].lower():
                schedule_entity = entity
                break
        
        if schedule_entity and course_entity:
            return f"""
SELECT s.schedule_id, s.day, s.start_time, s.end_time, c.title as course_title
FROM Schedules s
JOIN Courses c ON s.course_id = c.course_id
ORDER BY c.title, s.day, s.start_time;
"""
    
    # If two entities are detected and there is a relationship, generate a JOIN
    if len(detected_entities) >= 2:
        e1, e2 = detected_entities[0], detected_entities[1]
        rel = find_relationship(e1['name'], e2['name']) or find_relationship(e2['name'], e1['name'])
        if rel:
            # Find the join keys
            e1_key = None
            e2_key = None
            for attr in e1['attributes']:
                if e2['name'][:-1].lower() in attr.lower() or e2['name'].lower()[:-1] in attr.lower():
                    e1_key = attr
                    break
            for attr in e2['attributes']:
                if e1['name'][:-1].lower() in attr.lower() or e1['name'].lower()[:-1] in attr.lower():
                    e2_key = attr
                    break
            # Fallback to first attribute if not found
            if not e1_key:
                e1_key = e1['attributes'][0]
            if not e2_key:
                e2_key = e2['attributes'][0]
            # Use all attributes from the first entity
            select_attrs = ', '.join([f"{e1['name'][0].lower()}.{attr}" for attr in e1['attributes']])
            return f"""
SELECT {select_attrs}
FROM {e1['name']} {e1['name'][0].lower()}
JOIN {e2['name']} {e2['name'][0].lower()} ON {e1['name'][0].lower()}.{e1_key} = {e2['name'][0].lower()}.{e2_key}
LIMIT 10;
"""

    # --- Existing logic for single-entity queries and patterns ---
    if 'user' in query_lower and 'order' in query_lower and 'count' in query_lower:
        user_entity = find_entity_by_type('user')
        order_entity = find_entity_by_type('order')
        if user_entity and order_entity:
            rel = find_relationship(user_entity['name'], order_entity['name'])
            if rel:
                return f"""
SELECT u.{user_entity['attributes'][1] if len(user_entity['attributes']) > 1 else 'name'}, 
       u.{user_entity['attributes'][2] if len(user_entity['attributes']) > 2 else 'email'}, 
       COUNT(o.id) as order_count
FROM {user_entity['name']} u
LEFT JOIN {order_entity['name']} o ON u.id = o.{rel['from'].lower()}_id
GROUP BY u.id, u.{user_entity['attributes'][1] if len(user_entity['attributes']) > 1 else 'name'}
ORDER BY order_count DESC;
"""
    
    elif 'user' in query_lower and 'order' in query_lower:
        user_entity = find_entity_by_type('user')
        order_entity = find_entity_by_type('order')
        if user_entity and order_entity:
            rel = find_relationship(user_entity['name'], order_entity['name'])
            if rel:
                return f"""
SELECT u.{user_entity['attributes'][1] if len(user_entity['attributes']) > 1 else 'name'}, 
       u.{user_entity['attributes'][2] if len(user_entity['attributes']) > 2 else 'email'}, 
       o.id as order_id, o.{order_entity['attributes'][2] if len(order_entity['attributes']) > 2 else 'total'}
FROM {user_entity['name']} u
JOIN {order_entity['name']} o ON u.id = o.{rel['from'].lower()}_id
ORDER BY o.id DESC;
"""
    
    elif 'product' in query_lower and 'price' in query_lower:
        product_entity = find_entity_by_type('product')
        if product_entity:
            price_attr = None
            for attr in product_entity['attributes']:
                if 'price' in attr.lower():
                    price_attr = attr
                    break
            if not price_attr:
                price_attr = product_entity['attributes'][2] if len(product_entity['attributes']) > 2 else 'price'
            
            if 'greater' in query_lower or 'more' in query_lower or '>' in query_lower:
                return f"""
SELECT {', '.join(product_entity['attributes'][:3])}
FROM {product_entity['name']}
WHERE {price_attr} > 50
ORDER BY {price_attr} DESC;
"""
            else:
                return f"""
SELECT {', '.join(product_entity['attributes'][:3])}
FROM {product_entity['name']}
ORDER BY {price_attr} ASC;
"""
    
    elif 'order' in query_lower and 'status' in query_lower:
        order_entity = find_entity_by_type('order')
        if order_entity:
            status_attr = None
            for attr in order_entity['attributes']:
                if 'status' in attr.lower():
                    status_attr = attr
                    break
            if not status_attr:
                status_attr = order_entity['attributes'][3] if len(order_entity['attributes']) > 3 else 'status'
            
            if 'pending' in query_lower:
                return f"""
SELECT {', '.join(order_entity['attributes'])}
FROM {order_entity['name']}
WHERE {status_attr} = 'pending'
ORDER BY id DESC;
"""
            else:
                return f"""
SELECT {', '.join(order_entity['attributes'])}
FROM {order_entity['name']}
ORDER BY id DESC;
"""
    
    elif 'sales' in query_lower and 'category' in query_lower:
        product_entity = find_entity_by_type('product')
        if product_entity:
            category_attr = None
            price_attr = None
            for attr in product_entity['attributes']:
                if 'category' in attr.lower():
                    category_attr = attr
                elif 'price' in attr.lower():
                    price_attr = attr
            
            if category_attr and price_attr:
                return f"""
SELECT {category_attr}, SUM({price_attr}) as total_sales
FROM {product_entity['name']}
GROUP BY {category_attr}
ORDER BY total_sales DESC;
"""
    
    elif 'recent' in query_lower or 'last' in query_lower:
        order_entity = find_entity_by_type('order')
        if order_entity:
            date_attr = None
            for attr in order_entity['attributes']:
                if any(date_word in attr.lower() for date_word in ['date', 'created', 'time']):
                    date_attr = attr
                    break
            if not date_attr:
                date_attr = order_entity['attributes'][-1] if order_entity['attributes'] else 'created_at'
            
            return f"""
SELECT *
FROM {order_entity['name']}
WHERE {date_attr} >= DATE_SUB(NOW(), INTERVAL 30 DAY)
ORDER BY {date_attr} DESC;
"""
    
    elif 'total' in query_lower or 'sum' in query_lower:
        order_entity = find_entity_by_type('order')
        if order_entity:
            total_attr = None
            for attr in order_entity['attributes']:
                if any(total_word in attr.lower() for total_word in ['total', 'amount', 'price']):
                    total_attr = attr
                    break
            if not total_attr:
                total_attr = order_entity['attributes'][2] if len(order_entity['attributes']) > 2 else 'total'
            
            return f"""
SELECT SUM({total_attr}) as total_revenue
FROM {order_entity['name']};
"""
    
    elif 'find' in query_lower or 'search' in query_lower:
        user_entity = find_entity_by_type('user')
        if user_entity:
            return f"""
SELECT {', '.join(user_entity['attributes'])}
FROM {user_entity['name']}
WHERE {user_entity['attributes'][1] if len(user_entity['attributes']) > 1 else 'name'} LIKE '%search_term%';
"""
    
    elif 'all' in query_lower:
        # Find the most appropriate entity based on query
        target_entity = None
        if 'user' in query_lower:
            target_entity = find_entity_by_type('user')
        elif 'order' in query_lower:
            target_entity = find_entity_by_type('order')
        elif 'product' in query_lower:
            target_entity = find_entity_by_type('product')
        
        if target_entity:
            return f"""
SELECT {', '.join(target_entity['attributes'])}
FROM {target_entity['name']}
ORDER BY id DESC;
"""
    
    # Generic pattern matching for any entity names
    elif 'student' in query_lower:
        student_entity = find_entity_by_type('student')
        if student_entity:
            return f"""
SELECT {', '.join(student_entity['attributes'])}
FROM {student_entity['name']}
ORDER BY id DESC;
"""
    
    elif 'course' in query_lower:
        course_entity = find_entity_by_type('course')
        if course_entity:
            # Check if query mentions credits
            if 'credit' in query_lower and ('greater' in query_lower or 'more' in query_lower or '>' in query_lower):
                credits_attr = None
                for attr in course_entity['attributes']:
                    if 'credit' in attr.lower():
                        credits_attr = attr
                        break
                if credits_attr:
                    return f"""
SELECT {', '.join(course_entity['attributes'])}
FROM {course_entity['name']}
WHERE {credits_attr} > 3
ORDER BY {credits_attr} DESC;
"""
            else:
                return f"""
SELECT {', '.join(course_entity['attributes'])}
FROM {course_entity['name']}
ORDER BY id DESC;
"""
    
    # If no specific pattern matches, generate a query based on available entities
    if entities:
        # Try to find a good primary entity
        primary_entity = None
        for entity in entities:
            if entity['name'].lower() in ['users', 'user', 'customers', 'customer']:
                primary_entity = entity
                break
            elif entity['name'].lower() in ['orders', 'order']:
                primary_entity = entity
                break
            elif entity['name'].lower() in ['products', 'product']:
                primary_entity = entity
                break
            elif entity['name'].lower() in ['students', 'student']:
                primary_entity = entity
                break
            elif entity['name'].lower() in ['courses', 'course']:
                primary_entity = entity
                break
        
        if not primary_entity:
            primary_entity = entities[0]
        
        # Generate a basic query for the primary entity
        return f"""
SELECT {', '.join(primary_entity['attributes'][:3])}
FROM {primary_entity['name']}
ORDER BY id DESC
LIMIT 10;
"""
    
    # Fallback
    return """
SELECT * FROM table_name LIMIT 10;
"""

@app.route('/api/explain-sql', methods=['POST'])
@limiter.limit("20 per minute")
def explain_sql():
    data = request.get_json()
    sql = data.get('sql')
    if not sql:
        return jsonify({'error': 'SQL is required'}), 400
    prompt = f"""
Explain this SQL in plain English.

SQL:
{sql}
"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        # Mock explanation
        return jsonify({'explanation': f'This SQL query does the following: {sql[:60]}...'}), 200
    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that explains SQL queries in plain English."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.3
        )
        explanation = response.choices[0].message.content if response.choices and response.choices[0].message and response.choices[0].message.content else None
        if explanation:
            explanation = explanation.strip()
        else:
            explanation = 'No explanation available.'
        return jsonify({'explanation': explanation})
    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        return jsonify({'error': 'Failed to explain SQL'}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'Backend server is running'})

@app.route('/api/request-password-reset', methods=['POST'])
@limiter.limit("5 per minute")
def request_password_reset():
    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({'error': 'Email is required'}), 400
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'message': 'If this email is registered, a reset link has been sent.'})
    token = secrets.token_urlsafe(32)
    password_reset_tokens[token] = (email, time.time() + RESET_TOKEN_EXPIRY)
    # Simulate sending email by printing token to console
    print(f"[Password Reset] Token for {email}: {token}")
    return jsonify({'message': 'If this email is registered, a reset link has been sent.'})

@app.route('/api/reset-password', methods=['POST'])
@limiter.limit("5 per minute")
def reset_password():
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')
    if not token or not new_password:
        return jsonify({'error': 'Token and new password are required.'}), 400
    entry = password_reset_tokens.get(token)
    if not entry:
        return jsonify({'error': 'Invalid or expired token.'}), 400
    email, expiry = entry
    if time.time() > expiry:
        del password_reset_tokens[token]
        return jsonify({'error': 'Token has expired.'}), 400
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'User not found.'}), 400
    user.set_password(new_password)
    db.session.commit()
    del password_reset_tokens[token]
    return jsonify({'message': 'Password has been reset successfully.'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 8001))
    app.run(debug=True, host='0.0.0.0', port=port) 