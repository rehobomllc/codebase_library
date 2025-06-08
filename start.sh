#!/bin/bash

# 🎓 Scholarship Finder - Complete Startup Script
# This script will start all required services and the application

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

# Logging mode configuration (console by default, background with --daemon flag)
CONSOLE_LOGS=true
DAEMON_MODE=false

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

# Function to generate SSL certificates
generate_ssl_certificates() {
    print_status "Setting up SSL certificates for HTTPS..."
    
    # Activate virtual environment first
    source "$VENV_DIR/bin/activate"
    
    # Run the SSL certificate generation script
    if python "$SCRIPT_DIR/generate_ssl_cert.py"; then
        print_success "SSL certificates generated/verified successfully"
        return 0
    else
        print_error "Failed to generate SSL certificates"
        print_warning "Falling back to HTTP mode"
        return 1
    fi
}

# Function to get the application URL based on HTTPS configuration
get_app_url() {
    # Source .env to get HTTPS configuration
    if [[ -f "$SCRIPT_DIR/.env" ]]; then
        source "$SCRIPT_DIR/.env"
    fi
    
    if [[ "$USE_HTTPS" == "true" ]]; then
        echo "https://localhost:5000"
    else
        echo "http://localhost:5000"
    fi
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
    
    if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
        print_error ".env file not found!"
        print_status "Creating template .env file..."
        cat > "$SCRIPT_DIR/.env" << EOF
# Critical API Keys - REPLACE WITH YOUR ACTUAL KEYS
ARCADE_API_KEY=your_arcade_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Database Configuration
DATABASE_URL=postgresql://scholarship_user:your_password@localhost:5432/scholarship_finder

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Application Settings
DEBUG=true
LOG_LEVEL=INFO

# HTTPS Configuration (auto-generated by SSL script)
USE_HTTPS=false
SSL_CERT_FILE=
SSL_KEY_FILE=
APP_URL=http://localhost:5000
EOF
        print_warning "Please edit .env file with your actual API keys and database credentials"
        print_status "Then run this script again"
        exit 1
    fi
    
    # Source the .env file
    source "$SCRIPT_DIR/.env"
    
    # Check critical variables
    if [[ "$ARCADE_API_KEY" == "your_arcade_api_key_here" ]] || [[ -z "$ARCADE_API_KEY" ]]; then
        print_error "ARCADE_API_KEY not set in .env file"
        return 1
    fi
    
    if [[ "$OPENAI_API_KEY" == "your_openai_api_key_here" ]] || [[ -z "$OPENAI_API_KEY" ]]; then
        print_error "OPENAI_API_KEY not set in .env file"
        return 1
    fi
    
    print_success "Environment variables validated"
}

# Function to initialize database
init_database() {
    print_status "Initializing database..."
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Run database initialization
    if python "$SCRIPT_DIR/init_db.py" >/dev/null 2>&1; then
        print_success "Database initialized"
    else
        print_warning "Database initialization had issues (may already be initialized)"
    fi
}

# Function to start Celery worker
start_celery() {
    print_status "Starting Celery worker..."
    
    if is_service_running "celery"; then
        print_success "Celery worker is already running"
        return 0
    fi
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Start Celery worker
    cd "$SCRIPT_DIR"
    
    if [[ "$CONSOLE_LOGS" == "true" && "$DAEMON_MODE" == "false" ]]; then
        # Console logging mode - output to both console and log file
        print_status "Starting Celery worker with console output..."
        celery -A tasks.celery_app worker --loglevel=info --concurrency=4 2>&1 | tee "$LOG_DIR/celery.log" &
        local celery_pid=$!
    else
        # Background daemon mode - output only to log file
        print_status "Starting Celery worker in daemon mode..."
        nohup celery -A tasks.celery_app worker --loglevel=info --concurrency=4 \
            > "$LOG_DIR/celery.log" 2>&1 &
        local celery_pid=$!
    fi
    
    echo $celery_pid > "$PID_DIR/celery.pid"
    
    # Wait a moment and check if it's still running
    sleep 3
    if kill -0 $celery_pid 2>/dev/null; then
        print_success "Celery worker started (PID: $celery_pid)"
        if [[ "$CONSOLE_LOGS" == "true" && "$DAEMON_MODE" == "false" ]]; then
            print_status "📊 Celery logs will appear in this console"
        fi
    else
        print_error "Celery worker failed to start"
        return 1
    fi
}

