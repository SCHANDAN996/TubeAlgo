// static/js/planner.js

// Ensure SortableJS is loaded (e.g., via CDN in your base template)
// <script src="https://cdn.jsdelivr.net/npm/sortablejs@latest/Sortable.min.js"></script>

// Ensure MarkedJS is loaded (e.g., via CDN in your base template)
// <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>

document.addEventListener('alpine:init', () => {
    Alpine.data('contentPlanner', () => ({
        // Existing State
        plannerData: { idea: [], scripting: [], filming: [], editing: [], scheduled: [] },
        plannerColumns: [
            { id: 'idea', title: '💡 Ideas', icon: '🧠' },
            { id: 'scripting', title: '✍️ Scripting', icon: '📝' },
            { id: 'filming', title: '🎬 Filming', icon: '🎥' },
            { id: 'editing', title: '✂️ Editing', icon: '🎞️' },
            { id: 'scheduled', title: '🗓️ Scheduled', icon: '✅' }
        ],
        columnColors: {
            idea: 'border-blue-500',
            scripting: 'border-purple-500',
            filming: 'border-red-500',
            editing: 'border-yellow-500',
            scheduled: 'border-green-500'
        },
        ideaEntryMode: 'button', // 'button' or 'manual'
        newIdeaTitle: '',
        isGeneratorOpen: false,
        generatorStep: 'input', // 'input' or 'results'
        generatorTopic: '',
        generatorDescription: '',
        generatorVideoType: 'any',
        generatorLanguage: 'English',
        isGeneratorLoading: false,
        loadingStepMessage: '',
        generatedIdeas: [],
        currentIdeaIndex: 0,
        copyButtonText: 'Copy Outline',
        isEditModalOpen: false,
        editingIdea: {},
        editingStatus: '',
        editModalTab: 'write', // 'write' or 'preview'
        editModalCopyText: 'Copy Notes',
        showDeleteConfirmModal: false,
        ideaToDelete: null,

        // --- NEW Transcript Import State ---
        isTranscriptModalOpen: false,
        transcriptStep: 'input', // 'input' or 'results'
        transcriptUrl: '',
        isTranscriptLoading: false,
        transcriptError: '',
        transcriptTab: 'voiceover', // 'voiceover', 'script', 'original'
        transcriptCopyText: 'Copy',
        transcriptData: {
            original: '',
            voiceover: '',
            script: ''
        },
        // --- End NEW State ---

        // Initialization
        init() {
            // Load data first
            this.loadPlannerData(); // loadPlannerData will call initializeSortable after loading

            // Configure MarkedJS
            if (window.marked) {
                window.marked.setOptions({
                    breaks: true, // Add <br> on single line breaks
                    gfm: true     // Use GitHub Flavored Markdown
                });
            } else {
                console.warn("MarkedJS not found. Markdown preview will not work.");
            }
        },

        // --- Existing Methods ---
        async loadPlannerData() {
            try {
                const response = await fetch(PAGE_DATA.urls.getIdeas);
                const data = await response.json();
                // Ensure all columns exist, even if empty
                this.plannerColumns.forEach(col => {
                    // Make sure data is always an array
                    this.plannerData[col.id] = Array.isArray(data[col.id]) ? data[col.id] : [];
                });

                // Crucial: Initialize Sortable *after* data is loaded and Alpine has updated the DOM
                this.$nextTick(() => {
                    this.initializeSortable();
                });

            } catch (error) {
                console.error("Error loading planner data:", error);
                alert('Failed to load planner data. Please refresh the page.');
            }
        },

        // --- === CORRECTED initializeSortable METHOD === ---
        initializeSortable() {
            // Check if Sortable library is available
            if (typeof Sortable === 'undefined') {
                console.error("SortableJS library is not loaded. Drag and drop will not work.");
                return;
            }

            // Select all column elements using the data-status attribute within this component's root ($el)
            // $el refers to the root div of the Alpine component (<div x-data="contentPlanner()">)
            const columnElements = this.$el.querySelectorAll('[data-status]');

            if (!columnElements || columnElements.length === 0) {
                // This might happen briefly during initial load, wait a bit and retry once.
                // Or maybe the selector is wrong if the structure changed.
                console.warn("Planner columns ([data-status]) not found immediately. Will retry once.");
                setTimeout(() => this.initializeSortableRetry(), 100); // Retry after a short delay
                return;
            }

            // console.log(`Found ${columnElements.length} columns to initialize Sortable on.`);

            columnElements.forEach(columnEl => {
                // Double check the element exists and hasn't been removed
                if (!columnEl) {
                    console.warn("A column element was null during Sortable initialization loop.");
                    return; // Skip this iteration
                }

                // Destroy existing Sortable instance if it exists, before creating a new one
                // This prevents memory leaks if initializeSortable is called multiple times
                if (columnEl.sortableInstance) {
                    // console.log(`Destroying existing Sortable for: ${columnEl.dataset.status}`);
                    columnEl.sortableInstance.destroy();
                }

                // Create new Sortable instance and store it on the element
                // console.log(`Initializing Sortable for: ${columnEl.dataset.status}`);
                columnEl.sortableInstance = Sortable.create(columnEl, {
                    group: 'planner-ideas', // Items can be dragged between lists with the same group name
                    handle: '.drag-handle', // Specify drag handle element selector
                    animation: 150,        // ms, animation speed moving items when sorting, `0` — without animation
                    ghostClass: 'sortable-ghost',  // Class name for the drop placeholder
                    chosenClass: 'sortable-chosen', // Class name for the chosen item
                    dragClass: 'sortable-drag',    // Class name for the dragging item
                    onEnd: (evt) => {       // Element dragging ended
                        this.handleDrop(evt); // Call Alpine method to handle data update
                    }
                });
            });
        },

        // Added retry mechanism for initialization
        initializeSortableRetry() {
             console.log("Retrying Sortable initialization...");
             const columnElements = this.$el.querySelectorAll('[data-status]');
             if (!columnElements || columnElements.length === 0) {
                  console.error("Planner columns ([data-status]) still not found on retry. Drag and drop might fail.");
                  return;
             }
             // Call the main function again
             this.initializeSortable();
        },
        // --- === END CORRECTED METHODS === ---


        async handleDrop(evt) {
            const ideaId = evt.item.dataset.id;
            const fromStatus = evt.from.dataset.status;
            const toStatus = evt.to.dataset.status;
            const newIndex = evt.newIndex; // Index within the new list
             // const oldIndex = evt.oldIndex; // Index within the old list

            // --- Client-side Data Update ---
            // Find the idea object being moved
            if (!this.plannerData[fromStatus]) {
                 console.error(`Source column data for status "${fromStatus}" not found during handleDrop.`);
                 this.loadPlannerData(); return; // Recover
            }
            const movedIdeaIndex = this.plannerData[fromStatus].findIndex(idea => idea.id == ideaId);
            if (movedIdeaIndex === -1) {
                 console.error(`Moved idea ID ${ideaId} not found in local data for status "${fromStatus}".`);
                 this.loadPlannerData(); return; // Recover
            }

            // Remove from the old array
            const [movedIdea] = this.plannerData[fromStatus].splice(movedIdeaIndex, 1);

            // Add to the new array at the correct position
            if (!this.plannerData[toStatus]) {
                 this.plannerData[toStatus] = []; // Ensure target array exists
            }
            this.plannerData[toStatus].splice(newIndex, 0, movedIdea);
            // --- End Client-side Data Update ---


            // --- Server-side Data Update ---
            // Prepare data: Send the new order of IDs for *all* columns
            const updateData = {};
            this.plannerColumns.forEach(col => {
                updateData[col.id] = (this.plannerData[col.id] || []).map(idea => idea.id);
            });

            // Send update to server
            try {
                const response = await fetch(PAGE_DATA.urls.moveIdea, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
                    },
                    body: JSON.stringify(updateData)
                });
                const result = await response.json();
                if (!result.success) {
                    console.error("Failed to save move on server:", result.message);
                    alert(`Error saving changes: ${result.message || 'Please try again.'}`);
                    // Revert UI changes by reloading data from server
                    this.loadPlannerData();
                } else {
                    console.log("Card move saved successfully on server.");
                     // Optional: maybe update the movedIdea object's status locally if backend confirms
                     // movedIdea.status = toStatus; // Less critical as full order is saved
                }
            } catch (error) {
                console.error("Network error saving move:", error);
                 alert('A network error occurred while saving the changes.');
                // Revert UI changes by reloading data
                this.loadPlannerData();
            }
            // --- End Server-side Data Update ---
        },


        async addNewIdea(title = null, notes = null) {
            const ideaTitle = title || this.newIdeaTitle.trim();
            if (!ideaTitle) return;

            const newIdeaData = {
                title: ideaTitle,
                notes: notes, // Pass notes if provided (for transcript import)
                status: 'idea' // Always add to 'idea' column initially
            };

            try {
                const response = await fetch(PAGE_DATA.urls.createIdea, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
                    },
                    body: JSON.stringify(newIdeaData)
                });

                if (response.ok) {
                    const createdIdea = await response.json();
                    if (!this.plannerData['idea']) {
                         this.plannerData['idea'] = [];
                    }
                     // Add all necessary fields to the local object for UI consistency
                    this.plannerData['idea'].push({
                        id: createdIdea.id,
                        title: createdIdea.title,
                        display_title: createdIdea.display_title || createdIdea.title, // Use title as fallback
                        notes: createdIdea.notes || null, // Ensure notes exist or are null
                        status: createdIdea.status
                    });
                    this.newIdeaTitle = '';
                    this.ideaEntryMode = 'button';
                } else {
                    const errorData = await response.json();
                    console.error("Failed to add idea:", errorData.error);
                     alert(`Error adding idea: ${errorData.error}`); // Show error to user
                }
            } catch (error) {
                console.error("Error adding new idea:", error);
                 alert('A network error occurred while adding the idea.');
            }
        },

        editIdea(idea, status, initialTab = 'write') {
             // Create a deep copy to avoid modifying original data until save
            this.editingIdea = JSON.parse(JSON.stringify(idea));
             // Ensure display_title exists, use title as fallback
            if (!this.editingIdea.display_title) {
                 this.editingIdea.display_title = this.editingIdea.title;
            }
             // Ensure notes is not null/undefined for the textarea binding
            if (this.editingIdea.notes === null || typeof this.editingIdea.notes === 'undefined') {
                this.editingIdea.notes = '';
            }
            this.editingStatus = status; // Keep track of original status
            this.editModalTab = initialTab;
            this.isEditModalOpen = true;
            this.editModalCopyText = 'Copy Notes'; // Reset copy button text
        },


        async saveIdea() {
            if (!this.editingIdea || !this.editingIdea.id) return;

            // Ensure display_title is not empty, use title if it is
            const displayTitle = this.editingIdea.display_title?.trim() ? this.editingIdea.display_title.trim() : this.editingIdea.title;

            const updateData = {
                title: this.editingIdea.title,
                display_title: displayTitle,
                notes: this.editingIdea.notes
                // No transcript here anymore
            };

            const url = PAGE_DATA.urls.updateIdeaBase + this.editingIdea.id;

            try {
                const response = await fetch(url, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
                    },
                    body: JSON.stringify(updateData)
                });

                if (response.ok) {
                    const updatedIdea = await response.json();
                    const statusWhereIdeaIs = this.editingStatus; // Status where the idea currently resides in the UI

                     // Find and update the idea in the local plannerData
                    if (this.plannerData[statusWhereIdeaIs]) {
                         const index = this.plannerData[statusWhereIdeaIs].findIndex(i => i.id === updatedIdea.id);
                         if (index !== -1) {
                              // Update the existing idea object in the array
                              // Ensure all required fields are present in updatedIdea or merge safely
                              this.plannerData[statusWhereIdeaIs][index] = {
                                 ...this.plannerData[statusWhereIdeaIs][index], // Keep old fields like status if not returned
                                 title: updatedIdea.title,
                                 display_title: updatedIdea.display_title || updatedIdea.title, // Use fallback
                                 notes: updatedIdea.notes !== undefined ? updatedIdea.notes : null, // Handle notes potentially becoming null
                                 // Update status ONLY if the API returns it and it changed
                                 // status: updatedIdea.status ? updatedIdea.status : statusWhereIdeaIs
                             };
                             // IMPORTANT: Our current backend PUT /ideas/<id> doesn't handle status changes.
                             // Status changes are handled ONLY by POST /ideas/move via handleDrop.
                             // So, we do NOT need to handle moving the item here after save.
                         } else {
                              console.warn(`Idea with ID ${updatedIdea.id} not found in status "${statusWhereIdeaIs}" after update.`);
                              this.loadPlannerData(); // Fallback: reload all data
                         }
                    } else {
                         console.warn(`Status column "${statusWhereIdeaIs}" not found in plannerData.`);
                         this.loadPlannerData(); // Fallback: reload all data
                    }


                    this.isEditModalOpen = false;
                    this.editingIdea = {};
                } else {
                    const errorData = await response.json();
                    console.error("Failed to update idea:", errorData.error);
                     alert(`Error updating idea: ${errorData.error}`); // Show error
                }
            } catch (error) {
                console.error("Error updating idea:", error);
                 alert('A network error occurred while saving the idea.');
            }
        },

        copyEditScript() {
            let contentToCopy = this.editingIdea.notes || '';
            // No transcript copying here anymore

            navigator.clipboard.writeText(contentToCopy).then(() => {
                this.editModalCopyText = 'Copied!';
                setTimeout(() => { this.editModalCopyText = 'Copy Notes'; }, 2000);
            }).catch(err => {
                 console.error('Failed to copy notes: ', err);
                  alert('Could not copy notes. Please check browser permissions.');
                 this.editModalCopyText = 'Copy Failed';
                 setTimeout(() => { this.editModalCopyText = 'Copy Notes'; }, 2000);
            });
        },

        // Move card left/right using data manipulation and API call
        moveCard(idea, currentStatus, direction) {
            const currentIndex = this.plannerColumns.findIndex(col => col.id === currentStatus);
            let targetIndex = direction === 'next' ? currentIndex + 1 : currentIndex - 1;

            if (targetIndex >= 0 && targetIndex < this.plannerColumns.length) {
                const targetStatus = this.plannerColumns[targetIndex].id;

                 // --- Simulate drop event for handleDrop function ---
                // Find the actual DOM element representing the item
                const itemElement = this.$el.querySelector(`.group[data-id="${idea.id}"]`); // Target the main card div
                const fromElement = this.$el.querySelector(`[data-status="${currentStatus}"]`);
                const toElement = this.$el.querySelector(`[data-status="${targetStatus}"]`);


                if (!itemElement || !fromElement || !toElement) {
                    console.error("DOM elements not found for simulating move. Aborting.", {ideaId: idea.id, from: currentStatus, to: targetStatus});
                    alert("Could not move card due to an internal error. Please try dragging.");
                    // Don't reload here, as it might infinite loop if elements are consistently missing
                    return;
                }

                // Calculate the new index (append to the end of the target list)
                const newIndex = toElement.querySelectorAll('.group[data-id]').length;

                const fakeEvt = {
                    item: itemElement, // The DOM node being moved
                    from: fromElement, // The source list's DOM node
                    to: toElement,     // The target list's DOM node
                    newIndex: newIndex // Target index (append to end)
                };

                // Call handleDrop to manage data update and API call
                this.handleDrop(fakeEvt);
            }
        },


        deleteIdea(ideaId, status) {
            this.ideaToDelete = { id: ideaId, status: status };
            this.showDeleteConfirmModal = true;
        },

        async proceedWithDelete() {
            if (!this.ideaToDelete) return;

            const { id, status } = this.ideaToDelete;
            const url = PAGE_DATA.urls.deleteIdeaBase + id;

            try {
                const response = await fetch(url, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
                    }
                });

                if (response.ok) {
                    // Remove from local data
                    if (this.plannerData[status]) {
                        const index = this.plannerData[status].findIndex(idea => idea.id === id);
                        if (index !== -1) {
                            this.plannerData[status].splice(index, 1);
                        }
                    }
                } else {
                    const errorData = await response.json();
                    console.error("Failed to delete idea:", errorData.error);
                     alert(`Error deleting idea: ${errorData.error}`); // Show error
                }
            } catch (error) {
                console.error("Error deleting idea:", error);
                 alert('A network error occurred while deleting the idea.');
            } finally {
                this.showDeleteConfirmModal = false;
                this.ideaToDelete = null;
            }
        },

        // AI Generator Methods
        openGeneratorModal() {
            this.isGeneratorOpen = true;
            this.generatorStep = 'input';
            this.generatedIdeas = [];
            this.currentIdeaIndex = 0;
            this.generatorTopic = ''; // Reset fields
            this.generatorDescription = '';
            // Reset language and type to sensible defaults or keep last used? Resetting for now.
            this.generatorLanguage = 'English';
            this.generatorVideoType = 'any';
            // Clear potential validation error state
            this.$nextTick(() => { // Ensure element exists if modal was hidden
                 // Assuming x-ref="generatorTopicInput" on the topic input field in planner.html
                 this.$refs.generatorTopicInput?.classList.remove('border-red-500', 'focus:ring-red-500');
            });
        },


        async fetchGeneratedIdeas(regenerate = false, forceLanguage = null) {
            // Add reference to input field for validation highlighting
             // Assuming x-ref="generatorTopicInput" on the topic input field in planner.html
             const topicInput = this.$refs.generatorTopicInput;

             if (!this.generatorTopic.trim() && !regenerate) {
                topicInput?.classList.add('border-red-500', 'focus:ring-red-500'); // Add error style
                topicInput?.focus(); // Focus the field
                return;
            }
            topicInput?.classList.remove('border-red-500', 'focus:ring-red-500'); // Remove error style


            this.isGeneratorLoading = true;
            this.generatorStep = 'results'; // Switch to results view
            this.loadingStepMessage = 'Initializing AI...';

            const lang = forceLanguage || this.generatorLanguage;
            if (forceLanguage) {
                this.generatorLanguage = forceLanguage; // Update state if forced
            }

             let loadingInterval; // Define interval variable outside try block

            try {
                // Simulate steps with interval
                const steps = ['Analyzing topic...', 'Generating creative angles...', 'Writing script outlines...'];
                let stepIndex = 0;
                 // Clear previous interval if any
                if (loadingInterval) clearInterval(loadingInterval);

                loadingInterval = setInterval(() => {
                    if (!this.isGeneratorLoading) { // Stop if loading finished early
                         clearInterval(loadingInterval);
                         return;
                    }
                    if (stepIndex < steps.length) {
                        this.loadingStepMessage = steps[stepIndex];
                        stepIndex++;
                    } else {
                         this.loadingStepMessage = 'Finalizing results...'; // Or a final message
                    }
                }, 1500); // Adjust timing

                const response = await fetch(PAGE_DATA.urls.generateIdeas, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
                    },
                    body: JSON.stringify({
                        topic: this.generatorTopic,
                        description: this.generatorDescription,
                        language: lang,
                        video_type: this.generatorVideoType
                    })
                });

                 // Ensure interval is cleared even if response is immediate
                if(loadingInterval) clearInterval(loadingInterval);

                const result = await response.json();

                // Check if the response structure is as expected (contains 'ideas' array)
                 // Updated check for backend change: result itself might be the array or object with ideas
                 let ideasArray = [];
                 if (response.ok && result.ideas && Array.isArray(result.ideas)) {
                      ideasArray = result.ideas; // If structure is {success: true, ideas: [...]}
                 } else if (response.ok && Array.isArray(result)) {
                      ideasArray = result; // If backend directly returns [...]
                 }


                 if (ideasArray.length > 0) {
                     this.generatedIdeas = ideasArray.map(idea => ({
                        // Ensure required fields exist, provide defaults
                        title: idea.title || 'Untitled Idea',
                        outline: idea.outline || ''
                    }));
                    this.currentIdeaIndex = 0;
                    this.copyButtonText = 'Copy Outline';
                } else {
                     // Handle errors more gracefully
                    let errorMessage = 'Could not generate ideas. The AI might be unavailable or the response was invalid.';
                    if (response.status === 429) {
                        // Use error from JSON if available, otherwise generic
                        errorMessage = result?.error || 'You have exceeded the AI generation limit for today.';
                    } else if (result?.error) { // Check if result has an error property
                        errorMessage = result.error;
                    } else if (!response.ok) {
                         errorMessage = `Server error (${response.status}). Please try again later.`;
                    } else if (ideasArray.length === 0) {
                         errorMessage = 'The AI did not return any ideas for this topic.';
                    }
                    console.error("AI Generation failed:", errorMessage, result); // Log full result for debugging
                    this.generatedIdeas = [{ title: 'Generation Failed', outline: errorMessage }];
                    this.currentIdeaIndex = 0;
                }
            } catch (error) {
                 if(loadingInterval) clearInterval(loadingInterval); // Ensure interval cleared on network error
                console.error("Error fetching generated ideas:", error);
                 this.generatedIdeas = [{ title: 'Network Error', outline: 'Could not connect to the AI service. Please check your connection.' }];
                 this.currentIdeaIndex = 0;
            } finally {
                this.isGeneratorLoading = false;
                this.loadingStepMessage = '';
            }
        },


        previousIdea() {
            if (this.currentIdeaIndex > 0) {
                this.currentIdeaIndex--;
                this.copyButtonText = 'Copy Outline';
            }
        },

        nextIdea() {
            if (this.currentIdeaIndex < this.generatedIdeas.length - 1) {
                this.currentIdeaIndex++;
                this.copyButtonText = 'Copy Outline';
            }
        },

        copyScript() {
             if (this.generatedIdeas.length > 0 && this.currentIdeaIndex < this.generatedIdeas.length && this.generatedIdeas[this.currentIdeaIndex]) {
                const outline = this.generatedIdeas[this.currentIdeaIndex].outline || '';
                navigator.clipboard.writeText(outline).then(() => {
                    this.copyButtonText = 'Copied!';
                    setTimeout(() => { this.copyButtonText = 'Copy Outline'; }, 2000);
                }).catch(err => {
                     console.error('Failed to copy outline: ', err);
                      alert('Could not copy outline. Please check browser permissions.');
                     this.copyButtonText = 'Copy Failed';
                     setTimeout(() => { this.copyButtonText = 'Copy Outline'; }, 2000);
                });
            } else {
                 console.warn("No valid idea selected to copy outline.");
            }
        },


        saveIdeaToPlanner() {
             if (this.generatedIdeas.length > 0 && this.currentIdeaIndex < this.generatedIdeas.length && this.generatedIdeas[this.currentIdeaIndex]) {
                const idea = this.generatedIdeas[this.currentIdeaIndex];
                // Check if title or outline might indicate an error before saving
                 if (idea.title && !idea.title.includes('Failed') && !idea.title.includes('Error')) {
                     this.addNewIdea(idea.title, idea.outline); // Save title and outline
                     this.isGeneratorOpen = false; // Close modal after saving
                 } else {
                      // Optionally show a message that error ideas cannot be saved
                      alert("Cannot save an idea that resulted in an error or is incomplete.");
                 }
            } else {
                 console.warn("No valid idea selected to save.");
            }
        },


        // --- NEW Transcript Import Methods ---
        openTranscriptModal() {
            this.isTranscriptModalOpen = true;
            this.transcriptStep = 'input';
            this.transcriptUrl = '';
            this.transcriptError = '';
            this.transcriptData = { original: '', voiceover: '', script: '' };
             // Clear potential validation error state
             this.$nextTick(() => { // Ensure element exists if modal was hidden
                  // Assuming x-ref="transcriptUrlInput" on the URL input in planner.html
                  this.$refs.transcriptUrlInput?.classList.remove('border-red-500', 'focus:ring-red-500');
             });
        },


        closeTranscriptModal() {
            this.isTranscriptModalOpen = false;
        },

        async fetchTranscript() {
            // Assuming x-ref="transcriptUrlInput" on the URL input in planner.html
             const urlInput = this.$refs.transcriptUrlInput;

            if (!this.transcriptUrl.trim()) {
                this.transcriptError = 'Please enter a YouTube URL.';
                urlInput?.classList.add('border-red-500', 'focus:ring-red-500');
                urlInput?.focus();
                return;
            }
            // Enhanced URL validation to extract Video ID
            let videoId = null;
            let isValidUrl = false;
             try {
                  const url = new URL(this.transcriptUrl);
                  const hostname = url.hostname.toLowerCase();
                  const pathname = url.pathname;
                  const searchParams = url.searchParams;

                  if (hostname.includes('youtube.com')) {
                       if (pathname === '/watch' && searchParams.has('v')) {
                            videoId = searchParams.get('v');
                       } else if (pathname.startsWith('/shorts/')) {
                            videoId = pathname.split('/shorts/')[1]?.split('?')[0];
                       }
                  } else if (hostname.includes('youtu.be')) {
                       videoId = pathname.substring(1).split('?')[0]; // Remove leading '/'
                  }

                  // Basic check for typical YouTube ID length/format (alphanumeric, -, _)
                  if (videoId && /^[a-zA-Z0-9_-]{11}$/.test(videoId)) {
                       isValidUrl = true;
                  }

             } catch (_) {
                  // Handle cases where input is not a valid URL structure
                  // Check if it looks like just a video ID
                  const potentialId = this.transcriptUrl.trim();
                   if (/^[a-zA-Z0-9_-]{11}$/.test(potentialId)) {
                        videoId = potentialId;
                        isValidUrl = true;
                        // Reconstruct a valid URL for the backend if needed, or let backend handle ID directly
                         // this.transcriptUrl = `https://www.youtube.com/watch?v=${videoId}`; // Optional reconstruction
                   } else {
                       isValidUrl = false;
                   }
             }


            if (!isValidUrl) {
                 this.transcriptError = 'Please enter a valid YouTube video URL or Video ID.';
                 urlInput?.classList.add('border-red-500', 'focus:ring-red-500');
                 urlInput?.focus();
                 return;
            }
             urlInput?.classList.remove('border-red-500', 'focus:ring-red-500'); // Remove error style


            this.isTranscriptLoading = true;
            this.transcriptError = '';

            try {
                // Use the potentially reconstructed URL or the original input if backend handles IDs
                const urlToSend = this.transcriptUrl; // Send what the user entered

                const response = await fetch(PAGE_DATA.urls.importTranscript, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
                    },
                    body: JSON.stringify({ url: urlToSend })
                });

                const data = await response.json();

                if (!response.ok) {
                    let errorMsg = data.error || `Failed to process request (${response.status}).`;
                    if (response.status === 429) {
                         errorMsg = data.error || 'AI processing limit reached. Cannot generate AI versions.';
                         if(data.original){ // If original transcript was still fetched
                              this.transcriptData = {
                                   original: data.original,
                                   voiceover: `Error: ${errorMsg}`, script: `Error: ${errorMsg}`
                              };
                              this.transcriptStep = 'results'; this.transcriptTab = 'original';
                              this.transcriptCopyText = 'Copy'; this.transcriptError = errorMsg;
                              return; // Stop but show original
                         }
                    }
                     this.transcriptError = errorMsg;
                     // If we have an error and no original data, stay on input step
                     if (!data.original) {
                          this.transcriptStep = 'input';
                     }

                } else {
                    // Success case
                    this.transcriptData = {
                         original: data.original || 'Original transcript not available.',
                         voiceover: data.voiceover || 'AI Voiceover script generation failed or not available.',
                         script: data.script || 'AI Full script generation failed or not available.'
                    };
                    this.transcriptStep = 'results';
                    // Check if AI parts failed, default to original if both did
                     const voiceoverFailed = typeof this.transcriptData.voiceover !== 'string' || this.transcriptData.voiceover.startsWith("Error:") || this.transcriptData.voiceover.includes('failed or not available');
                     const scriptFailed = typeof this.transcriptData.script !== 'string' || this.transcriptData.script.startsWith("Error:") || this.transcriptData.script.includes('failed or not available');

                    if (voiceoverFailed && scriptFailed) {
                         this.transcriptTab = 'original';
                         this.transcriptError = 'Original transcript fetched, but AI processing failed.'; // Show warning
                    } else {
                         this.transcriptTab = 'voiceover'; // Default to AI voiceover
                    }
                    this.transcriptCopyText = 'Copy';
                }
            } catch (error) {
                this.transcriptError = 'A network error occurred. Please check your connection and try again.';
                console.error('Fetch transcript error:', error);
            } finally {
                this.isTranscriptLoading = false;
            }
        },

        copyTranscript() {
            let contentToCopy = '';
            let currentData = '';

            if (this.transcriptTab === 'original') {
                currentData = this.transcriptData.original;
            } else if (this.transcriptTab === 'voiceover') {
                currentData = this.transcriptData.voiceover;
            } else if (this.transcriptTab === 'script') {
                 currentData = this.transcriptData.script;
            }

            // Always copy the raw data, whether it's content or an error message
            contentToCopy = typeof currentData === 'string' ? currentData : '';

            // Check for placeholder/error messages that shouldn't be copied meaningfully
            const nonCopyableMessages = [
                 'Original transcript not available.',
                 'AI Voiceover script generation failed or not available.',
                 'AI Full script generation failed or not available.'
            ];
            // Also check for actual error strings
             const isError = contentToCopy.startsWith("Error:");

            if (!contentToCopy || nonCopyableMessages.includes(contentToCopy) || isError) {
                 console.warn("Nothing substantial to copy for tab:", this.transcriptTab);
                 this.transcriptCopyText = isError ? 'Cannot Copy Error' : 'Nothing to Copy';
                 setTimeout(() => { this.transcriptCopyText = 'Copy'; }, 2000);
                 return;
            }


            navigator.clipboard.writeText(contentToCopy.trim()).then(() => {
                this.transcriptCopyText = 'Copied!';
                setTimeout(() => { this.transcriptCopyText = 'Copy'; }, 2000);
            }).catch(err => {
                 console.error('Failed to copy text: ', err);
                 this.transcriptCopyText = 'Copy Failed';
                 alert('Could not copy text. Please check browser permissions.'); // Inform user
                 setTimeout(() => { this.transcriptCopyText = 'Copy'; }, 2000);
            });
        },

        addTranscriptToPlanner() {
            let title = 'New Idea from Transcript';
            let videoId = null;
             // Extract Video ID more reliably
             try {
                  // Use previous regex method for robustness if URL object fails
                   const matchId = this.transcriptUrl.match(/(?:v=|\/shorts\/|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
                   videoId = matchId ? matchId[1] : null;

                  if (videoId) {
                      title = `Idea from YT: ${videoId}`;
                  }
             } catch (e) { console.warn("Could not parse video ID from URL for title."); }


            let notes = '';
            let dataToAdd = '';
            let header = '';

            // Choose which version to add based on the active tab
            if (this.transcriptTab === 'original') {
                dataToAdd = this.transcriptData.original;
                header = '# Original Transcript';
            } else if (this.transcriptTab === 'voiceover') {
                dataToAdd = this.transcriptData.voiceover;
                 header = '# AI-Ready Voiceover';
            } else if (this.transcriptTab === 'script') {
                 dataToAdd = this.transcriptData.script;
                 header = '# AI Full Script';
            }

             // Check if the selected content indicates an error or is unavailable
             const isErrorOrUnavailable = typeof dataToAdd !== 'string' ||
                                          dataToAdd.startsWith("Error:") ||
                                          dataToAdd === 'Original transcript not available.' ||
                                          dataToAdd.includes('failed or not available');


            if (isErrorOrUnavailable && this.transcriptTab !== 'original') {
                 // Fallback: Add original + note about the error
                 const errorNote = typeof dataToAdd === 'string' ? `\n\nNote: ${dataToAdd}` : '\n\nNote: AI processed version was unavailable.';
                 const originalContent = this.transcriptData.original || '(Original transcript data not available)';
                 notes = `# Original Transcript (AI Failed/Unavailable)\n\n${originalContent}${errorNote}`;
                 // If original is also unavailable, just add a placeholder note
                 if (originalContent === '(Original transcript data not available)') {
                      notes = `# Imported Idea: ${title}\n\n(Transcript data could not be retrieved or processed.)`;
                 }
            } else if (dataToAdd && typeof dataToAdd === 'string' && dataToAdd !== 'Original transcript not available.') {
                 // Add the selected content if it's valid
                 notes = `${header}\n\n${dataToAdd}`;
            } else {
                 // Absolute fallback if everything is empty or unavailable
                  notes = `# Imported Idea: ${title}\n\n(Transcript data was empty or unavailable.)`;
            }


            this.addNewIdea(title, notes);
            this.closeTranscriptModal();
        }
        // --- End NEW Transcript Methods ---

    }));
});