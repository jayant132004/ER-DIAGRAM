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
from flask_mail import Mail, Message
import smtplib
import random

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True)  # Enable CORS for all routes
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'devsecret')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Flask-Mail configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'aisql1304@gmail.com')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'aisql1304@gmail.com')

db = SQLAlchemy(app)
login_manager = LoginManager(app)

# Initialize Flask-Limiter
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"])

mail = Mail(app)

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

# In-memory store for password reset OTPs (for demo only)
password_reset_otps = {}  # email: (otp, expiry)
# In-memory store for email verification OTPs (for demo only)
email_verification_otps = {}  # email: (otp, expiry)
RESET_TOKEN_EXPIRY = 15 * 60  # 15 minutes

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
    user = User(email=email, verified=True)  # Auto-verify users
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return jsonify({'message': 'Signup successful!', 'user': {'id': user.id, 'email': user.email}})

@app.route('/api/verify-email', methods=['POST'])
def verify_email():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    if not email or not otp:
        return jsonify({'error': 'Email and OTP required.'}), 400
    entry = email_verification_otps.get(email)
    if not entry or entry[0] != otp or time.time() > entry[1]:
        return jsonify({'error': 'Invalid or expired OTP.'}), 400
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'User not found.'}), 400
    user.verified = True
    db.session.commit()
    del email_verification_otps[email]
    return jsonify({'message': 'Email verified successfully.'})

