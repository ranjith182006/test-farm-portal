// Global State Variables
let currentUser = null;
let livestockList = [];
let drugsList = [];
let treatmentsList = [];
let analyticsData = {};

// Chart References (for updates/destruction)
let amuChartInstance = null;
let decayChartInstance = null;
let classChartInstance = null;
let whoChartInstance = null;

// API Fetch Wrapper to Intercept 401 / 403 Errors
async function apiFetch(url, options = {}) {
    try {
        const response = await fetch(url, options);
        
        if (response.status === 401) {
            currentUser = null;
            document.getElementById('app-container').style.display = 'none';
            document.getElementById('login-container').style.display = 'flex';
            return null;
        }
        
        if (response.status === 403) {
            alert("Action Forbidden: Administrator privileges required.");
            throw new Error("Forbidden access");
        }
        
        return response;
    } catch (err) {
        console.error("API Fetch Error:", err);
        throw err;
    }
}

// Clock update
function updateClock() {
    const clockEl = document.getElementById('current-time');
    if (clockEl) {
        const now = new Date();
        clockEl.textContent = now.toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        }) + ' | ' + now.toLocaleTimeString('en-US');
    }
}
setInterval(updateClock, 1000);
updateClock();

// Modal Open/Close Controls
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'flex';
        
        if (modalId === 'modal-log-treatment') {
            const startInput = document.getElementById('treat-start');
            const endInput = document.getElementById('treat-end');
            
            const now = new Date();
            const localNowString = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
            startInput.value = localNowString;
            
            const threeDaysLater = new Date(now.getTime() + 3 * 24 * 60 * 60 * 1000);
            const localThreeDaysString = new Date(threeDaysLater.getTime() - threeDaysLater.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
            endInput.value = localThreeDaysString;
            
            populateTreatmentFormDropdowns();
        }
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

// Close modal when clicking outside
window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.style.display = 'none';
    }
});

// View Routing (Tab Switching)
document.querySelectorAll('.nav-menu .nav-item').forEach(item => {
    item.addEventListener('click', () => {
        document.querySelectorAll('.nav-menu .nav-item').forEach(nav => nav.classList.remove('active'));
        item.classList.add('active');
        
        const targetView = item.getAttribute('data-view');
        document.querySelectorAll('.content-view').forEach(view => view.classList.remove('active'));
        document.getElementById(`view-${targetView}`).classList.add('active');
        
        const viewTitles = {
            'dashboard': 'Dashboard Overview',
            'livestock': 'Livestock Registry',
            'treatments': 'Treatment & Medication Logs',
            'drugs': 'Veterinary Drug Database',
            'analytics': 'Analytics & Stewardship Reports'
        };
        document.getElementById('view-title').textContent = viewTitles[targetView] || 'Overview';
        
        if (targetView === 'dashboard') loadDashboard();
        else if (targetView === 'livestock') loadLivestock();
        else if (targetView === 'treatments') loadTreatments();
        else if (targetView === 'drugs') loadDrugs();
        else if (targetView === 'analytics') loadAnalytics();
    });
});

// Helper: Format Time Duration (seconds)
function formatTimeRemaining(seconds) {
    if (seconds <= 0) return 'Cleared';
    
    const days = Math.floor(seconds / (3600 * 24));
    seconds -= days * 3600 * 24;
    const hours = Math.floor(seconds / 3600);
    seconds -= hours * 3600;
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    
    let parts = [];
    if (days > 0) parts.push(`${days}d`);
    if (hours > 0 || days > 0) parts.push(`${hours}h`);
    if (minutes > 0 || hours > 0 || days > 0) parts.push(`${minutes}m`);
    parts.push(`${secs}s`);
    
    return parts.join(' ');
}

// Helper: Format Date String
function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    const d = new Date(dateStr.replace(' ', 'T'));
    return d.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// -------------------- AUTHENTICATION LOGIC --------------------

