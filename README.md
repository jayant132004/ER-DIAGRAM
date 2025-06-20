# AI SQL Query Generator

A full-stack web application that generates SQL queries using AI based on ER diagram structures and natural language descriptions.

## 🚀 Features

- **AI-Powered SQL Generation**: Uses OpenAI GPT to generate intelligent SQL queries
- **ER Diagram Support**: Parse and visualize Entity-Relationship diagrams
- **Natural Language Interface**: Describe what you want to query in plain English
- **Query History**: Track and review previously generated queries
- **Modern UI**: Beautiful, responsive interface built with React and TypeScript
- **Real-time Processing**: Instant SQL generation with loading states

## 🛠️ Tech Stack

### Frontend
- **React 19** with TypeScript
- **React Dropzone** for file uploads
- **Lucide React** for icons
- **Axios** for HTTP requests
- **CSS3** with modern styling

### Backend
- **Python Flask** server
- **OpenAI API** integration
- **Flask-CORS** for cross-origin requests
- **python-dotenv** for environment management

## 📦 Installation

### Prerequisites
- Node.js (v16 or higher)
- Python 3.8 or higher
- OpenAI API key

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/jayant132004/sql-query-generator.git
   cd sql-query-generator
   ```

2. **Install Frontend Dependencies**
   ```bash
   cd sql-query-generator
   npm install
   ```

3. **Install Backend Dependencies**
   ```bash
   cd backend
   pip3 install -r requirements.txt
   ```

4. **Configure Environment Variables**
   ```bash
   cd backend
   cp env.example .env
   ```
   
   Edit `.env` and add your OpenAI API key:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   PORT=8000
   ```

## 🚀 Running the Application

### Start the Backend Server
```bash
cd backend
python3 app.py
```
The backend will run on `http://localhost:8000`

### Start the Frontend Development Server
```bash
cd sql-query-generator
npm start
```
The frontend will run on `http://localhost:3000`

## 📖 Usage

1. **Enter ER Structure**: Input your ER diagram structure in JSON format
2. **Parse Structure**: Click "Parse ER Structure" to validate and visualize
3. **Describe Query**: Enter what you want to query in natural language
4. **Generate SQL**: Click "Generate SQL" to get AI-powered SQL queries
5. **Review History**: View and copy previously generated queries

### Example ER Structure
```json
{
  "entities": [
    { "name": "Users", "attributes": ["id", "name", "email", "created_at"] },
    { "name": "Orders", "attributes": ["id", "user_id", "total", "status", "created_at"] },
    { "name": "Products", "attributes": ["id", "name", "price", "category"] }
  ],
  "relationships": [
    { "from": "Users", "to": "Orders", "type": "one-to-many" },
    { "from": "Orders", "to": "Products", "type": "many-to-many" }
  ]
}
```

### Example Query Descriptions
- "Show all users with their order count"
- "Find products with price greater than $50"
- "Get orders with status 'pending'"
- "List users who made orders in the last 30 days"

## 🔧 API Endpoints

### POST `/api/generate-sql`
Generate SQL queries based on ER diagram and description.

**Request Body:**
```json
{
  "erDiagramData": {
    "entities": [...],
    "relationships": [...]
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

## 🎯 Features in Detail

### AI-Powered SQL Generation
- Uses OpenAI GPT-3.5-turbo for intelligent query generation
- Context-aware based on ER diagram structure
- Handles complex relationships and joins
- Generates optimized SQL queries

### ER Diagram Visualization
- Visual representation of entities and relationships
- Attribute display for each entity
- Relationship type indicators
- Interactive diagram viewer

### Query History
- Persistent storage of generated queries
- Copy-to-clipboard functionality
- Timestamp tracking
- Query descriptions for context

## 🔒 Security

- Environment variables for sensitive data
- CORS configuration for secure API communication
- Input validation and sanitization
- Error handling and logging

## 🚀 Deployment

### Frontend (React)
```bash
cd sql-query-generator
npm run build
```

### Backend (Flask)
```bash
cd backend
pip3 install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👨‍💻 Author

**Jayant** - [GitHub Profile](https://github.com/jayant132004)

## 🙏 Acknowledgments

- OpenAI for providing the GPT API
- React team for the amazing framework
- Flask team for the Python web framework
- All contributors and users of this project

---

⭐ **Star this repository if you find it helpful!** 