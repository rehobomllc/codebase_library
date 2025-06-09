#!/bin/bash

# 🏥 Treatment Navigator - Complete Startup Script
# This script will start all required services and the Treatment Navigator application

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
LOG_DIR="$SCRIPT_DIR/logs"
PID_DIR="$SCRIPT_DIR/pids"

# Default settings
CONSOLE_LOGS=true
DAEMON_MODE=false
PORT=8000
HOST="0.0.0.0"

# Create necessary directories
mkdir -p "$LOG_DIR" "$PID_DIR"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a service is running
is_service_running() {
    local service_name="$1"
    local pid_file="$PID_DIR/${service_name}.pid"
    
    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        else
            rm -f "$pid_file"
            return 1
        fi
    fi
    return 1
}

# Function to start Redis if not running
start_redis() {
    print_status "Checking Redis..."
    
    if redis-cli ping >/dev/null 2>&1; then
        print_success "Redis is already running"
        return 0
    fi
    
    print_status "Starting Redis server..."
    
    if command_exists brew; then
        # macOS with Homebrew
        brew services start redis >/dev/null 2>&1 || {
            print_warning "Homebrew Redis service failed, trying direct start..."
            redis-server --daemonize yes --logfile "$LOG_DIR/redis.log"
        }
    elif command_exists systemctl; then
        # Linux with systemd
        sudo systemctl start redis-server >/dev/null 2>&1 || {
            print_warning "Systemd Redis failed, trying direct start..."
            redis-server --daemonize yes --logfile "$LOG_DIR/redis.log"
        }
    else
        # Direct start
        redis-server --daemonize yes --logfile "$LOG_DIR/redis.log"
    fi
    
    # Wait for Redis to start
    for i in {1..10}; do
        if redis-cli ping >/dev/null 2>&1; then
            print_success "Redis started successfully"
            return 0
        fi
        sleep 1
    done
    
    print_error "Failed to start Redis"
    return 1
}

# Function to start PostgreSQL if not running
start_postgresql() {
    print_status "Checking PostgreSQL..."
    
    if pg_isready >/dev/null 2>&1; then
        print_success "PostgreSQL is already running"
        return 0
    fi
    
    print_status "Starting PostgreSQL..."
    
    if command_exists brew; then
        # macOS with Homebrew
        brew services start postgresql >/dev/null 2>&1
    elif command_exists systemctl; then
        # Linux with systemd
        sudo systemctl start postgresql >/dev/null 2>&1
    else
        print_warning "Cannot auto-start PostgreSQL. Please start it manually."
        return 1
    fi
    
    # Wait for PostgreSQL to start
    for i in {1..15}; do
        if pg_isready >/dev/null 2>&1; then
            print_success "PostgreSQL started successfully"
            return 0
        fi
        sleep 1
    done
    
    print_error "Failed to start PostgreSQL"
    return 1
}

# Function to setup virtual environment
setup_venv() {
    print_status "Setting up Python virtual environment..."
    
    if [[ ! -d "$VENV_DIR" ]]; then
        print_status "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip >/dev/null 2>&1
    
    # Install requirements
    if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
        print_status "Installing Python dependencies..."
        pip install -r "$SCRIPT_DIR/requirements.txt" >/dev/null 2>&1
        print_success "Dependencies installed"
    else
        print_warning "requirements.txt not found"
    fi
}

# Function to check environment variables
check_env_vars() {
    print_status "Checking environment variables..."
    
    # Source .env file if it exists
    if [[ -f "$SCRIPT_DIR/.env" ]]; then
        source "$SCRIPT_DIR/.env"
        print_success "Environment variables loaded from .env"
    else
        print_warning ".env file not found. Using system environment variables."
    fi
    
    # Check critical environment variables
    local missing_vars=()
    
    if [[ -z "$DATABASE_URL" ]]; then
        missing_vars+=("DATABASE_URL")
    fi
    
    if [[ -z "$OPENAI_API_KEY" ]]; then
        missing_vars+=("OPENAI_API_KEY")
    fi
    
    if [[ -z "$ARCADE_API_KEY" ]]; then
        missing_vars+=("ARCADE_API_KEY")
    fi
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        print_error "Missing required environment variables: ${missing_vars[*]}"
        print_error "Please set these in your .env file or system environment"
        return 1
    fi
    
    print_success "Environment variables validated"
    return 0
}

# Function to test database connection
test_database() {
    print_status "Testing database connection..."
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Test database connection using Python
    python3 -c "
import asyncio
import asyncpg
import os
import sys
from dotenv import load_dotenv

load_dotenv()

async def test_db():
    try:
        conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
        await conn.execute('SELECT 1')
        await conn.close()
        print('Database connection successful')
        return True
    except Exception as e:
        print(f'Database connection failed: {e}')
        return False

result = asyncio.run(test_db())
sys.exit(0 if result else 1)
" >/dev/null 2>&1
    
    if [[ $? -eq 0 ]]; then
        print_success "Database connection test passed"
        return 0
    else
        print_error "Database connection test failed"
        return 1
    fi
}

