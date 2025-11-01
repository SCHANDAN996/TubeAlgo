// static/js/ai_generator.js

function aiGeneratorPage() {
    return {
        // State variables
        isLoading: false,
        loadingMessage: '',
        step: 1, // 1: Topic, 2: Titles, 3: Content
        topic: PAGE_DATA.initialTopic || '',
        csrfToken: '',
        
        // Step 2 data
        generatedTitles: [],
        selectedTitle: null,
        
        // Step 3 data
        generatedContent: {
            description: '',
            outline: '',
            tags: {}
        },
        activeTab: 'description',

        init() {
            const csrfInput = document.querySelector('input[name="csrf_token"]');
            if (csrfInput) {
                this.csrfToken = csrfInput.value;
            }
        },

        async generateTitles() {
            if (!this.topic.trim()) {
                alert('Please enter a topic for your video.');
                return;
            }
            this.isLoading = true;
            this.loadingMessage = 'Generating Titles & Tags...';

            try {
                const response = await fetch(PAGE_DATA.urls.generateTitles, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
                    body: JSON.stringify({ topic: this.topic })
                });
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'Failed to generate titles.');
                }
                this.generatedTitles = data.titles || [];
                // Save tags for later use in step 3
                this.generatedContent.tags = data.tags || {};
                this.selectedTitle = null; // Reset selection
                this.step = 2;
            } catch (error) {
                alert('Error: ' + error.message);
            } finally {
                this.isLoading = false;
            }
        },

        async generateFinalContent() {
            if (!this.selectedTitle) {
                alert('Please select a title before proceeding.');
                return;
            }

            this.isLoading = true;
            this.loadingMessage = 'Generating final content...';
            this.activeTab = 'description'; // Reset to first tab

            try {
                // We already have the tags from the first call.
                // Now, let's fetch description and script outline in parallel.
                const descPromise = fetch(PAGE_DATA.urls.generateDescription, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
                    body: JSON.stringify({ topic: this.topic, title: this.selectedTitle })
                }).then(res => res.json());

                const scriptPromise = fetch(PAGE_DATA.urls.generateScript, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken },
                    body: JSON.stringify({ topic: this.topic, title: this.selectedTitle })
                }).then(res => res.json());
                
                const [descResult, scriptResult] = await Promise.all([descPromise, scriptPromise]);

                if (descResult.error || scriptResult.error) {
                    throw new Error(descResult.error || scriptResult.error || 'Failed to generate content.');
                }

                this.generatedContent.description = descResult.description || 'Could not generate description.';
                this.generatedContent.outline = scriptResult.outline || 'Could not generate script outline.';
                
                this.step = 3;

            } catch (error) {
                alert('Error: ' + error.message);
            } finally {
                this.isLoading = false;
            }
        },

        copyToClipboard(text, buttonEl) {
            if (!text) return;
            navigator.clipboard.writeText(text).then(() => {
                const originalText = buttonEl.textContent;
                buttonEl.textContent = 'Copied!';
                setTimeout(() => {
                    buttonEl.textContent = originalText;
                }, 2000);
            });
        },

        copyAllTags(buttonEl) {
            if (!this.generatedContent || !this.generatedContent.tags) return;
            const allTags = [
                ...(this.generatedContent.tags.main_keywords || []),
                ...(this.generatedContent.tags.secondary_keywords || []),
                ...(this.generatedContent.tags.broad_tags || [])
            ];
            this.copyToClipboard(allTags.join(', '), buttonEl);
        }
    }
}

document.addEventListener('alpine:init', () => {
    Alpine.data('aiGeneratorPage', aiGeneratorPage);
});