/*!
 * Treatment Navigator - Common JavaScript Utilities
 * Healthcare Application with Accessibility and Security Features
 */

// Global application object
window.TreatmentNavigator = window.TreatmentNavigator || {};

(function(TN) {
    'use strict';
    
    // Configuration
    TN.config = {
        apiBaseUrl: '/api',
        sessionTimeout: 30 * 60 * 1000, // 30 minutes for healthcare security
        debounceDelay: 300,
        maxRetries: 3,
        timeouts: {
            default: 10000,
            vision: 30000,
            search: 5000
        }
    };
    
    // State management
    TN.state = {
        user: null,
        session: null,
        notifications: []
    };
    
    // Utility functions
    TN.utils = {
        
        // Debounce function for search/input optimization
        debounce: function(func, wait, immediate) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    timeout = null;
                    if (!immediate) func(...args);
                };
                const callNow = immediate && !timeout;
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
                if (callNow) func(...args);
            };
        },
        
        // Throttle function for scroll/resize events
        throttle: function(func, limit) {
            let inThrottle;
            return function(...args) {
                if (!inThrottle) {
                    func.apply(this, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        },
        
        // Sanitize HTML to prevent XSS
        sanitizeHTML: function(str) {
            const temp = document.createElement('div');
            temp.textContent = str;
            return temp.innerHTML;
        },
        
        // Format phone numbers for healthcare context
        formatPhoneNumber: function(phone) {
            const cleaned = phone.replace(/\D/g, '');
            if (cleaned.length === 10) {
                return `(${cleaned.slice(0,3)}) ${cleaned.slice(3,6)}-${cleaned.slice(6)}`;
            } else if (cleaned.length === 11 && cleaned[0] === '1') {
                return `+1 (${cleaned.slice(1,4)}) ${cleaned.slice(4,7)}-${cleaned.slice(7)}`;
            }
            return phone; // Return original if can't format
        },
        
        // Validate email addresses
        isValidEmail: function(email) {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            return emailRegex.test(email);
        },
        
        // Generate unique IDs for dynamic content
        generateId: function(prefix = 'tn') {
            return `${prefix}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        },
        
        // Format dates for healthcare context
        formatDate: function(date, format = 'medical') {
            const d = new Date(date);
            if (isNaN(d.getTime())) return 'Invalid Date';
            
            const options = {
                medical: { 
                    year: 'numeric', 
                    month: '2-digit', 
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                },
                friendly: { 
                    year: 'numeric', 
                    month: 'long', 
                    day: 'numeric' 
                },
                time: { 
                    hour: '2-digit', 
                    minute: '2-digit',
                    hour12: true 
                }
            };
            
            return d.toLocaleDateString('en-US', options[format] || options.medical);
        },
        
        // Get user's timezone for appointment scheduling
        getUserTimezone: function() {
            return Intl.DateTimeFormat().resolvedOptions().timeZone;
        },
        
        // Copy text to clipboard
        copyToClipboard: async function(text) {
            try {
                await navigator.clipboard.writeText(text);
                TN.notifications.show('Copied to clipboard', 'success');
                return true;
            } catch (err) {
                console.error('Failed to copy: ', err);
                TN.notifications.show('Failed to copy to clipboard', 'error');
                return false;
            }
        },
        
        // Check if user prefers reduced motion
        prefersReducedMotion: function() {
            return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        },
        
        // Get CSS custom property value
        getCSSVariable: function(variable) {
            return getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
        }
    };
    
    // API helper functions
    TN.api = {
        
        // Base fetch wrapper with error handling
        request: async function(url, options = {}) {
            const defaultOptions = {
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                timeout: TN.config.timeouts.default
            };
            
            // Add CSRF token if available
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            if (csrfToken) {
                defaultOptions.headers['X-CSRF-Token'] = csrfToken;
            }
            
            const mergedOptions = {
                ...defaultOptions,
                ...options,
                headers: { ...defaultOptions.headers, ...options.headers }
            };
            
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), mergedOptions.timeout);
                
                const response = await fetch(url, {
                    ...mergedOptions,
                    signal: controller.signal
                });
                
                clearTimeout(timeoutId);
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    return await response.json();
                } else {
                    return await response.text();
                }
                
            } catch (error) {
                if (error.name === 'AbortError') {
                    throw new Error('Request timed out');
                }
                throw error;
            }
        },
        
        // GET request
        get: function(endpoint, params = {}) {
            const url = new URL(`${TN.config.apiBaseUrl}${endpoint}`, window.location.origin);
            Object.keys(params).forEach(key => 
                url.searchParams.append(key, params[key])
            );
            return TN.api.request(url.toString());
        },
        
        // POST request
        post: function(endpoint, data = {}) {
            return TN.api.request(`${TN.config.apiBaseUrl}${endpoint}`, {
                method: 'POST',
                body: JSON.stringify(data)
            });
        },
        
        // PUT request
        put: function(endpoint, data = {}) {
            return TN.api.request(`${TN.config.apiBaseUrl}${endpoint}`, {
                method: 'PUT',
                body: JSON.stringify(data)
            });
        },
        
        // DELETE request
        delete: function(endpoint) {
            return TN.api.request(`${TN.config.apiBaseUrl}${endpoint}`, {
                method: 'DELETE'
            });
        },
        
        // Upload file with progress tracking
        uploadFile: function(endpoint, file, onProgress = null) {
            return new Promise((resolve, reject) => {
                const formData = new FormData();
                formData.append('file', file);
                
                const xhr = new XMLHttpRequest();
                
                if (onProgress) {
                    xhr.upload.addEventListener('progress', (e) => {
                        if (e.lengthComputable) {
                            const percentComplete = (e.loaded / e.total) * 100;
                            onProgress(percentComplete);
                        }
                    });
                }
                
                xhr.addEventListener('load', () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        try {
                            const response = JSON.parse(xhr.responseText);
                            resolve(response);
                        } catch (e) {
                            resolve(xhr.responseText);
                        }
                    } else {
                        reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`));
                    }
                });
                
                xhr.addEventListener('error', () => {
                    reject(new Error('Upload failed'));
                });
                
                xhr.open('POST', `${TN.config.apiBaseUrl}${endpoint}`);
                
                // Add CSRF token
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
                if (csrfToken) {
                    xhr.setRequestHeader('X-CSRF-Token', csrfToken);
                }
                
                xhr.send(formData);
            });
        }
    };
    
    // Notification system
    TN.notifications = {
        container: null,
        
        init: function() {
            this.container = document.getElementById('global-notifications');
            if (!this.container) {
                this.container = document.createElement('div');
                this.container.id = 'global-notifications';
                this.container.className = 'fixed top-4 right-4 z-50 space-y-2';
                this.container.setAttribute('aria-live', 'polite');
                this.container.setAttribute('aria-atomic', 'true');
                document.body.appendChild(this.container);
            }
        },
        
        show: function(message, type = 'info', duration = 5000) {
            if (!this.container) this.init();
            
            const notification = document.createElement('div');
            const id = TN.utils.generateId('notification');
            notification.id = id;
            
            const typeClasses = {
                success: 'bg-success border-success-border text-success-text',
                error: 'bg-error border-error-border text-error-text',
                warning: 'bg-warning border-warning-border text-warning-text',
                info: 'bg-info border-info-border text-info-text'
            };
            
            const icons = {
                success: 'fas fa-check-circle',
                error: 'fas fa-exclamation-circle',
                warning: 'fas fa-exclamation-triangle',
                info: 'fas fa-info-circle'
            };
            
            notification.className = `notification ${typeClasses[type]} p-4 rounded-lg border shadow-lg max-w-sm`;
            notification.setAttribute('role', type === 'error' ? 'alert' : 'status');
            notification.innerHTML = `
                <div class="flex items-start gap-3">
                    <i class="${icons[type]}" aria-hidden="true"></i>
                    <div class="flex-1">
                        <p class="text-sm font-medium">${TN.utils.sanitizeHTML(message)}</p>
                    </div>
                    <button type="button" class="notification-close" aria-label="Close notification">
                        <i class="fas fa-times" aria-hidden="true"></i>
                    </button>
                </div>
            `;
            
            // Add close functionality
            const closeBtn = notification.querySelector('.notification-close');
            closeBtn.addEventListener('click', () => {
                this.remove(id);
            });
            
            // Add to container with animation
            notification.style.opacity = '0';
            notification.style.transform = 'translateX(100%)';
            this.container.appendChild(notification);
            
            // Animate in
            requestAnimationFrame(() => {
                notification.style.transition = 'all 0.3s ease-out';
                notification.style.opacity = '1';
                notification.style.transform = 'translateX(0)';
            });
            
            // Auto-remove after duration
            if (duration > 0) {
                setTimeout(() => {
                    this.remove(id);
                }, duration);
            }
            
            return id;
        },
        
        remove: function(id) {
            const notification = document.getElementById(id);
            if (notification) {
                notification.style.transition = 'all 0.3s ease-out';
                notification.style.opacity = '0';
                notification.style.transform = 'translateX(100%)';
                
                setTimeout(() => {
                    if (notification.parentNode) {
                        notification.parentNode.removeChild(notification);
                    }
                }, 300);
            }
        },
        
        clear: function() {
            if (this.container) {
                this.container.innerHTML = '';
            }
        }
    };
    
    // Form validation and handling
    TN.forms = {
        
        // Validate form field
        validateField: function(field) {
            const value = field.value.trim();
            const type = field.type;
            const required = field.hasAttribute('required');
            
            let isValid = true;
            let message = '';
            
            // Required validation
            if (required && !value) {
                isValid = false;
                message = 'This field is required';
            }
            
            // Type-specific validation
            if (value && isValid) {
                switch (type) {
                    case 'email':
                        if (!TN.utils.isValidEmail(value)) {
                            isValid = false;
                            message = 'Please enter a valid email address';
                        }
                        break;
                    case 'tel':
                        const phoneRegex = /^[\+]?[1-9][\d]{0,15}$/;
                        const cleanPhone = value.replace(/\D/g, '');
                        if (!phoneRegex.test(cleanPhone)) {
                            isValid = false;
                            message = 'Please enter a valid phone number';
                        }
                        break;
                    case 'url':
                        try {
                            new URL(value);
                        } catch {
                            isValid = false;
                            message = 'Please enter a valid URL';
                        }
                        break;
                }
            }
            
            // Custom validation attributes
            const minLength = field.getAttribute('minlength');
            if (minLength && value.length < parseInt(minLength)) {
                isValid = false;
                message = `Must be at least ${minLength} characters`;
            }
            
            const maxLength = field.getAttribute('maxlength');
            if (maxLength && value.length > parseInt(maxLength)) {
                isValid = false;
                message = `Must be no more than ${maxLength} characters`;
            }
            
            // Update field UI
            this.updateFieldUI(field, isValid, message);
            
            return isValid;
        },
        
        // Update field visual state
        updateFieldUI: function(field, isValid, message) {
            const wrapper = field.closest('.form-group') || field.parentElement;
            const existingError = wrapper.querySelector('.field-error');
            
            // Remove existing error
            if (existingError) {
                existingError.remove();
            }
            
            // Update field classes
            field.classList.remove('field-valid', 'field-invalid');
            field.classList.add(isValid ? 'field-valid' : 'field-invalid');
            
            // Add error message if invalid
            if (!isValid && message) {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'field-error text-xs text-error-color mt-1';
                errorDiv.textContent = message;
                errorDiv.setAttribute('role', 'alert');
                wrapper.appendChild(errorDiv);
            }
        },
        
        // Validate entire form
        validateForm: function(form) {
            const fields = form.querySelectorAll('input, textarea, select');
            let isFormValid = true;
            
            fields.forEach(field => {
                if (!this.validateField(field)) {
                    isFormValid = false;
                }
            });
            
            return isFormValid;
        },
        
        // Setup form with validation
        setup: function(form) {
            const fields = form.querySelectorAll('input, textarea, select');
            
            // Add real-time validation
            fields.forEach(field => {
                const validateWithDebounce = TN.utils.debounce(() => {
                    this.validateField(field);
                }, 500);
                
                field.addEventListener('input', validateWithDebounce);
                field.addEventListener('blur', () => this.validateField(field));
            });
            
            // Handle form submission
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                
                if (this.validateForm(form)) {
                    this.submitForm(form);
                } else {
                    // Focus first invalid field
                    const firstInvalid = form.querySelector('.field-invalid');
                    if (firstInvalid) {
                        firstInvalid.focus();
                    }
                }
            });
        },
        
        // Submit form via AJAX
        submitForm: async function(form) {
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalText = submitBtn?.textContent;
            
            try {
                // Update submit button
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.innerHTML = '<i class="fas fa-spinner animate-spin mr-2"></i>Submitting...';
                }
                
                // Prepare form data
                const formData = new FormData(form);
                const data = Object.fromEntries(formData.entries());
                
                // Get form action and method
                const action = form.getAttribute('action') || window.location.pathname;
                const method = form.getAttribute('method') || 'POST';
                
                // Submit form
                const response = await TN.api.request(action, {
                    method: method.toUpperCase(),
                    body: JSON.stringify(data)
                });
                
                // Handle success
                TN.notifications.show('Form submitted successfully!', 'success');
                
                // Reset form if successful
                form.reset();
                
                // Trigger custom event
                form.dispatchEvent(new CustomEvent('formSubmitSuccess', {
                    detail: { response, data }
                }));
                
            } catch (error) {
                console.error('Form submission error:', error);
                TN.notifications.show(`Error: ${error.message}`, 'error');
                
                // Trigger custom event
                form.dispatchEvent(new CustomEvent('formSubmitError', {
                    detail: { error, data: Object.fromEntries(new FormData(form)) }
                }));
                
            } finally {
                // Restore submit button
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                }
            }
        }
    };
    
    // Loading states management
    TN.loading = {
        overlay: null,
        
        init: function() {
            this.overlay = document.getElementById('loading-overlay');
            if (!this.overlay) {
                this.overlay = document.createElement('div');
                this.overlay.id = 'loading-overlay';
                this.overlay.className = 'loading-overlay hidden';
                this.overlay.innerHTML = `
                    <div class="loading-content">
                        <div class="spinner animate-spin"></div>
                        <p class="loading-text">Loading...</p>
                    </div>
                `;
                document.body.appendChild(this.overlay);
            }
        },
        
        show: function(message = 'Loading...') {
            if (!this.overlay) this.init();
            
            const textElement = this.overlay.querySelector('.loading-text');
            if (textElement) {
                textElement.textContent = message;
            }
            
            this.overlay.classList.remove('hidden');
            this.overlay.setAttribute('aria-hidden', 'false');
            
            // Prevent body scroll
            document.body.style.overflow = 'hidden';
        },
        
        hide: function() {
            if (this.overlay) {
                this.overlay.classList.add('hidden');
                this.overlay.setAttribute('aria-hidden', 'true');
                
                // Restore body scroll
                document.body.style.overflow = '';
            }
        }
    };
    
    // Healthcare-specific utilities
    TN.healthcare = {
        
        // Validate insurance member ID
        validateInsuranceId: function(memberId) {
            // Basic validation - real implementation would check format by provider
            return memberId && memberId.length >= 6 && /^[A-Za-z0-9]+$/.test(memberId);
        },
        
        // Format medical condition names
        formatCondition: function(condition) {
            return condition
                .toLowerCase()
                .split(' ')
                .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                .join(' ');
        },
        
        // Check if treatment is urgent based on keywords
        assessUrgency: function(description) {
            const urgentKeywords = [
                'suicidal', 'suicide', 'self-harm', 'overdose', 'crisis',
                'emergency', 'immediate', 'urgent', 'severe', 'acute'
            ];
            
            const text = description.toLowerCase();
            return urgentKeywords.some(keyword => text.includes(keyword));
        },
        
        // Generate treatment summary
        generateSummary: function(treatmentData) {
            const { provider, type, location, insurance_accepted } = treatmentData;
            return `${type} treatment at ${provider} in ${location}. ${insurance_accepted ? 'Insurance accepted.' : 'Self-pay only.'}`;
        }
    };
    
    // Initialize common functionality
    TN.init = function() {
        console.log('Treatment Navigator initialized');
        
        // Initialize components
        TN.notifications.init();
        TN.loading.init();
        
        // Setup all forms on the page
        document.querySelectorAll('form[data-validate]').forEach(form => {
            TN.forms.setup(form);
        });
        
        // Add global keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Escape key closes modals/overlays
            if (e.key === 'Escape') {
                TN.loading.hide();
                // Close any open modals
                document.querySelectorAll('.modal:not(.hidden)').forEach(modal => {
                    modal.classList.add('hidden');
                });
            }
        });
        
        // Add global error handler
        window.addEventListener('error', (e) => {
            console.error('Global error:', e.error);
            if (TN.config.environment !== 'development') {
                TN.notifications.show('An unexpected error occurred', 'error');
            }
        });
        
        // Add unhandled promise rejection handler
        window.addEventListener('unhandledrejection', (e) => {
            console.error('Unhandled promise rejection:', e.reason);
            if (TN.config.environment !== 'development') {
                TN.notifications.show('An unexpected error occurred', 'error');
            }
        });
        
        // Track page views if analytics available
        if (typeof gtag === 'function') {
            gtag('config', 'GA_TRACKING_ID', {
                page_title: document.title,
                page_location: window.location.href
            });
        }
    };
    
    // Auto-initialize when DOM is loaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', TN.init);
    } else {
        TN.init();
    }
    
})(window.TreatmentNavigator);

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = window.TreatmentNavigator;
} 