// static/js/video_form.js

function videoForm() {
    return {
        // --- State Variables ---
        showCompetitorPrompt: false, actionToContinue: null, showTitleModal: false, showTagsModal: false, showTopicPrompt: false, showScheduleModal: false,
        isGenerating: false, generationMessage: "",
        showDescriptionModal: false, generatedDescription: "",
        titleField: "", descriptionField: "", tags: [],
        hasCompetitors: false,
        flatpickrInstance: null, scheduledTime: null, previousVisibility: "private", promptCallback: null, promptTopic: "", promptSuggestions: [],
        promptLoading: false, promptError: "", titleError: "",
        suggestedTitles: [], suggestedTags: {},
        selectedSuggestedTags: [], hasRemovedSuggestion: false,
        tagInput: "", visibility: "private", csrfToken: "",
        step: "date", selectedDate: null, selectedHour: "05", selectedMinute: "00", selectedPeriod: "PM",
        hours: ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"],
        minutes: ["00", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55"],
        period: ["AM", "PM"],
        isShort: false, // For edit page
        isVideoShort: false, // For upload page
        isDragging: false, fileName: "", fileSize: "",
        isDraggingThumbnail: false,
        newThumbnailUrl: null,
        isUploading: false,
        uploadProgress: 0,
        uploadMessage: '',
        uploadComplete: false,
        redirectUrl: '',

        init() {
            // Load initial data passed from the HTML template
            this.titleField = PAGE_DATA.initial.title || "";
            this.descriptionField = PAGE_DATA.initial.description || "";
            this.tags = PAGE_DATA.initial.tags || [];
            this.visibility = PAGE_DATA.initial.visibility || "private";
            this.scheduledTime = PAGE_DATA.initial.scheduledTime || null;
            this.isShort = PAGE_DATA.initial.isShort || false;
            this.isVideoShort = this.isShort; // Sync both variables

            this.csrfToken = PAGE_DATA.csrfToken;
            this.hasCompetitors = PAGE_DATA.hasCompetitors;

            if (this.scheduledTime) {
                const d = new Date(this.scheduledTime);
                let hour = d.getUTCHours();
                const minute = d.getUTCMinutes();
                this.selectedPeriod = hour >= 12 ? "PM" : "AM";
                hour = hour % 12;
                hour = hour ? hour : 12;
                this.selectedHour = String(hour).padStart(2, "0");
                this.selectedMinute = String(Math.round(minute / 5) * 5).padStart(2, "0");
            }

            // Watchers for local storage (only on upload page)
            if (PAGE_DATA.isUploadPage) {
                const savedTitle = localStorage.getItem("upload_title");
                const savedDesc = localStorage.getItem("upload_description");
                const savedTags = localStorage.getItem("upload_tags");
                if (savedTitle) this.titleField = savedTitle;
                if (savedDesc) this.descriptionField = savedDesc;
                if (savedTags) this.tags = JSON.parse(savedTags);

                this.$watch("titleField", value => { localStorage.setItem("upload_title", value); });
                this.$watch("descriptionField", value => { localStorage.setItem("upload_description", value); });
                this.$watch("tags", value => { localStorage.setItem("upload_tags", JSON.stringify(value)); });
            }

            this.$watch("visibility", (value) => { 
                if (value === "schedule") { 
                    this.previousVisibility = this.visibility === "schedule" ? "private" : this.visibility; 
                    this.showScheduleModal = true; 
                } else { 
                    this.scheduledTime = null; 
                } 
            });
            
            this.$watch("showScheduleModal", (value) => { 
                if (value && !this.flatpickrInstance) { 
                    this.flatpickrInstance = flatpickr(this.$refs.flatpickr_container, { 
                        inline: true, 
                        minDate: "today", 
                        defaultDate: this.scheduledTime || "today", 
                        onChange: (dates) => { 
                            if (dates.length > 0) { 
                                this.selectedDate = dates[0]; this.step = "time"; 
                            } 
                        } 
                    }); 
                } 
                if (!value) this.step = "date"; 
            });
        },

        // --- All other helper functions ---
        async executeWithUI(generationType, topic) { 
            const cacheKey = `ai_${generationType}_${topic.trim().toLowerCase()}`; 
            const cachedResult = localStorage.getItem(cacheKey); 
            if (cachedResult) { return JSON.parse(cachedResult); } 
            this.isGenerating = true; 
            this.generationMessage = `Generating ${generationType}...`; 
            let url, body; 
            if (generationType === "titles") { url = PAGE_DATA.urls.generateTitles; body = JSON.stringify({ topic: topic }); } 
            else if (generationType === "tags") { url = PAGE_DATA.urls.generateTags; body = JSON.stringify({ topic: topic }); } 
            else if (generationType === "description") { url = PAGE_DATA.urls.generateDescription; body = JSON.stringify({ topic: topic, title: this.titleField }); } 
            try { 
                const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": this.csrfToken }, body: body }); 
                const data = await response.json(); 
                if (!response.ok || data.error) { throw new Error(data.details || data.error || "An unknown error occurred."); } 
                localStorage.setItem(cacheKey, JSON.stringify(data)); return data; 
            } catch (error) { 
                alert(`Error: ${error.message}`); return null; 
            } finally { 
                this.isGenerating = false; 
            } 
        },
        async executeGenerateTitles(force = false) { this.getTopic(this.titleField, async (topic) => { if (!topic) return; if(force) { localStorage.removeItem(`ai_titles_${topic.trim().toLowerCase()}`); } const results = await this.executeWithUI("titles", topic); if (results && results.titles) { this.suggestedTitles = results.titles; this.showTitleModal = true; } }); },
        async executeGenerateDescription() { if (this.isTitleGeneric(this.titleField)) { this.titleError = "Please set a proper title before generating a description."; return; } this.titleError = ""; const results = await this.executeWithUI("description", this.titleField); if (results && results.description) { this.generatedDescription = results.description; this.showDescriptionModal = true; } },
        async executeGenerateTags(force = false) { this.getTopic(this.titleField, async (topic) => { if (!topic) return; if(force) { localStorage.removeItem(`ai_tags_${topic.trim().toLowerCase()}`); } const results = await this.executeWithUI("tags", topic); if (results && results.tags) { this.suggestedTags = results.tags || {}; this.selectedSuggestedTags = []; this.hasRemovedSuggestion = false; this.showTagsModal = true; } }); },
        useDescription() { this.descriptionField = this.generatedDescription; this.showDescriptionModal = false; },
        handleThumbnailSelect(event) { this.setThumbnailFile(event.target.files[0]); },
        handleThumbnailDrop(event) { this.isDraggingThumbnail = false; this.setThumbnailFile(event.dataTransfer.files[0]); },
        setThumbnailFile(file) { if (file && file.type.startsWith("image/")) { if (file.size > 2 * 1024 * 1024) { alert('Image file size should be less than 2MB.'); return; } const dataTransfer = new DataTransfer(); dataTransfer.items.add(file); this.$refs.thumbnailInput.files = dataTransfer.files; this.newThumbnailUrl = URL.createObjectURL(file); } else { alert("Please select a valid image file (PNG, JPG, etc.)."); } },
        clearThumbnail() { this.$refs.thumbnailInput.value = null; this.newThumbnailUrl = null; },
        handleFileSelect(event) { this.setFile(event.target.files[0]); },
        handleDrop(event) { this.isDragging = false; this.setFile(event.dataTransfer.files[0]); },
        setFile(file) { if (file && file.type.startsWith("video/")) { const dT = new DataTransfer(); dT.items.add(file); this.$refs.videoInput.files = dT.files; this.fileName = file.name; this.fileSize = (file.size / 1024 / 1024).toFixed(2) + " MB"; const vE = document.createElement("video"); vE.preload = "metadata"; vE.onloadedmetadata = () => { window.URL.revokeObjectURL(vE.src); this.isVideoShort = (vE.videoWidth / vE.videoHeight) <= 1; }; vE.src = URL.createObjectURL(file); } else { alert("Please select a valid video file."); } },
        clearFile() { this.$refs.videoInput.value = null; this.fileName = ""; this.fileSize = ""; this.isVideoShort = false; },
        confirmSchedule() { if (!this.selectedDate) { this.selectedDate = this.flatpickrInstance.selectedDates[0] || new Date(); } let hr = parseInt(this.selectedHour); if (this.selectedPeriod === "PM" && hr < 12) hr += 12; if (this.selectedPeriod === "AM" && hr === 12) hr = 0; this.selectedDate.setHours(hr, parseInt(this.selectedMinute), 0, 0); this.scheduledTime = this.selectedDate.toISOString().slice(0, 19); this.showScheduleModal = false; },
        cancelSchedule() { if (!this.scheduledTime) { this.visibility = this.previousVisibility; } this.showScheduleModal = false; },
        get formattedSelectedDate() { if (!this.selectedDate) return ""; return this.selectedDate.toLocaleString("en-US", { weekday: "long", month: "long", day: "numeric" }); },
        get formattedScheduledTime() { if (!this.scheduledTime) return ""; return new Date(this.scheduledTime.replace("T", " ")).toLocaleString("en-US", { month: "long", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true }); },
        startGeneration(type) { if (!this.hasCompetitors) { this.actionToContinue = type; this.showCompetitorPrompt = true; } else { if (type === "titles") this.executeGenerateTitles(); if (type === "tags") this.executeGenerateTags(); if (type === "description") this.executeGenerateDescription(); } },
        proceedWithoutCompetitors() { this.showCompetitorPrompt = false; if (this.actionToContinue) { if (this.actionToContinue === "titles") this.executeGenerateTitles(); if (this.actionToContinue === "tags") this.executeGenerateTags(); if (this.actionToContinue === "description") this.executeGenerateDescription(); } this.actionToContinue = null; },
        isTitleGeneric(title) { const lT = title.trim().toLowerCase(); if (lT === "") return true; return ["untitled", "test video", "my video", "new video", "video upload"].some(j => lT.includes(j)); },
        getTopic(currentTitle, callback) { if (this.isTitleGeneric(currentTitle)) { this.promptCallback = callback; this.showTopicPrompt = true; } else { callback(currentTitle); } },
        handleTopicSubmit() { if (this.promptTopic.trim() !== "") { this.promptCallback(this.promptTopic); this.showTopicPrompt = false; this.promptTopic = ""; } else { this.promptError = "Please enter a topic."; } },
        fetchPromptSuggestions() { if (this.promptTopic.length < 2) { this.promptSuggestions = []; return; } this.promptLoading = true; fetch(`${PAGE_DATA.urls.keywordSuggestions}?q=${this.promptTopic}`).then(r => r.json()).then(d => { this.promptSuggestions = d.suggestions || []; }).finally(() => this.promptLoading = false); },
        selectPromptSuggestion(suggestion) { this.promptTopic = suggestion.keyword; this.promptSuggestions = []; },
        appendTag(tag) { const currentLength = this.tags.join(', ').length; const newLength = currentLength + (currentLength > 0 ? 2 : 0) + tag.length; if (newLength > 500) { return false; } if (!this.tags.map(t => t.toLowerCase()).includes(tag.toLowerCase())) { this.tags.push(tag); } return true; },
        addTag() { const nT = this.tagInput.trim(); if (nT) { const wasAdded = this.appendTag(nT); if (wasAdded) { this.tagInput = ""; } else { alert("Character limit reached."); } } },
        removeTag(index) { this.tags.splice(index, 1); },
        selectTitle(title) { this.titleField = title; this.showTitleModal = false; },
        toggleSuggestedTag(tag) { const i = this.selectedSuggestedTags.indexOf(tag); if (i > -1) { this.selectedSuggestedTags.splice(i, 1); } else { this.selectedSuggestedTags.push(tag); } },
        addSelectedTags() { for (const tag of this.selectedSuggestedTags) { const wasAdded = this.appendTag(tag); if (!wasAdded) { alert("Character limit reached. Not all selected tags could be added."); break; } } this.showTagsModal = false; },
        addAllTags() { this.tags = []; if (typeof this.suggestedTags === 'object' && this.suggestedTags !== null) { const allGeneratedTags = [...(this.suggestedTags.main_keywords || []), ...(this.suggestedTags.secondary_keywords || []), ...(this.suggestedTags.broad_tags || [])]; for (const tag of allGeneratedTags) { const wasAdded = this.appendTag(tag); if (!wasAdded) { alert("Character limit reached. Not all tags could be added."); break; } } } this.showTagsModal = false; },
        removeSuggestedTag(index, tag, category) { const cT = this.suggestedTags[category]; if(cT) { const tI = cT.indexOf(tag); if (tI > -1) { cT.splice(tI, 1); } } const sI = this.selectedSuggestedTags.indexOf(tag); if (sI > -1) { this.selectedSuggestedTags.splice(sI, 1); } this.hasRemovedSuggestion = true; },
        copyTags(tags, buttonEl) { if (!Array.isArray(tags) || tags.length === 0) return; navigator.clipboard.writeText(tags.join(', ')).then(() => { const originalText = buttonEl.innerHTML; buttonEl.innerHTML = 'Copied!'; setTimeout(() => { buttonEl.innerHTML = 'Copy'; }, 2000); }); },
        clearSavedData() { localStorage.removeItem("upload_title"); localStorage.removeItem("upload_description"); localStorage.removeItem("upload_tags"); },
        submitUploadForm(event) {
            this.isUploading = true;
            this.uploadComplete = false;
            this.uploadMessage = 'Uploading your video...';
            this.uploadProgress = 0;
            const formData = new FormData(event.target);
            const xhr = new XMLHttpRequest();
            xhr.open('POST', PAGE_DATA.formActionUrl, true);
            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    this.uploadProgress = percentComplete;
                }
            };
            xhr.onload = () => {
                try {
                    const data = JSON.parse(xhr.responseText);
                    if (xhr.status >= 200 && xhr.status < 300 && data.success) {
                        this.uploadProgress = 100;
                        this.uploadMessage = data.message || 'Upload Complete!';
                        this.uploadComplete = true;
                        this.redirectUrl = data.redirect_url;
                        this.clearSavedData();
                    } else {
                        throw new Error(data.error || 'An unknown error occurred on the server.');
                    }
                } catch (e) {
                    this.isUploading = false;
                    alert('Error: ' + e.message);
                }
            };
            xhr.onerror = () => {
                this.isUploading = false;
                alert('A network error occurred. Please check your connection and try again.');
            };
            xhr.send(formData);
        },
        finishUpload() {
            if (this.redirectUrl) {
                window.location.href = this.redirectUrl;
            }
        }
    }
}