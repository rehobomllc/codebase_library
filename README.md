# 🏥 Treatment Navigator

**An AI-powered platform for mental health and substance abuse treatment assistance**

Treatment Navigator is an enterprise-grade web application that helps individuals find, evaluate, and access mental health and substance abuse treatment options. Built with modern AI agents, comprehensive safety features, and seamless integrations, it provides a complete treatment navigation experience.

## 🌟 Key Features

### 🤖 **Multi-Agent AI System**
- **Treatment Triage Agent**: First-point-of-contact for intake and routing
- **Facility Search Agent**: Intelligent treatment facility discovery
- **Insurance Verification Agent**: Real-time coverage validation
- **Appointment Scheduler Agent**: Automated appointment booking
- **Intake Form Agent**: Digital form processing and assistance
- **Reminder Agent**: Treatment milestone and appointment notifications
- **Communication Agent**: Automated facility correspondence

### 🛡️ **Enterprise Safety & Compliance**
- **Crisis Detection**: Automatic suicide/self-harm risk assessment
- **Emergency Response**: Immediate crisis resource provision (988, Crisis Text Line)
- **Privacy Protection**: PII detection and sanitization
- **Topic Relevance**: Treatment-focused conversation filtering
- **Response Safety**: Medical advice prevention and safety validation

### 🔍 **Vision Analysis Capabilities**
- **Medical Document Analysis**: Extract information from test results, doctor notes
- **Prescription Label Reading**: Medication details and dosage extraction
- **Insurance Card Processing**: Coverage verification from card images
- **Treatment Form Analysis**: Digital intake form processing

### 🏗️ **Advanced Architecture**
- **AsyncIO-based**: High-performance asynchronous processing
- **Database Pool Management**: Scalable PostgreSQL connection handling
- **Background Task System**: Celery-based job processing
- **Workflow Orchestration**: Complex treatment journey automation
- **Document Management**: Comprehensive file handling and storage
- **Real-time Progress Tracking**: Live updates via Redis pub/sub

## 🛠️ Technology Stack

### **Core Framework**
- **FastAPI**: Modern, high-performance web framework
- **Python 3.8+**: Asynchronous programming with type hints
- **Uvicorn**: ASGI server for production deployment

### **AI & ML Integration**
- **OpenAI Agents SDK**: Multi-agent conversation orchestration
- **Arcade AI**: Tool integration and external service connectivity
- **GPT-4 Turbo**: Advanced language model for agent intelligence
- **GPT-4 Vision**: Document and image analysis capabilities

### **Data & Storage**
- **PostgreSQL**: Primary relational database with async support
- **Redis**: Caching, session management, and pub/sub messaging
- **AsyncPG**: High-performance PostgreSQL async driver

### **Background Processing**
- **Celery**: Distributed task queue system
- **Redis**: Message broker for task distribution
- **Background Tasks**: Long-running job processing

### **Frontend & UI**
- **Jinja2**: Server-side template rendering
- **Modern CSS**: Responsive design with CSS Grid/Flexbox
- **Progressive Enhancement**: JavaScript for enhanced UX
- **PWA Features**: Service worker and offline capabilities

### **External Integrations**
- **Google Tools**: Calendar, Docs, Drive integration via Arcade
- **Web Search**: Real-time treatment facility discovery
- **ArXiv Research**: Academic treatment research access
- **Slack/LinkedIn**: Professional communication tools (optional)

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- PostgreSQL 12+
- Redis 6+
- OpenAI API Key
- Arcade AI API Key

### ⚡ **Essential Environment Variables**
Before starting, you **MUST** set these required environment variables:

```bash
export OPENAI_API_KEY="your_openai_api_key_here"
export ARCADE_API_KEY="your_arcade_api_key_here" 
export DATABASE_URL="postgresql://username:password@localhost/treatment_navigator"
export REDIS_URL="redis://localhost:6379/0"
```

**Without these, the application will not start properly.**

### 1. **Environment Setup**
```bash
# Clone the repository
git clone <repository-url>
cd treatment-navigator

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. **Database Configuration**
```bash
# Start PostgreSQL (if not running)
brew services start postgresql  # macOS
# OR
sudo systemctl start postgresql  # Linux

# Create database
createdb treatment_navigator
```

### 3. **Environment Variables**
Create a `.env` file in the project root:
```env
# Required API Keys
OPENAI_API_KEY=your_openai_api_key_here
ARCADE_API_KEY=your_arcade_api_key_here
FIRECRAWL_API_KEY=your_firecrawl_api_key_here

# Database Configuration
DATABASE_URL=postgresql://username:password@localhost/treatment_navigator
REDIS_URL=redis://localhost:6379/0

