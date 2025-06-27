const panels = Array.from(document.querySelectorAll('.onboarding-panel'));
const progress = document.getElementById('progress');
const form = document.getElementById('onboarding-form');
const loadingBar = document.getElementById('loading-bar');
const startSearchBtn = document.getElementById('start-search-btn');

let state = {
    name: '',
    email: '',
    location: '',
    treatment_type: '',
    payment_method: '',
    insurance_provider: '',
    special_needs: []
};
let currentPanel = 0;

function showPanel(idx) {
    panels.forEach((p, i) => {
        p.classList.toggle('active', i === idx);
    });
    progress.style.width = `${(idx) / (panels.length - 1) * 100}%`;
    currentPanel = idx;
    localStorage.setItem('onboardingState', JSON.stringify({state, currentPanel}));
    updateReviewPanel();
}

function nextPanel() {
    if (currentPanel < panels.length - 1) {
        animatePanel(currentPanel, currentPanel + 1);
    }
}
function prevPanel() {
    if (currentPanel > 0) {
        animatePanel(currentPanel, currentPanel - 1);
    }
}
function animatePanel(from, to) {
    const outPanel = panels[from];
    const inPanel = panels[to];
    if (window.gsap) {
        gsap.to(outPanel, {x: -40, opacity: 0, duration: 0.3, onComplete: () => {
            outPanel.classList.remove('active');
            outPanel.style.transform = '';
            inPanel.classList.add('active');
            gsap.fromTo(inPanel, {x: 40, opacity: 0}, {x: 0, opacity: 1, duration: 0.3});
        }});
    } else {
        outPanel.classList.remove('active');
        inPanel.classList.add('active');
    }
    progress.style.width = `${(to) / (panels.length - 1) * 100}%`;
    currentPanel = to;
    localStorage.setItem('onboardingState', JSON.stringify({state, currentPanel}));
    updateReviewPanel();
}

function validatePanel(idx) {
    switch(idx) {
        case 0:
            return form.name.value.trim() && form.email.value.trim() && form.location.value.trim();
        case 1:
            return !!state.treatment_type;
        case 2:
            return !!state.payment_method;
        case 3:
            // Only required if payment_method is Private Insurance
            if (state.payment_method === 'Private Insurance') {
                return form.insurance_provider.value.trim();
            }
            return true;
        case 4:
            return true; // special_needs is optional
        case 5:
            return true; // review panel
        default:
            return false;
    }
}

function updateStateFromPanel(idx) {
    switch(idx) {
        case 0:
            state.name = form.name.value.trim();
            state.email = form.email.value.trim();
            state.location = form.location.value.trim();
            break;
        case 1:
            // handled by chip click for treatment_type
            break;
        case 2:
            // handled by chip click for payment_method
            break;
        case 3:
            if (state.payment_method === 'Private Insurance') {
                state.insurance_provider = form.insurance_provider.value.trim();
            } else {
                state.insurance_provider = '';
            }
            break;
        case 4:
            // handled by chip click and custom input for special_needs
            break;
    }
    localStorage.setItem('onboardingState', JSON.stringify({state, currentPanel}));
}

function restoreState() {
    const saved = localStorage.getItem('onboardingState');
    if (saved) {
        try {
            const {state: savedState, currentPanel: savedPanel} = JSON.parse(saved);
            state = savedState || state;
            currentPanel = savedPanel || 0;
            form.name.value = state.name || '';
            form.email.value = state.email || '';
            form.location.value = state.location || '';
            form.insurance_provider.value = state.insurance_provider || '';
            // Defensive: ensure special_needs is always an array
            if (!Array.isArray(state.special_needs)) state.special_needs = [];
            // Restore chips
            document.querySelectorAll('#treatment-type-chips .chip').forEach(chip => {
                chip.classList.toggle('selected', chip.dataset.value === state.treatment_type);
            });
            document.querySelectorAll('#payment-method-chips .chip').forEach(chip => {
                chip.classList.toggle('selected', chip.dataset.value === state.payment_method);
            });
            // Special needs chips
            const initialChips = Array.from(document.querySelectorAll('#special-needs-chips .chip:not(#add-special-need-chip)'));
            const existingChipValues = initialChips.map(chip => chip.dataset.value);
            (state.special_needs || []).forEach(val => {
                const existingChip = initialChips.find(chip => chip.dataset.value === val);
                if (existingChip) {
                    existingChip.classList.add('selected');
                } else {
                    const newChip = createSpecialNeedChip(val);
                    newChip.classList.add('selected');
                    document.getElementById('special-needs-chips').insertBefore(newChip, document.getElementById('add-special-need-chip'));
                    addSpecialNeedChipEventListener(newChip);
                }
            });
            showPanel(currentPanel);
        } catch {}
    } else {
        showPanel(0);
    }
}

// Treatment type chips
const treatmentTypeChips = document.querySelectorAll('#treatment-type-chips .chip');
treatmentTypeChips.forEach(chip => {
    chip.addEventListener('click', () => {
        treatmentTypeChips.forEach(c => c.classList.remove('selected'));
        chip.classList.add('selected');
        state.treatment_type = chip.dataset.value;
        localStorage.setItem('onboardingState', JSON.stringify({state, currentPanel}));
        updateNextBtn();
    });
});