async function checkAuth() {
    try {
        const response = await fetch('/api/me');
        if (response.ok) {
            currentUser = await response.json();
            setupUserSessionUI();
        } else {
            currentUser = null;
            document.getElementById('login-container').style.display = 'flex';
            document.getElementById('app-container').style.display = 'none';
        }
    } catch (err) {
        console.error("Auth check failed:", err);
    }
}

async function submitLogin(e) {
    e.preventDefault();
    const usernameInput = document.getElementById('login-username').value;
    const passwordInput = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error-msg');
    
    errorEl.style.display = 'none';
    
    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: usernameInput, password: passwordInput })
        });
        
        if (response.ok) {
            const data = await response.json();
            currentUser = data.user;
            document.getElementById('form-login').reset();
            setupUserSessionUI();
        } else {
            const data = await response.json();
            errorEl.textContent = data.error || "Invalid username or password";
            errorEl.style.display = 'block';
        }
    } catch (err) {
        console.error("Login request failed:", err);
        errorEl.textContent = "Server connection error.";
        errorEl.style.display = 'block';
    }
}

async function submitRegister(e) {
    e.preventDefault();
    const usernameInput = document.getElementById('register-username').value;
    const passwordInput = document.getElementById('register-password').value;
    const confirmInput = document.getElementById('register-confirm-password').value;
    
    const errorEl = document.getElementById('register-error-msg');
    const successEl = document.getElementById('register-success-msg');
    
    errorEl.style.display = 'none';
    successEl.style.display = 'none';
    
    if (passwordInput !== confirmInput) {
        errorEl.textContent = "Passwords do not match.";
        errorEl.style.display = 'block';
        return;
    }
    
    try {
        const response = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: usernameInput, password: passwordInput })
        });
        
        if (response.ok) {
            const data = await response.json();
            successEl.textContent = data.message || "Registration successful!";
            successEl.style.display = 'block';
            document.getElementById('form-register').reset();
            
            // Auto slide back to login form after 1.5 seconds
            setTimeout(() => {
                toggleAuthForms();
            }, 1500);
        } else {
            const data = await response.json();
            errorEl.textContent = data.error || "Registration failed.";
            errorEl.style.display = 'block';
        }
    } catch (err) {
        console.error("Registration failed:", err);
        errorEl.textContent = "Server connection error.";
        errorEl.style.display = 'block';
    }
}

function toggleAuthForms(e) {
    if (e) e.preventDefault();
    const loginWrapper = document.getElementById('login-form-wrapper');
    const registerWrapper = document.getElementById('register-form-wrapper');
    
    // Clear validation messages on toggle
    document.getElementById('login-error-msg').style.display = 'none';
    document.getElementById('register-error-msg').style.display = 'none';
    document.getElementById('register-success-msg').style.display = 'none';
    
    if (loginWrapper.style.display === 'none') {
        registerWrapper.style.display = 'none';
        loginWrapper.style.display = 'block';
    } else {
        loginWrapper.style.display = 'none';
        registerWrapper.style.display = 'block';
    }
}

async function triggerLogout() {
    if (!confirm("Are you sure you want to sign out?")) return;
    try {
        await fetch('/api/logout', { method: 'POST' });
        currentUser = null;
        document.getElementById('app-container').style.display = 'none';
        document.getElementById('login-container').style.display = 'flex';
        // Force view back to sign-in panel
        const loginWrapper = document.getElementById('login-form-wrapper');
        const registerWrapper = document.getElementById('register-form-wrapper');
        loginWrapper.style.display = 'block';
        registerWrapper.style.display = 'none';
    } catch (err) {
        console.error("Logout failed:", err);
    }
}

function setupUserSessionUI() {
    if (!currentUser) return;
    
    document.getElementById('login-container').style.display = 'none';
    document.getElementById('app-container').style.display = 'flex';
    
    document.getElementById('user-display-name').textContent = currentUser.username;
    document.getElementById('user-display-role').textContent = currentUser.role === 'Admin' ? 'Administrator' : 'Standard User';
    document.getElementById('user-avatar').textContent = currentUser.username.slice(0, 2).toUpperCase();
    
    const isAdmin = currentUser.role === 'Admin';
    document.querySelectorAll('.admin-only').forEach(el => {
        el.style.display = isAdmin ? 'inline-flex' : 'none';
    });
    
    loadDashboard();
}

