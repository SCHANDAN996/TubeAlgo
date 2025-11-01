// static/js/dashboard.js

function dashboard() {
    return {
        isLoading: true,
        error: null,
        data: {
            kpis: {},
            growth_chart: { labels: [], subscribers: [], views: [] },
            ai_assistant: [],
            top_recent_videos: [],
            goal: null,
            best_time_to_post: null,
            layout: null
        },
        chart: null,
        activeChartMetric: 'subscribers',
        showGoalModal: false,
        goalError: '',
        newGoal: { type: 'subscribers', target: null, date: '' },
        csrfToken: null,
        isSavingLayout: false,
        saveStatus: '', // Can be 'Saving...', 'Saved!', or 'Error!'
        showResetConfirmModal: false,

        init() {
            // *** FIX: Corrected CSRF token selector ***
            const csrfInput = document.querySelector('input[name="csrf_token"]'); // Looks anywhere
            if (csrfInput) {
                this.csrfToken = csrfInput.value;
            } else {
                console.error('CSRF Token input field not found!'); // This should not happen now
            }
            // *** END FIX ***
            this.fetchData();
        },

        fetchData() {
            this.isLoading = true;
            fetch(`/api/dashboard/main-data?t=${new Date().getTime()}`)
                .then(res => res.json())
                .then(apiData => {
                    this.data = apiData;
                    this.error = null;
                    this.$nextTick(() => {
                        this.applyLayout();
                        this.renderChart();
                        this.initSortable();
                    });
                })
                .catch(err => {
                    this.error = err.message;
                })
                .finally(() => {
                    this.isLoading = false;
                });
        },

        initSortable() {
            const leftCol = document.getElementById('sortable-left');
            const rightCol = document.getElementById('sortable-right');

            const commonOptions = {
                group: 'dashboard-cards',
                animation: 150,
                handle: '.drag-handle',
                onEnd: () => this.saveLayout(),
            };

            if (leftCol && !leftCol.classList.contains('sortable-initialized')) {
                new Sortable(leftCol, commonOptions);
                leftCol.classList.add('sortable-initialized');
            }
            if (rightCol && !rightCol.classList.contains('sortable-initialized')) {
                new Sortable(rightCol, commonOptions);
                rightCol.classList.add('sortable-initialized');
            }
        },

        applyLayout() {
            if (!this.data.layout || !this.data.layout.left || !this.data.layout.right) return;
            const leftCol = document.getElementById('sortable-left');
            const rightCol = document.getElementById('sortable-right');
            if (!leftCol || !rightCol) return;
            const allCards = {};
            document.querySelectorAll('#sortable-left > [data-id], #sortable-right > [data-id]').forEach(el => {
                allCards[el.dataset.id] = el;
            });
            this.data.layout.left.forEach(id => {
                if (allCards[id]) leftCol.appendChild(allCards[id]);
            });
            this.data.layout.right.forEach(id => {
                if (allCards[id]) rightCol.appendChild(allCards[id]);
            });
        },

        async saveLayout() {
            this.isSavingLayout = true;
            this.saveStatus = 'Saving...';

            const leftIds = Array.from(document.getElementById('sortable-left').children).map(el => el.dataset.id);
            const rightIds = Array.from(document.getElementById('sortable-right').children).map(el => el.dataset.id);
            const newLayout = { left: leftIds, right: rightIds };

            if (!this.csrfToken) { // Check if token was found during init
                console.error('CSRF Token not found! Cannot save layout.');
                this.saveStatus = 'Error!';
                this.isSavingLayout = false;
                return;
            }

            try {
                const response = await fetch('/api/dashboard/save-layout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
                    body: JSON.stringify(newLayout)
                });

                if (!response.ok) {
                    throw new Error('Server responded with an error.');
                }

                const data = await response.json();

                if (data.success) {
                    this.saveStatus = 'Saved!';
                } else {
                    throw new Error(data.error || 'Failed to save.');
                }
            } catch (error) {
                this.saveStatus = 'Error!';
                console.error("Failed to save layout:", error);
            } finally {
                this.isSavingLayout = false;
                // Hide the message after 2 seconds
                setTimeout(() => {
                    this.saveStatus = '';
                }, 2000);
            }
        },

        resetLayout() {
            this.showResetConfirmModal = true;
        },

        cancelReset() {
            this.showResetConfirmModal = false;
        },

        proceedWithReset() {
            this.showResetConfirmModal = false;
            const defaultLayout = {
                left: ['kpis', 'growth_chart', 'top_videos'],
                right: ['goal', 'best_time', 'ai_assistant']
            };
            this.data.layout = defaultLayout;
            this.applyLayout();
            this.saveLayout();
        },

        renderChart() {
            if (this.chart) { this.chart.destroy(); }
            if (!this.$refs.growthChart || !this.data.growth_chart || !this.data.growth_chart.labels) { return; }

            const rootStyles = getComputedStyle(document.documentElement);
            const primaryColorHSL = rootStyles.getPropertyValue('--primary').trim();
            const primaryColorCommaSeparated = primaryColorHSL.replace(/ /g, ',');

            const ctx = this.$refs.growthChart.getContext('2d');
            const gradient = ctx.createLinearGradient(0, 0, 0, 250);
            gradient.addColorStop(0, `hsla(${primaryColorCommaSeparated}, 0.5)`);
            gradient.addColorStop(1, `hsla(${primaryColorCommaSeparated}, 0)`);

            const theme = localStorage.getItem('theme') || 'light';
            const gridColor = theme === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
            const labelColor = theme === 'dark' ? '#cbd5e1' : '#475569';

            this.chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: this.data.growth_chart.labels,
                    datasets: [{
                        label: this.activeChartMetric.charAt(0).toUpperCase() + this.activeChartMetric.slice(1),
                        data: this.data.growth_chart[this.activeChartMetric],
                        borderColor: `hsl(${primaryColorCommaSeparated})`,
                        backgroundColor: gradient,
                        borderWidth: 2,
                        pointBackgroundColor: `hsl(${primaryColorCommaSeparated})`,
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: false, grid: { color: gridColor }, ticks: { color: labelColor } },
                        x: { grid: { display: false }, ticks: { color: labelColor } }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'hsl(var(--card))',
                            titleColor: 'hsl(var(--foreground))',
                            bodyColor: 'hsl(var(--foreground))',
                            borderColor: 'hsl(var(--border))',
                            borderWidth: 1,
                        }
                    }
                }
            });
        },

        updateChart(metric) {
            this.activeChartMetric = metric;
            this.renderChart();
        },

        getIconForSuggestion(type) {
            switch(type) {
                case 'topic': return 'fa-solid fa-lightbulb text-yellow-500';
                case 'performance': return 'fa-solid fa-arrow-trend-up text-green-500';
                case 'consistency': return 'fa-solid fa-calendar-days text-blue-500';
                default: return 'fa-solid fa-star text-primary';
            }
        },

        openGoalModal() {
            this.goalError = '';
            this.newGoal = { type: 'subscribers', target: null, date: '' };
            this.showGoalModal = true;
        },

        async saveGoal() {
            this.goalError = '';
            if (!this.newGoal.target || this.newGoal.target <= 0) {
                this.goalError = 'Please enter a valid target value.';
                return;
            }

            try {
                const headers = { 'Content-Type': 'application/json' };
                if (this.csrfToken) { // Use the token found during init
                    headers['X-CSRFToken'] = this.csrfToken;
                } else {
                     console.error("Cannot save goal: CSRF Token is missing."); // Added check
                     this.goalError = "Security token missing. Please refresh the page.";
                     return;
                }

                const response = await fetch('/api/goals/', {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({
                        goal_type: this.newGoal.type,
                        target_value: this.newGoal.target,
                        target_date: this.newGoal.date || null
                    })
                });
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Failed to save goal.');
                }

                this.showGoalModal = false;
                this.fetchData(); // Reload dashboard data to show the new goal

            } catch (error) {
                this.goalError = error.message;
            }
        }
    }
}

document.addEventListener('alpine:init', () => {
    Alpine.data('dashboard', dashboard);
});