# Application Settings
DEFAULT_AGENT_MODEL=gpt-4.1
VISION_MODEL=gpt-4o
MAX_VISION_FILE_SIZE_MB=20
APP_URL=http://localhost:8000

# Feature Flags
ENABLE_VISION_ANALYSIS=true
ENABLE_ARCADE_VALIDATION=true
ENABLE_PROACTIVE_MONITORING=true
ENABLE_AGENT_OPTIMIZATION=true

# Safety & Compliance
DAILY_API_COST_LIMIT=50.00
MONTHLY_API_COST_LIMIT=500.00
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# SSL Configuration (for production)
USE_HTTPS=false
SSL_CERT_FILE=
SSL_KEY_FILE=
```

### 4. **Start Services**
```bash
# Start Redis
brew services start redis  # macOS
# OR
sudo systemctl start redis  # Linux

# Use the startup script (recommended)
chmod +x start.sh
./start.sh

# OR start manually
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 5. **Access the Application**
- **Main Application**: http://localhost:8000
- **Debug Dashboard**: http://localhost:8000/debug
- **Vision Test**: http://localhost:8000/vision-test
- **API Documentation**: http://localhost:8000/docs

## 📁 Project Structure

```
treatment-navigator/
├── app.py                      # Main FastAPI application
├── config.py                  # Configuration management
├── requirements.txt            # Python dependencies
├── start.sh                   # Startup script
├── tasks.py                   # Background task definitions
│
├── services/                   # Core business services
│   ├── ai_summarizer.py       # Content summarization
│   ├── background_tasks.py    # Task orchestration
│   ├── billing.py            # Usage tracking
│   ├── database.py           # Database operations
│   ├── document_manager.py   # File management
│   ├── vision_analyzer.py    # Image/document analysis
│   └── workflow_orchestrator.py # Process automation
│
├── treatment_agents/          # AI agent implementations
│   ├── triage_agent.py       # Main intake agent
│   ├── facility_search_agent.py # Facility discovery
│   ├── insurance_verification_agent.py # Coverage validation
│   ├── appointment_scheduler_agent.py # Booking automation
│   ├── intake_form_agent.py  # Form assistance
│   ├── reminder_agent.py     # Notification system
│   ├── communication_agent.py # Automated correspondence
│   └── guardrails.py         # Safety implementations
│
├── utils/                     # Utility modules
│   ├── agent_optimizer.py    # Performance optimization
│   ├── arcade_auth_helper.py # Authentication handling
│   ├── tool_provider.py      # Tool integration
│   └── debug_connection.py   # Development utilities
│
├── templates/                 # Web interface
│   ├── treatment_onboarding.html # User intake
│   ├── vision_test.html      # Document upload
│   ├── debug_dashboard.html  # System monitoring
│   └── partials/             # Reusable components
│
├── static/                    # Frontend assets
│   ├── css/                  # Stylesheets
│   ├── js/                   # JavaScript
│   └── images/               # Static images
│
└── logs/                      # Application logs
```

## 🔧 API Endpoints

### **Core Chat Interface**
- `POST /chat` - Main conversation endpoint with AI agents
- `GET /api/profile/{user_id}` - User profile management
- `GET /api/treatments/{user_id}` - Treatment history
- `GET /api/appointments/{user_id}` - Appointment tracking

### **Specialized Services**
- `POST /api/facility_search` - Treatment facility discovery
- `POST /api/insurance_verification` - Coverage validation
- `POST /api/schedule_appointment` - Appointment booking
- `POST /api/treatment_reminder` - Reminder management

### **Vision Analysis**
- `POST /api/vision/analyze_medical_document` - Medical document processing
- `POST /api/vision/analyze_prescription` - Prescription label reading
- `POST /api/vision/analyze_insurance_card` - Insurance card extraction
- `POST /api/vision/analyze_treatment_form` - Form processing

### **Workflow Management**
- `POST /api/workflow/create` - Create treatment workflows
- `POST /api/workflow/{id}/execute` - Execute workflow steps
- `GET /api/workflow/{id}/status` - Monitor workflow progress

### **Background Tasks**
- `POST /api/tasks/schedule` - Schedule background processing
- `GET /api/tasks/{user_id}` - Task status monitoring
- `POST /api/tasks/{id}/cancel` - Cancel running tasks

## 🛡️ Safety Features

### **Crisis Detection System**
The platform includes a comprehensive crisis detection system that:

- **Monitors conversations** for suicide, self-harm, and substance abuse emergencies
- **Provides immediate resources** including 988 Suicide & Crisis Lifeline
- **Escalates appropriately** based on risk assessment (1-5 scale)
- **Logs incidents** for compliance and follow-up