@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        # Remove email verification check - allow login regardless of verification status
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

    def get_primary_key(entity):
        """Get the primary key attribute for an entity"""
        for attr in entity['attributes']:
            if 'id' in attr.lower() or attr.lower().endswith('_id'):
                return attr
        return entity['attributes'][0] if entity['attributes'] else 'id'

    def get_foreign_key(entity, target_entity):
        """Get the foreign key attribute that references the target entity"""
        target_name = target_entity['name'].lower()
        for attr in entity['attributes']:
            if target_name[:-1] in attr.lower() or target_name in attr.lower():
                return attr
        return f"{target_name}_id"

    # --- Improved Multi-entity JOIN logic ---
    # Try to detect multiple entities in the query
    detected_entities = []
    for entity in entities:
        entity_name_lower = entity['name'].lower()
        if entity_name_lower in query_lower or entity_name_lower[:-1] in query_lower:
            detected_entities.append(entity)
    
    # If two or more entities are detected and there is a relationship, generate a JOIN
    if len(detected_entities) >= 2:
        e1, e2 = detected_entities[0], detected_entities[1]
        rel = find_relationship(e1['name'], e2['name']) or find_relationship(e2['name'], e1['name'])
        
        if rel:
            # Determine the correct join direction
            if rel['from'].lower() == e1['name'].lower():
                from_entity, to_entity = e1, e2
            else:
                from_entity, to_entity = e2, e1
            
            # Get primary and foreign keys
            from_pk = get_primary_key(from_entity)
            to_fk = get_foreign_key(to_entity, from_entity)
            
            # Select meaningful attributes
            from_attrs = ', '.join([f"{from_entity['name'][0].lower()}.{attr}" for attr in from_entity['attributes'][:3]])
            to_attrs = ', '.join([f"{to_entity['name'][0].lower()}.{attr}" for attr in to_entity['attributes'][:3]])
            
            return f"""
SELECT {from_attrs}, {to_attrs}
FROM {from_entity['name']} {from_entity['name'][0].lower()}
JOIN {to_entity['name']} {to_entity['name'][0].lower()} ON {from_entity['name'][0].lower()}.{from_pk} = {to_entity['name'][0].lower()}.{to_fk}
ORDER BY {from_entity['name'][0].lower()}.{from_pk}
LIMIT 10;
"""

    # --- Improved single-entity queries ---
    if 'count' in query_lower:
        # Find the most appropriate entity for counting
        target_entity = None
        if 'user' in query_lower:
            target_entity = find_entity_by_type('user')
        elif 'order' in query_lower:
            target_entity = find_entity_by_type('order')
        elif 'product' in query_lower:
            target_entity = find_entity_by_type('product')
        elif 'student' in query_lower:
            target_entity = find_entity_by_type('student')
        elif 'course' in query_lower:
            target_entity = find_entity_by_type('course')
        
        if target_entity:
            pk = get_primary_key(target_entity)
            return f"""
SELECT COUNT(*) as total_count
FROM {target_entity['name']};
"""
    
    elif 'price' in query_lower or 'cost' in query_lower:
        # Find entity with price/cost attributes
        for entity in entities:
            price_attrs = [attr for attr in entity['attributes'] if 'price' in attr.lower() or 'cost' in attr.lower()]
            if price_attrs:
                price_attr = price_attrs[0]
                if 'greater' in query_lower or 'more' in query_lower or '>' in query_lower:
                    return f"""
SELECT {', '.join(entity['attributes'][:3])}
FROM {entity['name']}
WHERE {price_attr} > 50
ORDER BY {price_attr} DESC;
"""
                else:
                    return f"""
SELECT {', '.join(entity['attributes'][:3])}
FROM {entity['name']}
ORDER BY {price_attr} ASC;
"""
    
    elif 'status' in query_lower:
        # Find entity with status attributes
        for entity in entities:
            status_attrs = [attr for attr in entity['attributes'] if 'status' in attr.lower()]
            if status_attrs:
                status_attr = status_attrs[0]
                if 'pending' in query_lower:
                    return f"""
SELECT {', '.join(entity['attributes'])}
FROM {entity['name']}
WHERE {status_attr} = 'pending'
ORDER BY {get_primary_key(entity)} DESC;
"""
                else:
                    return f"""
SELECT {', '.join(entity['attributes'])}
FROM {entity['name']}
ORDER BY {get_primary_key(entity)} DESC;
"""
    
    elif 'recent' in query_lower or 'last' in query_lower:
        # Find entity with date/time attributes
        for entity in entities:
            date_attrs = [attr for attr in entity['attributes'] if any(date_word in attr.lower() for date_word in ['date', 'created', 'time', 'updated'])]
            if date_attrs:
                date_attr = date_attrs[0]
                return f"""
SELECT *
FROM {entity['name']}
WHERE {date_attr} >= DATE_SUB(NOW(), INTERVAL 30 DAY)
ORDER BY {date_attr} DESC;
"""
    
    elif 'total' in query_lower or 'sum' in query_lower:
        # Find entity with numeric attributes
        for entity in entities:
            numeric_attrs = [attr for attr in entity['attributes'] if any(num_word in attr.lower() for num_word in ['total', 'amount', 'price', 'cost', 'quantity'])]
            if numeric_attrs:
                numeric_attr = numeric_attrs[0]
                return f"""
SELECT SUM({numeric_attr}) as total_amount
FROM {entity['name']};
"""
    
    elif 'find' in query_lower or 'search' in query_lower:
        # Find entity with text attributes
        for entity in entities:
            text_attrs = [attr for attr in entity['attributes'] if any(text_word in attr.lower() for text_word in ['name', 'title', 'description', 'email'])]
            if text_attrs:
                text_attr = text_attrs[0]
                return f"""
SELECT {', '.join(entity['attributes'])}
FROM {entity['name']}
WHERE {text_attr} LIKE '%search_term%';
"""
    
    elif 'all' in query_lower:
        # Find the most appropriate entity based on query
        target_entity = None
        for entity_type in ['user', 'order', 'product', 'student', 'course']:
            target_entity = find_entity_by_type(entity_type)
            if target_entity:
                break
        
        if target_entity:
            return f"""
SELECT {', '.join(target_entity['attributes'])}
FROM {target_entity['name']}
ORDER BY {get_primary_key(target_entity)} DESC;
"""
    
    # --- Entity-specific patterns ---
    for entity in entities:
        entity_name_lower = entity['name'].lower()
        if entity_name_lower in query_lower or entity_name_lower[:-1] in query_lower:
            # Check for specific conditions
            if 'credit' in query_lower and entity_name_lower in ['course', 'courses']:
                credit_attrs = [attr for attr in entity['attributes'] if 'credit' in attr.lower()]
                if credit_attrs:
                    credit_attr = credit_attrs[0]
                    if 'greater' in query_lower or 'more' in query_lower or '>' in query_lower:
                        return f"""
SELECT {', '.join(entity['attributes'])}
FROM {entity['name']}
WHERE {credit_attr} > 3
ORDER BY {credit_attr} DESC;
"""
            
            # Default query for the entity
            return f"""
SELECT {', '.join(entity['attributes'])}
FROM {entity['name']}
ORDER BY {get_primary_key(entity)} DESC
LIMIT 10;
"""
    
    # --- Fallback: Generate a query based on available entities ---
    if entities:
        # Try to find a good primary entity
        primary_entity = None
        priority_entities = ['user', 'customer', 'student', 'order', 'product', 'course']
        
        for priority in priority_entities:
            for entity in entities:
                if entity['name'].lower() in [priority, priority + 's']:
                    primary_entity = entity
                    break
            if primary_entity:
                break
        
        if not primary_entity:
            primary_entity = entities[0]
        
        # Generate a basic query for the primary entity
        pk = get_primary_key(primary_entity)
        attrs = ', '.join(primary_entity['attributes'][:3])
        return f"""
SELECT {attrs}
FROM {primary_entity['name']}
ORDER BY {pk} DESC
LIMIT 10;
"""
    
    # --- Final fallback ---
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
        return jsonify({'message': 'If this email is registered, an OTP has been sent.'})
    otp = str(random.randint(100000, 999999))
    password_reset_otps[email] = (otp, time.time() + RESET_TOKEN_EXPIRY)
    # Send real password reset OTP email
    msg = Message(
        subject="Password Reset OTP",
        recipients=[email],
        body=f"Your password reset OTP is: {otp}\nIt is valid for 15 minutes."
    )
    try:
        mail.send(msg)
    except Exception as e:
        print(f"[Password Reset] Failed to send email to {email}: {e}")
    return jsonify({'message': 'If this email is registered, an OTP has been sent.'})

@app.route('/api/reset-password', methods=['POST'])
@limiter.limit("5 per minute")
def reset_password():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    new_password = data.get('new_password')
    if not email or not otp or not new_password:
        return jsonify({'error': 'Email, OTP, and new password are required.'}), 400
    entry = password_reset_otps.get(email)
    if not entry or entry[0] != otp or time.time() > entry[1]:
        return jsonify({'error': 'Invalid or expired OTP.'}), 400
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'User not found.'}), 400
    user.set_password(new_password)
    db.session.commit()
    del password_reset_otps[email]
    return jsonify({'message': 'Password has been reset successfully.'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 8000))
    app.run(debug=True, host='0.0.0.0', port=port) 