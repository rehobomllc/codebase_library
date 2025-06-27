document.addEventListener('DOMContentLoaded', () => {
    const tabs = document.querySelectorAll('#dashboard-tabs .tab-btn');
    const panels = document.querySelectorAll('.dashboard-panel');
    const helpIcon = document.getElementById('help-icon');
    const helpModal = document.getElementById('help-modal');
    const closeHelpModal = document.getElementById('close-help-modal');
    const fabAdd = document.getElementById('fab-add');
    const notificationTray = document.getElementById('notification-tray');
    const dashboardContainer = document.getElementById('dashboard-container');
    const currentUserId = dashboardContainer ? dashboardContainer.dataset.userId : null;
    let facilityPollInterval = null; // To store the interval ID for polling

    // --- Helper: Function to display facilities ---
    function displayFacilities(facilities) {
        const container = document.getElementById('facility-items-container');
        if (!container) return;

        if (facilities && facilities.length > 0) {
            container.innerHTML = '';
            const list = document.createElement('div');
            list.className = 'facility-list';

            facilities.forEach(f => {
                const title = f.title || f.name || 'Untitled facility';
                const raw = f.description || '';
                const desc = raw.length > 160 ? raw.slice(0,157).trim() + '…' : raw;
                const card = document.createElement('div');
                card.className = 'facility-card fade-in';

                card.innerHTML = `
                    <h3>${title}</h3>
                    <p>${desc || 'No description available.'}</p>
                    ${f.address ? `<span class="fac-meta"><strong>Address:</strong> ${f.address}</span>` : ''}
                    ${f.phone ? `<span class="fac-meta"><strong>Phone:</strong> ${f.phone}</span>` : ''}
                    ${f.treatment_types ? `<span class="fac-meta"><strong>Treatment Types:</strong> ${Array.isArray(f.treatment_types) ? f.treatment_types.join(', ') : f.treatment_types}</span>` : ''}
                    ${f.payment_methods ? `<span class="fac-meta"><strong>Payment Methods:</strong> ${Array.isArray(f.payment_methods) ? f.payment_methods.join(', ') : f.payment_methods}</span>` : ''}
                    ${f.insurance_accepted ? `<span class="fac-meta"><strong>Insurance Accepted:</strong> ${Array.isArray(f.insurance_accepted) ? f.insurance_accepted.join(', ') : f.insurance_accepted}</span>` : ''}
                    ${f.special_programs ? `<span class="fac-meta"><strong>Special Programs:</strong> ${Array.isArray(f.special_programs) ? f.special_programs.join(', ') : f.special_programs}</span>` : ''}
                    ${f.url ? `<a class="learn-more" href="${f.url}" target="_blank" rel="noopener">Visit Website</a>` : ''}
                `;

                list.appendChild(card);
                requestAnimationFrame(()=>card.classList.add('visible'));
            });

            container.appendChild(list);
        } else {
            container.innerHTML = '<p>No facilities found matching your criteria at this time.</p>';
        }
    }

    // --- Facility Search from Dashboard ---
    const startSearchBtn = document.getElementById('start-search-btn');
    const searchStatusDiv = document.getElementById('search-status');

    if (startSearchBtn) {
        startSearchBtn.addEventListener('click', async () => {
            if (!currentUserId) {
                showNotification('User not found. Please log in again.', 'error');
                return;
            }
            startSearchBtn.disabled = true;
            startSearchBtn.textContent = 'Searching...';
            searchStatusDiv.innerHTML = '<span class="spinner"></span> Starting facility search...';
            try {
                const response = await fetch(`/start_search?user_id=${currentUserId}`);
                if (!response.ok) throw new Error('Failed to start search.');
                const data = await response.json();
                if (data.reply) {
                    showNotification(data.reply, 'info');
                }
                pollForFacilities(currentUserId);
            } catch (error) {
                console.error('Error starting search:', error);
                searchStatusDiv.innerHTML = `<p style="color: red;">Error starting search: ${error.message}. Please try again.</p>`;
                showNotification(`Error: ${error.message}`, 'error');
                startSearchBtn.disabled = false;
                startSearchBtn.textContent = 'Start My Search';
            }
        });
    }

    // --- Polling for Facility Search Updates ---
    function pollForFacilities(userId) {
        if (facilityPollInterval) clearInterval(facilityPollInterval);
        facilityPollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/facilities?user_id=${userId}`);
                if (!response.ok) {
                    console.error('Polling error:', response.status);
                    searchStatusDiv.innerHTML = `<p style="color: red;">Error fetching search updates. Status: ${response.status}. Polling stopped.</p>`;
                    clearInterval(facilityPollInterval);
                    return;
                }
                const data = await response.json();
                if (data.status === 'completed') {
                    clearInterval(facilityPollInterval);
                    searchStatusDiv.innerHTML = data.facilities && data.facilities.length > 0 ? 
                        '<p>Search complete! Displaying all found facilities.</p>' :
                        '<p>Search complete. No new facilities were found based on your search.</p>';
                    displayFacilities(data.facilities || []);
                    enableAllTabs && enableAllTabs();
                    showNotification('Facility search complete!', 'success');
                } else if (data.status === 'completed_with_warnings') {
                    clearInterval(facilityPollInterval);
                    searchStatusDiv.innerHTML = data.facilities && data.facilities.length > 0 ? 
                        '<p>Search complete! Some facilities found, but the search may have encountered minor issues.</p>' :
                        '<p>Search complete with warnings. No new facilities were found.</p>';
                    displayFacilities(data.facilities || []);
                    enableAllTabs && enableAllTabs();
                    showNotification('Facility search completed with warnings.', 'warning');
                } else if (data.status === 'not_started') {
                    // Do nothing, wait for user to start search or for initial data load
                } else {
                    searchStatusDiv.innerHTML = `<p><span class="spinner"></span> Current status: ${data.message || data.status}...</p>`;
                }
            } catch (error) {
                console.error('Error polling for facilities:', error);
                searchStatusDiv.innerHTML = `<p style="color: red;">Error updating facility status: ${error.message}. Polling stopped.</p>`;
                clearInterval(facilityPollInterval);
            }
        }, 5000);
    }

    // --- Tab Functionality ---
    function activateTab(tabId) {
        tabs.forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabId);
        });
        panels.forEach(panel => {
            panel.classList.toggle('active', panel.id === `${tabId}-panel`);
        });
        localStorage.setItem('activeDashboardTab', tabId);
        tabs.forEach(t => t.disabled = false);
    }

    // Always activate 'facilities' tab/panel on load
    activateTab('facilities');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            activateTab(tab.dataset.tab);
        });
    });

    // Restore last active tab or default to opportunities
    const savedTab = localStorage.getItem('activeDashboardTab');
    if (savedTab) {
        activateTab(savedTab);
    } else if (tabs.length > 0) {
        activateTab(tabs[0].dataset.tab); // Default to the first tab
        // Initially disable other tabs if it's the default opportunities view without facilities
        const opportunitiesPanel = document.getElementById('opportunities-panel');
        const initialSearchPanel = opportunitiesPanel ? opportunitiesPanel.querySelector('.initial-search-panel') : null;
        if (initialSearchPanel) { // If the search prompt is visible, lock other tabs
            tabs.forEach(t => {
                if (t.dataset.tab !== 'opportunities') t.disabled = true;
            });
        }
    }

    // --- Help Modal Functionality ---
    if (helpIcon && helpModal && closeHelpModal) {
        helpIcon.addEventListener('click', () => {
            helpModal.classList.add('is-visible');
            helpModal.removeAttribute('hidden'); // Good practice to remove if setting display via class
        });
        closeHelpModal.addEventListener('click', () => {
            helpModal.classList.remove('is-visible');
        });
        // Close modal if clicked outside of modal-content
        helpModal.addEventListener('click', (event) => {
            if (event.target === helpModal) {
                helpModal.classList.remove('is-visible');
            }
        });
        // Close modal on Escape key
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && helpModal.classList.contains('is-visible')) {
                helpModal.classList.remove('is-visible');
            }
        });
    }

    // --- Floating Action Button (FAB) Functionality (Placeholder) ---
    if (fabAdd) {
        fabAdd.addEventListener('click', () => {
            // Example: Show a notification or open a form/modal
            showNotification('FAB clicked - Add new info functionality to be implemented.', 'info');
        });
    }

    // --- Notification Tray Functionality (Placeholder) ---
    function showNotification(message, type = 'info', duration = 3000) {
        if (!notificationTray) return;

        const toast = document.createElement('div');
        toast.classList.add('toast-notification');
        if (type === 'error') {
            toast.style.backgroundColor = '#d9534f'; // Example error color
        } else if (type === 'success') {
            toast.style.backgroundColor = '#5cb85c'; // Example success color
        }
        toast.textContent = message;
        
        notificationTray.appendChild(toast);

        // Animate in
        setTimeout(() => {
            toast.classList.add('show');
        }, 10); // Small delay to ensure transition triggers

        // Remove after duration
        setTimeout(() => {
            toast.classList.remove('show');
            // Remove from DOM after transition
            toast.addEventListener('transitionend', () => {
                toast.remove();
            });
        }, duration);
    }

    // Example of using the notification (you can remove this)
    // showNotification('Dashboard loaded successfully!', 'success');

    // Check if a search was in progress for this user and resume polling if necessary
    // This handles page reloads while a search is active.
    if (currentUserId) {
        fetch(`/api/facilities?user_id=${encodeURIComponent(currentUserId)}`)
            .then(res => res.json())
            .then(data => {
                if (data.status === "crawling" || data.status === "processing_data") {
                    showToast(`Resuming check for ongoing facility search (${data.status})...`, 'info');
                    searchStatusDiv.innerHTML = `<p><span class="spinner" style="border-top-color: #1877f2; width: 1.5em; height: 1.5em; margin-right: 8px; vertical-align: text-bottom;"></span> ${data.message || data.status} </p>`
                }
            })
            .catch(err => console.error("Error checking initial facility status:", err));
    }

    // Ensure the main content area and sidebar are arranged correctly
    // This is more of a CSS concern but can be influenced by JS if needed.
    // For now, assuming CSS handles the flex layout of dashboard-main and dashboard-sidebar.
    // We need to wrap #dashboard-main and #dashboard-sidebar in a .dashboard-content-area div
    // in the HTML for the provided CSS to work as intended for side-by-side layout.

    // Check if dashboard-content-area exists, if not, create it dynamically if necessary
    // For simplicity, this step is best done in the HTML template itself.
    // The provided CSS structure with .dashboard-content-area is for a common layout pattern.

    // Initial load calls (if needed, e.g. if content could be pre-populated)
    // loadEssays(); // Called by pollForFacilities when complete, or on initial load if search already done.
    // Default to opportunities tab
});