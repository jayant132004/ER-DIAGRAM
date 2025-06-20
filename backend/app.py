from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure OpenAI (you'll need to set OPENAI_API_KEY in .env file)
openai.api_key = os.getenv('OPENAI_API_KEY')

@app.route('/api/generate-sql', methods=['POST'])
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
        
        # If OpenAI API key is not available, return a mock response
        if not openai.api_key:
            # Mock SQL generation based on the query description
            mock_sql = generate_mock_sql(er_diagram_data, query_description)
            return jsonify({'sql': mock_sql})
        
        # Call OpenAI API
        api_key = os.getenv('OPENAI_API_KEY')
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
        
        return jsonify({'sql': sql_query})
        
    except Exception as e:
        print(f"Error generating SQL: {str(e)}")
        return jsonify({'error': 'Failed to generate SQL query'}), 500

def generate_mock_sql(er_diagram_data, query_description):
    """Generate mock SQL when OpenAI API is not available"""
    entities = er_diagram_data.get('entities', [])
    relationships = er_diagram_data.get('relationships', [])
    
    # Simple mock SQL generation based on common patterns
    query_lower = query_description.lower()
    
    if 'user' in query_lower and 'order' in query_lower:
        return """
SELECT u.name, u.email, COUNT(o.id) as order_count
FROM Users u
LEFT JOIN Orders o ON u.id = o.user_id
GROUP BY u.id, u.name, u.email
ORDER BY order_count DESC;
"""
    elif 'product' in query_lower and 'price' in query_lower:
        return """
SELECT name, price, category
FROM Products
WHERE price > 50
ORDER BY price DESC;
"""
    elif 'order' in query_lower and 'status' in query_lower:
        return """
SELECT id, user_id, total, status, created_at
FROM Orders
WHERE status = 'pending'
ORDER BY created_at DESC;
"""
    elif 'sales' in query_lower and 'category' in query_lower:
        return """
SELECT p.category, SUM(oi.quantity * p.price) as total_sales
FROM Products p
JOIN OrderItems oi ON p.id = oi.product_id
GROUP BY p.category
ORDER BY total_sales DESC;
"""
    else:
        # Generic query
        if entities:
            first_entity = entities[0]
            return f"""
SELECT *
FROM {first_entity['name']}
LIMIT 10;
"""

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'Backend server is running'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(debug=True, host='0.0.0.0', port=port) 