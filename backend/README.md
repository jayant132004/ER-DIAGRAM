# SQL Query Generator Backend

A Flask backend server that provides SQL query generation API endpoints.

## Features

- RESTful API for SQL query generation
- Integration with OpenAI GPT for intelligent SQL generation
- Mock SQL generation when OpenAI API is not available
- CORS enabled for frontend integration
- Health check endpoint

## Setup

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables (Optional):**
   Create a `.env` file in the backend directory:
   ```bash
   cp env.example .env
   ```
   
   Then edit `.env` and add your OpenAI API key:
   ```
   OPENAI_API_KEY=your_actual_openai_api_key_here
   PORT=5000
   ```

   **Note:** If you don't provide an OpenAI API key, the server will use mock responses.

## Running the Server

```bash
python app.py
```

The server will start on `http://localhost:5000`

## API Endpoints

### POST `/api/generate-sql`
Generate SQL queries based on ER diagram data and query description.

**Request Body:**
```json
{
  "erDiagramData": {
    "entities": [
      {
        "name": "Users",
        "attributes": ["id", "name", "email", "created_at"]
      }
    ],
    "relationships": [
      {
        "from": "Users",
        "to": "Orders",
        "type": "one-to-many"
      }
    ]
  },
  "queryDescription": "Show all users with their order count"
}
```

**Response:**
```json
{
  "sql": "SELECT u.name, u.email, COUNT(o.id) as order_count FROM Users u LEFT JOIN Orders o ON u.id = o.user_id GROUP BY u.id, u.name, u.email ORDER BY order_count DESC;"
}
```

### GET `/api/health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "message": "Backend server is running"
}
```

## Development

The server runs in debug mode by default. For production, set `debug=False` in `app.py`. 