# Function to start FastAPI application
start_fastapi() {
    print_status "Starting FastAPI application..."
    
    if is_service_running "fastapi"; then
        print_success "FastAPI application is already running"
        return 0
    fi
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Start FastAPI application
    cd "$SCRIPT_DIR"
    
    if [[ "$CONSOLE_LOGS" == "true" && "$DAEMON_MODE" == "false" ]]; then
        # Console logging mode - output to both console and log file
        print_status "Starting FastAPI application with console output..."
        python app.py 2>&1 | tee "$LOG_DIR/fastapi.log" &
        local fastapi_pid=$!
    else
        # Background daemon mode - output only to log file
        print_status "Starting FastAPI application in daemon mode..."
        nohup python app.py > "$LOG_DIR/fastapi.log" 2>&1 &
        local fastapi_pid=$!
    fi
    
    echo $fastapi_pid > "$PID_DIR/fastapi.pid"
    
    # Get the application URL
    local app_url=$(get_app_url)
    
    # Wait for the application to start
    print_status "Waiting for application to start..."
    for i in {1..30}; do
        if curl -k -s "$app_url" >/dev/null 2>&1; then
            print_success "FastAPI application started (PID: $fastapi_pid)"
            print_success "Application is running at: $app_url"
            if [[ "$USE_HTTPS" == "true" ]]; then
                print_warning "Using self-signed certificate - browsers will show security warnings"
                print_status "To bypass: Click 'Advanced' → 'Proceed to localhost (unsafe)'"
            fi
            if [[ "$CONSOLE_LOGS" == "true" && "$DAEMON_MODE" == "false" ]]; then
                print_status "📊 FastAPI logs will appear in this console"
            fi
            return 0
        fi
        sleep 1
    done
    
    print_error "FastAPI application failed to start or is not responding"
    return 1
}

# Function to show status
show_status() {
    echo
    print_status "=== SERVICE STATUS ==="
    
    # Get app URL
    local app_url=$(get_app_url)
    
    # Redis
    if redis-cli ping >/dev/null 2>&1; then
        print_success "✅ Redis: Running"
    else
        print_error "❌ Redis: Not running"
    fi
    
    # PostgreSQL
    if pg_isready >/dev/null 2>&1; then
        print_success "✅ PostgreSQL: Running"
    else
        print_error "❌ PostgreSQL: Not running"
    fi
    
    # Celery
    if is_service_running "celery"; then
        local celery_pid=$(cat "$PID_DIR/celery.pid")
        print_success "✅ Celery Worker: Running (PID: $celery_pid)"
    else
        print_error "❌ Celery Worker: Not running"
    fi
    
    # FastAPI
    if is_service_running "fastapi"; then
        local fastapi_pid=$(cat "$PID_DIR/fastapi.pid")
        print_success "✅ FastAPI App: Running (PID: $fastapi_pid)"
        if [[ "$USE_HTTPS" == "true" ]]; then
            print_success "🔐 HTTPS: Enabled with SSL certificates"
        else
            print_success "🌐 HTTP: Enabled"
        fi
        print_success "🌐 Application URL: $app_url"
    else
        print_error "❌ FastAPI App: Not running"
    fi
    
    # SSL Certificate status
    if [[ "$USE_HTTPS" == "true" ]] && [[ -f "$SSL_CERT_FILE" ]] && [[ -f "$SSL_KEY_FILE" ]]; then
        print_success "🔐 SSL Certificates: Valid and present"
    elif [[ "$USE_HTTPS" == "true" ]]; then
        print_error "❌ SSL Certificates: Missing or invalid"
    fi
    
    echo
    print_status "=== LOGGING CONFIGURATION ==="
    if [[ "$CONSOLE_LOGS" == "true" && "$DAEMON_MODE" == "false" ]]; then
        print_success "📊 Logging Mode: Console + Files"
        print_status "   Logs appear in terminal AND saved to files"
    else
        print_success "📄 Logging Mode: Files Only (Daemon)"
        print_status "   Logs saved to files, running in background"
    fi
    
    echo
    print_status "=== LOG FILES ==="
    echo "📄 Application logs: $LOG_DIR/fastapi.log"
    echo "📄 Celery logs: $LOG_DIR/celery.log"
    echo "📄 Redis logs: $LOG_DIR/redis.log"
    echo
}

