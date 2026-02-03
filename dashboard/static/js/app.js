// GATEKEEPER Dashboard JavaScript

// Close alerts
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.alert-close').forEach(btn => {
        btn.addEventListener('click', function () {
            this.parentElement.remove();
        });
    });
});

// API helper
async function apiRequest(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json'
        }
    };

    if (data) {
        options.body = JSON.stringify(data);
    }

    const response = await fetch(endpoint, options);
    return response.json();
}

// Refresh stats periodically
function startStatsRefresh() {
    setInterval(async () => {
        try {
            const stats = await apiRequest('/api/stats');
            updateStatsDisplay(stats);
        } catch (e) {
            console.error('Failed to refresh stats:', e);
        }
    }, 30000); // Every 30 seconds
}

function updateStatsDisplay(stats) {
    const pendingEl = document.querySelector('.stat-card.pending .stat-value');
    if (pendingEl) {
        pendingEl.textContent = stats.pending;
    }

    const approvedEl = document.querySelector('.stat-card.approved .stat-value');
    if (approvedEl) {
        approvedEl.textContent = stats.approved_today;
    }

    const rejectedEl = document.querySelector('.stat-card.rejected .stat-value');
    if (rejectedEl) {
        rejectedEl.textContent = stats.rejected_today;
    }
}

// Keyboard shortcuts
document.addEventListener('keydown', function (e) {
    // Escape to close modals
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal').forEach(modal => {
            modal.style.display = 'none';
        });
    }
});

// Initialize
document.addEventListener('DOMContentLoaded', function () {
    startStatsRefresh();
});