// -------------------- API INTEGRATIONS --------------------

// 1. Load Dashboard Data
async function loadDashboard() {
    try {
        const response = await apiFetch('/api/analytics');
        if (!response) return;
        
        analyticsData = await response.json();
        
        document.getElementById('stat-amu-index').textContent = analyticsData.amu_index.toFixed(2);
        document.getElementById('stat-compliance-rate').textContent = `${analyticsData.compliance_rate}%`;
        document.getElementById('stat-active-treatments').textContent = analyticsData.status_counts.Treated;
        document.getElementById('stat-in-withdrawal').textContent = analyticsData.status_counts['In Withdrawal'];
        
        const alertsBar = document.getElementById('global-alerts-bar');
        const alertsList = document.getElementById('global-alerts-list');
        
        if (analyticsData.withdrawal_alerts && analyticsData.withdrawal_alerts.length > 0) {
            alertsBar.style.display = 'block';
            alertsList.innerHTML = '';
            
            analyticsData.withdrawal_alerts.forEach(alert => {
                const item = document.createElement('div');
                item.className = 'alert-item';
                item.innerHTML = `
                    <div class="alert-desc">
                        <strong>${alert.tag_id}</strong> (${alert.species}) in <strong>${alert.pen_number}</strong> 
                        is under withdrawal for drug <strong>${alert.drug_name}</strong>.
                    </div>
                    <div class="alert-timer" id="countdown-alert-${alert.tag_id}" data-seconds="${alert.remaining_seconds}">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                        </svg>
                        <span>${formatTimeRemaining(alert.remaining_seconds)}</span>
                    </div>
                `;
                alertsList.appendChild(item);
            });
        } else {
            alertsBar.style.display = 'none';
        }
        
        const quickTable = document.getElementById('dashboard-quick-status');
        quickTable.innerHTML = '';
        
        const livestockRes = await apiFetch('/api/livestock');
        if (!livestockRes) return;
        const livestock = await livestockRes.json();
        
        const activeAnimals = livestock.filter(a => a.status !== 'Healthy');
        
        if (activeAnimals.length === 0) {
            quickTable.innerHTML = `
                <tr>
                    <td colspan="3" style="text-align: center; color: var(--text-muted); padding: 20px;">
                        All animals comply with MRL. No active treatments.
                    </td>
                </tr>
            `;
        } else {
            activeAnimals.forEach(animal => {
                let badgeClass = 'badge-healthy';
                let actionReq = 'Eligible for sale';
                
                if (animal.status === 'Treated') {
                    badgeClass = 'badge-treated';
                    actionReq = 'Do not move/slaughter. Complete treatment.';
                } else if (animal.status === 'In Withdrawal') {
                    badgeClass = 'badge-withdrawal';
                    actionReq = `Withhold until ${formatDate(animal.clearance_date)}`;
                } else if (animal.status === 'Quarantine') {
                    badgeClass = 'badge-quarantine';
                    actionReq = 'Quarantine Active. Monitor residue testing.';
                }
                
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${animal.tag_id}</strong></td>
                    <td><span class="badge ${badgeClass}">${animal.status}</span></td>
                    <td style="color: var(--text-secondary);">${actionReq}</td>
                `;
                quickTable.appendChild(tr);
            });
        }
        
        renderAMUTrendChart(analyticsData.monthly_stats);
        
    } catch (err) {
        console.error("Error loading dashboard data:", err);
    }
}

function renderAMUTrendChart(monthlyData) {
    const canvas = document.getElementById('dashboardAMUChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    if (amuChartInstance) {
        amuChartInstance.destroy();
    }
    
    const labels = monthlyData.map(d => d.month);
    const treatmentsCount = monthlyData.map(d => d.treatments_count);
    const amuMg = monthlyData.map(d => d.amu_mg);
    
    amuChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Antimicrobial Volume (mg)',
                    data: amuMg,
                    backgroundColor: 'rgba(6, 182, 212, 0.4)',
                    borderColor: '#06b6d4',
                    borderWidth: 2,
                    borderRadius: 6,
                    yAxisID: 'y'
                },
                {
                    label: 'Treatment Operations',
                    data: treatmentsCount,
                    type: 'line',
                    borderColor: '#3b82f6',
                    backgroundColor: 'transparent',
                    pointBackgroundColor: '#3b82f6',
                    borderWidth: 3,
                    tension: 0.3,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#9ca3af', font: { family: 'Inter' } }
                },
                y: {
                    position: 'left',
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#9ca3af', font: { family: 'Inter' } },
                    title: { display: true, text: 'Medication Vol (mg)', color: '#06b6d4' }
                },
                y1: {
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#9ca3af', font: { family: 'Inter' } },
                    title: { display: true, text: 'Operational Runs', color: '#3b82f6' }
                }
            },
            plugins: {
                legend: {
                    labels: { color: '#f3f4f6', font: { family: 'Inter', weight: 500 } }
                }
            }
        }
    });
}

// 2. Load Livestock Registry
async function loadLivestock() {
    try {
        const response = await apiFetch('/api/livestock');
        if (!response) return;
        livestockList = await response.json();
        filterLivestock();
    } catch (err) {
        console.error("Error fetching livestock list:", err);
    }
}

function filterLivestock() {
    const searchQuery = document.getElementById('search-livestock-tag').value.toLowerCase();
    const speciesFilter = document.getElementById('filter-livestock-species').value;
    const statusFilter = document.getElementById('filter-livestock-status').value;
    
    const tableBody = document.getElementById('livestock-table-body');
    if (!tableBody) return;
    tableBody.innerHTML = '';
    
    const filtered = livestockList.filter(animal => {
        const matchesSearch = animal.tag_id.toLowerCase().includes(searchQuery);
        const matchesSpecies = speciesFilter === 'ALL' || animal.species === speciesFilter;
        const matchesStatus = statusFilter === 'ALL' || animal.status === statusFilter;
        return matchesSearch && matchesSpecies && matchesStatus;
    });
    
    if (filtered.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 30px;">
                    No livestock matches the specified filters.
                </td>
            </tr>
        `;
        return;
    }
    
    const isAdmin = currentUser && currentUser.role === 'Admin';
    
    filtered.forEach(animal => {
        let badgeClass = 'badge-healthy';
        if (animal.status === 'Treated') badgeClass = 'badge-treated';
        else if (animal.status === 'In Withdrawal') badgeClass = 'badge-withdrawal';
        else if (animal.status === 'Quarantine') badgeClass = 'badge-quarantine';
        
        const clearDateFormatted = animal.clearance_date ? formatDate(animal.clearance_date) : 'Eligible';
        const timerHtml = animal.withdrawal_remaining_seconds > 0 
            ? `<span class="countdown-timer" data-seconds="${animal.withdrawal_remaining_seconds}" id="countdown-live-${animal.id}">${formatTimeRemaining(animal.withdrawal_remaining_seconds)}</span>` 
            : 'Immediate Clearance';
        
        const actionsHtml = isAdmin 
            ? `<div style="display:flex; gap:8px;">
                    <button class="btn btn-secondary" style="padding:6px 12px; font-size:12px;" onclick="quarantineAnimal(${animal.id}, '${animal.status}')">
                        ${animal.status === 'Quarantine' ? 'Release' : 'Quarantine'}
                    </button>
                    <button class="btn btn-danger" style="padding:6px 12px; font-size:12px;" onclick="deleteLivestock(${animal.id})">
                        Delete
                    </button>
               </div>`
            : `<span style="color: var(--text-muted); font-size: 12px; font-style: italic;">Read-Only</span>`;
            
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${animal.tag_id}</strong></td>
            <td>${animal.species}</td>
            <td>${animal.breed}</td>
            <td>${animal.weight.toFixed(1)}</td>
            <td>${animal.pen_number}</td>
            <td><span class="badge ${badgeClass}">${animal.status}</span></td>
            <td>
                <div style="display:flex; flex-direction:column; gap:4px;">
                    <span>${clearDateFormatted}</span>
                    <span style="font-size:11px; color:var(--text-muted);">${timerHtml}</span>
                </div>
            </td>
            <td>${actionsHtml}</td>
        `;
        tableBody.appendChild(tr);
    });
}

async function quarantineAnimal(id, currentStatus) {
    const nextStatus = currentStatus === 'Quarantine' ? 'Healthy' : 'Quarantine';
    try {
        const response = await apiFetch(`/api/livestock/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: nextStatus })
        });
        if (response && response.ok) {
            loadLivestock();
        }
    } catch (err) {
        console.error("Error toggling quarantine:", err);
    }
}