# Function to stop all services
stop_services() {
    print_status "Stopping all services..."
    
    # Stop FastAPI
    if [[ -f "$PID_DIR/fastapi.pid" ]]; then
        local fastapi_pid=$(cat "$PID_DIR/fastapi.pid")
        if kill -0 $fastapi_pid 2>/dev/null; then
            kill $fastapi_pid
            print_success "FastAPI application stopped"
        fi
        rm -f "$PID_DIR/fastapi.pid"
    fi
    
    # Stop Celery
    if [[ -f "$PID_DIR/celery.pid" ]]; then
        local celery_pid=$(cat "$PID_DIR/celery.pid")
        if kill -0 $celery_pid 2>/dev/null; then
            kill $celery_pid
            print_success "Celery worker stopped"
        fi
        rm -f "$PID_DIR/celery.pid"
    fi
    
    print_success "All services stopped"
}

# Function to parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --daemon|-d)
                DAEMON_MODE=true
                CONSOLE_LOGS=false
                print_status "Running in daemon mode (background logging)"
                shift
                ;;
            --background|-b)
                DAEMON_MODE=true
                CONSOLE_LOGS=false
                print_status "Running in background mode (file logging only)"
                shift
                ;;
            --console|-c)
                CONSOLE_LOGS=true
                DAEMON_MODE=false
                print_status "Running with console logging enabled"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                # Unknown option, keep it for case statement
                break
                ;;
        esac
    done
}

# Function to show help
show_help() {
    echo "🎓 Scholarship Finder - Startup Script"
    echo "======================================"
    echo
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo
    echo "Commands:"
    echo "  start        - Start all services (default)"
    echo "  stop         - Stop all services"
    echo "  status       - Show service status"
    echo "  restart      - Restart all services"
    echo "  logs         - Show recent logs"
    echo "  enable-https - Enable HTTPS with self-signed certificates"
    echo "  disable-https- Disable HTTPS and use HTTP"
    echo
    echo "Options:"
    echo "  --console, -c    - Enable console logging (default)"
    echo "  --daemon, -d     - Run in daemon mode (background logging only)"
    echo "  --background, -b - Same as --daemon"
    echo "  --help, -h       - Show this help message"
    echo
    echo "Examples:"
    echo "  $0 start                 # Start with console logging (default)"
    echo "  $0 start --daemon        # Start in background mode"
    echo "  $0 start --console       # Explicitly enable console logging"
    echo "  $0 restart --background  # Restart in background mode"
    echo
    echo "Logging Modes:"
    echo "  Console Mode (default): Logs appear in terminal AND saved to files"
    echo "                         Script waits and shows live logs until Ctrl+C"
    echo "  Daemon Mode: Logs only saved to files, services run in background"
    echo "               Script exits after starting services"
    echo
    echo "HTTPS Configuration:"
    echo "  • HTTPS uses self-signed certificates for local development"
    echo "  • Browsers will show security warnings for self-signed certificates"
    echo "  • Use 'enable-https' to generate certificates and enable HTTPS"
    echo "  • Use 'disable-https' to switch back to HTTP"
    echo
}