### **Privacy Protection**
- **PII Detection**: Automatically identifies and sanitizes personal information
- **HIPAA Considerations**: Healthcare data handling best practices
- **Audit Logging**: Comprehensive interaction tracking
- **Data Retention**: Configurable retention policies

### **Input/Output Guardrails**
- **Topic Filtering**: Ensures treatment-related conversations
- **Response Safety**: Prevents medical advice and dangerous recommendations
- **Content Validation**: Maintains appropriate tone and content

## 🧪 Testing

### **Manual Testing**
```bash
# Test crisis detection
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"I want to hurt myself","user_id":"test_user"}'

# Test facility search
curl -X POST http://localhost:8000/api/facility_search \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","location":"Seattle, WA","treatment_type":"mental_health"}'
```

### **Vision Analysis Testing**
Upload test images via the vision test interface at `/vision-test` to validate:
- Medical document extraction
- Prescription label reading
- Insurance card processing
- Treatment form analysis

## 🚀 Deployment

### **Production Deployment**

1. **Environment Setup**
```bash
# Enable HTTPS
export USE_HTTPS=true
export SSL_CERT_FILE=/path/to/cert.pem
export SSL_KEY_FILE=/path/to/key.pem
export APP_URL=https://yourdomain.com
```

2. **Database Migration**
```bash
# Production database setup
export DATABASE_URL=postgresql://user:pass@prod-db/treatment_navigator
python -c "from services.database import db_manager; import asyncio; asyncio.run(db_manager.create_tables())"
```

3. **Process Management**
```bash
# Start in daemon mode
./start.sh --daemon --port 8000

# Or use process manager
gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### **Docker Deployment**
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 📊 Monitoring & Analytics

### **Debug Dashboard**
Access the debug dashboard at `/debug` for:
- **System Status**: Service health and connectivity
- **Performance Metrics**: Response times and error rates
- **Agent Activity**: Conversation flows and handoffs
- **Resource Usage**: API consumption and costs

### **Logging**
- **Structured JSON Logs**: Machine-readable log format
- **Log Levels**: Configurable verbosity (DEBUG, INFO, WARNING, ERROR)
- **Log Rotation**: Automatic file management
- **Error Tracking**: Exception monitoring and alerting

### **Usage Analytics**
- **API Consumption**: Track OpenAI and Arcade API usage
- **Cost Management**: Monitor daily/monthly spending limits
- **User Analytics**: Interaction patterns and success rates
- **Performance Optimization**: Identify bottlenecks and improvements

## 🔧 Configuration

### **Feature Flags**
Control system behavior through environment variables:

```env
# AI Features
ENABLE_VISION_ANALYSIS=true
ENABLE_AGENT_OPTIMIZATION=true
ENABLE_PROACTIVE_MONITORING=true

# External Integrations
ENABLE_ARCADE_GOOGLE_TOOLS=true
ENABLE_SLACK_INTEGRATION=false
ENABLE_LINKEDIN_INTEGRATION=false

# Safety Features
ENABLE_COST_TRACKING=true
GRACEFUL_DEGRADATION=true
MAX_CONCURRENT_VALIDATIONS=3
```

### **Cost Management**
- **Daily Limits**: Prevent unexpected API charges
- **Rate Limiting**: Control request frequency
- **Usage Tracking**: Monitor consumption patterns
- **Alert Thresholds**: Automated cost notifications

## 🤝 Contributing

### **Development Workflow**
1. **Fork** the repository
2. **Create feature branch**: `git checkout -b feature/amazing-feature`
3. **Make changes** with comprehensive tests
4. **Follow code style**: PEP 8 with type hints
5. **Submit pull request** with detailed description

### **Code Standards**
- **Type Hints**: All functions should include type annotations
- **Async/Await**: Use async patterns for I/O operations
- **Error Handling**: Comprehensive exception management
- **Documentation**: Docstrings for all public functions
- **Testing**: Unit tests for new functionality

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

### **Crisis Resources**
- **National Suicide Prevention Lifeline**: 988
- **Crisis Text Line**: Text HOME to 741741
- **Emergency Services**: 911

### **Technical Support**
- **Issues**: Report bugs via GitHub Issues
- **Documentation**: Comprehensive API docs at `/docs`
- **Community**: Discussion forums and support channels

## 🙏 Acknowledgments

- **OpenAI**: For providing advanced language models and agent frameworks
- **Arcade AI**: For tool integration and external service connectivity
- **Mental Health Community**: For guidance on safety features and best practices
- **Open Source Contributors**: For the foundational libraries that make this possible

---

**Built with ❤️ for mental health and substance abuse treatment accessibility** 