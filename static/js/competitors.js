// static/js/competitors.js

function formatRelativeTimeAlpine(isoDate) {
    if (!isoDate) return '';
    const dt = new Date(isoDate);
    const now = new Date();
    const diff = (now.getTime() - dt.getTime()) / 1000;

    if (diff < 60) return 'just now';
    const minutes = Math.floor(diff / 60);
    if (minutes < 60) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days} day${days > 1 ? 's' : ''} ago`; //
    const months = Math.floor(days / 30);
    if (months < 12) return `${months} month${months > 1 ? 's' : ''} ago`;
    const years = Math.floor(months / 12);
    return `${years} year${years > 1 ? 's' : ''} ago`;
}

function competitorPage() {
    return {
        showConfirmModal: false,
        competitorToDelete: null,
        competitors: [],
        query: '',
        suggestions: [],
        loading: false, //
        showSuggestions: false,
        activeIndex: -1,
        selectedChannelTitle: '',
        isAdding: false,
        limit: -1,
        formError: '', // Shows error messages
        showIdeaModal: false,
        isGeneratingIdeas: false,
        ideaSourceTitle: '',
        generatedIdeas: [], //
        showAnalysisModal: false,
        analysisLoading: false,
        currentAnalysis: null, // Holds AI analysis results
        analysisError: '',
        videoForAnalysis: null,

        init() {
            this.competitors = JSON.parse(document.getElementById('competitors-data').textContent); //
            this.limit = COMPETITOR_LIMIT; //

            this.$watch('query', (newValue) => {
                this.formError = ''; //
                if (newValue !== this.selectedChannelTitle) { //
                    if (this.$refs.hiddenIdInput) this.$refs.hiddenIdInput.value = ''; //
                    this.selectedChannelTitle = ''; //
                }
            });
            this.$el.addEventListener('confirm-delete', (event) => this.confirmDelete(event.detail)); //
            this.$el.addEventListener('move-competitor', (event) => this.moveCompetitor(event.detail.id, event.detail.direction)); //
            this.$el.addEventListener('go-to-analysis', (event) => this.goToDeepAnalysis(event.detail.data, event.detail.competitor)); //
            this.$el.addEventListener('analyze-transcript', (event) => this.analyzeTranscript(event.detail.video)); //
        },

        get currentCount() { return this.competitors.length; },
        get limitReached() { return this.limit !== -1 && this.currentCount >= this.limit; },

        async handleAddCompetitor() {
            this.formError = ''; //
            if (!this.$refs.hiddenIdInput.value) { //
                if (this.suggestions.length === 1 && this.query.toLowerCase() === this.suggestions[0].title.toLowerCase()) {
                    this.selectSuggestion(this.suggestions[0]); //
                    setTimeout(() => this.handleAddCompetitor(), 100); //
                } else {
                    this.formError = 'Please type and select a channel from the suggestion list.'; //
                }
                return;
            }

            if (this.isAdding) return; //
            this.isAdding = true; //
            const form = this.$refs.addCompetitorForm; //
            const payload = {
                channel_url: this.query, //
                channel_id_hidden: this.$refs.hiddenIdInput.value //
            };
            try {
                const response = await fetch(form.action, { //
                    method: 'POST', //
                    headers: {
                        'Content-Type': 'application/json', //
                        'X-CSRFToken': form.querySelector('input[name=csrf_token]').value //
                    },
                    body: JSON.stringify(payload) //
                });
                const data = await response.json(); //
                if (!response.ok) { //
                    throw new Error(data.error || 'An unknown error occurred.'); //
                }
                if (data.success && data.competitor) { //
                    this.competitors.unshift(data.competitor); //
                    this.query = ''; //
                    if (this.$refs.hiddenIdInput) this.$refs.hiddenIdInput.value = ''; //
                    this.suggestions = []; //
                }
            } catch (error) {
                console.error('Error adding competitor:', error.message); //
                this.formError = error.message; // Set formError instead of alert
            } finally {
                this.isAdding = false; //
            }
        },

        fetchSuggestions() {
            if (this.query.length < 2) { this.suggestions = []; this.showSuggestions = false; return; } //
            this.loading = true; //
            this.showSuggestions = true; //
            fetch(`/api/search-channels?q=${this.query}`) //
                .then(res => res.json()).then(data => { this.suggestions = data; this.activeIndex = -1; }) //
                .finally(() => this.loading = false); //
        },
        selectSuggestion(channel) {
            this.query = channel.title; //
            this.selectedChannelTitle = channel.title; //
            this.$refs.hiddenIdInput.value = channel.channel_id; //
            this.showSuggestions = false; this.activeIndex = -1; //
        },
        handleKeydown(event) {
            if (!this.showSuggestions || this.suggestions.length === 0) return; //
            if (event.key === 'ArrowDown') { event.preventDefault(); this.activeIndex = (this.activeIndex + 1) % this.suggestions.length; }
            else if (event.key === 'ArrowUp') { event.preventDefault(); this.activeIndex = (this.activeIndex - 1 + this.suggestions.length) % this.suggestions.length; }
            else if (event.key === 'Enter') { //
                event.preventDefault(); //
                if (this.activeIndex !== -1) {
                    this.selectSuggestion(this.suggestions[this.activeIndex]); //
                } else {
                    this.handleAddCompetitor(); //
                }
            }
        }, //
        confirmDelete(competitorId) { this.competitorToDelete = competitorId; this.showConfirmModal = true; },
        proceedWithDelete() {
            if (this.competitorToDelete) { //
                document.getElementById(`delete-form-${this.competitorToDelete}`).submit(); //
            }
            this.showConfirmModal = false; //
        },
        moveCompetitor(id, direction) {
            const index = this.competitors.findIndex(c => c.id === id); //
            if (index === -1) return; //
            const otherIndex = direction === 'up' ? index - 1 : index + 1; //
            if (otherIndex < 0 || otherIndex >= this.competitors.length) return; //
            [this.competitors[index], this.competitors[otherIndex]] = [this.competitors[otherIndex], this.competitors[index]]; // Swap in UI
            const csrfToken = document.querySelector('form[id="add-competitor-form"] input[name=csrf_token]').value; //
            fetch(`/competitors/move/${id}/${direction}`, { //
                method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken } //
            }).then(res => res.json()).then(data => { //
                if (!data.success) { //
                    [this.competitors[index], this.competitors[otherIndex]] = [this.competitors[otherIndex], this.competitors[index]]; // Revert UI swap on error
                    alert('Could not update position. Please refresh.'); //
                }
            });
        },
        goToDeepAnalysis(cardData, competitor) {
            sessionStorage.setItem('deepAnalysisPreload', JSON.stringify(cardData)); //
            window.location.href = `/deep-analysis/${competitor.channel_id_youtube}`; //
        },

        analyzeTranscript(video) {
            this.videoForAnalysis = video; //
            this.showAnalysisModal = true; //
            this.analysisLoading = true; //
            this.currentAnalysis = null; // Reset previous results
            this.analysisError = ''; // Reset previous error

            const csrfToken = document.querySelector('form[id="add-competitor-form"] input[name=csrf_token]').value; //
            fetch(`/api/competitor/analyze-transcript/${video.id}`, { //
                method: 'POST', //
                headers: { 'X-CSRFToken': csrfToken } //
            })
            .then(res => res.json()) //
            .then(data => {
                // *** FIX: Handle potential null data and ensure structure ***
                if (data.error) {
                    this.analysisError = data.error; //
                    this.currentAnalysis = null; // Ensure it's null on error
                } else {
                    // Ensure the expected structure exists, provide defaults if not
                    this.currentAnalysis = { //
                        summary: data.summary || 'Summary not available.',
                        keywords: data.keywords || [],
                        content_gaps: data.content_gaps || []
                    };
                    this.analysisError = ''; // Clear previous errors
                }
                // *** END FIX ***
            })
            .catch(() => {
                this.analysisError = 'An unexpected network error occurred.'; //
                this.currentAnalysis = null; // Ensure it's null on catch
            })
            .finally(() => {
                this.analysisLoading = false; //
            });
        },

        closeAnalysisModal() {
            this.showAnalysisModal = false; //
            this.videoForAnalysis = null; //
            this.currentAnalysis = null; //
            this.analysisError = ''; //
        }
    }
}

function competitorCard(competitor) {
    return {
        isLoading: true,
        isRefreshing: false,
        isRefreshed: false,
        error: null,
        data: null,
        activeSort: 'date',
        activeFilter: 'all',
        allVideos: [],
        retryTimeout: null,
        ideaGenerationStatus: {}, //

        init() {
            // Preload data if available in session storage
            const preloadData = sessionStorage.getItem('deepAnalysisPreload');
            if (preloadData) {
                try {
                    const parsedData = JSON.parse(preloadData);
                    // Basic check to see if it's likely the correct data
                    if (parsedData && parsedData.details && parsedData.details.id === competitor.channel_id_youtube) {
                        this.data = parsedData;
                        this.processVideoSets();
                        this.isLoading = false;
                        this.error = null;
                        sessionStorage.removeItem('deepAnalysisPreload'); // Clear after use
                        return; // Don't fetch if preloaded
                    } else {
                        sessionStorage.removeItem('deepAnalysisPreload'); // Clear invalid data
                    }
                } catch (e) {
                    sessionStorage.removeItem('deepAnalysisPreload'); // Clear corrupt data
                }
            }
            // Fetch if not preloaded
            setTimeout(() => this.fetchData(10), 500); // Fetch data after a short delay
        },

        fetchData(retriesLeft = 0) {
            if (this.retryTimeout) clearTimeout(this.retryTimeout); //
            this.isLoading = true; //
            fetch(`/api/competitor/${competitor.id}/data`) //
                .then(res => res.json()) //
                .then(apiData => {
                    if ((apiData.error || !apiData.details) && retriesLeft > 0) { //
                        // Retry if error or no details and retries remain
                        this.retryTimeout = setTimeout(() => this.fetchData(retriesLeft - 1), 5000); //
                    } else if (apiData.error) {
                        this.error = apiData.error; //
                        this.isLoading = false; //
                    } else {
                        // Success
                        this.data = apiData; //
                        this.processVideoSets(); //
                        this.isLoading = false; //
                        this.error = null; //
                    }
                })
                .catch(() => { //
                    // Catch network errors or JSON parsing errors
                    if (retriesLeft > 0) { //
                        this.retryTimeout = setTimeout(() => this.fetchData(retriesLeft - 1), 5000); //
                    } else {
                        this.error = 'Failed to load data after multiple attempts.'; //
                        this.isLoading = false; //
                    }
                });
        },

        refreshData() {
            this.isRefreshing = true; //
            this.isRefreshed = false; //
            const csrfToken = document.querySelector('form[id="add-competitor-form"] input[name=csrf_token]').value; //
            fetch(`/api/competitor/${competitor.id}/refresh`, { method: 'POST', headers: { 'X-CSRFToken': csrfToken } }) //
                .then(res => res.json())
                .then(apiData => { //
                    if (apiData.error) { this.error = apiData.error; }
                    else { this.data = apiData; this.processVideoSets(); this.isRefreshed = true; } //
                })
                .catch(() => this.error = 'Failed to refresh data.') //
                .finally(() => this.isRefreshing = false); //
        },

        processVideoSets() {
            const videosByDate = this.data.recent_videos_data.videos || []; //
            const videosByViews = this.data.most_viewed_videos_data.videos || []; //

            // Use a dictionary to merge and deduplicate videos
            const allVideosDict = {}; //
            [...videosByDate, ...videosByViews].forEach(v => { if (v && v.id) allVideosDict[v.id] = v; }); //
            this.allVideos = Object.values(allVideosDict).filter(Boolean); // Convert back to array
        },

        get displayedVideos() {
            let processed = [...this.allVideos]; //

            // Apply filter
            if (this.activeFilter === 'shorts') { //
                processed = processed.filter(v => v.is_short); //
            } else if (this.activeFilter === 'videos') { //
                processed = processed.filter(v => !v.is_short); //
            }

            // Apply sort
            if (this.activeSort === 'date') { //
                processed.sort((a, b) => new Date(b.upload_date) - new Date(a.upload_date)); //
            } else if (this.activeSort === 'viewCount') { //
                processed.sort((a, b) => b.view_count - a.view_count); //
            } else if (this.activeSort === 'most_comments') { //
                processed.sort((a, b) => b.comment_count - a.comment_count); //
            }

            // Return only the top 5 for the card display
            return processed.slice(0, 5); //
        },

        addIdeaToPlanner(video) {
            this.ideaGenerationStatus[video.id] = 'loading'; //

            const csrfToken = document.querySelector('form[id="add-competitor-form"] input[name=csrf_token]').value; //
            fetch('/api/competitor/add-idea-from-video', { //
                method: 'POST', //
                headers: {
                    'Content-Type': 'application/json', //
                    'X-CSRFToken': csrfToken //
                },
                body: JSON.stringify({ title: video.title }) //
            })
            .then(res => res.json()) //
            .then(data => { //
                if (data.success) { //
                    this.ideaGenerationStatus[video.id] = 'success'; //
                } else {
                    this.ideaGenerationStatus[video.id] = 'error'; //
                    alert(data.error || 'Failed to add idea.'); //
                }
            })
            .catch(() => { //
                this.ideaGenerationStatus[video.id] = 'error'; //
                alert('An unexpected error occurred.'); //
            });
        }
    }
}

document.addEventListener('alpine:init', () => {
    Alpine.data('competitorPage', competitorPage); //
    Alpine.data('competitorCard', competitorCard); //
});