# Main execution
main() {
    # Parse command line arguments first
    parse_args "$@"
    
    echo "🎓 Scholarship Finder - Startup Script"
    echo "======================================"
    
    # Get the command (first non-option argument)
    local command="${1:-start}"
    
    case "$command" in
        "start")
            # Check dependencies
            if ! command_exists python3; then
                print_error "Python 3 is required but not installed"
                exit 1
            fi
            
            if ! command_exists redis-cli; then
                print_error "Redis is required but not installed"
                print_status "Install Redis: brew install redis (macOS) or apt install redis-server (Ubuntu)"
                exit 1
            fi
            
            if ! command_exists pg_isready; then
                print_error "PostgreSQL is required but not installed"
                print_status "Install PostgreSQL: brew install postgresql (macOS) or apt install postgresql (Ubuntu)"
                exit 1
            fi
            
            # Start services
            start_redis || exit 1
            start_postgresql || exit 1
            setup_venv || exit 1
            check_env_vars || exit 1
            
            # Generate SSL certificates if needed
            generate_ssl_certificates
            
            init_database || exit 1
            start_celery || exit 1
            start_fastapi || exit 1
            
            show_status
            
            # Get the final app URL for display
            local app_url=$(get_app_url)
            
            echo
            print_success "🎉 All services started successfully!"
            print_success "🌐 Open your browser to: $app_url"
            if [[ "$USE_HTTPS" == "true" ]]; then
                print_warning "⚠️  Self-signed certificate - browsers will show security warnings"
                print_status "   To bypass: Click 'Advanced' → 'Proceed to localhost (unsafe)'"
                print_status "   Or add certificate exception in browser settings"
            fi
            
            if [[ "$CONSOLE_LOGS" == "true" && "$DAEMON_MODE" == "false" ]]; then
                print_status "📊 Console logging enabled - logs will appear below"
                print_status "   Log files are also saved to: $LOG_DIR/"
                print_warning "⚠️  Keep this terminal open to see live logs"
                print_status "🛑 Press Ctrl+C to stop all services"
                echo
                print_status "=== LIVE LOGS ==="
                
                # Wait for processes in console mode
                wait
            else
                print_status "📄 Services running in daemon mode"
                print_status "📊 Use './start.sh status' to check service status"
                print_status "📄 Use './start.sh logs' to view recent logs"
                print_status "🛑 Use './start.sh stop' to stop all services"
            fi
            ;;
            
        "stop")
            stop_services
            ;;
            
        "status")
            show_status
            ;;
            
        "restart")
            stop_services
            sleep 2
            
            # Preserve logging mode for restart
            local restart_args=""
            if [[ "$DAEMON_MODE" == "true" ]]; then
                restart_args="--daemon"
            elif [[ "$CONSOLE_LOGS" == "true" ]]; then
                restart_args="--console"
            fi
            
            $0 start $restart_args
            ;;
            
        "logs")
            print_status "Recent application logs:"
            tail -n 50 "$LOG_DIR/fastapi.log" 2>/dev/null || echo "No FastAPI logs found"
            echo
            print_status "Recent Celery logs:"
            tail -n 50 "$LOG_DIR/celery.log" 2>/dev/null || echo "No Celery logs found"
            ;;
            
        "enable-https")
            print_status "Enabling HTTPS for the scholarship finder..."
            
            # Check dependencies
            if ! command_exists python3; then
                print_error "Python 3 is required but not installed"
                exit 1
            fi
            
            # Setup virtual environment if needed
            if [[ ! -d "$VENV_DIR" ]]; then
                setup_venv || exit 1
            else
                source "$VENV_DIR/bin/activate"
            fi
            
            # Generate SSL certificates
            if generate_ssl_certificates; then
                print_success "🔐 HTTPS enabled successfully!"
                print_status "🌐 Your application will now use: https://localhost:5000"
                print_warning "⚠️  Remember to restart the application for changes to take effect"
                print_status "   Use './start.sh restart' to restart with HTTPS"
            else
                print_error "Failed to enable HTTPS"
                exit 1
            fi
            ;;
            
        "disable-https")
            print_status "Disabling HTTPS for the scholarship finder..."
            
            if [[ -f "$SCRIPT_DIR/.env" ]]; then
                # Update .env to disable HTTPS
                sed -i.bak 's/USE_HTTPS=true/USE_HTTPS=false/g' "$SCRIPT_DIR/.env"
                sed -i.bak 's|APP_URL=https://localhost:5000|APP_URL=http://localhost:5000|g' "$SCRIPT_DIR/.env"
                
                print_success "🌐 HTTPS disabled successfully!"
                print_status "🌐 Your application will now use: http://localhost:5000"
                print_warning "⚠️  Remember to restart the application for changes to take effect"
                print_status "   Use './start.sh restart' to restart with HTTP"
            else
                print_error ".env file not found"
                exit 1
            fi
            ;;
            
        *)
            show_help
            exit 1
            ;;
    esac
}

# Function to handle script interruption
handle_interrupt() {
    echo
    if [[ "$CONSOLE_LOGS" == "true" && "$DAEMON_MODE" == "false" ]]; then
        print_status "🛑 Console logging interrupted - stopping all services..."
        stop_services
        print_success "✅ All services stopped"
    else
        print_status "Script interrupted. Use \"./start.sh stop\" to stop services."
    fi
    exit 0
}

# Trap to cleanup on exit
trap 'handle_interrupt' INT TERM

# Run main function
main "$@" 