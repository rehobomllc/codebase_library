// Treatment Navigator - Main JavaScript

class TreatmentNavigator {
    constructor() {
        this.userId = null;
        this.isProcessing = false;
        this.conversationHistory = [];
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadStoredUserId();
        this.setupQuickActions();
        this.focusMessageInput();
    }
    
    bindEvents() {
        // Send message events
        const sendButton = document.getElementById('send-button');
        const messageInput = document.getElementById('user-message');
        
        if (sendButton) {
            sendButton.addEventListener('click', () => this.sendMessage());
        }
        
        if (messageInput) {
            messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }
        
        // User ID setup
        const setUserIdButton = document.getElementById('set-user-id');
        const userIdInput = document.getElementById('user-id');
        
        if (setUserIdButton) {
            setUserIdButton.addEventListener('click', () => this.setUserId());
        }
        
        if (userIdInput) {
            userIdInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.setUserId();
                }
            });
        }
        
        // Crisis banner interactions
        this.setupCrisisBanner();
        
        // Error handling for JS errors
        window.addEventListener('error', (e) => {
            this.logJSError(e);
        });
    }
    
    setupCrisisBanner() {
        const crisisBanner = document.getElementById('crisis-banner');
        if (crisisBanner) {
            // Add click tracking for crisis button
            const crisisButton = crisisBanner.querySelector('.crisis-button');
            if (crisisButton) {
                crisisButton.addEventListener('click', () => {
                    // Track crisis button click
                    this.trackEvent('crisis_button_clicked', {
                        timestamp: new Date().toISOString(),
                        user_id: this.userId || 'anonymous'
                    });
                });
            }
        }
    }
    
    setupQuickActions() {
        const quickActions = document.querySelectorAll('.quick-action');
        quickActions.forEach(button => {
            button.addEventListener('click', (e) => {
                const message = e.target.getAttribute('data-message');
                if (message) {
                    document.getElementById('user-message').value = message;
                    this.sendMessage();
                }
            });
        });
    }
    
    loadStoredUserId() {
        const storedUserId = localStorage.getItem('treatment_navigator_user_id');
        if (storedUserId) {
            this.userId = storedUserId;
            document.getElementById('user-id').value = storedUserId;
            this.updateUIForUser();
        }
    }
    
    setUserId() {
        const userIdInput = document.getElementById('user-id');
        const newUserId = userIdInput.value.trim();
        
        if (!newUserId) {
            this.showAlert('Please enter a valid user ID', 'warning');
            return;
        }
        
        // Validate user ID format
        if (newUserId.length < 3) {
            this.showAlert('User ID must be at least 3 characters long', 'warning');
            return;
        }
        
        this.userId = newUserId;
        window.currentUserId = newUserId; // Keep global reference in sync
        localStorage.setItem('treatment_navigator_user_id', newUserId);
        this.updateUIForUser();
        this.showAlert('User ID set successfully! You can now start chatting.', 'success');
        
        this.focusMessageInput();
    }
    
    updateUIForUser() {
        const setUserIdButton = document.getElementById('set-user-id');
        if (setUserIdButton) {
            setUserIdButton.textContent = 'Update ID';
            setUserIdButton.classList.add('updated');
        }
        
        // Enable chat interface
        const messageInput = document.getElementById('user-message');
        const sendButton = document.getElementById('send-button');
        
        if (messageInput) {
            messageInput.disabled = false;
            messageInput.placeholder = 'Type your message here...';
        }
        
        if (sendButton) {
            sendButton.disabled = false;
        }
    }
    
    focusMessageInput() {
        setTimeout(() => {
            const messageInput = document.getElementById('user-message');
            if (messageInput && this.userId) {
                messageInput.focus();
            }
        }, 100);
    }
    
    async sendMessage() {
        if (this.isProcessing) return;
        
        const messageInput = document.getElementById('user-message');
        const message = messageInput.value.trim();
        
        if (!message) {
            this.showAlert('Please enter a message', 'warning');
            return;
        }
        
        if (!this.userId) {
            this.showAlert('Please set your user ID first', 'warning');
            document.getElementById('user-id').focus();
            return;
        }
        
        this.isProcessing = true;
        this.updateSendButton(true);
        
        try {
            // Add user message to chat
            this.addMessageToChat(message, 'user');
            messageInput.value = '';
            
            // Show loading indicator
            this.showLoading('Getting response...');
            
            // Send to backend
            const response = await this.callChatAPI(message);
            
            if (response.reply) {
                this.addMessageToChat(response.reply, 'bot');
                
                // Check if bot suggests insurance card upload
                this.checkForInsuranceUploadSuggestion(response.reply);
                
                // Handle appointment scheduling if present
                if (response.appointment_id) {
                    this.handleAppointmentScheduled(response.appointment_id);
                }
            } else {
                throw new Error('No reply received from server');
            }
            
        } catch (error) {
            console.error('Error sending message:', error);
            this.addMessageToChat(
                'I apologize, but I encountered an error. Please try again. If you\'re in crisis, please call 988 immediately.',
                'bot',
                'error'
            );
            this.trackEvent('chat_error', {
                error: error.message,
                user_id: this.userId,
                message: message
            });
        } finally {
            this.isProcessing = false;
            this.updateSendButton(false);
            this.hideLoading();
            this.focusMessageInput();
        }
    }
    
    async callChatAPI(message) {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                user_id: this.userId
            })
        });
        
        if (!response.ok) {
            if (response.status === 401) {
                const errorData = await response.json();
                if (errorData.authorization_url) {
                    this.handleAuthorizationRequired(errorData);
                    return { reply: 'Authorization required. Please check the popup or notification.' };
                }
            }
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return await response.json();
    }
    
    handleAuthorizationRequired(authData) {
        const message = `To access Google Workspace features (Calendar, Gmail, Docs), please authorize the application: ${authData.authorization_url}`;
        this.addMessageToChat(message, 'bot', 'warning');
        
        // Open authorization URL in new tab
        if (authData.authorization_url) {
            window.open(authData.authorization_url, '_blank');
        }
    }
    
    checkForInsuranceUploadSuggestion(botReply) {
        // Keywords that suggest insurance verification
        const insuranceKeywords = [
            'insurance card', 'upload', 'photo', 'image', 'verify coverage',
            'insurance information', 'member id', 'plan details', 'insurance plan'
        ];
        
        const replyLower = botReply.toLowerCase();
        const suggestsUpload = insuranceKeywords.some(keyword => replyLower.includes(keyword));
        
        if (suggestsUpload) {
            // Show the upload button
            if (window.showInsuranceUploadOption) {
                window.showInsuranceUploadOption();
            }
        }
    }

    handleAppointmentScheduled(appointmentId) {
        this.trackEvent('appointment_scheduled', {
            appointment_id: appointmentId,
            user_id: this.userId,
            timestamp: new Date().toISOString()
        });
        
        // Could add UI feedback here
        this.showAlert('Appointment scheduled successfully!', 'success');
    }
    
    addMessageToChat(message, sender, type = 'normal') {
        const chatMessages = document.getElementById('chat-messages');
        if (!chatMessages) return;
        
        const messageElement = document.createElement('div');
        messageElement.className = `message ${sender}-message`;
        
        if (type === 'error') {
            messageElement.classList.add('error-message');
        } else if (type === 'warning') {
            messageElement.classList.add('warning-message');
        }
        
        const avatarIcon = sender === 'user' ? 'fa-user' : 'fa-user-nurse';
        
        messageElement.innerHTML = `
            <div class="message-avatar">
                <i class="fas ${avatarIcon}"></i>
            </div>
            <div class="message-content">
                <p>${this.formatMessage(message)}</p>
            </div>
        `;
        
        chatMessages.appendChild(messageElement);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        // Add to conversation history
        this.conversationHistory.push({
            message: message,
            sender: sender,
            timestamp: new Date().toISOString()
        });
    }
    
    formatMessage(message) {
        // Basic formatting for messages
        return message
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
    }
    
    updateSendButton(isLoading) {
        const sendButton = document.getElementById('send-button');
        if (!sendButton) return;
        
        if (isLoading) {
            sendButton.disabled = true;
            sendButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        } else {
            sendButton.disabled = false;
            sendButton.innerHTML = '<i class="fas fa-paper-plane"></i>';
        }
    }
    
    showLoading(message = 'Processing...') {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            const loadingText = loadingOverlay.querySelector('p');
            if (loadingText) {
                loadingText.textContent = message;
            }
            loadingOverlay.classList.remove('hidden');
        }
    }
    
    hideLoading() {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            loadingOverlay.classList.add('hidden');
        }
    }
    
    showAlert(message, type = 'info') {
        // Create alert element
        const alert = document.createElement('div');
        alert.className = `alert alert-${type}`;
        alert.style.cssText = `
            position: fixed;
            top: 100px;
            right: 20px;
            background: ${type === 'success' ? '#10b981' : type === 'warning' ? '#f59e0b' : '#3b82f6'};
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 0.5rem;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
            z-index: 10000;
            max-width: 400px;
            transform: translateX(100%);
            transition: transform 0.3s ease;
        `;
        
        alert.innerHTML = `
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'warning' ? 'fa-exclamation-triangle' : 'fa-info-circle'}"></i>
                <span>${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" style="background: none; border: none; color: white; margin-left: auto; cursor: pointer;">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        
        document.body.appendChild(alert);
        
        // Animate in
        setTimeout(() => {
            alert.style.transform = 'translateX(0)';
        }, 100);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            if (alert.parentElement) {
                alert.style.transform = 'translateX(100%)';
                setTimeout(() => {
                    if (alert.parentElement) {
                        alert.remove();
                    }
                }, 300);
            }
        }, 5000);
    }
    
    trackEvent(eventName, data) {
        // Track events for analytics/debugging
        console.log(`Event: ${eventName}`, data);
        
        // Could send to analytics service here
        // This could also be sent to the debug endpoint
        fetch('/api/debug/js-error', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                type: 'event',
                event: eventName,
                data: data,
                timestamp: new Date().toISOString()
            })
        }).catch(error => {
            console.warn('Failed to track event:', error);
        });
    }
    
    logJSError(error) {
        const errorData = {
            message: error.message || 'Unknown error',
            filename: error.filename || 'Unknown file',
            lineno: error.lineno || 'Unknown line',
            colno: error.colno || 'Unknown column',
            stack: error.error?.stack || 'No stack trace',
            timestamp: new Date().toISOString(),
            user_id: this.userId || 'anonymous',
            url: window.location.href
        };
        
        fetch('/api/debug/js-error', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(errorData)
        }).catch(err => {
            console.warn('Failed to log JS error:', err);
        });
    }
}

// Global functions for integration
window.addBotMessage = function(message) {
    if (window.treatmentNavigator) {
        window.treatmentNavigator.addMessageToChat(message, 'bot');
    }
};

window.sendMessageToChat = function(message) {
    if (window.treatmentNavigator) {
        const messageInput = document.getElementById('user-message');
        if (messageInput) {
            messageInput.value = message;
            window.treatmentNavigator.sendMessage();
        }
    }
};

window.currentUserId = null;

// Utility functions
function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function generateUserId() {
    return 'user_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.treatmentNavigator = new TreatmentNavigator();
    
    // Set global currentUserId
    window.currentUserId = window.treatmentNavigator.userId;
    
    // Add helpful shortcut for generating user ID
    const userIdInput = document.getElementById('user-id');
    if (userIdInput && !userIdInput.value) {
        const generateButton = document.createElement('button');
        generateButton.type = 'button';
        generateButton.textContent = 'Generate ID';
        generateButton.className = 'generate-id-button';
        generateButton.style.cssText = `
            margin-left: 0.5rem;
            padding: 0.5rem 1rem;
            background: #6b7280;
            color: white;
            border: none;
            border-radius: 0.5rem;
            cursor: pointer;
            font-size: 0.875rem;
        `;
        
        generateButton.addEventListener('click', () => {
            userIdInput.value = generateUserId();
        });
        
        userIdInput.parentElement.appendChild(generateButton);
    }
});

// Export for testing/debugging
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TreatmentNavigator;
} 