# Function to start the Treatment Navigator application
start_treatment_navigator() {
    print_status "Starting Treatment Navigator application..."
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Check if app is already running
    if is_service_running "treatment_navigator"; then
        print_warning "Treatment Navigator appears to be already running"
        return 0
    fi
    
    if [[ "$DAEMON_MODE" == "true" ]]; then
        # Start in daemon mode
        print_status "Starting Treatment Navigator in daemon mode on $HOST:$PORT..."
        nohup uvicorn app:app --host "$HOST" --port "$PORT" \
            > "$LOG_DIR/treatment_navigator.log" 2>&1 &
        echo $! > "$PID_DIR/treatment_navigator.pid"
        
        # Wait a moment and check if it started
        sleep 3
        if is_service_running "treatment_navigator"; then
            print_success "Treatment Navigator started successfully in daemon mode"
            print_status "Access the application at: http://$HOST:$PORT"
            print_status "Debug dashboard at: http://$HOST:$PORT/debug"
            print_status "Logs: $LOG_DIR/treatment_navigator.log"
        else
            print_error "Treatment Navigator failed to start in daemon mode"
            return 1
        fi
    else
        # Start in console mode
        print_success "Starting Treatment Navigator in console mode on $HOST:$PORT..."
        print_status "Access the application at: http://$HOST:$PORT"
        print_status "Debug dashboard at: http://$HOST:$PORT/debug"
        print_status "Press Ctrl+C to stop the server"
        echo ""
        uvicorn app:app --host "$HOST" --port "$PORT"
    fi
}

# Function to stop services
stop_services() {
    print_status "Stopping Treatment Navigator services..."
    
    if is_service_running "treatment_navigator"; then
        local pid=$(cat "$PID_DIR/treatment_navigator.pid")
        kill "$pid" 2>/dev/null || true
        rm -f "$PID_DIR/treatment_navigator.pid"
        print_success "Treatment Navigator stopped"
    else
        print_status "Treatment Navigator was not running"
    fi
}

# Function to show status
show_status() {
    echo -e "${BLUE}Treatment Navigator Status${NC}"
    echo "=========================="
    
    # Check Redis
    if redis-cli ping >/dev/null 2>&1; then
        echo -e "Redis: ${GREEN}Running${NC}"
    else
        echo -e "Redis: ${RED}Not Running${NC}"
    fi
    
    # Check PostgreSQL
    if pg_isready >/dev/null 2>&1; then
        echo -e "PostgreSQL: ${GREEN}Running${NC}"
    else
        echo -e "PostgreSQL: ${RED}Not Running${NC}"
    fi
    
    # Check Treatment Navigator
    if is_service_running "treatment_navigator"; then
        echo -e "Treatment Navigator: ${GREEN}Running${NC} (PID: $(cat "$PID_DIR/treatment_navigator.pid"))"
        echo -e "URL: ${BLUE}http://$HOST:$PORT${NC}"
        echo -e "Debug: ${BLUE}http://$HOST:$PORT/debug${NC}"
    else
        echo -e "Treatment Navigator: ${RED}Not Running${NC}"
    fi
    
    echo ""
    echo "Log files in: $LOG_DIR"
    echo "PID files in: $PID_DIR"
}

# Function to show usage
show_usage() {
    echo "Treatment Navigator Startup Script"
    echo "================================="
    echo ""
    echo "Usage: $0 [options] [command]"
    echo ""
    echo "Commands:"
    echo "  start     Start all services (default)"
    echo "  stop      Stop all services"
    echo "  restart   Restart all services"
    echo "  status    Show service status"
    echo "  setup     Setup environment only"
    echo ""
    echo "Options:"
    echo "  --daemon  Run in daemon mode (background)"
    echo "  --port    Specify port (default: 8000)"
    echo "  --host    Specify host (default: 0.0.0.0)"
    echo "  --help    Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Start in console mode"
    echo "  $0 --daemon          # Start in daemon mode"
    echo "  $0 --port 9000       # Start on port 9000"
    echo "  $0 stop               # Stop all services"
    echo "  $0 status             # Show status"
}

# Parse command line arguments
COMMAND="start"
while [[ $# -gt 0 ]]; do
    case $1 in
        --daemon)
            DAEMON_MODE=true
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --help)
            show_usage
            exit 0
            ;;
        start|stop|restart|status|setup)
            COMMAND="$1"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main script execution
echo -e "${BLUE}🏥 Treatment Navigator - Startup Script${NC}"
echo "======================================"

case $COMMAND in
    setup)
        start_redis
        start_postgresql
        setup_venv
        check_env_vars
        test_database
        print_success "Environment setup complete"
        ;;
    start)
        start_redis
        start_postgresql
        setup_venv
        check_env_vars
        test_database
        start_treatment_navigator
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        sleep 2
        start_redis
        start_postgresql
        setup_venv
        check_env_vars
        test_database
        start_treatment_navigator
        ;;
    status)
        show_status
        ;;
    *)
        print_error "Unknown command: $COMMAND"
        show_usage
        exit 1
        ;;
esac 