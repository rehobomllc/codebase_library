# 🏥 Rehobom Treatment Navigator

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

## 🚀 Quick Start

See the main project README for detailed setup instructions.

```bash
cd projects/rehobom-treatment-system
pip install -r requirements.txt
./start.sh
```

## 📁 Project Structure

```
rehobom-treatment-system/
├── app.py                      # Main FastAPI application
├── config.py                  # Configuration management
├── requirements.txt            # Python dependencies
├── start.sh                   # Startup script
├── tasks.py                   # Background task definitions
│
├── services/                   # Core business services
├── treatment_agents/          # AI agent implementations
├── utils/                     # Utility modules
├── templates/                 # Web interface
├── static/                    # Frontend assets
└── logs/                      # Application logs
```

## 🔧 Configuration

This project requires several environment variables. See `.env.example` for configuration options.

## 🛡️ Safety Features

The platform includes comprehensive crisis detection, privacy protection, and content validation systems designed for healthcare environments.

---

Part of the [Rehobom LLC Code Library](../../README.md) 