async function deleteLivestock(id) {
    if (!confirm("Are you sure you want to delete this livestock? This deletes all associated treatment logs.")) return;
    try {
        const response = await apiFetch(`/api/livestock/${id}`, {
            method: 'DELETE'
        });
        if (response && response.ok) {
            loadLivestock();
        }
    } catch (err) {
        console.error("Error deleting animal:", err);
    }
}

// 3. Load Treatments View
async function loadTreatments() {
    try {
        const response = await apiFetch('/api/treatments');
        if (!response) return;
        treatmentsList = await response.json();
        filterTreatments();
    } catch (err) {
        console.error("Error fetching treatments:", err);
    }
}

function filterTreatments() {
    const searchQuery = document.getElementById('search-treatment-tag').value.toLowerCase();
    const statusFilter = document.getElementById('filter-treatment-status').value;
    
    const tableBody = document.getElementById('treatments-table-body');
    if (!tableBody) return;
    tableBody.innerHTML = '';
    
    const filtered = treatmentsList.filter(t => {
        const matchesSearch = t.livestock_tag.toLowerCase().includes(searchQuery) || t.vet_name.toLowerCase().includes(searchQuery);
        const matchesStatus = statusFilter === 'ALL' || t.status === statusFilter;
        return matchesSearch && matchesStatus;
    });
    
    if (filtered.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="9" style="text-align: center; color: var(--text-muted); padding: 30px;">
                    No treatment history matching the search criteria.
                </td>
            </tr>
        `;
        return;
    }
    
    filtered.forEach(t => {
        let stateBadge = 'badge-healthy';
        if (t.status === 'Active Treatment') stateBadge = 'badge-treated';
        else if (t.status === 'In Withdrawal') stateBadge = 'badge-withdrawal';
        
        const countdownVal = t.withdrawal_remaining_seconds > 0 
            ? `<span class="countdown-timer" data-seconds="${t.withdrawal_remaining_seconds}" id="countdown-treat-${t.id}">${formatTimeRemaining(t.withdrawal_remaining_seconds)}</span>` 
            : 'Cleared';
            
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${t.livestock_tag}</strong></td>
            <td>
                <div style="display:flex; flex-direction:column;">
                    <span><strong>${t.drug_name}</strong></span>
                    <span style="font-size:11px; color:var(--text-muted);">${t.drug_class}</span>
                </div>
            </td>
            <td>${t.dosage_mg_per_kg} mg/kg</td>
            <td>${t.total_mg.toFixed(1)} mg (${t.route})</td>
            <td>${formatDate(t.end_date)}</td>
            <td>${t.withdrawal_meat_days} Meat / ${t.withdrawal_milk_days} Milk</td>
            <td>${formatDate(t.clearance_date)}</td>
            <td><span class="badge ${stateBadge}">${t.status}</span></td>
            <td>
                <button class="btn btn-secondary" style="padding:6px 12px; font-size:12px; display:inline-flex; align-items:center; gap:4px;" onclick="viewDecayModel(${t.id})">
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                    Decay Graph
                </button>
            </td>
        `;
        tableBody.appendChild(tr);
    });
}

