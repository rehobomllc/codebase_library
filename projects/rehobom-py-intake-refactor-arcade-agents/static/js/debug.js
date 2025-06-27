// Debug Dashboard JavaScript

class DebugDashboard {
    constructor() {
        this.refreshInterval = null;
        this.autoRefreshEnabled = true;
        this.refreshIntervalMs = 30000; // 30 seconds
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadDashboardData();
        this.startAutoRefresh();
        this.updateLastRefreshTime();
    }
    
    bindEvents() {
        // Refresh button
        const refreshButton = document.getElementById('refresh-data');
        if (refreshButton) {
            refreshButton.addEventListener('click', () => {
                this.loadDashboardData();
            });
        }
        
        // Clear events button
        const clearEventsButton = document.getElementById('clear-events');
        if (clearEventsButton) {
            clearEventsButton.addEventListener('click', () => {
                this.clearEvents();
            });
        }
        
        // Clear errors button
        const clearErrorsButton = document.getElementById('clear-errors');
        if (clearErrorsButton) {
            clearErrorsButton.addEventListener('click', () => {
                this.clearErrors();
            });
        }
        
        // Auto-refresh toggle (could add this to UI)
        document.addEventListener('keydown', (e) => {
            if (e.key === 'r' && e.ctrlKey) {
                e.preventDefault();
                this.loadDashboardData();
            }
        });
    }
    
    async loadDashboardData() {
        try {
            this.showLoading();
            
            // Load all dashboard data
            await Promise.all([
                this.loadSystemStatus(),
                this.loadAgentPerformance(),
                this.loadRecentEvents(),
                this.loadAPIUsage(),
                this.loadErrorLogs(),
                this.loadConfiguration()
            ]);
            
            this.updateLastRefreshTime();
            this.showRefreshSuccess();
            
        } catch (error) {
            console.error('Error loading dashboard data:', error);
            this.showRefreshError(error);
        } finally {
            this.hideLoading();
        }
    }
    
    async loadSystemStatus() {
        try {
            const response = await fetch('/api/debug/dashboard');
            const data = await response.json();
            
            if (data.status === 'success') {
                this.updateSystemStatus(data.debug_data);
            } else {
                throw new Error(data.message || 'Failed to load system status');
            }
        } catch (error) {
            console.error('Error loading system status:', error);
            this.updateSystemStatus({ status: 'error', events_count: 0, recent_events: [] });
        }
    }
    
    updateSystemStatus(debugData) {
        // Update overall system status
        const systemStatus = document.getElementById('system-status');
        if (systemStatus) {
            const statusDot = systemStatus.querySelector('.status-dot');
            const statusText = systemStatus.querySelector('.status-text');
            
            if (debugData.status === 'active') {
                statusDot.className = 'status-dot';
                statusText.textContent = 'System Online';
            } else {
                statusDot.className = 'status-dot danger';
                statusText.textContent = 'System Issues';
            }
        }
        
        // Update individual status cards
        this.updateStatusCard('db-status', 'Connected');
        this.updateStatusCard('agents-status', '7 Active');
        this.updateStatusCard('arcade-status', 'Connected');
        this.updateStatusCard('active-users', Math.floor(Math.random() * 25) + 5); // Simulated
    }
    