// Payment method chips
const paymentMethodChips = document.querySelectorAll('#payment-method-chips .chip');
paymentMethodChips.forEach(chip => {
    chip.addEventListener('click', () => {
        paymentMethodChips.forEach(c => c.classList.remove('selected'));
        chip.classList.add('selected');
        state.payment_method = chip.dataset.value;
        localStorage.setItem('onboardingState', JSON.stringify({state, currentPanel}));
        updateNextBtn();
        // If not Private Insurance, skip insurance panel
        if (state.payment_method !== 'Private Insurance' && currentPanel === 2) {
            // Clear insurance_provider
            state.insurance_provider = '';
            setTimeout(() => {
                updateStateFromPanel(2);
                nextPanel();
            }, 200);
        }
    });
});

// Special needs chips
function addSpecialNeedChipEventListener(chip) {
    chip.addEventListener('click', () => {
        if (!Array.isArray(state.special_needs)) state.special_needs = [];
        chip.classList.toggle('selected');
        const val = chip.dataset.value;
        if (chip.classList.contains('selected')) {
            if (!state.special_needs.includes(val)) state.special_needs.push(val);
        } else {
            state.special_needs = state.special_needs.filter(v => v !== val);
        }
        localStorage.setItem('onboardingState', JSON.stringify({state, currentPanel}));
        updateNextBtn();
    });
}
document.querySelectorAll('#special-needs-chips .chip:not(#add-special-need-chip)').forEach(addSpecialNeedChipEventListener);

// Custom special need addition
const addSpecialNeedChipBtn = document.getElementById('add-special-need-chip');
const customSpecialNeedInput = document.getElementById('custom-special-need-input');
function createSpecialNeedChip(value) {
    const chip = document.createElement('span');
    chip.classList.add('chip');
    chip.dataset.value = value;
    chip.textContent = value;
    return chip;
}
if (addSpecialNeedChipBtn) {
    addSpecialNeedChipBtn.addEventListener('click', () => {
        customSpecialNeedInput.style.display = 'block';
        customSpecialNeedInput.focus();
    });
}
if (customSpecialNeedInput) {
    customSpecialNeedInput.addEventListener('keypress', e => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const val = customSpecialNeedInput.value.trim();
            if (val && !state.special_needs.includes(val)) {
                const newChip = createSpecialNeedChip(val);
                newChip.classList.add('selected');
                document.getElementById('special-needs-chips').insertBefore(newChip, addSpecialNeedChipBtn);
                addSpecialNeedChipEventListener(newChip);
                state.special_needs.push(val);
                localStorage.setItem('onboardingState', JSON.stringify({state, currentPanel}));
                updateNextBtn();
            }
            customSpecialNeedInput.value = '';
            customSpecialNeedInput.style.display = 'none';
        }
    });
}

// Next/Back buttons
panels.forEach((panel, idx) => {
    const nextBtn = panel.querySelector('.next-btn');
    const backBtn = panel.querySelector('.back-btn');
    if (nextBtn) {
        nextBtn.addEventListener('click', () => {
            updateStateFromPanel(idx);
            if (validatePanel(idx)) nextPanel();
        });
    }
    if (backBtn) {
        backBtn.addEventListener('click', () => {
            prevPanel();
        });
    }
    panel.addEventListener('keydown', e => {
        if (e.key === 'Enter' && validatePanel(idx)) {
            e.preventDefault();
            updateStateFromPanel(idx);
            nextPanel();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            prevPanel();
        }
    });
});

function updateNextBtn() {
    const panel = panels[currentPanel];
    const nextBtn = panel.querySelector('.next-btn');
    if (nextBtn) {
        nextBtn.disabled = !validatePanel(currentPanel);
    }
}
form.addEventListener('input', updateNextBtn);

function updateReviewPanel() {
    if (currentPanel === 5) {
        const review = document.getElementById('review-info');
        review.innerHTML = `
            <ul style="padding-left:18px;">
                <li><b>Name:</b> ${state.name}</li>
                <li><b>Email:</b> ${state.email}</li>
                <li><b>Location:</b> ${state.location}</li>
                <li><b>Treatment Type:</b> ${state.treatment_type}</li>
                <li><b>Payment Method:</b> ${state.payment_method}</li>
                <li><b>Insurance Provider:</b> ${state.insurance_provider || 'N/A'}</li>
                <li><b>Special Needs:</b> ${(state.special_needs && state.special_needs.length > 0) ? state.special_needs.join(', ') : 'None'}</li>
            </ul>
        `;
    }
}

// Submit handler
form.addEventListener('submit', async e => {
    e.preventDefault();
    updateStateFromPanel(5);
    form.style.display = 'none';
    loadingBar.style.display = 'block';
    const payload = {
        ...state,
        user_id: state.email || state.name || 'onboarding_user'
    };
    try {
        const resp = await fetch('/onboarding/submit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (data.success && data.user_id) {
            localStorage.setItem('treatment_app_user_id', data.user_id);
            window.location.href = `/dashboard?user_id=${encodeURIComponent(data.user_id)}`;
        } else {
            loadingBar.textContent = data.error || 'Sorry, something went wrong. Please ensure email is valid.';
        }
    } catch (err) {
        loadingBar.textContent = 'Error: ' + err;
    }
    localStorage.removeItem('onboardingState');
});

window.addEventListener('DOMContentLoaded', () => {
    restoreState();
    updateNextBtn();
}); 