// 4. Load Drug Database View
async function loadDrugs() {
    try {
        const response = await apiFetch('/api/drugs');
        if (!response) return;
        drugsList = await response.json();
        
        const tableBody = document.getElementById('drugs-table-body');
        if (!tableBody) return;
        tableBody.innerHTML = '';
        
        drugsList.forEach(drug => {
            let classBadge = 'badge-hia';
            if (drug.classification === 'Highest Priority Critically Important') classBadge = 'badge-hpcia';
            else if (drug.classification === 'High Priority Critically Important') classBadge = 'badge-hpia';
            
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${drug.name}</strong></td>
                <td>${drug.active_ingredient}</td>
                <td>${drug.drug_class}</td>
                <td><span class="badge ${classBadge}">${drug.classification}</span></td>
                <td>
                    <div style="display:flex; flex-direction:column; gap:2px;">
                        <span>Meat: <strong>${drug.withdrawal_meat_days}d</strong></span>
                        <span>Milk: <strong>${drug.withdrawal_milk_days}d</strong></span>
                        <span>Eggs: <strong>${drug.withdrawal_eggs_days}d</strong></span>
                    </div>
                </td>
                <td>${drug.mrl_limit} ppb (mcg/kg)</td>
                <td>${drug.half_life_hours} hours</td>
            `;
            tableBody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error loading drug directory:", err);
    }
}

async function populateTreatmentFormDropdowns() {
    try {
        const [livestockRes, drugsRes] = await Promise.all([
            apiFetch('/api/livestock'),
            apiFetch('/api/drugs')
        ]);
        
        if (!livestockRes || !drugsRes) return;
        
        const animals = await livestockRes.json();
        const drugs = await drugsRes.json();
        
        const selectL = document.getElementById('treat-l-id');
        const selectD = document.getElementById('treat-d-id');
        
        if (!selectL || !selectD) return;
        
        selectL.innerHTML = '';
        selectD.innerHTML = '';
        
        animals.forEach(a => {
            const opt = document.createElement('option');
            opt.value = a.id;
            opt.textContent = `${a.tag_id} - ${a.species} (${a.breed}, ${a.weight}kg)`;
            selectL.appendChild(opt);
        });
        
        drugs.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.id;
            opt.textContent = `${d.name} (${d.active_ingredient})`;
            selectD.appendChild(opt);
        });
    } catch (err) {
        console.error("Error loading dropdown data:", err);
    }
}

async function submitLivestock(e) {
    e.preventDefault();
    const data = {
        tag_id: document.getElementById('new-l-tag').value,
        species: document.getElementById('new-l-species').value,
        breed: document.getElementById('new-l-breed').value,
        weight: parseFloat(document.getElementById('new-l-weight').value),
        pen_number: document.getElementById('new-l-pen').value
    };
    
    try {
        const response = await apiFetch('/api/livestock', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response && response.ok) {
            closeModal('modal-add-livestock');
            document.getElementById('form-add-livestock').reset();
            loadLivestock();
        } else if (response) {
            const err = await response.json();
            alert(err.error || "Failed to register livestock");
        }
    } catch (err) {
        console.error("Error registering animal:", err);
    }
}

async function submitDrug(e) {
    e.preventDefault();
    const data = {
        name: document.getElementById('new-d-name').value,
        active_ingredient: document.getElementById('new-d-ingredient').value,
        drug_class: document.getElementById('new-d-class').value,
        classification: document.getElementById('new-d-classification').value,
        withdrawal_meat_days: parseInt(document.getElementById('new-d-w-meat').value),
        withdrawal_milk_days: parseInt(document.getElementById('new-d-w-milk').value),
        withdrawal_eggs_days: parseInt(document.getElementById('new-d-w-eggs').value),
        mrl_limit: parseFloat(document.getElementById('new-d-mrl').value),
        half_life_hours: parseFloat(document.getElementById('new-d-halflife').value)
    };
    
    try {
        const response = await apiFetch('/api/drugs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response && response.ok) {
            closeModal('modal-add-drug');
            document.getElementById('form-add-drug').reset();
            loadDrugs();
        } else if (response) {
            const err = await response.json();
            alert(err.error || "Failed to create drug sheet");
        }
    } catch (err) {
        console.error("Error adding drug reference:", err);
    }
}

async function submitTreatment(e) {
    e.preventDefault();
    const data = {
        livestock_id: parseInt(document.getElementById('treat-l-id').value),
        drug_id: parseInt(document.getElementById('treat-d-id').value),
        dosage_mg_per_kg: parseFloat(document.getElementById('treat-dosage').value),
        route: document.getElementById('treat-route').value,
        start_date: document.getElementById('treat-start').value.replace('T', ' ') + ':00',
        end_date: document.getElementById('treat-end').value.replace('T', ' ') + ':00',
        vet_name: document.getElementById('treat-vet').value
    };
    
    try {
        const response = await apiFetch('/api/treatments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response && response.ok) {
            closeModal('modal-log-treatment');
            document.getElementById('form-log-treatment').reset();
            
            const activeNav = document.querySelector('.nav-item.active').getAttribute('data-view');
            if (activeNav === 'dashboard') loadDashboard();
            else if (activeNav === 'treatments') loadTreatments();
            else if (activeNav === 'livestock') loadLivestock();
        } else if (response) {
            const err = await response.json();
            alert(err.error || "Failed to log treatment");
        }
    } catch (err) {
        console.error("Error saving treatment:", err);
    }
}

async function viewDecayModel(treatmentId) {
    try {
        const response = await apiFetch(`/api/treatments/${treatmentId}/decay`);
        if (!response || !response.ok) return;
        
        const data = await response.json();
        
        document.getElementById('decay-meta-animal').textContent = data.livestock_tag;
        document.getElementById('decay-meta-drug').textContent = data.drug_name;
        document.getElementById('decay-meta-halflife').textContent = `${data.half_life_hours}h`;
        document.getElementById('decay-meta-mrl').textContent = `${data.mrl_limit} ppb`;
        document.getElementById('decay-meta-withdrawal').textContent = `${data.withdrawal_days} days`;
        document.getElementById('decay-meta-end').textContent = formatDate(data.end_date);
        
        openModal('modal-decay-curve');
        
        setTimeout(() => {
            const canvas = document.getElementById('decayModelChart');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            
            if (decayChartInstance) {
                decayChartInstance.destroy();
            }
            
            const labels = data.points.map(p => p.time_label);
            const concentrations = data.points.map(p => p.concentration);
            const mrlLimits = data.points.map(p => p.mrl);
            
            decayChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Predicted Residue Level (ppb)',
                            data: concentrations,
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            fill: true,
                            borderWidth: 3,
                            pointRadius: 4,
                            pointBackgroundColor: '#3b82f6',
                            tension: 0.2
                        },
                        {
                            label: `MRL Safe Limit (${data.mrl_limit} ppb)`,
                            data: mrlLimits,
                            borderColor: '#f43f5e',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            borderDash: [6, 6],
                            pointRadius: 0,
                            fill: false
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#9ca3af', font: { family: 'Inter' }, maxRotation: 45, minRotation: 45 }
                        },
                        y: {
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#9ca3af', font: { family: 'Inter' } },
                            title: { display: true, text: 'Residue Concentration (ppb)', color: '#f3f4f6' }
                        }
                    },
                    plugins: {
                        legend: {
                            labels: { color: '#f3f4f6', font: { family: 'Inter', weight: 500 } }
                        }
                    }
                }
            });
        }, 100);
        
    } catch (err) {
        console.error("Error launching residue decay model:", err);
    }
}

async function loadAnalytics() {
    try {
        const response = await apiFetch('/api/analytics');
        if (!response) return;
        analyticsData = await response.json();
        
        renderClassChart(analyticsData.drug_class_usage);
        renderWHOChart(analyticsData.classification_usage);
        
    } catch (err) {
        console.error("Error loading analytics data:", err);
    }
}

function renderClassChart(classUsage) {
    const canvas = document.getElementById('analyticsClassChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    if (classChartInstance) {
        classChartInstance.destroy();
    }
    
    const labels = Object.keys(classUsage);
    const data = Object.values(classUsage);
    
    classChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: [
                    'rgba(6, 182, 212, 0.6)',
                    'rgba(59, 130, 246, 0.6)',
                    'rgba(16, 185, 129, 0.6)',
                    'rgba(245, 158, 11, 0.6)',
                    'rgba(139, 92, 246, 0.6)'
                ],
                borderColor: '#111827',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: '#f3f4f6', font: { family: 'Inter' } }
                }
            }
        }
    });
}

function renderWHOChart(whoUsage) {
    const canvas = document.getElementById('analyticsWHOChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    if (whoChartInstance) {
        whoChartInstance.destroy();
    }
    
    const labels = Object.keys(whoUsage);
    const data = Object.values(whoUsage);
    
    whoChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Active Medication Load (mg)',
                data: data,
                backgroundColor: 'rgba(244, 63, 94, 0.5)',
                borderColor: '#f43f5e',
                borderWidth: 2,
                borderRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#9ca3af', font: { family: 'Inter' } }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#9ca3af', font: { family: 'Inter' } }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

function exportData(format) {
    if (treatmentsList.length === 0) {
        alert("No treatment logs available to export.");
        return;
    }
    
    let content = "";
    let mimeType = "";
    let filename = "";
    
    if (format === 'csv') {
        const headers = ["ID", "Animal Tag", "Medication", "Dosage (mg/kg)", "Total (mg)", "Route", "Start", "End", "Clearance Date", "Vet", "Status"];
        const rows = treatmentsList.map(t => [
            t.id, t.livestock_tag, t.drug_name, t.dosage_mg_per_kg, t.total_mg, t.route, t.start_date, t.end_date, t.clearance_date, t.vet_name, t.status
        ]);
        content = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        mimeType = "text/csv";
        filename = `mrl_amu_audit_report_${new Date().toISOString().split('T')[0]}.csv`;
    } else if (format === 'json') {
        content = JSON.stringify(treatmentsList, null, 4);
        mimeType = "application/json";
        filename = `mrl_amu_audit_report_${new Date().toISOString().split('T')[0]}.json`;
    }
    
    const blob = new Blob([content], { type: mimeType });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// -------------------- TIMER COUNTDOWNS OPERATOR --------------------
function runLiveCountdowns() {
    document.querySelectorAll('.countdown-timer').forEach(el => {
        let seconds = parseInt(el.getAttribute('data-seconds'));
        if (seconds > 0) {
            seconds--;
            el.setAttribute('data-seconds', seconds);
            el.textContent = formatTimeRemaining(seconds);
            if (seconds === 0) {
                const activeNav = document.querySelector('.nav-menu .nav-item.active').getAttribute('data-view');
                if (activeNav === 'dashboard') loadDashboard();
                else if (activeNav === 'livestock') loadLivestock();
                else if (activeNav === 'treatments') loadTreatments();
            }
        }
    });
    
    document.querySelectorAll('.alert-timer').forEach(el => {
        let seconds = parseInt(el.getAttribute('data-seconds'));
        if (seconds > 0) {
            seconds--;
            el.setAttribute('data-seconds', seconds);
            el.querySelector('span').textContent = formatTimeRemaining(seconds);
            if (seconds === 0) {
                loadDashboard();
            }
        }
    });
}
setInterval(runLiveCountdowns, 1000);

// Initial Page Load Hook
window.addEventListener('DOMContentLoaded', () => {
    checkAuth();
});