    updateStatusCard(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = value;
        }
    }
    
    async loadAgentPerformance() {
        // Simulate agent performance data (in real app, this would come from your metrics)
        const performanceData = {
            triage: {
                sessions: Math.floor(Math.random() * 50) + 20,
                responseTime: Math.floor(Math.random() * 500) + 200
            },
            facility_search: {
                searches: Math.floor(Math.random() * 30) + 10,
                successRate: Math.floor(Math.random() * 20) + 80
            },
            insurance: {
                verifications: Math.floor(Math.random() * 20) + 5,
                coverageFound: Math.floor(Math.random() * 30) + 70
            },
            appointments: {
                scheduled: Math.floor(Math.random() * 15) + 5,
                successRate: Math.floor(Math.random() * 25) + 75
            }
        };
        
        this.updateAgentPerformance(performanceData);
    }
    
    updateAgentPerformance(data) {
        // Update triage agent metrics
        this.updateMetric('triage-sessions', data.triage.sessions);
        this.updateMetric('triage-response-time', `${data.triage.responseTime}ms`);
        
        // Update facility search metrics
        this.updateMetric('facility-searches', data.facility_search.searches);
        this.updateMetric('facility-success-rate', `${data.facility_search.successRate}%`);
        
        // Update insurance verification metrics
        this.updateMetric('insurance-verifications', data.insurance.verifications);
        this.updateMetric('coverage-found', `${data.insurance.coverageFound}%`);
        
        // Update appointment scheduling metrics
        this.updateMetric('appointments-scheduled', data.appointments.scheduled);
        this.updateMetric('appointment-success-rate', `${data.appointments.successRate}%`);
    }
    
    updateMetric(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = value;
        }
    }
    
    async loadRecentEvents() {
        try {
            // In a real app, this would fetch from your event logging system
            const events = this.generateSampleEvents();
            this.updateRecentEvents(events);
        } catch (error) {
            console.error('Error loading recent events:', error);
            this.updateRecentEvents([]);
        }
    }
    
    generateSampleEvents() {
        const eventTypes = [
            { type: 'info', message: 'User started treatment search', timestamp: new Date(Date.now() - 60000) },
            { type: 'success', message: 'Facility search completed successfully', timestamp: new Date(Date.now() - 120000) },
            { type: 'warning', message: 'Insurance verification took longer than expected', timestamp: new Date(Date.now() - 180000) },
            { type: 'info', message: 'Appointment scheduled via Google Calendar', timestamp: new Date(Date.now() - 240000) },
            { type: 'success', message: 'Treatment reminder set up', timestamp: new Date(Date.now() - 300000) }
        ];
        
        return eventTypes.slice(0, Math.floor(Math.random() * 5) + 3);
    }
    
    updateRecentEvents(events) {
        const eventsList = document.getElementById('events-list');
        if (!eventsList) return;
        
        if (events.length === 0) {
            eventsList.innerHTML = '<div class="loading-placeholder">No recent events</div>';
            return;
        }
        
        eventsList.innerHTML = '';
        events.forEach(event => {
            const eventItem = document.createElement('div');
            eventItem.className = `event-item ${event.type}`;
            eventItem.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span>${event.message}</span>
                    <small>${this.formatTimestamp(event.timestamp)}</small>
                </div>
            `;
            eventsList.appendChild(eventItem);
        });
    }
    
    async loadAPIUsage() {
        // Simulate API usage data
        const usageData = {
            totalRequests: Math.floor(Math.random() * 500) + 100,
            chatMessages: Math.floor(Math.random() * 200) + 50,
            facilityApiCalls: Math.floor(Math.random() * 100) + 20,
            insuranceApiCalls: Math.floor(Math.random() * 80) + 15
        };
        
        this.updateAPIUsage(usageData);
    }
    
    updateAPIUsage(data) {
        this.updateUsageValue('total-requests', data.totalRequests);
        this.updateUsageValue('chat-messages', data.chatMessages);
        this.updateUsageValue('facility-api-calls', data.facilityApiCalls);
        this.updateUsageValue('insurance-api-calls', data.insuranceApiCalls);
    }
    
    updateUsageValue(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = value.toLocaleString();
        }
    }
    
    async loadErrorLogs() {
        try {
            // In a real app, this would fetch from your error logging system
            const errors = this.generateSampleErrors();
            this.updateErrorLogs(errors);
        } catch (error) {
            console.error('Error loading error logs:', error);
            this.updateErrorLogs([]);
        }
    }
    
    generateSampleErrors() {
        const shouldHaveErrors = Math.random() > 0.7; // 30% chance of having errors
        
        if (!shouldHaveErrors) {
            return [];
        }
        
        return [
            {
                type: 'warning',
                message: 'OpenAI API rate limit approaching',
                timestamp: new Date(Date.now() - 300000)
            },
            {
                type: 'error',
                message: 'Failed to connect to external facility database',
                timestamp: new Date(Date.now() - 600000)
            }
        ];
    }
    
    updateErrorLogs(errors) {
        const errorLogs = document.getElementById('error-logs');
        if (!errorLogs) return;
        
        if (errors.length === 0) {
            errorLogs.innerHTML = '<div class="no-errors">No recent errors detected</div>';
            return;
        }
        
        errorLogs.innerHTML = '';
        errors.forEach(error => {
            const logItem = document.createElement('div');
            logItem.className = `log-item ${error.type}`;
            logItem.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span>${error.message}</span>
                    <small>${this.formatTimestamp(error.timestamp)}</small>
                </div>
            `;
            errorLogs.appendChild(logItem);
        });
    }
    
    async loadConfiguration() {
        // Update configuration status indicators
        this.updateConfigStatus('openai-config', true);
        this.updateConfigStatus('arcade-config', true);
        this.updateConfigStatus('database-config', true);
    }
    
    updateConfigStatus(elementId, isHealthy) {
        const element = document.getElementById(elementId);
        if (!element) return;
        
        const indicator = element.querySelector('.status-indicator');
        const text = element.querySelector('.status-text');
        
        if (indicator) {
            indicator.className = isHealthy ? 'status-indicator' : 'status-indicator danger';
        }
        
        if (text) {
            text.textContent = isHealthy ? 'Configured' : 'Error';
        }
    }
    
    clearEvents() {
        const eventsList = document.getElementById('events-list');
        if (eventsList) {
            eventsList.innerHTML = '<div class="loading-placeholder">Events cleared</div>';
        }
        
        this.showAlert('Events cleared successfully', 'success');
    }
    
    clearErrors() {
        const errorLogs = document.getElementById('error-logs');
        if (errorLogs) {
            errorLogs.innerHTML = '<div class="no-errors">No recent errors detected</div>';
        }
        
        this.showAlert('Error logs cleared successfully', 'success');
    }
    
    startAutoRefresh() {
        if (this.autoRefreshEnabled) {
            this.refreshInterval = setInterval(() => {
                this.loadDashboardData();
            }, this.refreshIntervalMs);
        }
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
    
    updateLastRefreshTime() {
        const lastUpdatedElement = document.getElementById('last-updated-time');
        if (lastUpdatedElement) {
            lastUpdatedElement.textContent = new Date().toLocaleTimeString();
        }
    }
    
    formatTimestamp(timestamp) {
        return new Date(timestamp).toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }
    
    showLoading() {
        const refreshButton = document.getElementById('refresh-data');
        if (refreshButton) {
            refreshButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Refreshing...';
            refreshButton.disabled = true;
        }
    }
    
    hideLoading() {
        const refreshButton = document.getElementById('refresh-data');
        if (refreshButton) {
            refreshButton.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
            refreshButton.disabled = false;
        }
    }
    
    showRefreshSuccess() {
        this.showAlert('Dashboard data refreshed successfully', 'success');
    }
    
    showRefreshError(error) {
        this.showAlert(`Failed to refresh data: ${error.message}`, 'error');
    }
    
    showAlert(message, type = 'info') {
        // Create alert element
        const alert = document.createElement('div');
        alert.className = `debug-alert alert-${type}`;
        alert.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 0.25rem;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
            z-index: 10000;
            max-width: 400px;
            transform: translateX(100%);
            transition: transform 0.3s ease;
            font-family: monospace;
            font-size: 0.875rem;
        `;
        
        alert.innerHTML = `
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'}"></i>
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
        
        // Auto remove after 3 seconds
        setTimeout(() => {
            if (alert.parentElement) {
                alert.style.transform = 'translateX(100%)';
                setTimeout(() => {
                    if (alert.parentElement) {
                        alert.remove();
                    }
                }, 300);
            }
        }, 3000);
    }
}

// Utility functions for debug dashboard
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
    
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function formatDuration(milliseconds) {
    const seconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) {
        return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${seconds % 60}s`;
    } else {
        return `${seconds}s`;
    }
}

// Initialize debug dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.debugDashboard = new DebugDashboard();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.debugDashboard) {
        window.debugDashboard.stopAutoRefresh();
    }
});

// Export for testing/debugging
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DebugDashboard;
} 